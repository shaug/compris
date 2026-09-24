"""Validate a rehydrated changeset chain against live git evidence."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from common import CommandError
from metadata import SourceIdentity
from publication import remote_branch_head, remote_identity_head
from rehydrate import Chain, RehydrationError, discover_changeset_heads

Severity = Literal["error", "warning"]
SourceStatus = Literal["unchanged", "advanced", "different", "unavailable"]


@dataclass(frozen=True)
class ValidationDiagnostic:
    """One candidate-bound live invariant result."""

    code: str
    severity: Severity
    message: str


@dataclass(frozen=True)
class ChainValidation:
    """Aggregate result for one rehydrated chain."""

    source_status: SourceStatus
    stamped_source: str
    current_source: str | None
    diagnostics: tuple[ValidationDiagnostic, ...]

    @property
    def errors(self) -> tuple[ValidationDiagnostic, ...]:
        return tuple(item for item in self.diagnostics if item.severity == "error")

    @property
    def warnings(self) -> tuple[ValidationDiagnostic, ...]:
        return tuple(item for item in self.diagnostics if item.severity == "warning")

    @property
    def valid(self) -> bool:
        return not self.errors


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Git is required to validate a changeset chain.") from exc


def _resolve(cwd: Path, ref: str) -> str | None:
    result = _git(cwd, "rev-parse", "--verify", ref)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _resolve_branch(cwd: Path, branch: str, remote: str) -> str | None:
    local = _resolve(cwd, f"refs/heads/{branch}^{{commit}}")
    if local is not None:
        return local
    return _resolve(cwd, f"refs/remotes/{remote}/{branch}^{{commit}}")


def _is_ancestor(cwd: Path, ancestor: str, descendant: str) -> bool | None:
    result = _git(cwd, "merge-base", "--is-ancestor", ancestor, descendant)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


def validate_live_chain(
    chain: Chain,
    *,
    cwd: Path | str = Path.cwd(),
    remote: str = "origin",
    allow_partial_propagation: bool = False,
    verify_live_remote: bool = True,
) -> ChainValidation:
    """Check ancestry, source identity, and equivalence using only live git."""

    repo = Path(cwd)
    diagnostics: list[ValidationDiagnostic] = []
    source_status: SourceStatus = "unavailable"

    if not chain.changesets:
        diagnostics.append(
            ValidationDiagnostic(
                "empty_chain", "error", "The changeset chain has no branches."
            )
        )

    stamped_source = _resolve(repo, f"{chain.source_sha}^{{commit}}")
    if stamped_source is None:
        diagnostics.append(
            ValidationDiagnostic(
                "stamped_source_missing",
                "error",
                f"Stamped source commit {chain.source_sha} is not available in live git.",
            )
        )

    for changeset in chain.changesets:
        metadata = changeset.metadata
        if (
            metadata.root_source.branch != chain.source_branch
            or metadata.root_source.sha != chain.root_source_sha
            or chain.source_lineage[: len(metadata.source_lineage)]
            != metadata.source_lineage
        ):
            diagnostics.append(
                ValidationDiagnostic(
                    "source_stamp_mismatch",
                    "error",
                    f"Changeset branch {changeset.branch} names lineage "
                    f"{' -> '.join(item.trailer for item in metadata.source_lineage)}; "
                    "expected a continuous prefix of "
                    f"{' -> '.join(item.trailer for item in chain.source_lineage)}.",
                )
            )

    native_lineage = any(
        changeset.metadata.version == 3 for changeset in chain.changesets
    )
    durable_remote_lineage = native_lineage or len(chain.source_lineage) > 1
    live_remote_heads: dict[SourceIdentity, str | None] = {}
    if durable_remote_lineage:
        for identity in chain.source_lineage:
            if identity.remote != remote:
                diagnostics.append(
                    ValidationDiagnostic(
                        "source_lineage_remote_mismatch",
                        "error",
                        f"Immutable lineage source {identity.branch!r} records remote "
                        f"{identity.remote!r}; selected remote is {remote!r}.",
                    )
                )
                continue
            if verify_live_remote:
                try:
                    current_identity = remote_identity_head(identity, cwd=repo)
                except CommandError:
                    current_identity = None
            else:
                current_identity = _resolve(
                    repo,
                    f"refs/remotes/{identity.remote}/{identity.branch}^{{commit}}",
                )
            live_remote_heads[identity] = current_identity
            if current_identity is None:
                diagnostics.append(
                    ValidationDiagnostic(
                        "source_lineage_ref_missing",
                        "error",
                        f"Immutable lineage source {identity.branch!r} is unavailable.",
                    )
                )
            elif current_identity != identity.sha:
                diagnostics.append(
                    ValidationDiagnostic(
                        "source_lineage_ref_moved",
                        "error",
                        f"Immutable lineage source {identity.branch} moved from "
                        f"{identity.sha} to {current_identity}.",
                    )
                )

    live_heads: dict[int, tuple[str, str]] | None
    try:
        if chain.native_topology:
            live_heads = {}
            for changeset in chain.changesets:
                local = _resolve(repo, f"refs/heads/{changeset.branch}^{{commit}}")
                published = _resolve(
                    repo,
                    f"refs/remotes/{remote}/{changeset.branch}^{{commit}}",
                )
                if local is not None and published is not None and local != published:
                    raise RehydrationError(
                        f"Changeset branch {changeset.branch} is ambiguous: local "
                        f"head {local} differs from {remote} head {published}."
                    )
                head = published or local
                if head is not None:
                    live_heads[changeset.position] = (changeset.branch, head)
        else:
            live_heads = discover_changeset_heads(repo, chain.source_branch, remote)
    except RehydrationError as exc:
        live_heads = None
        diagnostics.append(
            ValidationDiagnostic(
                "changeset_ref_ambiguous",
                "error",
                f"Current changeset refs are ambiguous: {exc}",
            )
        )

    expected_indices = {item.position for item in chain.changesets}
    if live_heads is not None:
        missing_open = {
            item.position
            for item in chain.changesets
            if item.pr_state != "MERGED" and item.position not in live_heads
        }
        unexpected = (
            set(live_heads) - expected_indices if not chain.native_topology else set()
        )
        if missing_open or unexpected:
            diagnostics.append(
                ValidationDiagnostic(
                    "chain_shape_changed",
                    "error",
                    "Current open changeset branch indices differ from the rehydrated "
                    f"chain: missing open {sorted(missing_open)}, unexpected "
                    f"{sorted(unexpected)}.",
                )
            )

    if verify_live_remote:
        try:
            base_head = remote_branch_head(remote, chain.base_branch, cwd=repo)
        except CommandError as exc:
            base_head = None
            diagnostics.append(
                ValidationDiagnostic(
                    "base_ref_unavailable",
                    "error",
                    f"Current selected-remote base {remote}/{chain.base_branch} "
                    f"could not be resolved exactly: {exc}",
                )
            )
    else:
        base_head = _resolve_branch(repo, chain.base_branch, remote)
    if base_head is None:
        diagnostics.append(
            ValidationDiagnostic(
                "base_missing",
                "error",
                f"Base branch {chain.base_branch!r} is not available from "
                f"{'selected remote ' + remote if verify_live_remote else 'local git'}.",
            )
        )

    open_changeset_seen = False
    merged_changeset_seen = False
    rehydrated_heads = {item.branch: item.head for item in chain.changesets}
    for changeset in chain.changesets:
        live = live_heads.get(changeset.position) if live_heads is not None else None
        is_merged = changeset.pr_state == "MERGED"
        if live is None and not is_merged:
            diagnostics.append(
                ValidationDiagnostic(
                    "changeset_ref_missing",
                    "error",
                    f"Changeset branch {changeset.branch} is not available in live git.",
                )
            )
            head = None
        elif live is None:
            head = changeset.head
        else:
            live_branch, head = live
            if live_branch != changeset.branch or head != changeset.head:
                diagnostics.append(
                    ValidationDiagnostic(
                        "changeset_ref_moved",
                        "error",
                        f"Changeset branch {changeset.branch} moved from rehydrated head "
                        f"{changeset.head} to current head {head}.",
                    )
                )

        if is_merged and open_changeset_seen:
            diagnostics.append(
                ValidationDiagnostic(
                    "merge_sequence_broken",
                    "error",
                    f"Changeset branch {changeset.branch} is merged after an unmerged "
                    "changeset; merges must remain a leading sequence.",
                )
            )
        if not is_merged:
            open_changeset_seen = True
        else:
            merged_changeset_seen = True

        if is_merged and base_head is not None:
            merged_result = _resolve(
                repo, f"{changeset.merge_sha or changeset.head}^{{commit}}"
            )
            represented = (
                _is_ancestor(repo, merged_result, base_head)
                if merged_result is not None
                else None
            )
            if represented is not True:
                diagnostics.append(
                    ValidationDiagnostic(
                        "merged_prefix_missing_from_base",
                        "error",
                        f"Merged changeset branch {changeset.branch} is not "
                        f"represented on current base {chain.base_branch} at "
                        f"{base_head}.",
                    )
                )

        predecessor_name = changeset.base
        predecessor = _resolve_branch(repo, predecessor_name, remote)
        if predecessor is None:
            predecessor = rehydrated_heads.get(predecessor_name)
        if not is_merged and predecessor is None:
            diagnostics.append(
                ValidationDiagnostic(
                    "predecessor_missing",
                    "error",
                    f"Predecessor {predecessor_name!r} for {changeset.branch} is not "
                    "available in live git.",
                )
            )
        if not is_merged and head is not None and predecessor is not None:
            ancestry = _is_ancestor(repo, predecessor, head)
            if (
                ancestry is False
                and allow_partial_propagation
                and merged_changeset_seen
            ):
                diagnostics.append(
                    ValidationDiagnostic(
                        "partial_propagation_frontier",
                        "warning",
                        f"Changeset branch {changeset.branch} is still based on its "
                        "pre-propagation predecessor; propagation must validate and "
                        "advance this live frontier.",
                    )
                )
            elif ancestry is False:
                diagnostics.append(
                    ValidationDiagnostic(
                        "predecessor_ancestry_broken",
                        "error",
                        f"Changeset branch {changeset.branch} at {head} is not a "
                        f"descendant of predecessor {predecessor_name} at {predecessor}.",
                    )
                )
            elif ancestry is None:
                diagnostics.append(
                    ValidationDiagnostic(
                        "ancestry_check_failed",
                        "error",
                        f"Git could not compare predecessor {predecessor_name} at "
                        f"{predecessor} with {changeset.branch} at {head}.",
                    )
                )

    if stamped_source is not None and chain.changesets and live_heads is not None:
        open_suffix = tuple(
            item for item in chain.changesets if item.pr_state != "MERGED"
        )
        tip_record = open_suffix[-1] if open_suffix else chain.changesets[-1]
        if open_suffix:
            live_tip = live_heads.get(tip_record.position)
            tip = live_tip[1] if live_tip is not None else None
        else:
            tip = base_head
        source_tree = _resolve(repo, f"{stamped_source}^{{tree}}")
        tip_tree = _resolve(repo, f"{tip}^{{tree}}") if tip is not None else None
        if source_tree is None or tip_tree is None:
            diagnostics.append(
                ValidationDiagnostic(
                    "equivalence_check_failed",
                    "error",
                    "Git could not resolve both trees required for source equivalence.",
                )
            )
        elif source_tree != tip_tree:
            diagnostics.append(
                ValidationDiagnostic(
                    "source_equivalence_mismatch",
                    "error",
                    f"Changeset tip {tip_record.branch} at {tip} does not "
                    f"recompose to active source {chain.active_source.branch} at "
                    f"{stamped_source}.",
                )
            )

    current_source = (
        live_remote_heads.get(chain.active_source)
        if durable_remote_lineage
        else _resolve_branch(repo, chain.active_source.branch, remote)
    )
    if current_source is None:
        diagnostics.append(
            ValidationDiagnostic(
                "source_branch_missing",
                "error",
                f"Source branch {chain.active_source.branch!r} is not available in live git.",
            )
        )
    elif stamped_source is not None and current_source == stamped_source:
        source_status = "unchanged"
    elif stamped_source is not None:
        advanced = _is_ancestor(repo, stamped_source, current_source)
        if durable_remote_lineage:
            source_status = "different"
        elif advanced is True:
            source_status = "advanced"
            diagnostics.append(
                ValidationDiagnostic(
                    "source_advanced",
                    "warning",
                    f"Source branch {chain.active_source.branch} legitimately advanced from "
                    f"stamped commit {stamped_source} to {current_source}; the chain "
                    "remains validated against the stamped source.",
                )
            )
        elif advanced is False:
            source_status = "different"
            diagnostics.append(
                ValidationDiagnostic(
                    "source_history_mismatch",
                    "error",
                    f"Source branch {chain.active_source.branch} at {current_source} does not "
                    f"descend from stamped commit {stamped_source}; the chain was built "
                    "against a different source history.",
                )
            )
        else:
            source_status = "unavailable"
            diagnostics.append(
                ValidationDiagnostic(
                    "source_ancestry_check_failed",
                    "error",
                    f"Git could not compare stamped source {stamped_source} with "
                    f"current source {current_source}; source history is unavailable.",
                )
            )

    return ChainValidation(
        source_status=source_status,
        stamped_source=chain.source_sha,
        current_source=current_source,
        diagnostics=tuple(diagnostics),
    )
