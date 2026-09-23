#!/usr/bin/env python3
"""Stateless merge, downstream propagation, and remote push safety."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from common import (
    CommandError,
    branch_exists,
    branch_name_for,
    current_branch,
    ensure_clean_tree,
    ensure_git_repo,
    git,
)
from github import (
    edit_pull_request,
    merge_pull_request,
    pull_request_by_number,
    pull_requests_for_source,
)
from metadata import (
    ChangesetMetadata,
    MetadataError,
    parse_commit_message,
    parse_pr_metadata,
)
from publication import verify_lineage_for_publication
from rehydrate import Chain, ChangesetRecord, PullRequestRecord, adopt_legacy_chain
from validate import validate_live_chain

AUTHORITY_FLAG = "--ack-merge-and-propagate"
_TITLE_COUNT_RE = re.compile(r"\s+\([1-9][0-9]* of [1-9][0-9]*\)$")


def _ensure_chain_exists(source: str, total: int) -> List[str]:
    chain = [branch_name_for(source, index) for index in range(1, total + 1)]
    missing = [branch for branch in chain if not branch_exists(branch)]
    if missing:
        raise CommandError("Missing changeset branches:\n" + "\n".join(missing))
    return chain


def remote_exists(remote: str) -> bool:
    return git("remote", "get-url", remote, check=False).returncode == 0


def remote_branch_head(remote: str, branch: str) -> str | None:
    result = git(
        "ls-remote",
        "--heads",
        remote,
        f"refs/heads/{branch}",
        check=False,
    )
    if result.returncode != 0:
        raise CommandError(f"Unable to resolve {remote}/{branch} before push.")
    line = result.stdout.strip()
    return line.split()[0] if line else None


def push_changeset_branch(
    branch: str,
    *,
    remote: str,
    dry_run: bool,
    expected_remote_head: str | None = None,
    local_ref: str | None = None,
) -> None:
    current = remote_branch_head(remote, branch)
    if expected_remote_head is not None and current != expected_remote_head:
        raise CommandError(
            f"Remote branch {remote}/{branch} moved from verified head "
            f"{expected_remote_head} to {current}; propagation was withheld."
        )
    expected = expected_remote_head if expected_remote_head is not None else current
    lease = f"--force-with-lease=refs/heads/{branch}:{expected or ''}"
    source_ref = local_ref or branch
    refspec = f"refs/heads/{source_ref}:refs/heads/{branch}"
    command = ("git", "push", remote, refspec, lease)
    print(f"[STEP] Pushing changeset branch {branch} to {remote} with an exact lease")
    if dry_run:
        print("[DRY-RUN] Would run:")
        print(" ".join(command))
        return
    git("push", remote, refspec, lease)


def push_chain(plan: Dict, *, remote: str, dry_run: bool) -> None:
    """Push changeset branches only; never force-push the base or source."""

    ensure_git_repo()
    ensure_clean_tree()
    if not remote_exists(remote):
        raise CommandError(f"Remote does not exist: {remote}")

    base = plan["base_branch"]
    source = plan["source_branch"]
    chain = _ensure_chain_exists(source, len(plan["changesets"]))
    if not dry_run:
        verify_lineage_for_publication(chain, remote=remote)
    print(
        f"[INFO] Base branch {base} is intentionally excluded. Push or update it "
        "separately with a verified fast-forward-only workflow."
    )
    print(f"[INFO] Source branch {source} is immutable and will not be pushed.")
    for branch in chain:
        push_changeset_branch(branch, remote=remote, dry_run=dry_run)

    if dry_run:
        print("[OK] Dry-run push-chain complete. Re-run with --no-dry-run to execute.")
    else:
        print("[OK] push-chain completed.")


def _fetch_remote(remote: str) -> None:
    if not remote_exists(remote):
        raise CommandError(f"Remote does not exist: {remote}")
    git("fetch", "--prune", remote)


def _remote_ref(remote: str, branch: str) -> str:
    return f"refs/remotes/{remote}/{branch}"


def _resolve(ref: str) -> str:
    result = git("rev-parse", "--verify", f"{ref}^{{commit}}", check=False)
    if result.returncode != 0:
        raise CommandError(f"Git commit is unavailable: {ref}")
    return result.stdout.strip()


def _is_ancestor(ancestor: str, descendant: str) -> bool:
    result = git("merge-base", "--is-ancestor", ancestor, descendant, check=False)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise CommandError(
        f"Git could not compare mainline commit {descendant} with merged commit {ancestor}."
    )


def _rehydrate_live(
    *, source: str, base: str | None, remote: str
) -> tuple[Chain, dict[int, PullRequestRecord]]:
    _fetch_remote(remote)
    pull_requests = pull_requests_for_source(source, remote=remote)
    for pr in pull_requests:
        if pr.state.upper() != "MERGED":
            continue
        available = git("cat-file", "-e", f"{pr.head_sha}^{{commit}}", check=False)
        if available.returncode == 0:
            continue
        fetched = git("fetch", remote, f"refs/pull/{pr.number}/head", check=False)
        available = git("cat-file", "-e", f"{pr.head_sha}^{{commit}}", check=False)
        if fetched.returncode != 0 or available.returncode != 0:
            raise CommandError(
                f"Merged PR #{pr.number} head {pr.head_sha} is unavailable; "
                "fetch its exact GitHub PR head before retrying."
            )
    chain = adopt_legacy_chain(
        source_branch=source,
        base_branch=base,
        pull_requests=pull_requests,
        cwd=Path.cwd(),
        remote=remote,
        prefer_remote=True,
    )
    validation = validate_live_chain(
        chain,
        cwd=Path.cwd(),
        remote=remote,
        allow_partial_propagation=True,
    )
    if not validation.valid:
        detail = "; ".join(
            f"{diagnostic.code}: {diagnostic.message}"
            for diagnostic in validation.errors
        )
        raise CommandError(f"Live changeset chain is invalid: {detail}")
    by_number = {pr.number: pr for pr in pull_requests}
    return chain, by_number


def _target(
    chain: Chain,
    pull_requests: dict[int, PullRequestRecord],
    *,
    pr_number: int | None,
    index: int | None,
) -> tuple[ChangesetRecord, PullRequestRecord]:
    if (pr_number is None) == (index is None):
        raise CommandError("Pass exactly one of --pr or --index.")
    record: ChangesetRecord | None = None
    if index is not None:
        if index < 1 or index > len(chain.changesets):
            raise CommandError(
                f"--index must be between 1 and {len(chain.changesets)}."
            )
        record = chain.changesets[index - 1]
    else:
        record = next(
            (item for item in chain.changesets if item.pr_number == pr_number), None
        )
        if record is None:
            raise CommandError(
                f"PR #{pr_number} does not belong to this changeset chain."
            )
    if record.pr_number is None or record.pr_number not in pull_requests:
        raise CommandError(
            f"Changeset {record.position} has no verified GitHub pull request."
        )
    return record, pull_requests[record.pr_number]


def _require_sequential_target(chain: Chain, target_index: int) -> None:
    for item in chain.changesets[: target_index - 1]:
        if item.pr_state != "MERGED":
            raise CommandError(
                f"Changeset {target_index} cannot proceed before PR for changeset "
                f"{item.position} is verified merged."
            )
    for item in chain.changesets[target_index:]:
        if item.pr_state == "MERGED":
            raise CommandError(f"Changeset {item.position} is merged out of sequence.")
        if item.pr_state != "OPEN":
            raise CommandError(
                f"Downstream PR #{item.pr_number} must be OPEN, got {item.pr_state or 'missing'}."
            )


def _require_authority(*, dry_run: bool, authority_acknowledged: bool) -> None:
    if not dry_run and not authority_acknowledged:
        raise CommandError(
            f"Remote execution requires {AUTHORITY_FLAG} in addition to --no-dry-run."
        )


def _verify_merged_on_base(
    pr: PullRequestRecord, *, base: str, remote: str
) -> PullRequestRecord:
    live = pull_request_by_number(pr.number, remote=remote)
    if live.state.upper() != "MERGED":
        raise CommandError(
            f"PR #{pr.number} is {live.state or 'UNKNOWN'}, not verified MERGED; "
            "downstream propagation was withheld."
        )
    if live.head_branch != pr.head_branch:
        raise CommandError(
            f"PR #{pr.number} head branch changed from {pr.head_branch!r} "
            f"to {live.head_branch!r}."
        )
    if live.head_sha != pr.head_sha:
        raise CommandError(
            f"PR #{pr.number} head moved from verified commit {pr.head_sha} "
            f"to {live.head_sha}."
        )
    if not live.merge_sha:
        raise CommandError(
            f"PR #{pr.number} is merged but GitHub did not report a merge commit."
        )
    _fetch_remote(remote)
    base_head = _resolve(_remote_ref(remote, base))
    merge_head = _resolve(live.merge_sha)
    if not _is_ancestor(merge_head, base_head):
        raise CommandError(
            f"PR #{pr.number} reports merge commit {merge_head}, but {remote}/{base} "
            f"at {base_head} does not contain it."
        )
    return live


def _ensure_local_branch(record: ChangesetRecord) -> None:
    local = git(
        "rev-parse",
        "--verify",
        f"refs/heads/{record.branch}^{{commit}}",
        check=False,
    )
    if local.returncode == 0:
        if local.stdout.strip() != record.head:
            raise CommandError(
                f"Local branch {record.branch} moved from verified head {record.head} "
                f"to {local.stdout.strip()}."
            )
        return
    git("branch", record.branch, record.head)


def _rewrite_rebase(
    record: ChangesetRecord, *, old_base: str, new_base: str, dry_run: bool
) -> str:
    print(f"[STEP] Rebasing {record.branch} onto {new_base}")
    if dry_run:
        print(
            f"[DRY-RUN] Would run: git rebase --onto {new_base} {old_base} {record.branch}"
        )
        return record.head
    _ensure_local_branch(record)
    git("rebase", "--onto", new_base, old_base, record.branch)
    return _resolve(f"refs/heads/{record.branch}")


def _rewrite_cherry_pick(
    record: ChangesetRecord, *, old_base: str, new_base: str, dry_run: bool
) -> str:
    commits = [
        value
        for value in git(
            "rev-list", "--reverse", f"{old_base}..{record.head}"
        ).stdout.splitlines()
        if value
    ]
    if not commits:
        raise CommandError(
            f"Changeset branch {record.branch} has no commits beyond its verified predecessor."
        )
    print(
        f"[STEP] Cherry-picking {len(commits)} commit(s) for {record.branch} onto {new_base}"
    )
    if dry_run:
        print(f"[DRY-RUN] Would detach at {new_base} and cherry-pick exact commits.")
        return record.head
    _ensure_local_branch(record)
    git("checkout", "--detach", new_base)
    for commit in commits:
        git("cherry-pick", commit)
    rewritten = _resolve("HEAD")
    git("update-ref", f"refs/heads/{record.branch}", rewritten, record.head)
    git("checkout", record.branch)
    return rewritten


def _updated_title(pr: PullRequestRecord, *, index: int, total: int) -> str:
    current = pr.title.strip()
    if not current:
        raise CommandError(f"PR #{pr.number} has no title to update.")
    prefix = _TITLE_COUNT_RE.sub("", current)
    return f"{prefix} ({index} of {total})"


def _matches_historical_predecessor(
    metadata: ChangesetMetadata, previous: ChangesetRecord
) -> bool:
    """Match legacy history to the live topology position during migration."""

    if (
        metadata.slug != previous.metadata.slug
        or metadata.root_source != previous.metadata.root_source
    ):
        return False
    if metadata.legacy_position is not None:
        return metadata.legacy_position == previous.position
    return metadata.same_changeset_as(previous.metadata)


def _durable_predecessor(
    record: ChangesetRecord,
    previous: ChangesetRecord,
    *,
    missing_message: str | None = None,
) -> str:
    """Find the prior changeset commit in an unpropagated branch's ancestry."""

    if _is_ancestor(previous.head, record.head):
        return previous.head
    for commit in git("rev-list", record.head).stdout.splitlines():
        message = git("show", "-s", "--format=%B", commit).stdout
        try:
            metadata = parse_commit_message(
                message, remote=previous.metadata.root_source.remote
            )
        except MetadataError:
            continue
        if _matches_historical_predecessor(metadata, previous):
            return commit
    raise CommandError(
        missing_message
        or (
            f"Changeset branch {record.branch} does not contain durable predecessor "
            f"metadata for changeset {previous.position}."
        )
    )


