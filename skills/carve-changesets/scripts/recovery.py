#!/usr/bin/env python3
"""Recover an owned unmerged suffix onto an immutable successor source."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from common import (
    CommandError,
    checkout_restore,
    current_branch,
    delete_branch,
    ensure_clean_tree,
    ensure_git_repo,
    git,
    message_file,
    unique_temp_branch,
)
from github import (
    edit_pull_request,
    pull_request_by_number,
    pull_requests_for_source,
)
from metadata import (
    ChangesetMetadata,
    MetadataError,
    SourceIdentity,
    embed_pr_metadata,
    has_legacy_pr_metadata_comment,
    parse_commit_message,
    parse_pr_metadata,
    stamp_commit_message,
)
from propagate import (
    _durable_predecessor,
    _verify_merged_on_base,
    push_changeset_branch,
    remote_branch_head,
)
from publication import remote_identity_head, verify_remote_lineage
from rehydrate import (
    Chain,
    ChangesetRecord,
    PullRequestRecord,
    RehydrationError,
    adopt_legacy_chain,
)
from validate import validate_live_chain

RECOVERY_AUTHORITY_FLAG = "--ack-suffix-recovery"


@dataclass(frozen=True)
class RecoveryProjection:
    """Exact local successor projection derived from current live suffix state."""

    chain: Chain
    pull_requests: tuple[PullRequestRecord, ...]
    suffix: tuple[ChangesetRecord, ...]
    candidates: Mapping[str, str]
    metadata: Mapping[str, ChangesetMetadata]
    expected_bases: Mapping[int, str]
    target_lineage: tuple[SourceIdentity, ...]


def _resolve(ref: str) -> str | None:
    result = git("rev-parse", "--verify", ref, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def _resolve_identity(identity: SourceIdentity, *, remote: str) -> str:
    if identity.remote != remote:
        raise CommandError(
            f"Immutable source records remote {identity.remote!r}, not selected "
            f"remote {remote!r}."
        )
    local = _resolve(f"refs/heads/{identity.branch}")
    published = remote_identity_head(identity)
    if local and local != published:
        raise CommandError(
            f"Immutable source {identity.branch!r} is ambiguous: local head {local} "
            f"differs from {remote} head {published}."
        )
    if published != identity.sha:
        raise CommandError(
            f"Immutable source {identity.branch} moved from {identity.sha} to {published}; "
            "suffix recovery was withheld."
        )
    return published


def _is_ancestor(ancestor: str, descendant: str) -> bool:
    result = git("merge-base", "--is-ancestor", ancestor, descendant, check=False)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise CommandError(f"Git could not compare {ancestor} with {descendant}.")


def _ensure_pr_heads_available(
    pull_requests: list[PullRequestRecord], *, remote: str
) -> None:
    for pr in pull_requests:
        if _resolve(pr.head_sha) is None:
            fetched = git("fetch", remote, f"refs/pull/{pr.number}/head", check=False)
            if fetched.returncode != 0 or _resolve(pr.head_sha) is None:
                raise CommandError(
                    f"PR #{pr.number} head {pr.head_sha} is unavailable in live git."
                )
        try:
            metadata = parse_commit_message(
                git("show", "-s", "--format=%B", pr.head_sha).stdout,
                remote=remote,
            )
        except MetadataError as exc:
            raise CommandError(
                f"PR #{pr.number} head metadata is invalid: {exc}"
            ) from exc
        predecessor = metadata.recovery_from_head
        if predecessor is not None and _resolve(predecessor) is None:
            fetched = git("fetch", remote, predecessor, check=False)
            if fetched.returncode != 0 or _resolve(predecessor) is None:
                raise CommandError(
                    f"PR #{pr.number} exact recovery predecessor {predecessor} "
                    "is unavailable in live git."
                )


def _metadata_for_recovery(
    record: ChangesetRecord, target_lineage: tuple[SourceIdentity, ...]
) -> ChangesetMetadata:
    if record.metadata.source_lineage == target_lineage:
        return record.metadata
    if record.metadata.source_lineage != target_lineage[:-1]:
        raise CommandError(
            f"Changeset {record.position} does not carry the current lineage "
            "or the requested successor lineage."
        )
    return ChangesetMetadata(
        slug=record.metadata.slug,
        source_lineage=target_lineage,
        recovery_from_head=record.head,
    )


def _amend_metadata(metadata: ChangesetMetadata) -> str:
    message = git("show", "-s", "--format=%B", "HEAD").stdout
    author_date = git("show", "-s", "--format=%aI", "HEAD").stdout.strip()
    restamped = stamp_commit_message(message, metadata)
    with message_file(restamped) as path:
        git(
            "commit",
            "--amend",
            "-F",
            path,
            env={"GIT_COMMITTER_DATE": author_date},
        )
    return git("rev-parse", "HEAD").stdout.strip()


def _branch_checked_out_elsewhere(branch: str) -> bool:
    current_path: str | None = None
    for line in git("worktree", "list", "--porcelain").stdout.splitlines():
        if line.startswith("worktree "):
            current_path = line.removeprefix("worktree ")
        elif line == f"branch refs/heads/{branch}":
            if current_path != str(Path.cwd().resolve()):
                return True
    return False


def _sync_local_branch(
    record: ChangesetRecord, *, candidate: str, metadata: ChangesetMetadata
) -> None:
    checked_out_here = current_branch() == record.branch
    if _branch_checked_out_elsewhere(record.branch):
        raise CommandError(
            f"Owned suffix branch {record.branch} is checked out in a worktree; "
            "local synchronization was withheld."
        )
    ref = f"refs/heads/{record.branch}"
    local = _resolve(ref)
    if local == candidate:
        return
    allowed = {record.head}
    if metadata.recovery_from_head:
        allowed.add(metadata.recovery_from_head)
    if local is not None and local not in allowed:
        raise CommandError(
            f"Local suffix branch {record.branch} unexpectedly advanced to {local}; "
            "recovery will not overwrite it."
        )
    if checked_out_here:
        git("checkout", "--detach", local or record.head)
    if local is None:
        git("update-ref", ref, candidate, "0" * 40)
    else:
        git("update-ref", ref, candidate, local)
    if checked_out_here:
        git("checkout", record.branch)


def _verify_open_suffix_pr(
    record: ChangesetRecord,
    *,
    expected_head: str,
    expected_base: str,
    target_lineage: tuple[SourceIdentity, ...],
    remote: str,
) -> PullRequestRecord:
    if record.pr_number is None:
        raise CommandError(
            f"Changeset {record.position} has no canonical published PR."
        )
    live = pull_request_by_number(record.pr_number, remote=remote)
    if live.state.upper() != "OPEN":
        raise CommandError(f"Suffix PR #{live.number} is not OPEN.")
    if live.is_cross_repository:
        raise CommandError(f"Suffix PR #{live.number} uses an unowned fork branch.")
    if live.head_branch != record.branch:
        raise CommandError(
            f"Suffix PR #{live.number} head branch changed to {live.head_branch!r}."
        )
    if live.head_sha != expected_head:
        raise CommandError(
            f"Suffix PR #{live.number} head moved from {expected_head} to {live.head_sha}."
        )
    if live.base_branch != expected_base:
        raise CommandError(
            f"Suffix PR #{live.number} base changed from {expected_base!r} "
            f"to {live.base_branch!r}."
        )
    current_remote = remote_branch_head(remote, record.branch)
    if current_remote != expected_head:
        raise CommandError(
            f"Remote suffix branch {remote}/{record.branch} moved from "
            f"{expected_head} to {current_remote}."
        )
    metadata = record.metadata
    has_legacy_metadata = has_legacy_pr_metadata_comment(live.body)
    if record.metadata.version in {1, 2} and not has_legacy_metadata:
        raise CommandError(f"Suffix PR #{live.number} lacks required legacy metadata.")
    if has_legacy_metadata:
        try:
            metadata = parse_pr_metadata(live.body, remote=remote)
        except MetadataError as exc:
            raise CommandError(
                f"Suffix PR #{live.number} metadata is invalid: {exc}"
            ) from exc
        if record.pr_metadata is not None and metadata != record.pr_metadata:
            raise CommandError(
                f"Suffix PR #{live.number} metadata conflicts with live recovery evidence."
            )
    current_lineage = target_lineage[:-1]
    expected_position = record.metadata.legacy_position
    if (
        metadata.slug != record.metadata.slug
        or (
            expected_position is not None
            and metadata.legacy_position != expected_position
        )
        or metadata.root_source != record.metadata.root_source
        or metadata.source_lineage not in (current_lineage, target_lineage)
    ):
        raise CommandError(
            f"Suffix PR #{live.number} no longer has the owned stable changeset identity."
        )
    if (
        record.metadata.source_lineage == current_lineage
        and metadata != record.metadata
    ):
        raise CommandError(
            f"Suffix PR #{live.number} metadata conflicts before its head is recovered."
        )
    if (
        record.metadata.source_lineage == target_lineage
        and metadata.source_lineage == target_lineage
        and metadata != record.metadata
    ):
        raise CommandError(
            f"Suffix PR #{live.number} has conflicting recovered provenance."
        )
    return live


def project_suffix_recovery_from_live(
    *,
    source: str,
    base: str,
    from_index: int,
    successor_branch: str,
    successor_sha: str,
    remote: str,
) -> RecoveryProjection:
    """Build exact successor heads locally without changing remote state."""

    ensure_git_repo()
    ensure_clean_tree()
    git("fetch", "--prune", remote)
    successor = SourceIdentity(remote, successor_branch, successor_sha)
    pull_requests = pull_requests_for_source(source, remote=remote)
    _ensure_pr_heads_available(pull_requests, remote=remote)
    try:
        chain = adopt_legacy_chain(
            source_branch=source,
            base_branch=base,
            pull_requests=pull_requests,
            cwd=Path.cwd(),
            remote=remote,
            prefer_remote=True,
            recovery_successor=successor,
        )
    except RehydrationError as exc:
        raise CommandError(f"Live suffix recovery state is invalid: {exc}") from exc
    first_open = next(
        (
            offset
            for offset, record in enumerate(chain.changesets, start=1)
            if record.pr_state != "MERGED"
        ),
        None,
    )
    if first_open is None:
        raise CommandError("The changeset chain has no unmerged suffix to recover.")
    if from_index != first_open:
        raise CommandError(
            f"--from-index must select the first unmerged changeset {first_open}; "
            f"got {from_index}."
        )
    if successor.branch == source:
        raise CommandError(
            "A successor source must use a distinct branch; the original source "
            "must remain immutable."
        )
    for identity in chain.source_lineage:
        _resolve_identity(identity, remote=remote)

    prefix = chain.changesets[: first_open - 1]
    by_number = {pr.number: pr for pr in pull_requests}
    for record in prefix:
        if record.pr_state != "MERGED" or record.pr_number not in by_number:
            raise CommandError(
                f"Changeset {record.position} is not a verified merged prefix."
            )
        _verify_merged_on_base(
            by_number[record.pr_number], base=chain.base_branch, remote=remote
        )

    suffix = tuple(chain.changesets[first_open - 1 :])
    target_lineage = chain.source_lineage
    expected_bases = {
        record.position: (
            chain.base_branch
            if record.position == first_open
            else chain.changesets[record.position - 2].branch
        )
        for record in suffix
    }
    for record in suffix:
        _verify_open_suffix_pr(
            record,
            expected_head=record.head,
            expected_base=expected_bases[record.position],
            target_lineage=target_lineage,
            remote=remote,
        )

    candidates_by_index: dict[int, str] = {}
    metadata_by_index: dict[int, ChangesetMetadata] = {}
    temp_branches: list[str] = []
    with checkout_restore() as original:
        try:
            for record in suffix:
                metadata = _metadata_for_recovery(record, target_lineage)
                metadata_by_index[record.position] = metadata
                if record.metadata == metadata:
                    candidates_by_index[record.position] = record.head
                    continue
                temp = unique_temp_branch(f"carve-recover-{record.position}")
                temp_branches.append(temp)
                git("branch", temp, record.head)
                git("checkout", temp)
                if record.position == first_open:
                    base_head = _resolve(f"refs/remotes/{remote}/{chain.base_branch}")
                    if base_head is None or not _is_ancestor(base_head, record.head):
                        raise CommandError(
                            f"First suffix branch {record.branch} is not propagated "
                            f"onto current {remote}/{chain.base_branch}."
                        )
                else:
                    previous = chain.changesets[record.position - 2]
                    old_base = _durable_predecessor(
                        record,
                        previous,
                        missing_message=(
                            f"Changeset {record.position} does not contain the durable "
                            f"predecessor for changeset {previous.position}."
                        ),
                    )
                    git(
                        "rebase",
                        "--committer-date-is-author-date",
                        "--onto",
                        candidates_by_index[record.position - 1],
                        old_base,
                        temp,
                    )
                candidates_by_index[record.position] = _amend_metadata(metadata)

            successor_tree = _resolve(f"{successor.sha}^{{tree}}")
            tip = candidates_by_index[suffix[-1].position]
            tip_tree = _resolve(f"{tip}^{{tree}}")
            if successor_tree is None or tip_tree != successor_tree:
                raise CommandError(
                    "Recovered suffix does not recompose to the exact successor-source tree."
                )
        finally:
            if current_branch() != original:
                git("checkout", original)
            for temp in temp_branches:
                delete_branch(temp)

    return RecoveryProjection(
        chain=chain,
        pull_requests=tuple(pull_requests),
        suffix=suffix,
        candidates={
            record.branch: candidates_by_index[record.position] for record in suffix
        },
        metadata={
            record.branch: metadata_by_index[record.position] for record in suffix
        },
        expected_bases=expected_bases,
        target_lineage=target_lineage,
    )


def recover_suffix_from_live(
    *,
    source: str,
    base: str,
    from_index: int,
    successor_branch: str,
    successor_sha: str,
    remote: str,
    dry_run: bool,
    authority_acknowledged: bool,
    approved_pr_text: dict[int, tuple[str, str]] | None = None,
    approved_ref_transitions: Mapping[str, tuple[str, str]] | None = None,
    approved_lineage: Sequence[SourceIdentity] | None = None,
) -> None:
    """Restamp only the first unmerged suffix against an immutable successor."""

    if not dry_run and not authority_acknowledged:
        raise CommandError(
            f"Remote execution requires {RECOVERY_AUTHORITY_FLAG} in addition "
            "to --no-dry-run."
        )
    projection = project_suffix_recovery_from_live(
        source=source,
        base=base,
        from_index=from_index,
        successor_branch=successor_branch,
        successor_sha=successor_sha,
        remote=remote,
    )
    if approved_lineage is not None and tuple(approved_lineage) != (
        projection.target_lineage
    ):
        raise CommandError(
            "Computed recovery lineage differs from the approved manifest lineage."
        )
    suffix = projection.suffix
    if approved_ref_transitions is not None:
        selected = tuple(record.branch for record in suffix)
        if tuple(approved_ref_transitions) != selected:
            raise CommandError(
                "Approved manifest ref membership does not match the recovery "
                f"suffix: approved {tuple(approved_ref_transitions)!r}; "
                f"observed {selected!r}."
            )
        for record in suffix:
            approved_old, approved_new = approved_ref_transitions[record.branch]
            if record.head != approved_old:
                raise CommandError(
                    f"Changeset {record.branch} is {record.head}; approved manifest "
                    f"requires old head {approved_old}."
                )
            candidate = projection.candidates[record.branch]
            if candidate != approved_new:
                raise CommandError(
                    f"Computed recovery head for {record.branch} is {candidate}; "
                    f"approved manifest requires {approved_new}."
                )

    for record in suffix:
        candidate = projection.candidates[record.branch]
        metadata = projection.metadata[record.branch]
        approved_ref = (
            None
            if approved_ref_transitions is None
            else approved_ref_transitions[record.branch]
        )
        live = _verify_open_suffix_pr(
            record,
            expected_head=record.head,
            expected_base=projection.expected_bases[record.position],
            target_lineage=projection.target_lineage,
            remote=remote,
        )
        updated_body = embed_pr_metadata(live.body, metadata)
        if approved_pr_text is not None:
            approved = approved_pr_text.get(live.number)
            if approved is None:
                raise CommandError(
                    f"Approved manifest has no PR text for #{live.number}."
                )
            approved_title, approved_body = approved
            if approved_title != live.title or approved_body != updated_body:
                raise CommandError(
                    f"PR #{live.number} automatic text differs from the "
                    "approved manifest; recovery was withheld."
                )
            updated_body = approved_body
        if candidate != record.head:
            push_changeset_branch(
                record.branch,
                remote=remote,
                dry_run=dry_run,
                expected_remote_head=(
                    record.head if approved_ref is None else approved_ref[0]
                ),
                local_ref=candidate,
            )
            if not dry_run:
                verify_remote_lineage(projection.target_lineage, remote=remote)
        if updated_body != live.body:
            edit_pull_request(
                live.number,
                remote=remote,
                body=updated_body,
                dry_run=dry_run,
            )
        if not dry_run:
            verified = pull_request_by_number(live.number, remote=remote)
            verified_metadata = parse_commit_message(
                git("show", "-s", "--format=%B", candidate).stdout,
                remote=remote,
            )
            if (
                verified.head_sha != candidate
                or verified.body != updated_body
                or verified_metadata != metadata
            ):
                raise CommandError(
                    f"Recovered PR #{live.number} could not be verified at "
                    f"exact head {candidate} with its expected body."
                )
            _sync_local_branch(record, candidate=candidate, metadata=metadata)

    if dry_run:
        print(
            "[OK] Dry-run suffix recovery passed local successor equivalence; "
            "remote branches and PR metadata were not changed."
        )
        return

    git("fetch", "--prune", remote)
    live_prs = pull_requests_for_source(source, remote=remote)
    recovered = adopt_legacy_chain(
        source_branch=source,
        base_branch=base,
        pull_requests=live_prs,
        cwd=Path.cwd(),
        remote=remote,
        prefer_remote=True,
    )
    validation = validate_live_chain(recovered, cwd=Path.cwd(), remote=remote)
    if not validation.valid:
        detail = "; ".join(f"{item.code}: {item.message}" for item in validation.errors)
        raise CommandError(f"Recovered live chain validation failed: {detail}")
    print(
        "[EVIDENCE-INVALIDATED] Rebuild validation, review-fix-loop, CI, "
        "connector, feedback, and thread evidence for every recovered head."
    )
    print("[OK] Suffix recovery completed and matches the immutable successor source.")
