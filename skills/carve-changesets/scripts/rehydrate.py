"""Reconstruct changeset topology from live git refs and GitHub PR records."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from common import CommandError
from metadata import (
    ChangesetMetadata,
    MetadataError,
    SourceIdentity,
    has_legacy_pr_metadata_comment,
    parse_commit_message,
    parse_pr_metadata,
    stamp_commit_message,
)
from native_stack import NativeStackSnapshot
from publication import remote_branch_head
from transitions import AuthorityGrant, EffectKind, StackOperation, TransitionPhase


class RehydrationError(RuntimeError):
    """Raised when live evidence cannot identify one unambiguous chain."""


@dataclass(frozen=True)
class StackFixHandback:
    reviewed_pr: int
    reviewed_head: str
    invalidated_branches: tuple[str, ...]
    invalidated_pull_requests: tuple[int, ...]
    invalidated_evidence: tuple[str, ...]
    requested_phase: str
    authority_required: str
    resume_command: str


@dataclass(frozen=True)
class CandidateEvidence:
    branch: str
    head: str
    effective_candidate: str


@dataclass(frozen=True)
class NativeRecoveryGuidance:
    terminal_state: str
    phase: str
    identities: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    blocker: str
    next_action: str


def native_interruption_guidance(
    *,
    kind: str,
    phase: str,
    stack_identity: str,
    branch: str,
    evidence_ids: tuple[str, ...],
    lock_owner: str | None = None,
) -> NativeRecoveryGuidance:
    """Report dependency-documented recovery without reading private state."""

    if not phase or not stack_identity or not branch:
        raise RehydrationError("Recovery needs exact phase and stack identities.")
    if kind == "rebase_conflict":
        blocker = f"Native rebase conflict at {branch}; dependency recovery state remains intact."
        action = "Resolve the reported conflict, then run gh stack rebase --continue."
    elif kind == "stack_lock":
        owner = lock_owner or "the current stack operation"
        blocker = f"Native stack lock is held by {owner}; no write was attempted."
        action = f"After {owner} releases the lock, run gh stack view --json."
    elif kind == "divergence":
        blocker = (
            "Local and remote native stack state diverged; no write was attempted."
        )
        action = "Run gh stack view --json and reconcile the divergence before a fresh manifest."
    elif kind == "interrupted_modify":
        blocker = f"Native modify is interrupted at {branch}; dependency recovery state remains intact."
        action = "Resolve the reported conflict, then run gh stack modify --continue."
    else:
        raise RehydrationError(f"Unknown native interruption kind {kind!r}.")
    return NativeRecoveryGuidance(
        "blocked", phase, (stack_identity, branch), evidence_ids, blocker, action
    )


def invalidated_candidate_evidence(
    evidence: Mapping[str, CandidateEvidence],
    *,
    current_heads: Mapping[str, str],
    effective_candidate: str,
) -> tuple[str, ...]:
    """Name every artifact whose head or effective candidate changed."""

    return tuple(
        evidence_id
        for evidence_id, binding in evidence.items()
        if current_heads.get(binding.branch) != binding.head
        or binding.effective_candidate != effective_candidate
    )


def parse_stack_fix_handback(raw: str) -> StackFixHandback:
    """Decode only the exact stack repair handback, never its authority."""

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RehydrationError(f"Invalid stack-fix handback JSON: {exc}") from exc
    expected = {
        "kind",
        "reviewed_pr",
        "reviewed_head",
        "invalidated_suffix",
        "invalidated_evidence",
        "requested_phase",
        "authority_required",
        "resume_command",
    }
    if not isinstance(data, dict) or set(data) != expected:
        raise RehydrationError("Stack-fix handback has missing or unknown fields.")
    suffix = data["invalidated_suffix"]
    if not isinstance(suffix, dict) or set(suffix) != {"branches", "pull_requests"}:
        raise RehydrationError(
            "Stack-fix handback suffix has missing or unknown fields."
        )
    number = data["reviewed_pr"]
    head = data["reviewed_head"]
    branches = suffix["branches"]
    prs = suffix["pull_requests"]
    evidence = data["invalidated_evidence"]
    if data["kind"] != "stack_fix_handback":
        raise RehydrationError("Unknown stack-fix handback kind.")
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise RehydrationError("Reviewed PR must be a positive number.")
    if not isinstance(head, str) or re.fullmatch(r"[0-9a-f]{40}", head) is None:
        raise RehydrationError("Reviewed head must be an exact full SHA.")
    if (
        not isinstance(branches, list)
        or not branches
        or any(not isinstance(item, str) or not item.strip() for item in branches)
        or len(set(branches)) != len(branches)
        or not isinstance(prs, list)
        or len(prs) != len(branches)
        or any(
            not isinstance(item, int) or isinstance(item, bool) or item < 1
            for item in prs
        )
        or len(set(prs)) != len(prs)
        or prs[0] != number
    ):
        raise RehydrationError("Stack-fix handback must name one ordered open suffix.")
    if (
        not isinstance(evidence, list)
        or not evidence
        or any(not isinstance(item, str) or not item.strip() for item in evidence)
        or len(set(evidence)) != len(evidence)
    ):
        raise RehydrationError("Stack-fix handback needs exact prior evidence IDs.")
    if data["requested_phase"] != "repair":
        raise RehydrationError("Stack-fix handback may request only the repair phase.")
    authority = data["authority_required"]
    if not isinstance(authority, str) or not authority.strip():
        raise RehydrationError("Stack-fix handback must name authority still needed.")
    command = data["resume_command"]
    expected_command = (
        f"python3 skills/carve-changesets/scripts/cli.py repair --pr {number}"
    )
    if command != expected_command:
        raise RehydrationError("Stack-fix handback has no exact resume command.")
    return StackFixHandback(
        number,
        head,
        tuple(branches),
        tuple(prs),
        tuple(evidence),
        "repair",
        authority,
        command,
    )


def render_stack_fix_handback(handback: StackFixHandback) -> str:
    """Render a parseable handback with no implied merge authority."""

    return (
        json.dumps(
            {
                "kind": "stack_fix_handback",
                "reviewed_pr": handback.reviewed_pr,
                "reviewed_head": handback.reviewed_head,
                "invalidated_suffix": {
                    "branches": list(handback.invalidated_branches),
                    "pull_requests": list(handback.invalidated_pull_requests),
                },
                "invalidated_evidence": list(handback.invalidated_evidence),
                "requested_phase": handback.requested_phase,
                "authority_required": handback.authority_required,
                "resume_command": handback.resume_command,
            },
            indent=2,
        )
        + "\n"
    )


def validate_stack_fix_handback(
    handback: StackFixHandback,
    *,
    snapshot: NativeStackSnapshot,
    pull_requests: Sequence[PullRequestRecord],
    repository: str,
    remote: str,
    authority: AuthorityGrant | None,
) -> StackFixHandback:
    """Bind a handback to fresh native/GitHub state and separate stack authority."""

    if authority is None or authority.operation is not StackOperation.REPAIR:
        raise RehydrationError("Explicit stack-wide repair authority is required.")
    if authority.repository != repository or authority.remote != remote:
        raise RehydrationError("Repair authority repository or remote does not match.")
    required_phases = frozenset(
        {
            TransitionPhase.REBASE_NO_TRUNK,
            TransitionPhase.PUSH,
            TransitionPhase.SYNC,
        }
    )
    required_effects = frozenset(
        {
            EffectKind.REBASE_BRANCH,
            EffectKind.PUSH_REF,
            EffectKind.UPDATE_PR,
            EffectKind.SYNC_STACK,
        }
    )
    if (
        authority.identities != handback.invalidated_branches
        or authority.branches != handback.invalidated_branches
        or authority.phases != required_phases
        or authority.effect_kinds != required_effects
    ):
        raise RehydrationError(
            "Repair authority does not exactly fence the named suffix."
        )
    reviewed_index = next(
        (
            index
            for index, layer in enumerate(snapshot.layers)
            if layer.pull_request is not None
            and layer.pull_request.number == handback.reviewed_pr
        ),
        None,
    )
    if reviewed_index is None:
        raise RehydrationError("Reviewed PR is absent from fresh native topology.")
    suffix = snapshot.layers[reviewed_index:]
    if (
        suffix[0].head != handback.reviewed_head
        or any(layer.merged or layer.pull_request is None for layer in suffix)
        or tuple(layer.branch for layer in suffix) != handback.invalidated_branches
        or tuple(layer.pull_request.number for layer in suffix if layer.pull_request)
        != handback.invalidated_pull_requests
    ):
        raise RehydrationError("Handback suffix disagrees with fresh native topology.")
    live_prs = {pr.number: pr for pr in pull_requests}
    if len(live_prs) != len(pull_requests):
        raise RehydrationError("Fresh GitHub PR readback has duplicate numbers.")
    for offset, layer in enumerate(suffix, reviewed_index):
        assert layer.pull_request is not None
        live = live_prs.get(layer.pull_request.number)
        if (
            live is None
            or live.state != "OPEN"
            or live.head_branch != layer.branch
            or live.head_sha != layer.head
            or live.is_cross_repository
        ):
            raise RehydrationError(
                "Handback suffix disagrees with fresh GitHub PR heads."
            )
        predecessor = snapshot.layers[offset - 1] if offset else None
        expected_base = (
            snapshot.trunk_branch
            if predecessor is None or predecessor.merged
            else predecessor.branch
        )
        if live.base_branch != expected_base:
            raise RehydrationError(
                f"Handback suffix PR #{live.number} base changed from {expected_base}."
            )
    return handback


@dataclass(frozen=True)
class PullRequestRecord:
    """GitHub fields supplied by the consolidated CLI's gh chokepoint."""

    number: int
    head_branch: str
    head_sha: str
    base_branch: str
    state: str
    body: str
    title: str = ""
    merge_sha: str | None = None
    is_cross_repository: bool = False
    head_rewrite_edges: tuple[tuple[str, str], ...] = ()
    draft: bool = False
    queued: bool = False
    auto_merge: bool = False
    merge_state_status: str = ""