def _verify_live_downstream(
    record: ChangesetRecord,
    *,
    expected_remote_head: str,
    allowed_bases: set[str],
    remote: str,
    role: str = "Downstream",
) -> PullRequestRecord:
    """Reauthorize one exact open downstream PR immediately before mutation."""

    if record.pr_number is None:
        raise CommandError(
            f"Downstream changeset {record.position} has no verified PR."
        )
    live = pull_request_by_number(record.pr_number, remote=remote)
    if live.state.upper() != "OPEN":
        raise CommandError(
            f"{role} PR #{live.number} changed to {live.state or 'UNKNOWN'}; "
            "remote mutation was withheld."
        )
    if live.is_cross_repository:
        raise CommandError(
            f"{role} PR #{live.number} changed to a fork head; remote mutation "
            "was withheld."
        )
    if live.head_branch != record.branch:
        raise CommandError(
            f"{role} PR #{live.number} head branch changed from {record.branch!r} "
            f"to {live.head_branch!r}; remote mutation was withheld."
        )
    if live.head_sha != expected_remote_head:
        raise CommandError(
            f"{role} PR #{live.number} head moved from {expected_remote_head} "
            f"to {live.head_sha}; remote mutation was withheld."
        )
    if live.base_branch not in allowed_bases:
        hint = (
            " Resume propagation for the preceding merged changeset first."
            if role == "Merge target"
            else ""
        )
        raise CommandError(
            f"{role} PR #{live.number} base changed from {record.base!r} to "
            f"{live.base_branch!r}; expected one of "
            f"{', '.join(repr(item) for item in sorted(allowed_bases))}. "
            f"Remote mutation was withheld.{hint}"
        )
    if record.metadata.version in {1, 2}:
        try:
            live_metadata = parse_pr_metadata(live.body, remote=remote)
        except MetadataError as exc:
            raise CommandError(
                f"{role} PR #{live.number} metadata is invalid: {exc}"
            ) from exc
        if live_metadata != record.metadata:
            raise CommandError(
                f"{role} PR #{live.number} no longer belongs to changeset "
                f"{record.position}; remote mutation was withheld."
            )
    remote_head = remote_branch_head(remote, record.branch)
    if remote_head != expected_remote_head:
        raise CommandError(
            f"Remote branch {remote}/{record.branch} moved from verified head "
            f"{expected_remote_head} to {remote_head}; remote mutation was withheld."
        )
    return live


