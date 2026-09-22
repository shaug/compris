#!/usr/bin/env python3
"""Recover an owned unmerged suffix onto an immutable successor source."""

from __future__ import annotations

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
    parse_commit_message,
    parse_pr_metadata,
    stamp_commit_message,
)
from propagate import (
    _verify_merged_on_base,
    push_changeset_branch,
    remote_branch_head,
)
from rehydrate import (
    ChangesetRecord,
    PullRequestRecord,
    RehydrationError,
    rehydrate_chain,
)
from validate import validate_live_chain

RECOVERY_AUTHORITY_FLAG = "--ack-suffix-recovery"


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
    published = _resolve(f"refs/remotes/{identity.remote}/{identity.branch}")
    if published is None:
        raise CommandError(
            f"Immutable source {identity.branch!r} is unavailable on {remote}; "
            "published suffix lineage must be reconstructible from remote refs."
        )
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
        if _resolve(pr.head_sha) is not None:
            continue
        fetched = git("fetch", remote, f"refs/pull/{pr.number}/head", check=False)
        if fetched.returncode != 0 or _resolve(pr.head_sha) is None:
            raise CommandError(
                f"PR #{pr.number} head {pr.head_sha} is unavailable in live git."
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
    if record.metadata.version == 3:
        return ChangesetMetadata(
            slug=record.metadata.slug,
            source_lineage=target_lineage,
            recovery_from_head=record.head,
        )
    successor = target_lineage[-1]
    return ChangesetMetadata(
        slug=record.metadata.slug,
        index=record.position,
        source_branch=successor.branch,
        source_sha=successor.sha,
        source_lineage=target_lineage,
        recovery_from_head=record.head,
    )


def _durable_predecessor(record: ChangesetRecord, previous: ChangesetRecord) -> str:
    if _is_ancestor(previous.head, record.head):
        return previous.head
    for commit in git("rev-list", record.head).stdout.splitlines():
        try:
            metadata = parse_commit_message(
                git("show", "-s", "--format=%B", commit).stdout,
                remote=previous.metadata.root_source.remote,
            )
        except MetadataError:
            continue
        same_legacy_position = (
            metadata.legacy_position == previous.metadata.legacy_position
            if metadata.legacy_position is not None
            or previous.metadata.legacy_position is not None
            else True
        )
        if (
            same_legacy_position
            and metadata.slug == previous.metadata.slug
            and metadata.root_source == previous.metadata.root_source
        ):
            return commit
    raise CommandError(
        f"Changeset {record.position} does not contain the durable predecessor "
        f"for changeset {previous.position}."
    )


def _amend_metadata(metadata: ChangesetMetadata) -> str:
    message = git("show", "-s", "--format=%B", "HEAD").stdout
    restamped = stamp_commit_message(message, metadata)
    with message_file(restamped) as path:
        git("commit", "--amend", "-F", path)
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
    if record.metadata.version in {1, 2}:
        try:
            metadata = parse_pr_metadata(live.body, remote=remote)
        except MetadataError as exc:
            raise CommandError(
                f"Suffix PR #{live.number} metadata is invalid: {exc}"
            ) from exc
    current_lineage = target_lineage[:-1]
    if (
        metadata.slug != record.metadata.slug
        or metadata.legacy_position != record.metadata.legacy_position
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
) -> None:
    """Restamp only the first unmerged suffix against an immutable successor."""

    ensure_git_repo()
    ensure_clean_tree()
    if not dry_run and not authority_acknowledged:
        raise CommandError(
            f"Remote execution requires {RECOVERY_AUTHORITY_FLAG} in addition "
            "to --no-dry-run."
        )
    git("fetch", "--prune", remote)
    successor = SourceIdentity(remote, successor_branch, successor_sha)
    pull_requests = pull_requests_for_source(source, remote=remote)
    _ensure_pr_heads_available(pull_requests, remote=remote)
    try:
        chain = rehydrate_chain(
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

    suffix = list(chain.changesets[first_open - 1 :])
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

    candidates: dict[int, str] = {}
    metadata_by_index: dict[int, ChangesetMetadata] = {}
    temp_branches: list[str] = []
    temp_by_index: dict[int, str] = {}
    with checkout_restore() as original:
        try:
            for record in suffix:
                metadata = _metadata_for_recovery(record, target_lineage)
                metadata_by_index[record.position] = metadata
                if record.metadata == metadata:
                    candidates[record.position] = record.head
                    continue
                temp = unique_temp_branch(f"carve-recover-{record.position}")
                temp_branches.append(temp)
                temp_by_index[record.position] = temp
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
                    old_base = _durable_predecessor(record, previous)
                    git(
                        "rebase",
                        "--onto",
                        candidates[record.position - 1],
                        old_base,
                        temp,
                    )
                candidates[record.position] = _amend_metadata(metadata)

            successor_tree = _resolve(f"{successor.sha}^{{tree}}")
            tip = candidates[suffix[-1].position]
            tip_tree = _resolve(f"{tip}^{{tree}}")
            if successor_tree is None or tip_tree != successor_tree:
                raise CommandError(
                    "Recovered suffix does not recompose to the exact successor-source tree."
                )

            for record in suffix:
                index = record.position
                candidate = candidates[index]
                metadata = metadata_by_index[index]
                live = _verify_open_suffix_pr(
                    record,
                    expected_head=record.head,
                    expected_base=expected_bases[index],
                    target_lineage=target_lineage,
                    remote=remote,
                )
                if candidate != record.head:
                    push_changeset_branch(
                        record.branch,
                        remote=remote,
                        dry_run=dry_run,
                        expected_remote_head=record.head,
                        local_ref=temp_by_index[index],
                    )
                updated_body = embed_pr_metadata(live.body, metadata)
                if (
                    metadata.version in {1, 2}
                    and parse_pr_metadata(live.body, remote=remote) != metadata
                ):
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
                    if verified.head_sha != candidate or verified_metadata != metadata:
                        raise CommandError(
                            f"Recovered PR #{live.number} could not be verified at "
                            f"exact head {candidate}."
                        )
                    _sync_local_branch(record, candidate=candidate, metadata=metadata)
        finally:
            if current_branch() != original:
                git("checkout", original)
            for temp in temp_branches:
                delete_branch(temp)

    if dry_run:
        print(
            "[OK] Dry-run suffix recovery passed local successor equivalence; "
            "remote branches and PR metadata were not changed."
        )
        return

    git("fetch", "--prune", remote)
    live_prs = pull_requests_for_source(source, remote=remote)
    recovered = rehydrate_chain(
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
