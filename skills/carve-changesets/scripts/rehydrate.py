"""Reconstruct changeset topology from live git refs and GitHub PR records."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from metadata import (
    ChangesetMetadata,
    MetadataError,
    SourceIdentity,
    parse_commit_message,
    parse_pr_metadata,
)
from native_stack import NativeStackSnapshot


class RehydrationError(RuntimeError):
    """Raised when live evidence cannot identify one unambiguous chain."""


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


def _same_changeset_position(left: ChangesetMetadata, right: ChangesetMetadata) -> bool:
    same_legacy_position = (
        left.legacy_position == right.legacy_position
        if left.legacy_position is not None or right.legacy_position is not None
        else True
    )
    return (
        left.slug == right.slug
        and same_legacy_position
        and left.root_source == right.root_source
    )


def _validate_lineage_sequence(
    records: Sequence[ChangesetRecord],
) -> tuple[SourceIdentity, ...]:
    previous: tuple[SourceIdentity, ...] | None = None
    previous_merged = False
    open_lineage: tuple[SourceIdentity, ...] | None = None
    for record in records:
        lineage = record.metadata.source_lineage
        if previous is not None and lineage != previous:
            extends = (
                previous_merged
                and len(lineage) == len(previous) + 1
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


def _validate_recovery_transition(
    records: Sequence[ChangesetRecord], successor: SourceIdentity
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
    if successor in base_lineage or any(
        identity.branch == successor.branch for identity in base_lineage
    ):
        raise RehydrationError(
            "Successor source repeats an existing lineage identity or branch."
        )
    target = (*base_lineage, successor)
    _validate_lineage_sequence(records[:first_open])
    prior_lineage_seen = False
    for record in records[first_open:]:
        commit_lineage = record.metadata.source_lineage
        if commit_lineage not in (base_lineage, target):
            raise RehydrationError(
                f"Changeset branch {record.branch} has lineage outside the current "
                "or requested successor recovery."
            )
        if commit_lineage == base_lineage:
            prior_lineage_seen = True
        elif prior_lineage_seen:
            raise RehydrationError(
                "Recovered changeset heads must form a leading prefix of the open "
                "suffix; live recovery lineage is discontinuous."
            )
        if record.pr_metadata is not None:
            pr_metadata = record.pr_metadata
            if pr_metadata.source_lineage not in (base_lineage, target):
                raise RehydrationError(
                    f"PR #{record.pr_number} has lineage outside the current or "
                    "requested successor recovery."
                )
            if not _same_changeset_position(record.metadata, pr_metadata):
                raise RehydrationError(
                    f"PR #{record.pr_number} metadata changes the stable changeset "
                    "position during recovery."
                )
            if commit_lineage == base_lineage and pr_metadata != record.metadata:
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
                    pr_metadata.source_lineage == base_lineage
                    and record.metadata.recovery_from_head == record.head
                ):
                    raise RehydrationError(
                        f"Changeset branch {record.branch} does not identify a distinct "
                        "pre-recovery head."
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
                try:
                    pr_metadata = parse_pr_metadata(pr.body, remote=remote)
                except MetadataError as exc:
                    raise RehydrationError(f"PR #{pr.number}: {exc}") from exc
                if pr_metadata != metadata and recovery_successor is None:
                    raise RehydrationError(
                        f"PR #{pr.number} metadata disagrees with commit trailers for {branch}."
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
            )
        )
        prior_prs_merged = (
            prior_prs_merged and pr is not None and pr.state.upper() == "MERGED"
        )

    assert root_source is not None
    source_lineage = (
        _validate_recovery_transition(records, recovery_successor)
        if recovery_successor is not None
        else _validate_lineage_sequence(records)
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
            )
        )
        previous_branch = layer.branch
        previous_layer_merged = layer.merged

    assert root_source is not None
    source_lineage = _validate_lineage_sequence(records)
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