def _require_merge_target_ancestry(
    record: ChangesetRecord, *, base: str, remote: str
) -> None:
    predecessor = _resolve(_remote_ref(remote, base))
    if not _is_ancestor(predecessor, record.head):
        raise CommandError(
            f"PR #{record.pr_number} cannot merge: changeset branch {record.branch} "
            f"does not descend from its live base {base}."
        )


def _verify_published_downstream(
    pr: PullRequestRecord,
    *,
    expected_head: str,
    expected_base: str,
    expected_title: str,
    remote: str,
) -> None:
    remote_head = remote_branch_head(remote, pr.head_branch)
    if remote_head != expected_head:
        raise CommandError(
            f"Remote branch {remote}/{pr.head_branch} is {remote_head}; "
            f"expected propagated head {expected_head}."
        )
    live = pull_request_by_number(pr.number, remote=remote)
    if live.state.upper() != "OPEN":
        raise CommandError(
            f"Downstream PR #{pr.number} is {live.state or 'UNKNOWN'}, not OPEN."
        )
    if live.head_sha != expected_head:
        raise CommandError(
            f"PR #{pr.number} head is {live.head_sha}; expected {expected_head}."
        )
    if live.base_branch != expected_base:
        raise CommandError(
            f"PR #{pr.number} base is {live.base_branch!r}; expected {expected_base!r}."
        )
    if live.title != expected_title:
        raise CommandError(
            f"PR #{pr.number} title is {live.title!r}; expected {expected_title!r}."
        )


