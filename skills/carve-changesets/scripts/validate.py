"""Validate a rehydrated changeset chain against live git evidence."""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

from common import CommandError
from metadata import SourceIdentity
from native_stack import NativeStackSnapshot
from publication import remote_branch_head, remote_identity_head
from rehydrate import (
    Chain,
    PullRequestRecord,
    RehydrationError,
    discover_changeset_heads,
)

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


@dataclass(frozen=True)
class LiveEquivalence:
    """Result of replaying the open native suffix onto exact remote trunk."""

    valid: bool
    code: str
    merged_prefix: tuple[int, ...]
    open_suffix: tuple[int, ...]
    reconstructed_tree: str | None
    source_tree: str | None
    trunk_head: str
    open_heads: tuple[tuple[str, str], ...]
    active_source: SourceIdentity
    topology: NativeStackSnapshot


def validate_live_equivalence(
    *,
    snapshot: NativeStackSnapshot,
    active_source: SourceIdentity,
    merged_prs: Mapping[int, PullRequestRecord] | None = None,
    historical_prs: tuple[int, ...] = (),
    cwd: Path | str | None = None,
) -> LiveEquivalence:
    """Reconstruct a native suffix without touching the caller's checkout.

    After native synchronization removes every layer, historical_prs names the
    ordered established chain whose live merged_prs readback proves its landings.
    """

    repo = Path.cwd() if cwd is None else Path(cwd)
    merged = historical_prs or tuple(
        layer.pull_request.number if layer.pull_request else index
        for index, layer in enumerate(snapshot.layers, 1)
        if layer.merged
    )
    opened = tuple(
        layer.pull_request.number if layer.pull_request else index
        for index, layer in enumerate(snapshot.layers, 1)
        if not layer.merged
    )

    def result(
        code: str, reconstructed: str | None = None, source: str | None = None
    ) -> LiveEquivalence:
        return LiveEquivalence(
            valid=code == "equivalent",
            code=code,
            merged_prefix=merged,
            open_suffix=opened,
            reconstructed_tree=reconstructed,
            source_tree=source,
            trunk_head=snapshot.trunk_head,
            open_heads=tuple(
                (layer.branch, layer.head) for layer in snapshot.open_suffix
            ),
            active_source=active_source,
            topology=snapshot,
        )

    try:
        trunk = remote_branch_head(
            active_source.remote, snapshot.trunk_branch, cwd=repo
        )
    except CommandError:
        return result("remote_trunk_unavailable")
    if trunk is None:
        return result("remote_trunk_unavailable")
    if trunk != snapshot.trunk_head:
        return result("remote_trunk_moved")
    try:
        published_source = remote_identity_head(active_source, cwd=repo)
    except CommandError:
        return result("successor_source_not_remote")
    if published_source != active_source.sha:
        return result("source_ref_moved")
    source_tree = _resolve(repo, f"{active_source.sha}^{{tree}}")
    if source_tree is None:
        return result("source_commit_unavailable")
    if _resolve(repo, f"{trunk}^{{commit}}") is None:
        return result("remote_trunk_commit_unavailable", source=source_tree)
    merged_readback = merged_prs or {}
    if (
        (historical_prs and snapshot.layers)
        or len(set(merged)) != len(merged)
        or any(number < 1 for number in merged)
        or set(merged_readback) != set(merged)
    ):
        return result("merged_prefix_unavailable", source=source_tree)
    open_seen = False
    predecessor = trunk
    for layer in snapshot.layers:
        if layer.merged:
            if open_seen:
                return result("native_topology_changed", source=source_tree)
        else:
            open_seen = True
            if layer.base != predecessor:
                return result("native_topology_changed", source=source_tree)
            predecessor = layer.head

    ref = f"refs/carve-changesets/equivalence/{uuid4().hex}"
    created = False
    current = trunk
    reconstructed: str | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="carve-equivalence-") as temporary:
            environment = os.environ.copy()
            environment["GIT_INDEX_FILE"] = str(Path(temporary) / "index")
            environment["GIT_AUTHOR_NAME"] = "Carve equivalence"
            environment["GIT_AUTHOR_EMAIL"] = "carve-equivalence@invalid.local"
            environment["GIT_COMMITTER_NAME"] = "Carve equivalence"
            environment["GIT_COMMITTER_EMAIL"] = "carve-equivalence@invalid.local"

            def run(
                *args: str, input_bytes: bytes | None = None
            ) -> subprocess.CompletedProcess[bytes]:
                return subprocess.run(
                    ["git", *args],
                    cwd=repo,
                    env=environment,
                    input=input_bytes,
                    capture_output=True,
                    check=False,
                )

            if run("read-tree", trunk).returncode != 0:
                return result("reconstruction_failed", source=source_tree)
            if run("update-ref", ref, trunk, "0" * 40).returncode != 0:
                return result("reconstruction_failed", source=source_tree)
            created = True
            prior_landing: str | None = None
            for index, number in enumerate(merged):
                layer = snapshot.layers[index] if snapshot.layers else None
                live_pr = merged_readback.get(number)
                if (
                    live_pr is None
                    or live_pr.number != number
                    or live_pr.state != "MERGED"
                    or live_pr.is_cross_repository
                    or live_pr.merge_sha is None
                    or _resolve(repo, f"{live_pr.head_sha}^{{commit}}") is None
                    or (
                        layer is not None
                        and (
                            layer.pull_request is None
                            or layer.pull_request.state != "MERGED"
                            or live_pr.head_branch != layer.branch
                            or live_pr.head_sha != layer.head
                        )
                    )
                ):
                    return result("merged_prefix_unavailable", source=source_tree)
                landing = live_pr.merge_sha
                if (
                    _resolve(repo, f"{landing}^{{commit}}") is None
                    or _is_ancestor(repo, landing, trunk) is not True
                    or (
                        prior_landing is not None
                        and _is_ancestor(repo, prior_landing, landing) is not True
                    )
                ):
                    return result(
                        "merged_prefix_missing_from_trunk", source=source_tree
                    )
                prior_landing = landing
            for layer in snapshot.open_suffix:
                if (
                    _resolve(repo, f"{layer.base}^{{commit}}") is None
                    or _resolve(repo, f"{layer.head}^{{commit}}") is None
                ):
                    return result("open_layer_unavailable", source=source_tree)
                ancestry = _is_ancestor(repo, layer.base, layer.head)
                if ancestry is False:
                    return result("predecessor_ancestry_broken", source=source_tree)
                if ancestry is None:
                    return result("ancestry_check_failed", source=source_tree)
                patch = run(
                    "diff",
                    "--binary",
                    "--full-index",
                    "--no-ext-diff",
                    "--no-textconv",
                    "--no-color",
                    "--src-prefix=a/",
                    "--dst-prefix=b/",
                    "--unified=3",
                    "--submodule=short",
                    "--ignore-submodules=none",
                    layer.base,
                    layer.head,
                    "--",
                )
                if patch.returncode != 0:
                    return result("reconstruction_failed", source=source_tree)
                if (
                    patch.stdout
                    and run(
                        "apply",
                        "--cached",
                        "--binary",
                        "--whitespace=nowarn",
                        "-",
                        input_bytes=patch.stdout,
                    ).returncode
                    != 0
                ):
                    return result("reconstruction_conflict", source=source_tree)
                tree = run("write-tree")
                if tree.returncode != 0:
                    return result("reconstruction_failed", source=source_tree)
                synthetic = run(
                    "commit-tree",
                    tree.stdout.strip().decode("ascii"),
                    "-p",
                    current,
                    input_bytes=b"replay open native layer\n",
                )
                if synthetic.returncode != 0:
                    return result("reconstruction_failed", source=source_tree)
                successor = synthetic.stdout.strip().decode("ascii")
                if run("update-ref", ref, successor, current).returncode != 0:
                    return result("reconstruction_failed", source=source_tree)
                current = successor
            reconstructed = _resolve(repo, f"{current}^{{tree}}")
    finally:
        if created:
            cleanup = _git(repo, "update-ref", "-d", ref, current)
            if cleanup.returncode != 0:
                raise RuntimeError(
                    f"Could not remove disposable equivalence ref {ref}."
                )

    if reconstructed is None:
        return result("reconstruction_failed", source=source_tree)
    return result(
        "equivalent" if reconstructed == source_tree else "source_equivalence_mismatch",
        reconstructed,
        source_tree,
    )


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
                repo, f"{changeset.pr_merge_sha or changeset.head}^{{commit}}"
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
        if predecessor_name == chain.base_branch:
            predecessor = base_head
        else:
            predecessor = next(
                (
                    live_head
                    for live_branch, live_head in (live_heads or {}).values()
                    if live_branch == predecessor_name
                ),
                None,
            )
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