@dataclass(frozen=True)
class ChangesetRecord:
    metadata: ChangesetMetadata
    branch: str
    head: str
    base: str
    pr_number: int | None = None
    pr_state: str | None = None
    pr_metadata: ChangesetMetadata | None = None
    topology_position: int | None = None
    pr_merge_sha: str | None = None
    pr_head_rewrite_edges: tuple[tuple[str, str], ...] = ()

    @property
    def position(self) -> int:
        """Return live topology order, falling back to legacy evidence."""

        if self.topology_position is not None:
            return self.topology_position
        if self.metadata.legacy_position is not None:
            return self.metadata.legacy_position
        raise RehydrationError(
            f"Changeset branch {self.branch!r} has no live topology position."
        )


@dataclass(frozen=True)
class Chain:
    base_branch: str
    source_branch: str
    source_sha: str
    root_source_sha: str
    source_lineage: tuple[SourceIdentity, ...]
    changesets: tuple[ChangesetRecord, ...]
    native_topology: bool

    @property
    def active_source(self) -> SourceIdentity:
        return self.source_lineage[-1]


def _git(cwd: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RehydrationError(
            "Git is required to rehydrate a changeset chain."
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RehydrationError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def _ensure_commit_available(repo: Path, sha: str, *, remote: str) -> None:
    """Acquire one exact historical commit without creating a synthetic ref."""

    try:
        _git(repo, "cat-file", "-e", f"{sha}^{{commit}}")
        return
    except RehydrationError:
        pass
    _git(
        repo,
        "fetch",
        "--no-tags",
        "--no-write-fetch-head",
        remote,
        sha,
    )
    _git(repo, "cat-file", "-e", f"{sha}^{{commit}}")


def _interrupted_legacy_pr_evidence(
    *,
    pr: PullRequestRecord,
    remote: str,
    allow_interrupted_recovery: bool = False,
) -> ChangesetMetadata | None:
    """Read the one permitted v3-head/legacy-body recovery interval."""

    if not has_legacy_pr_metadata_comment(pr.body):
        return None
    if not allow_interrupted_recovery:
        raise RehydrationError(
            f"PR #{pr.number} has an incomplete recovery state: its native head "
            "still has legacy PR metadata."
        )
    try:
        return parse_pr_metadata(pr.body, remote=remote)
    except MetadataError as exc:
        raise RehydrationError(
            f"PR #{pr.number} cannot prove interrupted recovery from legacy "
            f"metadata: {exc}"
        ) from exc


def discover_changeset_heads(
    cwd: Path,
    source_branch: str,
    remote: str,
    *,
    prefer_remote: bool = False,
) -> dict[int, tuple[str, str]]:
    """Resolve current changeset refs and reject local/remote ambiguity."""

    output = _git(
        cwd,
        "for-each-ref",
        "--format=%(refname)%00%(objectname)",
        "refs/heads",
        f"refs/remotes/{remote}",
    )
    prefix = re.escape(source_branch)
    local_pattern = re.compile(
        rf"^refs/heads/(?P<branch>{prefix}-(?P<index>[1-9][0-9]*))$"
    )
    remote_pattern = re.compile(
        rf"^refs/remotes/{re.escape(remote)}/(?P<branch>{prefix}-(?P<index>[1-9][0-9]*))$"
    )
    candidates: dict[int, dict[str, tuple[str, str]]] = {}
    for line in output.splitlines():
        ref, separator, head = line.partition("\0")
        if not separator:
            continue
        match = remote_pattern.fullmatch(ref)
        kind = "remote"
        if match is None:
            match = local_pattern.fullmatch(ref)
            kind = "local"
        if match is None:
            continue
        index = int(match.group("index"))
        candidates.setdefault(index, {})[kind] = (match.group("branch"), head)

    heads: dict[int, tuple[str, str]] = {}
    for index, variants in candidates.items():
        local = variants.get("local")
        published = variants.get("remote")
        if local and published and local[1] != published[1]:
            if prefer_remote:
                heads[index] = published
                continue
            raise RehydrationError(
                f"Changeset branch {local[0]} is ambiguous: local head {local[1]} "
                f"differs from {remote} head {published[1]}."
            )
        heads[index] = published or local  # type: ignore[assignment]
    return heads


def _pr_by_branch(
    pull_requests: Iterable[PullRequestRecord], source_branch: str
) -> dict[str, PullRequestRecord]:
    pattern = re.compile(rf"^{re.escape(source_branch)}-[1-9][0-9]*$")
    grouped: dict[str, list[PullRequestRecord]] = {}
    for pr in pull_requests:
        if pattern.fullmatch(pr.head_branch):
            grouped.setdefault(pr.head_branch, []).append(pr)
    duplicates = {branch: prs for branch, prs in grouped.items() if len(prs) > 1}
    if duplicates:
        detail = ", ".join(
            f"{branch} -> PRs {', '.join(f'#{pr.number}' for pr in prs)}"
            for branch, prs in sorted(duplicates.items())
        )
        raise RehydrationError(
            f"Multiple PRs claim the same changeset branch: {detail}."
        )
    return {branch: prs[0] for branch, prs in grouped.items()}


def _validate_lineage_sequence(
    records: Sequence[ChangesetRecord],
    *,
    allow_authenticated_multi_successor: bool = False,
) -> tuple[SourceIdentity, ...]:
    previous: tuple[SourceIdentity, ...] | None = None
    previous_merged = False
    open_lineage: tuple[SourceIdentity, ...] | None = None
    for record in records:
        lineage = record.metadata.source_lineage
        if previous is not None and lineage != previous:
            extends = (
                previous_merged
                and (
                    len(lineage) == len(previous) + 1
                    or (
                        allow_authenticated_multi_successor
                        and len(lineage) > len(previous)
                    )
                )
                and lineage[: len(previous)] == previous
            )
            if not extends:
                raise RehydrationError(
                    f"Changeset branch {record.branch} has missing, conflicting, "
                    "or discontinuous successor-source lineage."
                )
        if record.pr_state != "MERGED":
            if open_lineage is None:
                open_lineage = lineage
            elif lineage != open_lineage:
                raise RehydrationError(
                    "Open changeset suffix has conflicting or discontinuous "
                    "successor-source lineage."
                )
        previous = lineage
        previous_merged = record.pr_state == "MERGED"
    assert previous is not None
    return previous


def _validate_completed_recovery_provenance(
    records: Sequence[ChangesetRecord],
    *,
    repo: Path,
    remote: str,
    base_branch: str,
    base_authoritative: bool,
    evidence_join_successor: SourceIdentity | None = None,
) -> None:
    """Prove each completed successor head from its exact prior candidate."""

    proven_predecessors: dict[int, tuple[str, ChangesetMetadata]] = {}

    def remote_rewrite_boundary(
        record: ChangesetRecord,
        predecessor: str,
        *,
        expected_metadata: ChangesetMetadata | None = None,
    ) -> tuple[str, int] | None:
        """Return the authenticated first head for this successor lineage."""

        target_metadata = expected_metadata or record.metadata
        for index, (before, after) in enumerate(record.pr_head_rewrite_edges):
            try:
                _ensure_commit_available(repo, after, remote=remote)
                after_metadata = parse_commit_message(
                    _git(repo, "show", "-s", "--format=%B", after),
                    remote=remote,
                )
            except (MetadataError, RehydrationError):
                return None
            if after_metadata.source_lineage != target_metadata.source_lineage:
                continue
            if before != predecessor or after_metadata.slug != target_metadata.slug:
                return None
            return after, index
        return None

    def proves_linear_tail(start: str, end: str) -> bool:
        """Prove ordinary accepted commits after a recovery restamp."""

        if start == end:
            return True
        try:
            _git(repo, "merge-base", "--is-ancestor", start, end)
            return not _git(
                repo,
                "rev-list",
                "--merges",
                f"{start}..{end}",
            ).strip()
        except RehydrationError:
            return False

    def remote_rewrite_tip(
        record: ChangesetRecord,
        start: str,
        boundary_index: int,
        end: str,
    ) -> str | None:
        """Return the last authenticated rewrite before a linear tail."""

        current = start
        for before, after in record.pr_head_rewrite_edges[boundary_index + 1 :]:
            try:
                _ensure_commit_available(repo, before, remote=remote)
                _ensure_commit_available(repo, after, remote=remote)
            except RehydrationError:
                return None
            if proves_linear_tail(current, end):
                return current
            if before != current and not proves_linear_tail(current, before):
                return None
            current = after
        return current if proves_linear_tail(current, end) else None

    def proves_prior_rewrite_path(
        record: ChangesetRecord, start: str, end: str
    ) -> bool:
        """Prove one earlier published head advanced to the recorded predecessor."""

        if start == end:
            return True
        current = start
        started = False
        for before, after in record.pr_head_rewrite_edges:
            if before != current:
                if started:
                    return False
                continue
            started = True
            current = after
            if current == end:
                return True
        return False

    def patch_id(parent: str, child: str) -> bytes | None:
        """Return Git's stable identity for the exact layer delta."""

        diff = subprocess.run(
            ["git", "diff", "--no-ext-diff", "--binary", parent, child],
            cwd=repo,
            capture_output=True,
            check=False,
        )
        if diff.returncode != 0 or not diff.stdout:
            return None
        identified = subprocess.run(
            ["git", "patch-id", "--stable"],
            cwd=repo,
            input=diff.stdout,
            capture_output=True,
            check=False,
        )
        if identified.returncode != 0 or not identified.stdout.strip():
            return None
        return identified.stdout.split(maxsplit=1)[0]

    def first_parent_ancestors(head: str) -> list[str]:
        """Return the head's first-parent history below its tip."""

        return _git(repo, "rev-list", "--first-parent", f"{head}^").splitlines()

    def proven_post_merge_parent(
        previous: ChangesetRecord,
        record: ChangesetRecord,
        current_parent: str,
    ) -> bool:
        if (
            previous.pr_state != "MERGED"
            or previous.pr_merge_sha is None
            or record.base == previous.branch
        ):
            return False
        try:
            _ensure_commit_available(repo, previous.pr_merge_sha, remote=remote)
            live_base = _git(
                repo,
                "rev-parse",
                f"refs/remotes/{remote}/{record.base}^{{commit}}",
            ).strip()
            _git(
                repo,
                "merge-base",
                "--is-ancestor",
                previous.pr_merge_sha,
                current_parent,
            )
            _git(repo, "merge-base", "--is-ancestor", current_parent, live_base)
        except RehydrationError:
            return False
        return True

    def proves_evidence_preserving_join(
        record: ChangesetRecord,
        proof_head: str,
        proof_metadata: ChangesetMetadata,
    ) -> bool:
        """Authenticate the one exact current-base/reviewed-source join."""

        successor = evidence_join_successor
        if (
            successor is None
            or not base_authoritative
            or successor.remote != remote
            or successor in record.metadata.source_lineage
            or proof_head != record.head
            or proof_metadata != record.metadata
        ):
            return False
        try:
            _ensure_commit_available(repo, successor.sha, remote=remote)
            published_successor = remote_branch_head(
                remote,
                successor.branch,
                cwd=repo,
            )
            live_base = remote_branch_head(
                remote,
                base_branch,
                cwd=repo,
            )
            parents = _git(repo, "show", "-s", "--format=%P", proof_head).split()
            proof_tree = _git(repo, "rev-parse", f"{proof_head}^{{tree}}")
            successor_tree = _git(repo, "rev-parse", f"{successor.sha}^{{tree}}")
        except (CommandError, RehydrationError):
            return False
        return (
            published_successor == successor.sha
            and parents == [live_base, successor.sha]
            and proof_tree == successor_tree
        )

    for offset, record in enumerate(records):
        lineage = record.metadata.source_lineage
        if len(lineage) == 1:
            continue
        if len(lineage) > 2 and (
            offset == 0 or records[offset - 1].metadata.source_lineage != lineage
        ):
            group = []
            for candidate in records[offset:]:
                if candidate.metadata.source_lineage != lineage:
                    break
                group.append(candidate)
            prior_records = []
            try:
                for candidate in group:
                    prior_head = candidate.metadata.recovery_from_head
                    if prior_head is None:
                        raise RehydrationError("prior recovery head is missing")
                    _ensure_commit_available(repo, prior_head, remote=remote)
                    prior_metadata = parse_commit_message(
                        _git(repo, "show", "-s", "--format=%B", prior_head),
                        remote=remote,
                    )
                    if prior_metadata.source_lineage != lineage[:-1]:
                        raise RehydrationError("prior recovery lineage is invalid")
                    prior_pr_metadata = (
                        candidate.pr_metadata
                        if candidate.pr_metadata is not None
                        and candidate.pr_metadata.source_lineage == lineage[:-1]
                        else None
                    )
                    prior_records.append(
                        replace(
                            candidate,
                            metadata=prior_metadata,
                            head=prior_head,
                            pr_metadata=prior_pr_metadata,
                        )
                    )
                _validate_completed_recovery_provenance(
                    prior_records,
                    repo=repo,
                    remote=remote,
                    base_branch=base_branch,
                    base_authoritative=base_authoritative,
                    evidence_join_successor=lineage[-1],
                )
            except (MetadataError, RehydrationError) as exc:
                raise RehydrationError(
                    f"Changeset branch {record.branch} cannot prove its exact "
                    "pre-recovery head."
                ) from exc
        predecessor = record.metadata.recovery_from_head
        if predecessor is None:
            raise RehydrationError(
                f"Changeset branch {record.branch} cannot prove its exact "
                "pre-recovery head."
            )
        try:
            _ensure_commit_available(repo, predecessor, remote=remote)
            predecessor_message = _git(repo, "show", "-s", "--format=%B", predecessor)
            predecessor_metadata = parse_commit_message(
                predecessor_message,
                remote=remote,
            )
            boundary_result = remote_rewrite_boundary(record, predecessor)
            if boundary_result is None:
                raise RehydrationError("remote rewrite boundary is not proven")
            boundary_head, boundary_index = boundary_result
            boundary_message = _git(repo, "show", "-s", "--format=%B", boundary_head)
            boundary_metadata = parse_commit_message(
                boundary_message,
                remote=remote,
            )
            proof_head = remote_rewrite_tip(
                record,
                boundary_head,
                boundary_index,
                record.head,
            )
            if proof_head is None:
                raise RehydrationError("remote rewrite tail is not proven")
            proof_message = _git(repo, "show", "-s", "--format=%B", proof_head)
            proof_metadata = parse_commit_message(proof_message, remote=remote)
            same_tree = _git(repo, "rev-parse", f"{proof_head}^{{tree}}") == _git(
                repo, "rev-parse", f"{predecessor}^{{tree}}"
            )
            current_parents = _git(
                repo, "show", "-s", "--format=%P", proof_head
            ).split()
            expected_parents = _git(
                repo, "show", "-s", "--format=%P", predecessor
            ).split()
        except (MetadataError, RehydrationError) as exc:
            raise RehydrationError(
                f"Changeset branch {record.branch} cannot prove its exact "
                "pre-recovery head."
            ) from exc

        parent_proven = current_parents == expected_parents
        later_history_proven = proves_linear_tail(proof_head, record.head)
        if offset > 0:
            previous = records[offset - 1]
            if previous.metadata.source_lineage == lineage:
                previous_predecessor = proven_predecessors.get(offset - 1)
                if previous_predecessor is None:
                    raise RehydrationError(
                        f"Changeset branch {record.branch} cannot prove its exact "
                        "pre-recovery head."
                    )
                prior_parent = next(
                    (
                        candidate
                        for candidate in first_parent_ancestors(predecessor)
                        if proves_prior_rewrite_path(
                            previous,
                            candidate,
                            previous_predecessor[0],
                        )
                    ),
                    None,
                )
                if prior_parent is None:
                    raise RehydrationError(
                        f"Changeset branch {record.branch} cannot prove its exact "
                        "pre-recovery head."
                    )
                if previous.pr_state == "MERGED" and record.base != previous.branch:
                    recovered_parent = next(
                        (
                            candidate
                            for candidate in first_parent_ancestors(proof_head)
                            if proven_post_merge_parent(
                                previous,
                                record,
                                candidate,
                            )
                        ),
                        None,
                    )
                else:
                    recovered_parent = (
                        previous.head
                        if previous.head in first_parent_ancestors(proof_head)
                        else None
                    )
                if recovered_parent is None:
                    raise RehydrationError(
                        f"Changeset branch {record.branch} cannot prove its exact "
                        "pre-recovery head."
                    )
                same_tree = patch_id(prior_parent, predecessor) == patch_id(
                    recovered_parent, proof_head
                )
                parent_proven = True

        exact_restamp_proven = (
            same_tree
            and parent_proven
            and stamp_commit_message(predecessor_message, record.metadata).strip()
            == proof_message.strip()
        )
        evidence_join_proven = proves_evidence_preserving_join(
            record,
            proof_head,
            proof_metadata,
        )
        if (
            predecessor_metadata.slug != record.metadata.slug
            or predecessor_metadata.source_lineage != lineage[:-1]
            or boundary_metadata != record.metadata
            or (
                record.pr_metadata is not None
                and record.pr_metadata.source_lineage == lineage[:-1]
                and record.pr_metadata != predecessor_metadata
            )
            or not later_history_proven
            or not (exact_restamp_proven or evidence_join_proven)
        ):
            raise RehydrationError(
                f"Changeset branch {record.branch} cannot prove its exact "
                "pre-recovery head."
            )
        proven_predecessors[offset] = (predecessor, predecessor_metadata)


def _validate_authenticated_lineage_sequence(
    records: Sequence[ChangesetRecord],
    *,
    repo: Path,
    remote: str,
    base_branch: str,
    base_authoritative: bool,
) -> tuple[SourceIdentity, ...]:
    """Accept a multi-successor jump only after its provenance is proven."""

    try:
        lineage = _validate_lineage_sequence(records)
    except RehydrationError as sequence_error:
        try:
            lineage = _validate_lineage_sequence(
                records,
                allow_authenticated_multi_successor=True,
            )
            _validate_completed_recovery_provenance(
                records,
                repo=repo,
                remote=remote,
                base_branch=base_branch,
                base_authoritative=base_authoritative,
            )
        except RehydrationError:
            raise sequence_error
        return lineage
    _validate_completed_recovery_provenance(
        records,
        repo=repo,
        remote=remote,
        base_branch=base_branch,
        base_authoritative=base_authoritative,
    )
    return lineage


def _validate_recovery_transition(
    records: Sequence[ChangesetRecord],
    successor: SourceIdentity,
    *,
    repo: Path,
    remote: str,
    base_branch: str,
    base_authoritative: bool,
) -> tuple[SourceIdentity, ...]:
    first_open = next(
        (
            offset
            for offset, record in enumerate(records)
            if record.pr_state != "MERGED"
        ),
        None,
    )
    if first_open is None or first_open == 0:
        raise RehydrationError(
            "Suffix recovery requires a non-empty merged prefix and an open suffix."
        )
    base_lineage = records[first_open - 1].metadata.source_lineage
    current_lineage = base_lineage
    first_open_lineage = records[first_open].metadata.source_lineage
    requested_lineage = (*base_lineage, successor)
    repeated_legacy_recovery = (
        first_open_lineage != base_lineage
        and first_open_lineage != requested_lineage
        and len(first_open_lineage) > len(base_lineage)
        and first_open_lineage[: len(base_lineage)] == base_lineage
    )
    interrupted_repeated_recovery = (
        len(first_open_lineage) > len(base_lineage) + 1
        and first_open_lineage[: len(base_lineage)] == base_lineage
        and first_open_lineage[-1] == successor
    )
    if repeated_legacy_recovery or interrupted_repeated_recovery:
        current_lineage = (
            first_open_lineage[:-1]
            if interrupted_repeated_recovery
            else first_open_lineage
        )
        target_lineage = (*current_lineage, successor)
        if any(
            record.metadata.source_lineage not in (current_lineage, target_lineage)
            for record in records[first_open:]
        ):
            raise RehydrationError(
                "Open legacy changeset suffix has conflicting or discontinuous "
                "successor-source lineage."
            )
        _validate_completed_recovery_provenance(
            records[first_open:],
            repo=repo,
            remote=remote,
            base_branch=base_branch,
            base_authoritative=base_authoritative,
            evidence_join_successor=successor,
        )

    if successor in current_lineage or any(
        identity.branch == successor.branch for identity in current_lineage
    ):
        raise RehydrationError(
            "Successor source repeats an existing lineage identity or branch."
        )
    target = (*current_lineage, successor)
    _validate_lineage_sequence(records[:first_open])
    prior_lineage_seen = False
    for record in records[first_open:]:
        commit_lineage = record.metadata.source_lineage
        if commit_lineage not in (current_lineage, target):
            raise RehydrationError(
                f"Changeset branch {record.branch} has lineage outside the current "
                "or requested successor recovery."
            )
        if commit_lineage == current_lineage:
            prior_lineage_seen = True
        elif prior_lineage_seen:
            raise RehydrationError(
                "Recovered changeset heads must form a leading prefix of the open "
                "suffix; live recovery lineage is discontinuous."
            )
        if record.pr_metadata is not None:
            pr_metadata = record.pr_metadata
            if pr_metadata.source_lineage not in (current_lineage, target):
                raise RehydrationError(
                    f"PR #{record.pr_number} has lineage outside the current or "
                    "requested successor recovery."
                )
            if (
                record.metadata.slug != pr_metadata.slug
                or record.metadata.root_source != pr_metadata.root_source
            ):
                raise RehydrationError(
                    f"PR #{record.pr_number} metadata cannot prove the stable "
                    "changeset identity during recovery."
                )
            if commit_lineage == current_lineage and pr_metadata != record.metadata:
                raise RehydrationError(
                    f"PR #{record.pr_number} metadata advances or conflicts before "
                    "its changeset head is recovered."
                )
            if commit_lineage == target:
                if (
                    pr_metadata.source_lineage == target
                    and pr_metadata != record.metadata
                ):
                    raise RehydrationError(
                        f"PR #{record.pr_number} has conflicting recovered provenance."
                    )
                if (
                    pr_metadata.source_lineage == current_lineage
                    and record.metadata.recovery_from_head == record.head
                ):
                    raise RehydrationError(
                        f"Changeset branch {record.branch} does not identify a distinct "
                        "pre-recovery head."
                    )

    recovered_prefix: list[ChangesetRecord] = []
    for record in records[first_open:]:
        if record.metadata.source_lineage != target:
            break
        recovered_prefix.append(record)
    _validate_completed_recovery_provenance(
        recovered_prefix,
        repo=repo,
        remote=remote,
        base_branch=base_branch,
        base_authoritative=base_authoritative,
    )
    return target


def adopt_legacy_chain(
    *,
    source_branch: str,
    pull_requests: Sequence[PullRequestRecord] = (),
    base_branch: str | None = None,
    cwd: Path | str = Path.cwd(),
    remote: str = "origin",
    prefer_remote: bool = False,
    recovery_successor: SourceIdentity | None = None,
) -> Chain:
    """Adopt one legacy ``source-N`` chain from suffix and index evidence."""

    if not source_branch.strip():
        raise RehydrationError("Source branch must not be empty.")
    repo = Path(cwd)
    base_authoritative = base_branch is not None
    heads = discover_changeset_heads(
        repo, source_branch, remote, prefer_remote=prefer_remote
    )
    prs = _pr_by_branch(pull_requests, source_branch)
    pr_indices = {
        int(pr.head_branch.removeprefix(f"{source_branch}-")): pr for pr in prs.values()
    }
    found = sorted(set(heads) | set(pr_indices))
    if not found:
        raise RehydrationError(
            f"No changeset branches or PRs named {source_branch}-N were found."
        )
    expected = list(range(1, found[-1] + 1))
    if found != expected:
        missing = sorted(set(expected) - set(found))
        raise RehydrationError(
            "Changeset branch sequence has gap(s): missing index "
            + ", ".join(str(index) for index in missing)
            + "."
        )

    if base_branch is None:
        first_pr = prs.get(f"{source_branch}-1")
        if first_pr is None:
            raise RehydrationError(
                "Base branch is required when changeset 1 has no PR relationship."
            )
        base_branch = first_pr.base_branch
    if not base_branch.strip():
        raise RehydrationError("Base branch must not be empty.")

    records: list[ChangesetRecord] = []
    root_source: SourceIdentity | None = None
    slugs: set[str] = set()
    prior_prs_merged = True
    for index in found:
        pr = pr_indices.get(index)
        if index in heads:
            branch, head = heads[index]
        elif pr is not None and pr.state.upper() == "MERGED":
            branch, head = pr.head_branch, pr.head_sha
            _git(repo, "cat-file", "-e", f"{head}^{{commit}}")
        else:
            raise RehydrationError(
                f"Open changeset branch {source_branch}-{index} is missing locally and on {remote}."
            )
        message = _git(repo, "show", "-s", "--format=%B", head)
        try:
            metadata = parse_commit_message(message, remote=remote)
        except MetadataError as exc:
            raise RehydrationError(f"Changeset branch {branch}: {exc}") from exc
        if metadata.legacy_position is not None and metadata.index != index:
            raise RehydrationError(
                f"Changeset branch {branch} has Changeset-Index {metadata.index}; expected {index}."
            )
        if metadata.root_source.branch != source_branch:
            raise RehydrationError(
                f"Changeset branch {branch} names chain root "
                f"{metadata.root_source.branch!r}; expected {source_branch!r}."
            )
        if root_source is None:
            root_source = metadata.root_source
        elif metadata.root_source != root_source:
            raise RehydrationError(
                f"Changeset branch {branch} names root source "
                f"{metadata.root_source.trailer}; expected {root_source.trailer}."
            )
        if metadata.slug in slugs:
            raise RehydrationError(
                f"Duplicate changeset slug {metadata.slug!r} in chain."
            )
        slugs.add(metadata.slug)

        predecessor_base = base_branch if index == 1 else f"{source_branch}-{index - 1}"
        pr = prs.get(branch)
        pr_metadata: ChangesetMetadata | None = None
        if pr is not None:
            if pr.is_cross_repository:
                raise RehydrationError(
                    f"PR #{pr.number} uses a fork head; changeset branches must belong "
                    "to the selected repository."
                )
            if pr.head_sha != head:
                raise RehydrationError(
                    f"PR #{pr.number} head {pr.head_sha} disagrees with branch {branch} head {head}."
                )
            allowed_bases = {predecessor_base}
            if prior_prs_merged:
                allowed_bases.add(base_branch)
            if pr.base_branch not in allowed_bases:
                raise RehydrationError(
                    f"PR #{pr.number} base {pr.base_branch!r} conflicts with allowed "
                    f"base(s) {', '.join(repr(item) for item in sorted(allowed_bases))} "
                    f"for changeset {index}."
                )
            if metadata.version in {1, 2}:
                if has_legacy_pr_metadata_comment(pr.body):
                    try:
                        pr_metadata = parse_pr_metadata(pr.body, remote=remote)
                    except MetadataError as exc:
                        raise RehydrationError(f"PR #{pr.number}: {exc}") from exc
                    if pr_metadata != metadata:
                        if recovery_successor is not None:
                            raise RehydrationError(
                                f"PR #{pr.number} has conflicting recovered provenance."
                            )
                        raise RehydrationError(
                            f"PR #{pr.number} metadata disagrees with commit trailers for {branch}."
                        )
                else:
                    raise RehydrationError(
                        f"PR #{pr.number} lacks required legacy metadata for {branch}."
                    )
            else:
                pr_metadata = _interrupted_legacy_pr_evidence(
                    pr=pr,
                    remote=remote,
                    allow_interrupted_recovery=recovery_successor is not None,
                )
        records.append(
            ChangesetRecord(
                metadata=metadata,
                branch=branch,
                head=head,
                base=pr.base_branch if pr else predecessor_base,
                pr_number=pr.number if pr else None,
                pr_state=pr.state.upper() if pr else None,
                pr_metadata=pr_metadata,
                topology_position=index,
                pr_merge_sha=pr.merge_sha if pr else None,
                pr_head_rewrite_edges=pr.head_rewrite_edges if pr else (),
            )
        )
        prior_prs_merged = (
            prior_prs_merged and pr is not None and pr.state.upper() == "MERGED"
        )

    assert root_source is not None
    source_lineage = (
        _validate_recovery_transition(
            records,
            recovery_successor,
            repo=repo,
            remote=remote,
            base_branch=base_branch,
            base_authoritative=base_authoritative,
        )
        if recovery_successor is not None
        else _validate_authenticated_lineage_sequence(
            records,
            repo=repo,
            remote=remote,
            base_branch=base_branch,
            base_authoritative=base_authoritative,
        )
    )
    active_source = source_lineage[-1]
    return Chain(
        base_branch=base_branch,
        source_branch=source_branch,
        source_sha=active_source.sha,
        root_source_sha=root_source.sha,
        source_lineage=source_lineage,
        changesets=tuple(records),
        native_topology=False,
    )


def rehydrate_chain(
    *,
    source_branch: str,
    remote: str,
    native_snapshot: NativeStackSnapshot | None = None,
    pull_requests: Sequence[PullRequestRecord] = (),
    base_branch: str | None = None,
    cwd: Path | str = Path.cwd(),
) -> Chain:
    """Rehydrate ordinary stack truth exclusively from native layer order."""

    if native_snapshot is None:
        raise RehydrationError(
            "A reconciled native snapshot is required for ordinary rehydration; "
            "use adopt_legacy_chain() only for explicit legacy adoption."
        )
    if not source_branch.strip():
        raise RehydrationError("Source branch must not be empty.")
    if not native_snapshot.layers:
        raise RehydrationError("Native snapshot has no changeset layers.")
    if base_branch is not None and base_branch != native_snapshot.trunk_branch:
        raise RehydrationError(
            f"Requested base {base_branch!r} disagrees with native trunk "
            f"{native_snapshot.trunk_branch!r}."
        )

    repo = Path(cwd)
    prs: dict[int, PullRequestRecord] = {}
    for pr in pull_requests:
        if pr.number in prs:
            raise RehydrationError(
                f"Multiple GitHub records were supplied for PR #{pr.number}."
            )
        prs[pr.number] = pr

    records: list[ChangesetRecord] = []
    root_source: SourceIdentity | None = None
    slugs: set[str] = set()
    previous_branch = native_snapshot.trunk_branch
    previous_layer_merged = False
    for topology_position, layer in enumerate(native_snapshot.layers, start=1):
        message = _git(repo, "show", "-s", "--format=%B", layer.head)
        try:
            metadata = parse_commit_message(message, remote=remote)
        except MetadataError as exc:
            raise RehydrationError(f"Native layer {layer.branch}: {exc}") from exc
        if metadata.root_source.branch != source_branch:
            raise RehydrationError(
                f"Native layer {layer.branch} names chain root "
                f"{metadata.root_source.branch!r}; expected {source_branch!r}."
            )
        if root_source is None:
            root_source = metadata.root_source
        elif metadata.root_source != root_source:
            raise RehydrationError(
                f"Native layer {layer.branch} names root source "
                f"{metadata.root_source.trailer}; expected {root_source.trailer}."
            )
        if metadata.slug in slugs:
            raise RehydrationError(
                f"Duplicate changeset slug {metadata.slug!r} in native stack."
            )
        slugs.add(metadata.slug)

        native_pr = layer.pull_request
        pr = prs.get(native_pr.number) if native_pr is not None else None
        if native_pr is not None and pr is None:
            raise RehydrationError(
                f"Native layer {layer.branch} is missing GitHub PR #{native_pr.number}."
            )
        pr_metadata: ChangesetMetadata | None = None
        if pr is not None:
            if pr.is_cross_repository:
                raise RehydrationError(
                    f"PR #{pr.number} uses a fork head; native layers must belong "
                    "to the selected repository."
                )
            if metadata.version in {1, 2}:
                try:
                    pr_metadata = parse_pr_metadata(pr.body, remote=remote)
                except MetadataError as exc:
                    raise RehydrationError(f"PR #{pr.number}: {exc}") from exc
                if pr_metadata != metadata:
                    raise RehydrationError(
                        f"PR #{pr.number} metadata disagrees with commit trailers for "
                        f"native layer {layer.branch}."
                    )
            else:
                pr_metadata = _interrupted_legacy_pr_evidence(
                    pr=pr,
                    remote=remote,
                )
        materialized_base = (
            native_snapshot.trunk_branch
            if previous_layer_merged and not layer.merged
            else previous_branch
        )
        records.append(
            ChangesetRecord(
                metadata=metadata,
                branch=layer.branch,
                head=layer.head,
                base=pr.base_branch if pr is not None else materialized_base,
                pr_number=pr.number if pr is not None else None,
                pr_state=pr.state.upper() if pr is not None else None,
                pr_metadata=pr_metadata,
                topology_position=topology_position,
                pr_merge_sha=pr.merge_sha if pr is not None else None,
                pr_head_rewrite_edges=(pr.head_rewrite_edges if pr is not None else ()),
            )
        )
        previous_branch = layer.branch
        previous_layer_merged = layer.merged

    assert root_source is not None
    source_lineage = _validate_authenticated_lineage_sequence(
        records,
        repo=repo,
        remote=remote,
        base_branch=native_snapshot.trunk_branch,
        base_authoritative=True,
    )
    active_source = source_lineage[-1]
    return Chain(
        base_branch=native_snapshot.trunk_branch,
        source_branch=source_branch,
        source_sha=active_source.sha,
        root_source_sha=root_source.sha,
        source_lineage=source_lineage,
        changesets=tuple(records),
        native_topology=True,
    )