def _propagate_chain(
    chain: Chain,
    pull_requests: dict[int, PullRequestRecord],
    *,
    merged_index: int,
    strategy: str,
    remote: str,
    dry_run: bool,
) -> None:
    if strategy not in ("rebase", "cherry-pick"):
        raise CommandError("Propagation strategy must be 'rebase' or 'cherry-pick'.")
    downstream = list(chain.changesets[merged_index:])
    if not downstream:
        print("[OK] Merged changeset has no downstream branches to propagate.")
        return

    planned: list[tuple[ChangesetRecord, PullRequestRecord, str]] = []
    for record in downstream:
        pr_number = record.pr_number
        if pr_number is None or pr_number not in pull_requests:
            raise CommandError(
                f"Downstream changeset {record.position} has no verified PR."
            )
        pr = pull_requests[pr_number]
        expected_base = (
            chain.base_branch
            if record.position == merged_index + 1
            else chain.changesets[record.position - 2].branch
        )
        planned.append((record, pr, expected_base))

    original = current_branch()
    new_base = _remote_ref(remote, chain.base_branch)
    rewrite_frontier_reached = False
    for record, _pr, expected_base in planned:
        current_head = record.head
        allowed_bases = {record.base}
        if expected_base == chain.base_branch:
            allowed_bases.add(chain.base_branch)
        live = _verify_live_downstream(
            record,
            expected_remote_head=current_head,
            allowed_bases=allowed_bases,
            remote=remote,
        )
        already_propagated = not rewrite_frontier_reached and _is_ancestor(
            new_base, current_head
        )
        if already_propagated:
            new_head = current_head
            print(f"[INFO] {record.branch} is already propagated; push not needed.")
        else:
            rewrite_frontier_reached = True
            previous = chain.changesets[record.position - 2]
            old_base = _durable_predecessor(record, previous)
            if strategy == "rebase":
                new_head = _rewrite_rebase(
                    record, old_base=old_base, new_base=new_base, dry_run=dry_run
                )
            else:
                new_head = _rewrite_cherry_pick(
                    record, old_base=old_base, new_base=new_base, dry_run=dry_run
                )
            if not dry_run and current_branch() != original:
                git("checkout", original)

        if not already_propagated:
            live = _verify_live_downstream(
                record,
                expected_remote_head=current_head,
                allowed_bases=allowed_bases,
                remote=remote,
            )
        expected_title = _updated_title(
            live, index=record.position, total=len(chain.changesets)
        )
        if not already_propagated:
            push_changeset_branch(
                record.branch,
                remote=remote,
                dry_run=dry_run,
                expected_remote_head=current_head,
            )
        edit_pull_request(
            live.number,
            remote=remote,
            base=expected_base if live.base_branch != expected_base else None,
            title=expected_title if live.title != expected_title else None,
            dry_run=dry_run,
        )
        if not dry_run:
            _verify_published_downstream(
                live,
                expected_head=new_head,
                expected_base=expected_base,
                expected_title=expected_title,
                remote=remote,
            )
        if dry_run and not already_propagated:
            new_base = record.branch
        else:
            new_base = new_head

    if not dry_run and current_branch() != original:
        # Reaching this point means all rewrites completed without conflict.
        # A conflict intentionally remains checked out for manual recovery.
        if git("status", "--porcelain").stdout.strip():
            raise CommandError(
                "Propagation left local conflict artifacts; resolve them before retrying."
            )
        if current_branch() != original:
            git("checkout", original)


