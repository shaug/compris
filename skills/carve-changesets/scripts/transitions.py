#!/usr/bin/env python3
"""Operation-scoped manifests and readback for native-stack remote effects."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum

from gh_stack import GhStackProfile, StackCapability

ZERO_SHA = "0" * 40


class ManifestError(ValueError):
    """A mutation manifest is incomplete, ambiguous, or under-authorized."""


class StackOperation(str, Enum):
    PUBLISH = "publish"
    REPAIR = "repair"
    MERGE = "merge"
    RECOVER = "recover"


class TransitionPhase(str, Enum):
    PUSH = "push"
    SUBMIT = "submit"
    REBASE_NO_TRUNK = "rebase_no_trunk"
    SYNC = "sync"
    DIRECT_MERGE = "direct_merge"
    QUEUE_MERGE = "queue_merge"
    TRUNK_REFRESH = "trunk_refresh"


class MergeMode(str, Enum):
    DIRECT = "direct"
    QUEUE = "queue"


class EffectKind(str, Enum):
    PUSH_REF = "push_ref"
    CREATE_PR = "create_pr"
    UPDATE_PR = "update_pr"
    DISABLE_AUTO_MERGE = "disable_auto_merge"
    REGISTER_STACK = "register_stack"
    REBASE_BRANCH = "rebase_branch"
    SYNC_STACK = "sync_stack"
    REFRESH_TRUNK = "refresh_trunk"
    MERGE_PR = "merge_pr"
    QUEUE_PR = "queue_pr"


class TargetDisposition(str, Enum):
    CHANGED_AS_EXPECTED = "changed_as_expected"
    UNCHANGED = "unchanged"
    CHANGED_UNEXPECTEDLY = "changed_unexpectedly"


class TransitionState(str, Enum):
    COMPLETED = "completed"
    UNCHANGED = "unchanged"
    PARTIAL = "partial"
    DIVERGED = "diverged"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ExpectedRef:
    name: str
    old_sha: str
    proposed_sha: str

    def validate(self) -> None:
        if not self.name.startswith("refs/heads/"):
            raise ManifestError(f"expected ref is not a full branch ref: {self.name!r}")
        for label, sha in (("old", self.old_sha), ("proposed", self.proposed_sha)):
            if len(sha) != 40 or any(
                character not in "0123456789abcdef" for character in sha
            ):
                raise ManifestError(
                    f"{self.name} {label} SHA must be 40 lowercase hex characters"
                )


@dataclass(frozen=True)
class ExpectedPullRequest:
    number: int | None
    branch: str
    head: str | None
    base: str | None
    state: str
    draft: bool | None
    queued: bool | None
    auto_merge: bool | None
    title: str
    body: str
    current_title: str | None = None
    current_body: str | None = None

    def validate(self) -> None:
        if not self.branch.strip():
            raise ManifestError("expected pull request branch must be non-empty")
        if self.state == "ABSENT":
            if self.number is not None or any(
                value is not None
                for value in (
                    self.head,
                    self.base,
                    self.draft,
                    self.queued,
                    self.auto_merge,
                )
            ):
                raise ManifestError(
                    f"expected-absent pull request for {self.branch} carries live state"
                )
        else:
            if self.state not in {"OPEN", "CLOSED", "MERGED"}:
                raise ManifestError(
                    f"pull request for {self.branch} has unknown state {self.state!r}"
                )
            if (
                not isinstance(self.number, int)
                or isinstance(self.number, bool)
                or self.number < 1
            ):
                raise ManifestError(
                    f"pull request for {self.branch} needs a positive identity"
                )
            if self.head is None or self.base is None:
                raise ManifestError(
                    f"pull request #{self.number} needs exact head and base"
                )
            if len(self.head) != 40 or any(
                character not in "0123456789abcdef" for character in self.head
            ):
                raise ManifestError(
                    f"pull request #{self.number} head must be a full SHA"
                )
            if not isinstance(self.base, str) or not self.base.strip():
                raise ManifestError(
                    f"pull request #{self.number} base must be non-empty"
                )
            for label, value in (
                ("draft", self.draft),
                ("queued", self.queued),
                ("auto-merge", self.auto_merge),
            ):
                if not isinstance(value, bool):
                    raise ManifestError(
                        f"pull request #{self.number} {label} state must be boolean"
                    )
            if any(
                value is None for value in (self.draft, self.queued, self.auto_merge)
            ):
                raise ManifestError(
                    f"pull request #{self.number} needs draft, queue, and auto-merge state"
                )
        if not isinstance(self.title, str) or not self.title.strip():
            raise ManifestError(
                f"pull request for {self.branch} needs an explicit title"
            )
        if not isinstance(self.body, str) or not self.body.strip():
            raise ManifestError(
                f"pull request for {self.branch} needs an explicit pull-request body"
            )
        for label, value in (
            ("current title", self.current_title),
            ("current body", self.current_body),
        ):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ManifestError(
                    f"pull request for {self.branch} {label} must be non-empty"
                )

    @property
    def record(self) -> tuple[object, ...]:
        return (
            self.number,
            self.branch,
            self.head,
            self.base,
            self.state,
            self.draft,
            self.queued,
            self.auto_merge,
            self.current_title if self.current_title is not None else self.title,
            self.current_body if self.current_body is not None else self.body,
        )

    def proposed_record(
        self, *, expected_head: str, expected_base: str
    ) -> tuple[object, ...]:
        return (
            self.number,
            self.branch,
            expected_head,
            expected_base,
            "OPEN",
            False if self.draft is None else self.draft,
            False,
            False,
            self.title,
            self.body,
        )


@dataclass(frozen=True)
class ExpectedNativeStack:
    identity: str | None
    trunk: str
    trunk_head: str
    order: tuple[str, ...]

    def validate(self) -> None:
        if self.identity is not None and (
            not isinstance(self.identity, str) or not self.identity.strip()
        ):
            raise ManifestError("expected native stack identity must be non-empty")
        if not self.trunk.strip():
            raise ManifestError("expected native stack trunk must be non-empty")
        if len(self.trunk_head) != 40 or any(
            character not in "0123456789abcdef" for character in self.trunk_head
        ):
            raise ManifestError("expected native stack trunk head must be a full SHA")
        if not self.order or any(not branch.strip() for branch in self.order):
            raise ManifestError("expected native stack order must name every layer")
        if len(set(self.order)) != len(self.order):
            raise ManifestError("expected native stack order contains duplicates")


@dataclass(frozen=True)
class MutationEffect:
    kind: EffectKind
    target: str
    field: str
    before: object
    after: object

    @property
    def key(self) -> str:
        return f"{self.target}:{self.field}"


@dataclass(frozen=True)
class AuthorityGrant:
    operation: StackOperation
    repository: str
    remote: str
    identities: tuple[str, ...]
    branches: tuple[str, ...]
    phases: frozenset[TransitionPhase]
    effect_kinds: frozenset[EffectKind]

    @classmethod
    def publish(
        cls,
        *,
        repository: str,
        remote: str,
        branches: Sequence[str],
    ) -> AuthorityGrant:
        selected = tuple(branches)
        return cls(
            operation=StackOperation.PUBLISH,
            repository=repository,
            remote=remote,
            identities=selected,
            branches=selected,
            phases=frozenset({TransitionPhase.PUSH, TransitionPhase.SUBMIT}),
            effect_kinds=frozenset(
                {
                    EffectKind.PUSH_REF,
                    EffectKind.CREATE_PR,
                    EffectKind.UPDATE_PR,
                    EffectKind.DISABLE_AUTO_MERGE,
                    EffectKind.REGISTER_STACK,
                }
            ),
        )


@dataclass(frozen=True)
class MutationManifest:
    operation: StackOperation
    repository: str
    remote: str
    identities: tuple[str, ...]
    expected_refs: tuple[ExpectedRef, ...]
    expected_pull_requests: tuple[ExpectedPullRequest, ...]
    expected_native_stack: ExpectedNativeStack
    enabled_phases: tuple[TransitionPhase, ...]
    merge_mode: MergeMode | None
    effects: tuple[MutationEffect, ...]
    evidence: tuple[str, ...]
    authority: AuthorityGrant
    merge_prefix: tuple[int, ...] = ()

    def validate_complete(self) -> None:
        if not self.repository.strip() or "/" not in self.repository:
            raise ManifestError("manifest repository must be an owner/name identity")
        if not self.remote.strip():
            raise ManifestError("manifest remote must be non-empty")
        if not self.identities or any(
            not identity.strip() for identity in self.identities
        ):
            raise ManifestError("manifest must bind every selected identity")
        if not self.enabled_phases or len(set(self.enabled_phases)) != len(
            self.enabled_phases
        ):
            raise ManifestError("manifest enabled phases must be non-empty and unique")
        if not self.effects:
            raise ManifestError("manifest must enumerate its effects")
        if not self.evidence or any(not item.strip() for item in self.evidence):
            raise ManifestError("manifest must cite its snapshot evidence")
        for expected_ref in self.expected_refs:
            expected_ref.validate()
        for pull_request in self.expected_pull_requests:
            pull_request.validate()
        ref_names = tuple(item.name for item in self.expected_refs)
        if len(set(ref_names)) != len(ref_names):
            raise ManifestError("manifest contains duplicate expected refs")
        pr_branches = tuple(item.branch for item in self.expected_pull_requests)
        if len(set(pr_branches)) != len(pr_branches):
            raise ManifestError("manifest contains duplicate pull-request branches")
        pr_numbers = tuple(
            item.number
            for item in self.expected_pull_requests
            if item.number is not None
        )
        if len(set(pr_numbers)) != len(pr_numbers):
            raise ManifestError("manifest contains duplicate pull-request identities")
        self.expected_native_stack.validate()
        keys = tuple(effect.key for effect in self.effects)
        if len(set(keys)) != len(keys):
            raise ManifestError("manifest has duplicate target-field effects")
        effect_signatures = {
            (effect.kind, effect.target, effect.field) for effect in self.effects
        }
        ref_by_branch = {
            item.name.removeprefix("refs/heads/"): item for item in self.expected_refs
        }
        selected_branches = set(ref_by_branch) | {
            item.branch for item in self.expected_pull_requests
        }
        if selected_branches - set(self.expected_native_stack.order):
            raise ManifestError(
                "manifest selected branches are outside expected native stack order"
            )

        required_effects: set[tuple[EffectKind, str, str]] = set()
        if TransitionPhase.PUSH in self.enabled_phases:
            required_effects.update(
                (EffectKind.PUSH_REF, f"ref:{branch}", "sha")
                for branch in ref_by_branch
            )
        if TransitionPhase.SUBMIT in self.enabled_phases:
            for pull_request in self.expected_pull_requests:
                identity = (
                    str(pull_request.number)
                    if pull_request.number is not None
                    else pull_request.branch
                )
                required_effects.add(
                    (
                        EffectKind.CREATE_PR
                        if pull_request.state == "ABSENT"
                        else EffectKind.UPDATE_PR,
                        f"pr:{identity}",
                        "record",
                    )
                )
                if pull_request.auto_merge is True:
                    required_effects.add(
                        (
                            EffectKind.DISABLE_AUTO_MERGE,
                            f"pr:{pull_request.number}",
                            "auto_merge",
                        )
                    )
            required_effects.add(
                (
                    EffectKind.REGISTER_STACK,
                    f"stack:{self.expected_native_stack.identity or 'absent'}",
                    "order",
                )
            )
        if TransitionPhase.REBASE_NO_TRUNK in self.enabled_phases:
            required_effects.update(
                (EffectKind.REBASE_BRANCH, f"local:{branch}", "sha")
                for branch in ref_by_branch
            )
        if TransitionPhase.SYNC in self.enabled_phases and not any(
            effect.kind is EffectKind.SYNC_STACK for effect in self.effects
        ):
            raise ManifestError("manifest is missing required effect sync_stack")
        if TransitionPhase.TRUNK_REFRESH in self.enabled_phases:
            required_effects.add(
                (
                    EffectKind.REFRESH_TRUNK,
                    f"ref:{self.expected_native_stack.trunk}",
                    "sha",
                )
            )
        if TransitionPhase.DIRECT_MERGE in self.enabled_phases:
            required_effects.update(
                (EffectKind.MERGE_PR, f"pr:{number}", "state")
                for number in self.merge_prefix
            )
        if TransitionPhase.QUEUE_MERGE in self.enabled_phases:
            bottom = self.merge_prefix[0] if self.merge_prefix else None
            if bottom is not None:
                required_effects.update(
                    {
                        (EffectKind.QUEUE_PR, f"pr:{bottom}", "queued"),
                        (EffectKind.MERGE_PR, f"pr:{bottom}", "state"),
                    }
                )
        missing_required_effects = required_effects - effect_signatures
        if missing_required_effects:
            details = ", ".join(
                f"{kind.value}:{target}:{field}"
                for kind, target, field in sorted(
                    missing_required_effects,
                    key=lambda item: (item[0].value, item[1], item[2]),
                )
            )
            raise ManifestError(f"manifest is missing required effect: {details}")
        if self.operation is StackOperation.MERGE and self.merge_mode is None:
            raise ManifestError("merge manifests must select direct or queue mode")
        if self.operation is StackOperation.MERGE and not self.merge_prefix:
            raise ManifestError("merge manifests must bind a non-empty PR prefix")
        if self.operation is StackOperation.MERGE:
            if len(set(self.merge_prefix)) != len(self.merge_prefix) or any(
                not isinstance(number, int) or isinstance(number, bool) or number < 1
                for number in self.merge_prefix
            ):
                raise ManifestError(
                    "merge prefix must contain unique positive PR numbers"
                )
            ordered_open = tuple(
                item.number
                for item in self.expected_pull_requests
                if item.state == "OPEN" and item.number is not None
            )
            if self.merge_prefix != ordered_open[: len(self.merge_prefix)]:
                raise ManifestError(
                    "merge prefix must be an ordered bottom prefix of open pull requests"
                )
        if self.operation is not StackOperation.MERGE and self.merge_mode is not None:
            raise ManifestError("only merge manifests may select a merge mode")
        if self.operation is not StackOperation.MERGE and self.merge_prefix:
            raise ManifestError("only merge manifests may bind a PR prefix")

        grant = self.authority
        missing_phases = set(self.enabled_phases) - grant.phases
        missing_effects = {effect.kind for effect in self.effects} - grant.effect_kinds
        mutated_branches = {
            item.name.removeprefix("refs/heads/") for item in self.expected_refs
        } | {item.branch for item in self.expected_pull_requests}
        missing_branches = mutated_branches - set(grant.branches)
        if (
            grant.operation is not self.operation
            or grant.repository != self.repository
            or grant.remote != self.remote
            or set(self.identities) - set(grant.identities)
            or missing_phases
            or missing_effects
            or missing_branches
        ):
            missing = sorted(
                [phase.value for phase in missing_phases]
                + [effect.value for effect in missing_effects]
                + sorted(missing_branches)
            )
            detail = ", ".join(missing) if missing else "bound identities"
            raise ManifestError(f"authority grant does not cover manifest: {detail}")


@dataclass(frozen=True)
class TransitionObservation:
    values: tuple[tuple[str, object], ...]

    def as_mapping(self) -> Mapping[str, object]:
        result = dict(self.values)
        if len(result) != len(self.values):
            raise ManifestError("readback observation contains duplicate targets")
        return result

    @classmethod
    def from_manifest_before(cls, manifest: MutationManifest) -> TransitionObservation:
        return cls(
            values=tuple((effect.key, effect.before) for effect in manifest.effects)
        )


@dataclass(frozen=True)
class TargetReadback:
    effect: MutationEffect
    observed: object
    disposition: TargetDisposition


@dataclass(frozen=True)
class TransitionResult:
    state: TransitionState
    operation: StackOperation
    identities: tuple[str, ...]
    evidence: tuple[str, ...]
    targets: tuple[TargetReadback, ...] = ()
    blocker: str = ""
    next_action: str = ""
    fresh_manifest_required: bool = False


def _json_value(value: object) -> object:
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _frozen_value(value: object) -> object:
    if isinstance(value, list):
        return tuple(_frozen_value(item) for item in value)
    if isinstance(value, dict):
        return tuple(
            (str(key), _frozen_value(item)) for key, item in sorted(value.items())
        )
    return value


def manifest_to_json(manifest: MutationManifest) -> str:
    manifest.validate_complete()
    payload = {
        "schema_version": 1,
        "operation": manifest.operation.value,
        "repository": manifest.repository,
        "remote": manifest.remote,
        "identities": list(manifest.identities),
        "expected_refs": [
            {
                "name": item.name,
                "old_sha": item.old_sha,
                "proposed_sha": item.proposed_sha,
            }
            for item in manifest.expected_refs
        ],
        "expected_pull_requests": [
            {
                "number": item.number,
                "branch": item.branch,
                "head": item.head,
                "base": item.base,
                "state": item.state,
                "draft": item.draft,
                "queued": item.queued,
                "auto_merge": item.auto_merge,
                "title": item.title,
                "body": item.body,
                "current_title": item.current_title,
                "current_body": item.current_body,
            }
            for item in manifest.expected_pull_requests
        ],
        "expected_native_stack": {
            "identity": manifest.expected_native_stack.identity,
            "trunk": manifest.expected_native_stack.trunk,
            "trunk_head": manifest.expected_native_stack.trunk_head,
            "order": list(manifest.expected_native_stack.order),
        },
        "enabled_phases": [item.value for item in manifest.enabled_phases],
        "merge_mode": manifest.merge_mode.value if manifest.merge_mode else None,
        "merge_prefix": list(manifest.merge_prefix),
        "effects": [
            {
                "kind": item.kind.value,
                "target": item.target,
                "field": item.field,
                "before": _json_value(item.before),
                "after": _json_value(item.after),
            }
            for item in manifest.effects
        ],
        "evidence": list(manifest.evidence),
        "authority": {
            "operation": manifest.authority.operation.value,
            "repository": manifest.authority.repository,
            "remote": manifest.authority.remote,
            "identities": list(manifest.authority.identities),
            "branches": list(manifest.authority.branches),
            "phases": sorted(item.value for item in manifest.authority.phases),
            "effect_kinds": sorted(
                item.value for item in manifest.authority.effect_kinds
            ),
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _object(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ManifestError(f"{context} must be a JSON object")
    return value


def _array(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise ManifestError(f"{context} must be a JSON array")
    return value


def _strings(value: object, context: str) -> tuple[str, ...]:
    items = _array(value, context)
    if any(not isinstance(item, str) for item in items):
        raise ManifestError(f"{context} must contain only strings")
    return tuple(items)


def manifest_from_json(raw: str) -> MutationManifest:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest is not valid JSON: {exc}") from exc
    root = _object(payload, "manifest")
    if root.get("schema_version") != 1:
        raise ManifestError("manifest schema_version must be 1")
    try:
        refs = tuple(
            ExpectedRef(
                name=str(item["name"]),
                old_sha=str(item["old_sha"]),
                proposed_sha=str(item["proposed_sha"]),
            )
            for item in (
                _object(value, "expected ref")
                for value in _array(root["expected_refs"], "expected_refs")
            )
        )
        pull_requests = tuple(
            ExpectedPullRequest(
                number=item["number"],
                branch=str(item["branch"]),
                head=item["head"],
                base=item["base"],
                state=str(item["state"]),
                draft=item["draft"],
                queued=item["queued"],
                auto_merge=item["auto_merge"],
                title=str(item["title"]),
                body=str(item["body"]),
                current_title=item.get("current_title"),
                current_body=item.get("current_body"),
            )
            for item in (
                _object(value, "expected pull request")
                for value in _array(
                    root["expected_pull_requests"], "expected_pull_requests"
                )
            )
        )
        stack_data = _object(root["expected_native_stack"], "expected_native_stack")
        native_stack = ExpectedNativeStack(
            identity=stack_data["identity"],
            trunk=str(stack_data["trunk"]),
            trunk_head=str(stack_data["trunk_head"]),
            order=_strings(stack_data["order"], "expected_native_stack.order"),
        )
        effects = tuple(
            MutationEffect(
                kind=EffectKind(str(item["kind"])),
                target=str(item["target"]),
                field=str(item["field"]),
                before=_frozen_value(item["before"]),
                after=_frozen_value(item["after"]),
            )
            for item in (
                _object(value, "effect") for value in _array(root["effects"], "effects")
            )
        )
        authority_data = _object(root["authority"], "authority")
        authority = AuthorityGrant(
            operation=StackOperation(str(authority_data["operation"])),
            repository=str(authority_data["repository"]),
            remote=str(authority_data["remote"]),
            identities=_strings(authority_data["identities"], "authority.identities"),
            branches=_strings(authority_data["branches"], "authority.branches"),
            phases=frozenset(
                TransitionPhase(item)
                for item in _strings(authority_data["phases"], "authority.phases")
            ),
            effect_kinds=frozenset(
                EffectKind(item)
                for item in _strings(
                    authority_data["effect_kinds"], "authority.effect_kinds"
                )
            ),
        )
        merge_mode_value = root["merge_mode"]
        manifest = MutationManifest(
            operation=StackOperation(str(root["operation"])),
            repository=str(root["repository"]),
            remote=str(root["remote"]),
            identities=_strings(root["identities"], "identities"),
            expected_refs=refs,
            expected_pull_requests=pull_requests,
            expected_native_stack=native_stack,
            enabled_phases=tuple(
                TransitionPhase(item)
                for item in _strings(root["enabled_phases"], "enabled_phases")
            ),
            merge_mode=(
                None if merge_mode_value is None else MergeMode(str(merge_mode_value))
            ),
            effects=effects,
            evidence=_strings(root["evidence"], "evidence"),
            authority=authority,
            merge_prefix=tuple(
                int(item) for item in _array(root["merge_prefix"], "merge_prefix")
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ManifestError(f"manifest structure is invalid: {exc}") from exc
    manifest.validate_complete()
    return manifest


_PHASE_CAPABILITIES: Mapping[TransitionPhase, frozenset[StackCapability]] = {
    TransitionPhase.PUSH: frozenset({StackCapability.FENCED_PUSH}),
    TransitionPhase.SUBMIT: frozenset(
        {
            StackCapability.FENCED_SUBMIT,
            StackCapability.EXPLICIT_PULL_REQUEST_BODIES,
        }
    ),
    TransitionPhase.REBASE_NO_TRUNK: frozenset({StackCapability.LOCAL_REBASE_NO_TRUNK}),
    TransitionPhase.SYNC: frozenset({StackCapability.FENCED_SYNC}),
    TransitionPhase.DIRECT_MERGE: frozenset({StackCapability.FENCED_MERGE}),
    TransitionPhase.QUEUE_MERGE: frozenset(
        {StackCapability.FENCED_MERGE, StackCapability.DURABLE_QUEUE_FENCE}
    ),
    TransitionPhase.TRUNK_REFRESH: frozenset({StackCapability.PHASED_TRUNK_REFRESH}),
}


def required_capabilities(
    operation: StackOperation,
    *,
    phases: Sequence[TransitionPhase],
    merge_mode: MergeMode | None,
) -> frozenset[StackCapability]:
    selected = tuple(phases)
    if operation is StackOperation.MERGE:
        required_phase = {
            MergeMode.DIRECT: TransitionPhase.DIRECT_MERGE,
            MergeMode.QUEUE: TransitionPhase.QUEUE_MERGE,
        }.get(merge_mode)
        if required_phase is None or required_phase not in selected:
            raise ManifestError("merge mode and enabled merge phase disagree")
    elif merge_mode is not None:
        raise ManifestError("non-merge operation selected a merge mode")
    capabilities: set[StackCapability] = set()
    for phase in selected:
        capabilities.update(_PHASE_CAPABILITIES[phase])
    return frozenset(capabilities)


def preview_publish(
    *,
    repository: str,
    remote: str,
    refs: Sequence[ExpectedRef],
    pull_requests: Sequence[ExpectedPullRequest],
    native_stack: ExpectedNativeStack,
    authority: AuthorityGrant,
    evidence: Sequence[str],
) -> MutationManifest:
    expected_refs = tuple(refs)
    expected_pull_requests = tuple(pull_requests)
    effects: list[MutationEffect] = []
    for expected_ref in expected_refs:
        effects.append(
            MutationEffect(
                EffectKind.PUSH_REF,
                f"ref:{expected_ref.name.removeprefix('refs/heads/')}",
                "sha",
                expected_ref.old_sha,
                expected_ref.proposed_sha,
            )
        )
    proposed_heads = {
        item.name.removeprefix("refs/heads/"): item.proposed_sha
        for item in expected_refs
    }
    for pull_request in expected_pull_requests:
        try:
            proposed_head = proposed_heads[pull_request.branch]
        except KeyError as exc:
            raise ManifestError(
                f"pull request branch {pull_request.branch} has no proposed ref"
            ) from exc
        branch_index = native_stack.order.index(pull_request.branch)
        predecessor = (
            native_stack.trunk
            if branch_index == 0
            else native_stack.order[branch_index - 1]
        )
        effects.append(
            MutationEffect(
                EffectKind.CREATE_PR
                if pull_request.state == "ABSENT"
                else EffectKind.UPDATE_PR,
                f"pr:{pull_request.number if pull_request.number is not None else pull_request.branch}",
                "record",
                None if pull_request.state == "ABSENT" else pull_request.record,
                pull_request.proposed_record(
                    expected_head=proposed_head, expected_base=predecessor
                ),
            )
        )
    for pull_request in expected_pull_requests:
        if pull_request.auto_merge is True:
            effects.append(
                MutationEffect(
                    EffectKind.DISABLE_AUTO_MERGE,
                    f"pr:{pull_request.number}",
                    "auto_merge",
                    True,
                    False,
                )
            )
    effects.append(
        MutationEffect(
            EffectKind.REGISTER_STACK,
            f"stack:{native_stack.identity or 'absent'}",
            "order",
            native_stack.order,
            native_stack.order,
        )
    )
    manifest = MutationManifest(
        operation=StackOperation.PUBLISH,
        repository=repository,
        remote=remote,
        identities=tuple(item.branch for item in expected_pull_requests),
        expected_refs=expected_refs,
        expected_pull_requests=expected_pull_requests,
        expected_native_stack=native_stack,
        enabled_phases=(TransitionPhase.PUSH, TransitionPhase.SUBMIT),
        merge_mode=None,
        effects=tuple(effects),
        evidence=tuple(evidence),
        authority=authority,
    )
    manifest.validate_complete()
    return manifest


def preview_push(
    *,
    repository: str,
    remote: str,
    refs: Sequence[ExpectedRef],
    native_stack: ExpectedNativeStack,
    authority: AuthorityGrant,
    evidence: Sequence[str],
) -> MutationManifest:
    expected_refs = tuple(refs)
    effects = tuple(
        MutationEffect(
            EffectKind.PUSH_REF,
            f"ref:{item.name.removeprefix('refs/heads/')}",
            "sha",
            item.old_sha,
            item.proposed_sha,
        )
        for item in expected_refs
    )
    identities = tuple(item.name.removeprefix("refs/heads/") for item in expected_refs)
    manifest = MutationManifest(
        operation=StackOperation.PUBLISH,
        repository=repository,
        remote=remote,
        identities=identities,
        expected_refs=expected_refs,
        expected_pull_requests=(),
        expected_native_stack=native_stack,
        enabled_phases=(TransitionPhase.PUSH,),
        merge_mode=None,
        effects=effects,
        evidence=tuple(evidence),
        authority=authority,
    )
    manifest.validate_complete()
    return manifest


def _expected_pr_after(
    pull_request: ExpectedPullRequest,
    *,
    expected_head: str,
    expected_base: str,
) -> tuple[object, ...]:
    return pull_request.proposed_record(
        expected_head=expected_head, expected_base=expected_base
    )


def _repair_effects(
    refs: tuple[ExpectedRef, ...],
    pull_requests: tuple[ExpectedPullRequest, ...],
    native_stack: ExpectedNativeStack,
) -> tuple[MutationEffect, ...]:
    proposed = {
        item.name.removeprefix("refs/heads/"): item.proposed_sha for item in refs
    }
    effects: list[MutationEffect] = []
    for expected_ref in refs:
        if expected_ref.old_sha == expected_ref.proposed_sha:
            raise ManifestError(
                "repair preview cannot approve an unknown post-rebase head; "
                "materialize exact proposed heads before approval"
            )
        branch = expected_ref.name.removeprefix("refs/heads/")
        effects.append(
            MutationEffect(
                EffectKind.REBASE_BRANCH,
                f"local:{branch}",
                "sha",
                expected_ref.old_sha,
                expected_ref.proposed_sha,
            )
        )
    for expected_ref in refs:
        branch = expected_ref.name.removeprefix("refs/heads/")
        effects.append(
            MutationEffect(
                EffectKind.PUSH_REF,
                f"ref:{branch}",
                "sha",
                expected_ref.old_sha,
                expected_ref.proposed_sha,
            )
        )
    predecessor = native_stack.trunk
    for pull_request in pull_requests:
        head = proposed[pull_request.branch]
        effects.append(
            MutationEffect(
                EffectKind.UPDATE_PR,
                f"pr:{pull_request.number}",
                "record",
                pull_request.record,
                _expected_pr_after(
                    pull_request,
                    expected_head=head,
                    expected_base=predecessor,
                ),
            )
        )
        predecessor = pull_request.branch
    effects.append(
        MutationEffect(
            EffectKind.SYNC_STACK,
            f"stack:{native_stack.identity or 'absent'}",
            "order",
            native_stack.order,
            native_stack.order,
        )
    )
    return tuple(effects)


def preview_repair(
    *,
    repository: str,
    remote: str,
    refs: Sequence[ExpectedRef],
    pull_requests: Sequence[ExpectedPullRequest],
    native_stack: ExpectedNativeStack,
    authority: AuthorityGrant,
    evidence: Sequence[str],
) -> MutationManifest:
    expected_refs = tuple(refs)
    expected_pull_requests = tuple(pull_requests)
    manifest = MutationManifest(
        operation=StackOperation.REPAIR,
        repository=repository,
        remote=remote,
        identities=tuple(item.branch for item in expected_pull_requests),
        expected_refs=expected_refs,
        expected_pull_requests=expected_pull_requests,
        expected_native_stack=native_stack,
        enabled_phases=(
            TransitionPhase.REBASE_NO_TRUNK,
            TransitionPhase.PUSH,
            TransitionPhase.SYNC,
        ),
        merge_mode=None,
        effects=_repair_effects(expected_refs, expected_pull_requests, native_stack),
        evidence=tuple(evidence),
        authority=authority,
    )
    manifest.validate_complete()
    return manifest


def preview_merge(
    *,
    repository: str,
    remote: str,
    refs: Sequence[ExpectedRef] = (),
    pull_requests: Sequence[ExpectedPullRequest],
    native_stack: ExpectedNativeStack,
    prefix_numbers: Sequence[int],
    merge_mode: MergeMode,
    authority: AuthorityGrant,
    evidence: Sequence[str],
) -> MutationManifest:
    expected_pull_requests = tuple(pull_requests)
    expected_refs = tuple(refs)
    prefix = tuple(prefix_numbers)
    by_number = {item.number: item for item in expected_pull_requests}
    if any(number not in by_number for number in prefix):
        raise ManifestError("merge prefix contains a PR outside the selected stack")
    ordered_open = tuple(
        item.number
        for item in expected_pull_requests
        if item.state == "OPEN" and item.number is not None
    )
    if prefix != ordered_open[: len(prefix)]:
        raise ManifestError(
            "merge prefix must be an ordered bottom prefix of open pull requests"
        )
    effects: list[MutationEffect] = []
    if merge_mode is MergeMode.DIRECT:
        for number in prefix:
            effects.append(
                MutationEffect(
                    EffectKind.MERGE_PR,
                    f"pr:{number}",
                    "state",
                    by_number[number].state,
                    "MERGED",
                )
            )
        suffix = tuple(
            item.branch for item in expected_pull_requests if item.number not in prefix
        )
        ref_by_branch = {
            item.name.removeprefix("refs/heads/"): item for item in expected_refs
        }
        for branch in suffix:
            expected_ref = ref_by_branch.get(branch)
            if (
                expected_ref is None
                or expected_ref.old_sha == expected_ref.proposed_sha
            ):
                raise ManifestError(
                    "direct merge preview cannot approve unknown automatic suffix heads"
                )
            effects.append(
                MutationEffect(
                    EffectKind.SYNC_STACK,
                    f"stack:{native_stack.identity or 'absent'}:{branch}",
                    "head",
                    expected_ref.old_sha,
                    expected_ref.proposed_sha,
                )
            )
        phases = (TransitionPhase.DIRECT_MERGE,)
        if suffix:
            phases += (TransitionPhase.SYNC,)
    else:
        bottom = prefix[0] if prefix else None
        if bottom is None:
            raise ManifestError("queue merge must select a bottom pull request")
        effects.extend(
            (
                MutationEffect(
                    EffectKind.QUEUE_PR,
                    f"pr:{bottom}",
                    "queued",
                    by_number[bottom].queued,
                    True,
                ),
                MutationEffect(
                    EffectKind.MERGE_PR,
                    f"pr:{bottom}",
                    "state",
                    by_number[bottom].state,
                    "MERGED",
                ),
            )
        )
        phases = (TransitionPhase.QUEUE_MERGE,)
    manifest = MutationManifest(
        operation=StackOperation.MERGE,
        repository=repository,
        remote=remote,
        identities=tuple(item.branch for item in expected_pull_requests),
        expected_refs=expected_refs,
        expected_pull_requests=expected_pull_requests,
        expected_native_stack=native_stack,
        enabled_phases=phases,
        merge_mode=merge_mode,
        effects=tuple(effects),
        evidence=tuple(evidence),
        authority=authority,
        merge_prefix=prefix,
    )
    manifest.validate_complete()
    return manifest


def preview_recovery(
    *,
    repository: str,
    remote: str,
    refs: Sequence[ExpectedRef],
    pull_requests: Sequence[ExpectedPullRequest],
    native_stack: ExpectedNativeStack,
    authority: AuthorityGrant,
    evidence: Sequence[str],
    identities: Sequence[str] = (),
) -> MutationManifest:
    expected_refs = tuple(refs)
    expected_pull_requests = tuple(pull_requests)
    effects = (
        MutationEffect(
            EffectKind.REFRESH_TRUNK,
            f"ref:{native_stack.trunk}",
            "sha",
            native_stack.trunk_head,
            native_stack.trunk_head,
        ),
        *_repair_effects(expected_refs, expected_pull_requests, native_stack),
    )
    manifest = MutationManifest(
        operation=StackOperation.RECOVER,
        repository=repository,
        remote=remote,
        identities=tuple(identities)
        or tuple(item.branch for item in expected_pull_requests),
        expected_refs=expected_refs,
        expected_pull_requests=expected_pull_requests,
        expected_native_stack=native_stack,
        enabled_phases=(
            TransitionPhase.TRUNK_REFRESH,
            TransitionPhase.REBASE_NO_TRUNK,
            TransitionPhase.PUSH,
            TransitionPhase.SYNC,
        ),
        merge_mode=None,
        effects=effects,
        evidence=tuple(evidence),
        authority=authority,
    )
    manifest.validate_complete()
    return manifest


def classify_readback(
    manifest: MutationManifest,
    observation: TransitionObservation,
) -> TransitionResult:
    observed = observation.as_mapping()
    missing = object()
    targets: list[TargetReadback] = []
    for effect in manifest.effects:
        value = observed.get(effect.key, missing)
        if effect.before == effect.after and value == effect.after:
            disposition = TargetDisposition.UNCHANGED
        elif value == effect.after:
            disposition = TargetDisposition.CHANGED_AS_EXPECTED
        elif value == effect.before:
            disposition = TargetDisposition.UNCHANGED
        else:
            disposition = TargetDisposition.CHANGED_UNEXPECTEDLY
        targets.append(
            TargetReadback(effect=effect, observed=value, disposition=disposition)
        )

    dispositions = {target.disposition for target in targets}
    incomplete_mutations = any(
        target.disposition is TargetDisposition.UNCHANGED
        and target.effect.before != target.effect.after
        for target in targets
    )
    changed = any(
        target.disposition is TargetDisposition.CHANGED_AS_EXPECTED
        for target in targets
    )
    if TargetDisposition.CHANGED_UNEXPECTEDLY in dispositions:
        state = TransitionState.DIVERGED
    elif incomplete_mutations and changed:
        state = TransitionState.PARTIAL
    elif incomplete_mutations:
        state = TransitionState.UNCHANGED
    elif changed:
        state = TransitionState.COMPLETED
    else:
        state = TransitionState.UNCHANGED
    fresh_manifest_required = state in {
        TransitionState.PARTIAL,
        TransitionState.DIVERGED,
    }
    return TransitionResult(
        state=state,
        operation=manifest.operation,
        identities=manifest.identities,
        evidence=manifest.evidence,
        targets=tuple(targets),
        blocker=(
            "readback was partial or divergent; generate a fresh manifest before retry"
            if fresh_manifest_required
            else ""
        ),
        next_action=(
            "reread every target and authority input, then approve a new manifest"
            if fresh_manifest_required
            else ""
        ),
        fresh_manifest_required=fresh_manifest_required,
    )


def observation_from_manifest(
    approved: MutationManifest, current: MutationManifest
) -> TransitionObservation:
    """Project a fresh live manifest onto every declared effect target."""

    refs = {
        item.name.removeprefix("refs/heads/"): item for item in current.expected_refs
    }
    prs_by_branch = {item.branch: item for item in current.expected_pull_requests}
    prs_by_number = {
        item.number: item
        for item in current.expected_pull_requests
        if item.number is not None
    }
    values: list[tuple[str, object]] = []
    for effect in approved.effects:
        identity = effect.target.partition(":")[2]
        if effect.kind is EffectKind.PUSH_REF:
            observed: object = refs[identity].old_sha
        elif effect.kind is EffectKind.REBASE_BRANCH:
            observed = refs[identity].proposed_sha
        elif effect.kind in {EffectKind.CREATE_PR, EffectKind.UPDATE_PR}:
            pr = prs_by_branch.get(identity)
            if pr is None and identity.isdigit():
                pr = prs_by_number.get(int(identity))
            observed = None if pr is None or pr.state == "ABSENT" else pr.record
        elif effect.kind is EffectKind.DISABLE_AUTO_MERGE:
            observed = prs_by_number[int(identity)].auto_merge
        elif effect.kind in {EffectKind.REGISTER_STACK, EffectKind.SYNC_STACK}:
            if effect.field == "order":
                observed = current.expected_native_stack.order
            elif effect.field == "head":
                branch = identity.rpartition(":")[2]
                observed = refs[branch].old_sha
            else:
                raise ManifestError(
                    f"unsupported native-stack readback field: {effect.field}"
                )
        elif effect.kind in {EffectKind.MERGE_PR, EffectKind.QUEUE_PR}:
            pr = prs_by_number[int(identity)]
            observed = pr.state if effect.field == "state" else pr.queued
        elif effect.kind is EffectKind.REFRESH_TRUNK:
            observed = current.expected_native_stack.trunk_head
        else:  # pragma: no cover
            raise ManifestError(f"unsupported readback effect: {effect.kind.value}")
        values.append((effect.key, observed))
    return TransitionObservation(values=tuple(values))


def execute_transition(
    manifest: MutationManifest,
    *,
    profile: GhStackProfile,
    reread: Callable[[], MutationManifest],
    executor: Callable[[MutationManifest], object],
    readback: Callable[[], TransitionObservation],
) -> TransitionResult:
    try:
        manifest.validate_complete()
    except ManifestError as exc:
        return TransitionResult(
            state=TransitionState.BLOCKED,
            operation=manifest.operation,
            identities=manifest.identities,
            evidence=manifest.evidence,
            blocker=str(exc),
            next_action="approve a complete operation-scoped manifest",
        )
    try:
        current = reread()
        current.validate_complete()
    except ManifestError as exc:
        return TransitionResult(
            state=TransitionState.BLOCKED,
            operation=manifest.operation,
            identities=manifest.identities,
            evidence=manifest.evidence,
            blocker=f"pre-execution reread is invalid: {exc}",
            next_action="review and approve a newly generated manifest",
            fresh_manifest_required=True,
        )
    if current != manifest:
        return TransitionResult(
            state=TransitionState.BLOCKED,
            operation=manifest.operation,
            identities=manifest.identities,
            evidence=manifest.evidence,
            blocker="manifest changed during pre-execution reread",
            next_action="review and approve a newly generated manifest",
            fresh_manifest_required=True,
        )
    required = required_capabilities(
        manifest.operation,
        phases=manifest.enabled_phases,
        merge_mode=manifest.merge_mode,
    )
    missing = required - profile.capabilities
    if missing:
        names = ", ".join(sorted(capability.value for capability in missing))
        return TransitionResult(
            state=TransitionState.BLOCKED,
            operation=manifest.operation,
            identities=manifest.identities,
            evidence=manifest.evidence,
            blocker=f"gh stack profile {profile.version} lacks: {names}",
            next_action="install a repository-tested compatible gh-stack profile",
        )
    execution_error: Exception | None = None
    try:
        executor(manifest)
    except Exception as exc:  # readback must account for partial remote effects
        execution_error = exc
    try:
        result = classify_readback(manifest, readback())
    except Exception as exc:
        detail = f"executor failed ({execution_error}); " if execution_error else ""
        return TransitionResult(
            state=TransitionState.BLOCKED,
            operation=manifest.operation,
            identities=manifest.identities,
            evidence=manifest.evidence,
            blocker=f"{detail}post-command readback failed: {exc}",
            next_action="reread every declared target and generate a fresh manifest",
            fresh_manifest_required=True,
        )
    if execution_error is None:
        if result.state in {TransitionState.PARTIAL, TransitionState.DIVERGED}:
            return replace(
                result,
                state=TransitionState.BLOCKED,
                blocker="post-command readback was partial or divergent",
                next_action="reread every declared target and approve a fresh manifest",
                fresh_manifest_required=True,
            )
        return result
    if result.state is TransitionState.UNCHANGED:
        return replace(
            result,
            state=TransitionState.BLOCKED,
            blocker=f"executor failed without observed mutation: {execution_error}",
            next_action="resolve the executor failure before retrying",
        )
    return replace(
        result,
        blocker=f"executor failed after remote effects: {execution_error}",
        next_action=(
            "reread every declared target and generate a fresh manifest"
            if result.fresh_manifest_required
            else result.next_action
        ),
    )
