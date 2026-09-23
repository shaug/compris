"""Typed decoding and cross-source reconciliation for native GitHub stacks."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
PULL_REQUEST_STATES = frozenset({"OPEN", "CLOSED", "MERGED"})
TOP_LEVEL_KEYS = frozenset({"trunk", "currentBranch", "branches"})
LAYER_KEYS = frozenset(
    {
        "name",
        "head",
        "base",
        "isCurrent",
        "isMerged",
        "isQueued",
        "needsRebase",
        "pr",
    }
)
PULL_REQUEST_KEYS = frozenset({"number", "url", "state"})


class NativeStackError(RuntimeError):
    """Native, remote, and GitHub stack evidence cannot be reconciled."""


class TerminalState(str, Enum):
    PLAN_READY = "plan_ready"
    CHAIN_READY = "chain_ready"
    PRS_OPEN = "prs_open"
    ALL_MERGED = "all_merged"
    BLOCKED = "blocked"


class TruthPhase(str, Enum):
    PROPOSED = "proposed"
    MATERIALIZED = "materialized"
    PUBLISHED = "published"
    MERGED = "merged"


@dataclass(frozen=True)
class NativePullRequest:
    number: int
    url: str
    state: str


@dataclass(frozen=True)
class NativeLayer:
    branch: str
    head: str
    base: str
    merged: bool
    queued: bool
    needs_rebase: bool
    pull_request: NativePullRequest | None


@dataclass(frozen=True)
class NativeStackSnapshot:
    trunk_branch: str
    trunk_head: str
    current_branch: str
    layers: tuple[NativeLayer, ...]

    @property
    def open_suffix(self) -> tuple[NativeLayer, ...]:
        return tuple(layer for layer in self.layers if not layer.merged)


class PullRequestRecord(Protocol):
    number: int
    head_branch: str
    head_sha: str
    base_branch: str
    state: str


def _exact_keys(
    value: Mapping[str, object], expected: frozenset[str], context: str
) -> None:
    actual = frozenset(value)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    details: list[str] = []
    if missing:
        details.append("missing " + ", ".join(missing))
    if unknown:
        details.append("unknown " + ", ".join(unknown))
    raise NativeStackError(f"{context} has invalid fields: {'; '.join(details)}")


def _string(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NativeStackError(f"{context} must be a non-empty string")
    return value


def _sha(value: object, context: str) -> str:
    sha = _string(value, context)
    if not FULL_SHA.fullmatch(sha):
        raise NativeStackError(f"{context} must be a full SHA")
    return sha


def _boolean(value: object, context: str) -> bool:
    if not isinstance(value, bool):
        raise NativeStackError(f"{context} must be a boolean")
    return value


def _pull_request(value: object, branch: str) -> NativePullRequest | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise NativeStackError(f"layer {branch} PR must be an object or null")
    _exact_keys(value, PULL_REQUEST_KEYS, f"layer {branch} PR")
    number = value["number"]
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise NativeStackError(f"layer {branch} PR number must be a positive integer")
    url = _string(value["url"], f"layer {branch} PR URL")
    state = _string(value["state"], f"layer {branch} PR state").upper()
    if state not in PULL_REQUEST_STATES:
        raise NativeStackError(f"layer {branch} has unknown PR state {state}")
    return NativePullRequest(number=number, url=url, state=state)


def parse_native_stack(
    payload: Mapping[str, object], *, trunk_head: str
) -> NativeStackSnapshot:
    """Decode the reviewed ``gh stack view --json`` schema without coercion."""

    if not isinstance(payload, dict):
        raise NativeStackError("gh stack view --json must be an object")
    _exact_keys(payload, TOP_LEVEL_KEYS, "gh stack view")
    trunk_branch = _string(payload["trunk"], "native trunk")
    current_branch = _string(payload["currentBranch"], "native current branch")
    checked_trunk_head = _sha(trunk_head, "native trunk head")
    branches = payload["branches"]
    if not isinstance(branches, list):
        raise NativeStackError("native branches must be an array")

    layers: list[NativeLayer] = []
    seen_branches: set[str] = set()
    seen_pull_requests: set[int] = set()
    current_layers: list[str] = []
    predecessor: str | None = None
    first_open_branch: str | None = None
    for offset, item in enumerate(branches):
        if not isinstance(item, dict):
            raise NativeStackError(f"native layer {offset + 1} must be an object")
        _exact_keys(item, LAYER_KEYS, f"native layer {offset + 1}")
        branch = _string(item["name"], f"native layer {offset + 1} branch")
        if branch in seen_branches:
            raise NativeStackError(f"native stack has duplicate branch {branch}")
        seen_branches.add(branch)
        head = _sha(item["head"], f"layer {branch} head")
        base = _sha(item["base"], f"layer {branch} base")
        is_current = _boolean(item["isCurrent"], f"layer {branch} isCurrent")
        if is_current:
            current_layers.append(branch)
        pull_request = _pull_request(item["pr"], branch)
        if pull_request is not None:
            if pull_request.number in seen_pull_requests:
                raise NativeStackError(
                    f"native stack has duplicate PR #{pull_request.number}"
                )
            seen_pull_requests.add(pull_request.number)
        merged = _boolean(item["isMerged"], f"layer {branch} isMerged")
        if pull_request is not None and merged != (pull_request.state == "MERGED"):
            raise NativeStackError(
                f"layer {branch} merged flag {merged} disagrees with PR state "
                f"{pull_request.state}"
            )
        if merged and first_open_branch is not None:
            raise NativeStackError(
                f"layer {branch} is merged, but a merged layer follows open layer "
                f"{first_open_branch}"
            )
        if not merged and first_open_branch is None:
            first_open_branch = branch
        expected_base = None if merged else predecessor
        label = "predecessor head"
        if first_open_branch == branch:
            expected_base = checked_trunk_head
            label = "trunk head"
        if expected_base is not None and base != expected_base:
            raise NativeStackError(
                f"layer {branch} base {base} does not match expected {label} {expected_base}"
            )
        layers.append(
            NativeLayer(
                branch=branch,
                head=head,
                base=base,
                merged=merged,
                queued=_boolean(item["isQueued"], f"layer {branch} isQueued"),
                needs_rebase=_boolean(
                    item["needsRebase"], f"layer {branch} needsRebase"
                ),
                pull_request=pull_request,
            )
        )
        predecessor = head

    if layers:
        if len(current_layers) != 1:
            raise NativeStackError(
                "native stack must identify exactly one current layer"
            )
        if current_layers[0] != current_branch:
            raise NativeStackError(
                f"native current branch {current_branch} disagrees with current layer {current_layers[0]}"
            )
    elif current_branch != trunk_branch:
        raise NativeStackError(
            "an empty native stack must identify the trunk as the current branch"
        )

    return NativeStackSnapshot(
        trunk_branch=trunk_branch,
        trunk_head=checked_trunk_head,
        current_branch=current_branch,
        layers=tuple(layers),
    )


def reconcile_native_stack(
    snapshot: NativeStackSnapshot,
    *,
    remote_heads: Mapping[str, str],
    pull_requests: Mapping[int, PullRequestRecord],
    local_heads: Mapping[str, str] | None = None,
) -> NativeStackSnapshot:
    """Fail closed unless native, remote, and live GitHub evidence agree."""

    previous_branch = snapshot.trunk_branch
    previous_merged = True
    available_local_heads = local_heads or {}
    for layer in snapshot.layers:
        native_pr = layer.pull_request
        if native_pr is None or layer.branch in available_local_heads:
            local_head = available_local_heads.get(layer.branch)
            if local_head != layer.head:
                shown_local = local_head if local_head is not None else "missing"
                raise NativeStackError(
                    f"layer {layer.branch} local head mismatch: native {layer.head}; "
                    f"local {shown_local}"
                )
        if native_pr is not None and not layer.merged:
            remote_head = remote_heads.get(layer.branch)
            if remote_head != layer.head:
                shown_remote = remote_head if remote_head is not None else "missing"
                raise NativeStackError(
                    f"layer {layer.branch} remote head mismatch: native {layer.head}; "
                    f"remote {shown_remote}"
                )
        if native_pr is None:
            previous_branch = layer.branch
            previous_merged = layer.merged
            continue
        live = pull_requests.get(native_pr.number)
        if live is None:
            raise NativeStackError(
                f"layer {layer.branch} is missing GitHub PR #{native_pr.number}"
            )
        if live.head_branch != layer.branch:
            raise NativeStackError(
                f"layer {layer.branch} GitHub PR #{live.number} head branch mismatch: "
                f"native {layer.branch}; GitHub {live.head_branch}"
            )
        if live.head_sha != layer.head:
            raise NativeStackError(
                f"layer {layer.branch} GitHub PR #{live.number} head mismatch: "
                f"native {layer.head}; GitHub {live.head_sha}"
            )
        expected_bases = {previous_branch}
        if previous_merged:
            expected_bases.add(snapshot.trunk_branch)
        if live.base_branch not in expected_bases:
            expected_base = (
                snapshot.trunk_branch if previous_merged else previous_branch
            )
            relation = (
                "trunk" if expected_base == snapshot.trunk_branch else "predecessor"
            )
            raise NativeStackError(
                f"layer {layer.branch} GitHub PR #{live.number} base mismatch: "
                f"native {relation} {expected_base}; GitHub {live.base_branch}"
            )
        live_state = live.state.upper()
        if live_state != native_pr.state:
            raise NativeStackError(
                f"layer {layer.branch} GitHub PR #{live.number} state mismatch: "
                f"native {native_pr.state}; GitHub {live_state}"
            )
        previous_branch = layer.branch
        previous_merged = layer.merged
    return snapshot


def classify_truth_phase(
    *,
    plan_validated: bool,
    snapshot: NativeStackSnapshot | None,
    reconciled: bool,
) -> TruthPhase:
    """Classify evidence strength independently of workflow terminal readiness."""

    if not plan_validated:
        raise NativeStackError("truth phase requires a validated plan")
    if snapshot is None or not snapshot.layers:
        return TruthPhase.PROPOSED
    if not reconciled or any(layer.pull_request is None for layer in snapshot.layers):
        return TruthPhase.MATERIALIZED
    if snapshot.open_suffix:
        return TruthPhase.PUBLISHED
    if all(
        layer.merged
        and layer.pull_request is not None
        and layer.pull_request.state == "MERGED"
        for layer in snapshot.layers
    ):
        return TruthPhase.MERGED
    raise NativeStackError(
        "reconciled native stack has no open suffix but is not verified merged"
    )