def propagate_from_live(
    *,
    source: str,
    base: str | None,
    pr_number: int | None,
    index: int | None,
    strategy: str,
    remote: str,
    dry_run: bool,
    authority_acknowledged: bool,
) -> None:
    """Verify one merged PR and propagate its open downstream suffix."""

    ensure_git_repo()
    ensure_clean_tree()
    _require_authority(dry_run=dry_run, authority_acknowledged=authority_acknowledged)
    chain, pull_requests = _rehydrate_live(source=source, base=base, remote=remote)
    record, pr = _target(chain, pull_requests, pr_number=pr_number, index=index)
    target_index = record.position
    _require_sequential_target(chain, target_index)
    if pr.state.upper() != "MERGED":
        raise CommandError(
            f"PR #{pr.number} is {pr.state or 'UNKNOWN'}, not MERGED; use merge-propagate "
            "to merge it under explicit authority."
        )
    if not dry_run:
        _verify_merged_on_base(pr, base=chain.base_branch, remote=remote)
    else:
        print(
            f"[DRY-RUN] Would verify PR #{pr.number} is merged on {chain.base_branch}."
        )
    _propagate_chain(
        chain,
        pull_requests,
        merged_index=target_index,
        strategy=strategy,
        remote=remote,
        dry_run=dry_run,
    )
    print(
        "[OK] Dry-run propagation complete."
        if dry_run
        else "[OK] Propagation completed."
    )


def merge_propagate_from_live(
    *,
    source: str,
    base: str | None,
    pr_number: int | None,
    index: int | None,
    strategy: str,
    method: str,
    remote: str,
    dry_run: bool,
    authority_acknowledged: bool,
) -> None:
    """Merge one changeset PR, verify it remotely, then propagate downstream."""

    ensure_git_repo()
    ensure_clean_tree()
    _require_authority(dry_run=dry_run, authority_acknowledged=authority_acknowledged)
    chain, pull_requests = _rehydrate_live(source=source, base=base, remote=remote)
    record, pr = _target(chain, pull_requests, pr_number=pr_number, index=index)
    target_index = record.position
    _require_sequential_target(chain, target_index)
    state = pr.state.upper()
    if state == "CLOSED":
        raise CommandError(f"PR #{pr.number} is closed without merge.")
    if state != "MERGED":
        for prior in chain.changesets[: target_index - 1]:
            if prior.pr_number is None or prior.pr_number not in pull_requests:
                raise CommandError(
                    f"Preceding changeset {prior.position} has no verified PR."
                )
            _verify_merged_on_base(
                pull_requests[prior.pr_number],
                base=chain.base_branch,
                remote=remote,
            )
        live_target = _verify_live_downstream(
            record,
            expected_remote_head=record.head,
            allowed_bases={chain.base_branch},
            remote=remote,
            role="Merge target",
        )
        _require_merge_target_ancestry(
            record, base=live_target.base_branch, remote=remote
        )
        merge_pull_request(
            pr.number,
            expected_head=live_target.head_sha,
            method=method,
            remote=remote,
            dry_run=dry_run,
        )
    else:
        print(f"[INFO] PR #{pr.number} is already merged; resuming propagation.")
    if not dry_run:
        _verify_merged_on_base(pr, base=chain.base_branch, remote=remote)
    else:
        print(
            f"[DRY-RUN] Would verify PR #{pr.number} is MERGED and represented on "
            f"{remote}/{chain.base_branch} before propagation."
        )
    _propagate_chain(
        chain,
        pull_requests,
        merged_index=target_index,
        strategy=strategy,
        remote=remote,
        dry_run=dry_run,
    )
    print(
        "[OK] Dry-run merge-and-propagate complete."
        if dry_run
        else "[OK] Merge-and-propagate completed."
    )
