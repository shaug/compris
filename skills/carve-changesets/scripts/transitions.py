#!/usr/bin/env python3
"""Operation-scoped manifests and readback for native-stack remote effects."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum

from gh_stack import GhStackProfile, StackCapability

ZERO_SHA = "0" * 40
MISSING_OBSERVATION = object()


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
    READY_PR = "ready_pr"


class TargetDisposition(str, Enum):
    CHANGED_AS_EXPECTED = "changed_as_expected"
    UNCHANGED = "unchanged"
    CHANGED_UNEXPECTEDLY = "changed_unexpectedly"


class TransitionState(str, Enum):
    COMPLETED = "completed"
    ADMITTED = "admitted"
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
    merge_state_status: str | None = None

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
                    self.merge_state_status,
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
            if self.merge_state_status is not None and (
                not isinstance(self.merge_state_status, str)
                or not self.merge_state_status.strip()
            ):
                raise ManifestError(
                    f"pull request #{self.number} merge gate state must be non-empty"
                )
            if self.current_title is None or self.current_body is None:
                raise ManifestError(
                    f"pull request #{self.number} needs exact current title and body"
                )
        if self.state == "ABSENT" and (
            self.current_title is not None or self.current_body is not None
        ):
            raise ManifestError(
                f"expected-absent pull request for {self.branch} carries current text"
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
        self,
        *,
        expected_head: str,
        expected_base: str,
        ready_for_review: bool = False,
    ) -> tuple[object, ...]:
        proposed_draft = (
            not ready_for_review
            if self.state == "ABSENT"
            else False
            if ready_for_review
            else self.draft
        )
        return (
            self.number,
            self.branch,
            expected_head,
            expected_base,
            "OPEN",
            proposed_draft,
            False,
            False,
            self.title,
            self.body,
        )


@dataclass(frozen=True)
class ExpectedNativeLayer:
    branch: str
    head: str
    base: str
    merged: bool
    queued: bool
    needs_rebase: bool
    pull_request: int | None
    pull_request_state: str | None

    def validate(self) -> None:
        if not self.branch.strip():
            raise ManifestError("expected native layer branch must be non-empty")
        for label, sha in (("head", self.head), ("base", self.base)):
            if len(sha) != 40 or any(
                character not in "0123456789abcdef" for character in sha
            ):
                raise ManifestError(
                    f"native layer {self.branch} {label} must be a full SHA"
                )
        for label, value in (
            ("merged", self.merged),
            ("queued", self.queued),
            ("needs-rebase", self.needs_rebase),
        ):
            if not isinstance(value, bool):
                raise ManifestError(
                    f"native layer {self.branch} {label} must be boolean"
                )
        if self.pull_request is None:
            if self.pull_request_state is not None:
                raise ManifestError(
                    f"native layer {self.branch} has PR state without identity"
                )
            if self.merged or self.queued:
                raise ManifestError(
                    f"native layer {self.branch} has merge/queue state without a PR"
                )
        else:
            if (
                not isinstance(self.pull_request, int)
                or isinstance(self.pull_request, bool)
                or self.pull_request < 1
            ):
                raise ManifestError(
                    f"native layer {self.branch} PR must be a positive integer"
                )
            if self.pull_request_state not in {"OPEN", "CLOSED", "MERGED"}:
                raise ManifestError(f"native layer {self.branch} has invalid PR state")
            if self.merged != (self.pull_request_state == "MERGED"):
                raise ManifestError(
                    f"native layer {self.branch} merged flag disagrees with PR state"
                )


@dataclass(frozen=True)
class ExpectedNativeStack:
    identity: str | None
    registered: bool
    trunk: str
    trunk_head: str
    trunk_tree: str
    layers: tuple[ExpectedNativeLayer, ...]

    @property
    def order(self) -> tuple[str, ...]:
        return tuple(layer.branch for layer in self.layers)

    @property
    def open_order(self) -> tuple[str, ...]:
        return tuple(layer.branch for layer in self.layers if not layer.merged)

    def validate(self) -> None:
        if self.identity is not None and (
            not isinstance(self.identity, str) or not self.identity.strip()
        ):
            raise ManifestError("expected native stack identity must be non-empty")
        if not isinstance(self.registered, bool):
            raise ManifestError("expected native stack registration must be boolean")
        if self.registered and self.identity is None:
            raise ManifestError("registered native stack needs an exact identity")
        if not self.trunk.strip():
            raise ManifestError("expected native stack trunk must be non-empty")
        for label, sha in (("head", self.trunk_head), ("tree", self.trunk_tree)):
            if len(sha) != 40 or any(
                character not in "0123456789abcdef" for character in sha
            ):
                raise ManifestError(
                    f"expected native stack trunk {label} must be a full SHA"
                )
        if not self.layers:
            raise ManifestError("expected native stack order must name every layer")
        for layer in self.layers:
            layer.validate()
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
    ready_for_review: tuple[str, ...] = ()
    merge_method: str | None = None

    @classmethod
    def push(
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
            phases=frozenset({TransitionPhase.PUSH}),
            effect_kinds=frozenset({EffectKind.PUSH_REF}),
        )

    @classmethod
    def publish(
        cls,
        *,
        repository: str,
        remote: str,
        branches: Sequence[str],
        pull_requests: Sequence[ExpectedPullRequest],
        ready_for_review: Sequence[str] = (),
    ) -> AuthorityGrant:
        selected = tuple(branches)
        expected_pull_requests = tuple(pull_requests)
        ready = tuple(ready_for_review)
        effect_kinds = {EffectKind.PUSH_REF, EffectKind.REGISTER_STACK}
        if any(item.state == "ABSENT" for item in expected_pull_requests):
            effect_kinds.add(EffectKind.CREATE_PR)
        if any(item.state != "ABSENT" for item in expected_pull_requests):
            effect_kinds.add(EffectKind.UPDATE_PR)
        if any(item.auto_merge is True for item in expected_pull_requests):
            effect_kinds.add(EffectKind.DISABLE_AUTO_MERGE)
        if ready:
            effect_kinds.add(EffectKind.READY_PR)
        return cls(
            operation=StackOperation.PUBLISH,
            repository=repository,
            remote=remote,
            identities=selected,
            branches=selected,
            phases=frozenset({TransitionPhase.PUSH, TransitionPhase.SUBMIT}),
            effect_kinds=frozenset(effect_kinds),
            ready_for_review=ready,
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
    merge_method: str | None
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
        if len(set(self.identities)) != len(self.identities):
            raise ManifestError("manifest identities must not contain duplicates")
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
        ordered_pr_branches = tuple(
            branch
            for branch in self.expected_native_stack.order
            if branch in set(pr_branches)
        )
        if pr_branches != ordered_pr_branches:
            raise ManifestError(
                "manifest pull requests must follow expected native stack order"
            )
        if (
            self.operation is StackOperation.MERGE
            and pr_branches != self.expected_native_stack.order
        ):
            raise ManifestError(
                "manifest pull requests must cover the complete native stack order"
            )
        native_by_branch = {
            layer.branch: layer for layer in self.expected_native_stack.layers
        }
        merge_open_order = tuple(
            layer.branch
            for layer in self.expected_native_stack.layers
            if not layer.merged
        )
        for pull_request in self.expected_pull_requests:
            native_layer = native_by_branch[pull_request.branch]
            if pull_request.state == "ABSENT":
                consistent = (
                    native_layer.pull_request is None
                    and native_layer.pull_request_state is None
                    and not native_layer.queued
                    and not native_layer.merged
                )
            else:
                consistent = (
                    native_layer.pull_request == pull_request.number
                    and native_layer.pull_request_state == pull_request.state
                    and native_layer.head == pull_request.head
                    and native_layer.queued == pull_request.queued
                    and native_layer.merged == (pull_request.state == "MERGED")
                )
            if not consistent:
                raise ManifestError(
                    "pull request state disagrees with expected native layer "
                    f"{pull_request.branch}"
                )
            topology_order = (
                merge_open_order
                if self.operation is StackOperation.MERGE
                and pull_request.state != "MERGED"
                else self.expected_native_stack.order
            )
            branch_index = topology_order.index(pull_request.branch)
            expected_base = (
                self.expected_native_stack.trunk
                if branch_index == 0
                else topology_order[branch_index - 1]
            )
            if (
                self.operation is StackOperation.MERGE
                and pull_request.state != "ABSENT"
                and pull_request.state != "MERGED"
                and pull_request.base != expected_base
            ):
                raise ManifestError(
                    "pull request base disagrees with expected native stack topology: "
                    f"{pull_request.branch}"
                )
        if self.operation is StackOperation.MERGE:
            seen_unmerged = False
            for layer in self.expected_native_stack.layers:
                if layer.merged:
                    if seen_unmerged:
                        raise ManifestError(
                            "merged native layers must form a bottom prefix"
                        )
                else:
                    seen_unmerged = True
                    if layer.pull_request_state != "OPEN":
                        raise ManifestError(
                            "every unmerged native layer must have an open pull request"
                        )
        if self.operation in {StackOperation.REPAIR, StackOperation.RECOVER} and any(
            pull_request.state == "ABSENT"
            for pull_request in self.expected_pull_requests
        ):
            raise ManifestError("repair and recovery require existing pull requests")
        if len(set(self.authority.ready_for_review)) != len(
            self.authority.ready_for_review
        ):
            raise ManifestError("ready-for-review authority contains duplicates")
        for label, values in (
            ("identities", self.authority.identities),
            ("branches", self.authority.branches),
        ):
            if len(set(values)) != len(values):
                raise ManifestError(f"authority {label} must not contain duplicates")
        if set(self.authority.ready_for_review) - set(self.authority.branches):
            raise ManifestError(
                "ready-for-review authority is outside the granted branches"
            )
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
                if pull_request.branch in self.authority.ready_for_review and (
                    pull_request.draft is not False
                ):
                    required_effects.add(
                        (
                            EffectKind.READY_PR,
                            f"pr:{identity}",
                            "draft",
                        )
                    )
            required_effects.add(
                (
                    EffectKind.REGISTER_STACK,
                    f"stack:{self.expected_native_stack.identity or 'absent'}",
                    "identity",
                )
            )
            required_effects.add(
                (
                    EffectKind.REGISTER_STACK,
                    f"stack:{self.expected_native_stack.identity or 'absent'}",
                    "registered",
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
        if self.operation is StackOperation.MERGE:
            required_effects.update(
                {
                    (
                        EffectKind.REFRESH_TRUNK,
                        f"ref:{self.expected_native_stack.trunk}",
                        "tree",
                    ),
                    (
                        EffectKind.SYNC_STACK,
                        f"stack:{self.expected_native_stack.identity or 'absent'}",
                        "open_order",
                    ),
                }
            )
            suffix = tuple(
                item
                for item in self.expected_pull_requests
                if item.state == "OPEN" and item.number not in self.merge_prefix
            )
            required_effects.update(
                (
                    EffectKind.PUSH_REF,
                    f"ref:{pull_request.branch}",
                    "sha",
                )
                for pull_request in suffix
            )
            required_effects.update(
                (
                    EffectKind.UPDATE_PR,
                    f"pr:{pull_request.number}",
                    "record",
                )
                for pull_request in suffix
            )
            required_effects.update(
                (
                    EffectKind.SYNC_STACK,
                    "stack:"
                    f"{self.expected_native_stack.identity or 'absent'}:"
                    f"{pull_request.branch}",
                    "head",
                )
                for pull_request in suffix
            )
        if self.operation in {StackOperation.REPAIR, StackOperation.RECOVER}:
            required_effects.update(
                (
                    EffectKind.UPDATE_PR,
                    f"pr:{pull_request.number}",
                    "record",
                )
                for pull_request in self.expected_pull_requests
            )
            required_effects.add(
                (
                    EffectKind.SYNC_STACK,
                    f"stack:{self.expected_native_stack.identity or 'absent'}",
                    "order",
                )
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
        unexpected_effects = effect_signatures - required_effects
        if unexpected_effects:
            details = ", ".join(
                f"{kind.value}:{target}:{field}"
                for kind, target, field in sorted(
                    unexpected_effects,
                    key=lambda item: (item[0].value, item[1], item[2]),
                )
            )
            raise ManifestError(f"manifest has unexpected effect: {details}")
        expected_values: dict[tuple[EffectKind, str, str], tuple[object, object]] = {}
        for branch, expected_ref in ref_by_branch.items():
            for kind, target in (
                (EffectKind.PUSH_REF, f"ref:{branch}"),
                (EffectKind.REBASE_BRANCH, f"local:{branch}"),
            ):
                signature = (kind, target, "sha")
                if signature in required_effects:
                    expected_values[signature] = (
                        expected_ref.old_sha,
                        expected_ref.proposed_sha,
                    )
        if self.operation is StackOperation.PUBLISH:
            changing_pull_requests = self.expected_pull_requests
        elif self.operation in {StackOperation.REPAIR, StackOperation.RECOVER}:
            changing_pull_requests = self.expected_pull_requests
        elif self.operation is StackOperation.MERGE:
            changing_pull_requests = tuple(
                item
                for item in self.expected_pull_requests
                if item.state == "OPEN" and item.number not in self.merge_prefix
            )
        else:
            changing_pull_requests = ()
        predecessor = self.expected_native_stack.trunk
        for pull_request in changing_pull_requests:
            expected_ref = ref_by_branch.get(pull_request.branch)
            if expected_ref is None:
                raise ManifestError(
                    f"pull request branch {pull_request.branch} has no proposed ref"
                )
            ready = (
                self.operation is StackOperation.PUBLISH
                and pull_request.branch in self.authority.ready_for_review
            )
            if self.operation is StackOperation.PUBLISH:
                branch_index = self.expected_native_stack.order.index(
                    pull_request.branch
                )
                predecessor = (
                    self.expected_native_stack.trunk
                    if branch_index == 0
                    else self.expected_native_stack.order[branch_index - 1]
                )
            kind = (
                EffectKind.CREATE_PR
                if pull_request.state == "ABSENT"
                else EffectKind.UPDATE_PR
            )
            identity = (
                str(pull_request.number)
                if pull_request.number is not None
                else pull_request.branch
            )
            expected_values[(kind, f"pr:{identity}", "record")] = (
                None if pull_request.state == "ABSENT" else pull_request.record,
                pull_request.proposed_record(
                    expected_head=expected_ref.proposed_sha,
                    expected_base=predecessor,
                    ready_for_review=ready,
                ),
            )
            if pull_request.auto_merge is True:
                expected_values[
                    (
                        EffectKind.DISABLE_AUTO_MERGE,
                        f"pr:{pull_request.number}",
                        "auto_merge",
                    )
                ] = (True, False)
            if ready and pull_request.draft is not False:
                expected_values[(EffectKind.READY_PR, f"pr:{identity}", "draft")] = (
                    pull_request.draft,
                    False,
                )
            predecessor = pull_request.branch
        stack_target = f"stack:{self.expected_native_stack.identity or 'absent'}"
        if self.operation is StackOperation.PUBLISH:
            expected_values[(EffectKind.REGISTER_STACK, stack_target, "identity")] = (
                self.expected_native_stack.identity
                if self.expected_native_stack.registered
                else None,
                self.expected_native_stack.identity,
            )
            expected_values[(EffectKind.REGISTER_STACK, stack_target, "order")] = (
                self.expected_native_stack.order
                if self.expected_native_stack.registered
                else (),
                self.expected_native_stack.order,
            )
            expected_values[(EffectKind.REGISTER_STACK, stack_target, "registered")] = (
                self.expected_native_stack.registered,
                True,
            )
        if self.operation in {StackOperation.REPAIR, StackOperation.RECOVER}:
            expected_values[(EffectKind.SYNC_STACK, stack_target, "order")] = (
                self.expected_native_stack.order,
                self.expected_native_stack.order,
            )
        if self.operation is StackOperation.RECOVER:
            expected_values[
                (
                    EffectKind.REFRESH_TRUNK,
                    f"ref:{self.expected_native_stack.trunk}",
                    "sha",
                )
            ] = (
                self.expected_native_stack.trunk_head,
                self.expected_native_stack.trunk_head,
            )
        if self.operation is StackOperation.MERGE:
            pull_requests_by_number = {
                item.number: item for item in self.expected_pull_requests
            }
            for number in self.merge_prefix:
                pull_request = pull_requests_by_number[number]
                expected_values[(EffectKind.MERGE_PR, f"pr:{number}", "state")] = (
                    pull_request.state,
                    "MERGED",
                )
            if self.merge_mode is MergeMode.QUEUE:
                bottom = self.merge_prefix[0]
                expected_values[(EffectKind.QUEUE_PR, f"pr:{bottom}", "queued")] = (
                    pull_requests_by_number[bottom].queued,
                    True,
                )
            suffix = tuple(
                item
                for item in self.expected_pull_requests
                if item.state == "OPEN" and item.number not in self.merge_prefix
            )
            expected_values[(EffectKind.SYNC_STACK, stack_target, "open_order")] = (
                self.expected_native_stack.open_order,
                tuple(item.branch for item in suffix),
            )
            for pull_request in suffix:
                expected_ref = ref_by_branch[pull_request.branch]
                expected_values[
                    (
                        EffectKind.SYNC_STACK,
                        f"{stack_target}:{pull_request.branch}",
                        "head",
                    )
                ] = (expected_ref.old_sha, expected_ref.proposed_sha)
        specialized_bindings = (
            {
                (
                    EffectKind.REFRESH_TRUNK,
                    f"ref:{self.expected_native_stack.trunk}",
                    "tree",
                )
            }
            if self.operation is StackOperation.MERGE
            else set()
        )
        unbound_required_effects = (
            required_effects - set(expected_values) - specialized_bindings
        )
        if unbound_required_effects:
            details = ", ".join(
                f"{kind.value}:{target}:{field}"
                for kind, target, field in sorted(
                    unbound_required_effects,
                    key=lambda item: (item[0].value, item[1], item[2]),
                )
            )
            raise ManifestError(
                f"required effects lack expected-value bindings: {details}"
            )
        for effect in self.effects:
            signature = (effect.kind, effect.target, effect.field)
            expected = expected_values.get(signature)
            if expected is not None and not _exact_value_equal(
                (effect.before, effect.after), expected
            ):
                raise ManifestError(
                    "manifest effect values disagree with bound resource state: "
                    f"{effect.kind.value}:{effect.target}:{effect.field}"
                )
            if (
                effect.kind is EffectKind.REFRESH_TRUNK
                and effect.field == "tree"
                and (
                    effect.before != self.expected_native_stack.trunk_tree
                    or not isinstance(effect.after, str)
                    or len(effect.after) != 40
                    or any(
                        character not in "0123456789abcdef"
                        for character in effect.after
                    )
                )
            ):
                raise ManifestError(
                    "manifest effect values disagree with bound resource state: "
                    f"{effect.kind.value}:{effect.target}:{effect.field}"
                )
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
            if self.merge_mode is MergeMode.QUEUE and len(self.merge_prefix) != 1:
                raise ManifestError(
                    "queue merge prefix must contain exactly the bottom open pull request"
                )
            selected_pull_requests = {
                item.number: item for item in self.expected_pull_requests
            }
            missing_gate_state = tuple(
                number
                for number in self.merge_prefix
                if not selected_pull_requests[number].merge_state_status
            )
            if missing_gate_state:
                raise ManifestError(
                    "merge manifests must bind exact merge gate state for PRs: "
                    f"{missing_gate_state!r}"
                )
            if self.merge_mode is MergeMode.DIRECT:
                if self.merge_method not in {"merge", "squash", "rebase"}:
                    raise ManifestError(
                        "direct merge manifests must bind merge, squash, or rebase"
                    )
            elif self.merge_method is not None:
                raise ManifestError(
                    "queue merge method must be explicitly not applicable"
                )
        if self.operation is not StackOperation.MERGE and self.merge_mode is not None:
            raise ManifestError("only merge manifests may select a merge mode")
        if self.operation is not StackOperation.MERGE and self.merge_method is not None:
            raise ManifestError("only direct merge manifests may select a merge method")
        if self.operation is not StackOperation.MERGE and self.merge_prefix:
            raise ManifestError("only merge manifests may bind a PR prefix")

        grant = self.authority
        manifest_phases = frozenset(self.enabled_phases)
        manifest_effects = frozenset(effect.kind for effect in self.effects)
        mutated_branches = {
            item.name.removeprefix("refs/heads/") for item in self.expected_refs
        } | {item.branch for item in self.expected_pull_requests}
        if self.operation is StackOperation.MERGE:
            mutated_branches.update(
                effect.target.removeprefix("ref:")
                for effect in self.effects
                if effect.target.startswith("ref:")
            )
        ready_effect_branches = {
            item.branch
            for item in self.expected_pull_requests
            if item.branch in grant.ready_for_review and item.draft is not False
        }
        if (
            grant.operation is not self.operation
            or grant.repository != self.repository
            or grant.remote != self.remote
            or grant.identities != self.identities
            or set(grant.branches) != mutated_branches
            or grant.phases != manifest_phases
            or grant.effect_kinds != manifest_effects
            or set(grant.ready_for_review) != ready_effect_branches
            or grant.merge_method != self.merge_method
        ):
            raise ManifestError(
                "authority grant must exactly match manifest phases, effects, "
                "identities, branches, ready transitions, and merge method"
            )


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
    retained_manifest: MutationManifest | None = None


def _json_value(value: object) -> object:
    if value is MISSING_OBSERVATION:
        return {"missing": True}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def transition_result_to_json(result: TransitionResult) -> str:
    payload = {
        "schema_version": 1,
        "state": result.state.value,
        "operation": result.operation.value,
        "identities": list(result.identities),
        "evidence": list(result.evidence),
        "blocker": result.blocker,
        "next_action": result.next_action,
        "fresh_manifest_required": result.fresh_manifest_required,
        "approved_manifest_retained": result.retained_manifest is not None,
        "targets": [
            {
                "kind": item.effect.kind.value,
                "target": item.effect.target,
                "field": item.effect.field,
                "expected_before": _json_value(item.effect.before),
                "expected_after": _json_value(item.effect.after),
                "observed": _json_value(item.observed),
                "disposition": item.disposition.value,
            }
            for item in result.targets
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _frozen_value(value: object) -> object:
    if isinstance(value, list):
        return tuple(_frozen_value(item) for item in value)
    if isinstance(value, dict):
        return tuple(
            (str(key), _frozen_value(item)) for key, item in sorted(value.items())
        )
    return value


def _exact_value_equal(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, tuple):
        return len(left) == len(right) and all(
            _exact_value_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return left == right


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
                "merge_state_status": item.merge_state_status,
            }
            for item in manifest.expected_pull_requests
        ],
        "expected_native_stack": {
            "identity": manifest.expected_native_stack.identity,
            "registered": manifest.expected_native_stack.registered,
            "trunk": manifest.expected_native_stack.trunk,
            "trunk_head": manifest.expected_native_stack.trunk_head,
            "trunk_tree": manifest.expected_native_stack.trunk_tree,
            "layers": [
                {
                    "branch": item.branch,
                    "head": item.head,
                    "base": item.base,
                    "merged": item.merged,
                    "queued": item.queued,
                    "needs_rebase": item.needs_rebase,
                    "pull_request": item.pull_request,
                    "pull_request_state": item.pull_request_state,
                }
                for item in manifest.expected_native_stack.layers
            ],
        },
        "enabled_phases": [item.value for item in manifest.enabled_phases],
        "merge_mode": manifest.merge_mode.value if manifest.merge_mode else None,
        "merge_method": manifest.merge_method,
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
            "ready_for_review": list(manifest.authority.ready_for_review),
            "merge_method": manifest.authority.merge_method,
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


def _unique_strings(value: object, context: str) -> tuple[str, ...]:
    items = _strings(value, context)
    if len(set(items)) != len(items):
        raise ManifestError(f"{context} must not contain duplicates")
    return items


def _exact_object(
    value: object, context: str, expected_fields: frozenset[str]
) -> dict[str, object]:
    result = _object(value, context)
    actual_fields = frozenset(result)
    if actual_fields != expected_fields:
        missing = sorted(expected_fields - actual_fields)
        unknown = sorted(actual_fields - expected_fields)
        raise ManifestError(
            f"{context} fields are invalid; missing={missing!r}, unknown={unknown!r}"
        )
    return result


def _string(value: object, context: str) -> str:
    if not isinstance(value, str):
        raise ManifestError(f"{context} must be a string")
    return value


def _optional_string(value: object, context: str) -> str | None:
    if value is None:
        return None
    return _string(value, context)


def _integer(value: object, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ManifestError(f"{context} must be an integer")
    return value


def _optional_integer(value: object, context: str) -> int | None:
    if value is None:
        return None
    return _integer(value, context)


def _boolean(value: object, context: str) -> bool:
    if not isinstance(value, bool):
        raise ManifestError(f"{context} must be boolean")
    return value


def _optional_boolean(value: object, context: str) -> bool | None:
    if value is None:
        return None
    return _boolean(value, context)


def manifest_from_json(raw: str) -> MutationManifest:
    def reject_duplicate_members(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ManifestError(f"duplicate JSON member: {key}")
            result[key] = value
        return result

    def reject_nonstandard_constant(value: str) -> object:
        raise ManifestError(f"manifest contains non-standard JSON constant: {value}")

    try:
        payload = json.loads(
            raw,
            object_pairs_hook=reject_duplicate_members,
            parse_constant=reject_nonstandard_constant,
        )
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest is not valid JSON: {exc}") from exc
    root = _exact_object(
        payload,
        "manifest",
        frozenset(
            {
                "schema_version",
                "operation",
                "repository",
                "remote",
                "identities",
                "expected_refs",
                "expected_pull_requests",
                "expected_native_stack",
                "enabled_phases",
                "merge_mode",
                "merge_method",
                "merge_prefix",
                "effects",
                "evidence",
                "authority",
            }
        ),
    )
    if (
        not isinstance(root.get("schema_version"), int)
        or isinstance(root.get("schema_version"), bool)
        or root["schema_version"] != 1
    ):
        raise ManifestError("manifest schema_version must be 1")
    try:
        refs = tuple(
            ExpectedRef(
                name=_string(item["name"], "expected ref.name"),
                old_sha=_string(item["old_sha"], "expected ref.old_sha"),
                proposed_sha=_string(item["proposed_sha"], "expected ref.proposed_sha"),
            )
            for item in (
                _exact_object(
                    value,
                    "expected ref",
                    frozenset({"name", "old_sha", "proposed_sha"}),
                )
                for value in _array(root["expected_refs"], "expected_refs")
            )
        )
        pull_requests = tuple(
            ExpectedPullRequest(
                number=_optional_integer(
                    item["number"], "expected pull request.number"
                ),
                branch=_string(item["branch"], "expected pull request.branch"),
                head=_optional_string(item["head"], "expected pull request.head"),
                base=_optional_string(item["base"], "expected pull request.base"),
                state=_string(item["state"], "expected pull request.state"),
                draft=_optional_boolean(item["draft"], "expected pull request.draft"),
                queued=_optional_boolean(
                    item["queued"], "expected pull request.queued"
                ),
                auto_merge=_optional_boolean(
                    item["auto_merge"], "expected pull request.auto_merge"
                ),
                title=_string(item["title"], "expected pull request.title"),
                body=_string(item["body"], "expected pull request.body"),
                current_title=_optional_string(
                    item["current_title"], "expected pull request.current_title"
                ),
                current_body=_optional_string(
                    item["current_body"], "expected pull request.current_body"
                ),
                merge_state_status=_optional_string(
                    item["merge_state_status"],
                    "expected pull request.merge_state_status",
                ),
            )
            for item in (
                _exact_object(
                    value,
                    "expected pull request",
                    frozenset(
                        {
                            "number",
                            "branch",
                            "head",
                            "base",
                            "state",
                            "draft",
                            "queued",
                            "auto_merge",
                            "title",
                            "body",
                            "current_title",
                            "current_body",
                            "merge_state_status",
                        }
                    ),
                )
                for value in _array(
                    root["expected_pull_requests"], "expected_pull_requests"
                )
            )
        )
        stack_data = _exact_object(
            root["expected_native_stack"],
            "expected_native_stack",
            frozenset(
                {
                    "identity",
                    "registered",
                    "trunk",
                    "trunk_head",
                    "trunk_tree",
                    "layers",
                }
            ),
        )
        native_stack = ExpectedNativeStack(
            identity=_optional_string(
                stack_data["identity"], "expected_native_stack.identity"
            ),
            registered=_boolean(
                stack_data["registered"], "expected_native_stack.registered"
            ),
            trunk=_string(stack_data["trunk"], "expected_native_stack.trunk"),
            trunk_head=_string(
                stack_data["trunk_head"], "expected_native_stack.trunk_head"
            ),
            trunk_tree=_string(
                stack_data["trunk_tree"], "expected_native_stack.trunk_tree"
            ),
            layers=tuple(
                ExpectedNativeLayer(
                    branch=_string(item["branch"], "expected native layer.branch"),
                    head=_string(item["head"], "expected native layer.head"),
                    base=_string(item["base"], "expected native layer.base"),
                    merged=_boolean(item["merged"], "expected native layer.merged"),
                    queued=_boolean(item["queued"], "expected native layer.queued"),
                    needs_rebase=_boolean(
                        item["needs_rebase"], "expected native layer.needs_rebase"
                    ),
                    pull_request=_optional_integer(
                        item["pull_request"], "expected native layer.pull_request"
                    ),
                    pull_request_state=_optional_string(
                        item["pull_request_state"],
                        "expected native layer.pull_request_state",
                    ),
                )
                for item in (
                    _exact_object(
                        value,
                        "expected native layer",
                        frozenset(
                            {
                                "branch",
                                "head",
                                "base",
                                "merged",
                                "queued",
                                "needs_rebase",
                                "pull_request",
                                "pull_request_state",
                            }
                        ),
                    )
                    for value in _array(
                        stack_data["layers"], "expected_native_stack.layers"
                    )
                )
            ),
        )
        effects = tuple(
            MutationEffect(
                kind=EffectKind(_string(item["kind"], "effect.kind")),
                target=_string(item["target"], "effect.target"),
                field=_string(item["field"], "effect.field"),
                before=_frozen_value(item["before"]),
                after=_frozen_value(item["after"]),
            )
            for item in (
                _exact_object(
                    value,
                    "effect",
                    frozenset({"kind", "target", "field", "before", "after"}),
                )
                for value in _array(root["effects"], "effects")
            )
        )
        authority_data = _exact_object(
            root["authority"],
            "authority",
            frozenset(
                {
                    "operation",
                    "repository",
                    "remote",
                    "identities",
                    "branches",
                    "phases",
                    "effect_kinds",
                    "ready_for_review",
                    "merge_method",
                }
            ),
        )
        authority = AuthorityGrant(
            operation=StackOperation(
                _string(authority_data["operation"], "authority.operation")
            ),
            repository=_string(authority_data["repository"], "authority.repository"),
            remote=_string(authority_data["remote"], "authority.remote"),
            identities=_unique_strings(
                authority_data["identities"], "authority.identities"
            ),
            branches=_unique_strings(authority_data["branches"], "authority.branches"),
            phases=frozenset(
                TransitionPhase(item)
                for item in _unique_strings(
                    authority_data["phases"], "authority.phases"
                )
            ),
            effect_kinds=frozenset(
                EffectKind(item)
                for item in _unique_strings(
                    authority_data["effect_kinds"], "authority.effect_kinds"
                )
            ),
            ready_for_review=_unique_strings(
                authority_data["ready_for_review"], "authority.ready_for_review"
            ),
            merge_method=_optional_string(
                authority_data["merge_method"], "authority.merge_method"
            ),
        )
        merge_mode_value = root["merge_mode"]
        manifest = MutationManifest(
            operation=StackOperation(_string(root["operation"], "operation")),
            repository=_string(root["repository"], "repository"),
            remote=_string(root["remote"], "remote"),
            identities=_strings(root["identities"], "identities"),
            expected_refs=refs,
            expected_pull_requests=pull_requests,
            expected_native_stack=native_stack,
            enabled_phases=tuple(
                TransitionPhase(item)
                for item in _strings(root["enabled_phases"], "enabled_phases")
            ),
            merge_mode=(
                None
                if merge_mode_value is None
                else MergeMode(_string(merge_mode_value, "merge_mode"))
            ),
            merge_method=_optional_string(root["merge_method"], "merge_method"),
            effects=effects,
            evidence=_strings(root["evidence"], "evidence"),
            authority=authority,
            merge_prefix=tuple(
                _integer(item, "merge_prefix item")
                for item in _array(root["merge_prefix"], "merge_prefix")
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
        ready_for_review = pull_request.branch in authority.ready_for_review
        effects.append(
            MutationEffect(
                EffectKind.CREATE_PR
                if pull_request.state == "ABSENT"
                else EffectKind.UPDATE_PR,
                f"pr:{pull_request.number if pull_request.number is not None else pull_request.branch}",
                "record",
                None if pull_request.state == "ABSENT" else pull_request.record,
                pull_request.proposed_record(
                    expected_head=proposed_head,
                    expected_base=predecessor,
                    ready_for_review=ready_for_review,
                ),
            )
        )
        if ready_for_review and pull_request.draft is not False:
            effects.append(
                MutationEffect(
                    EffectKind.READY_PR,
                    f"pr:{pull_request.number if pull_request.number is not None else pull_request.branch}",
                    "draft",
                    pull_request.draft,
                    False,
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
            "identity",
            native_stack.identity if native_stack.registered else None,
            native_stack.identity,
        )
    )
    effects.append(
        MutationEffect(
            EffectKind.REGISTER_STACK,
            f"stack:{native_stack.identity or 'absent'}",
            "registered",
            native_stack.registered,
            True,
        )
    )
    effects.append(
        MutationEffect(
            EffectKind.REGISTER_STACK,
            f"stack:{native_stack.identity or 'absent'}",
            "order",
            native_stack.order if native_stack.registered else (),
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
        merge_method=None,
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
        merge_method=None,
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
        merge_method=None,
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
    merge_method: str | None,
    trunk_tree_before: str,
    trunk_tree_after: str,
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
    for label, tree in (
        ("current trunk", trunk_tree_before),
        ("landing trunk", trunk_tree_after),
    ):
        if len(tree) != 40 or any(
            character not in "0123456789abcdef" for character in tree
        ):
            raise ManifestError(f"{label} tree must be a full SHA")
    effects: list[MutationEffect] = []
    suffix = tuple(
        item
        for item in expected_pull_requests
        if item.state == "OPEN" and item.number not in prefix
    )
    ref_by_branch = {
        item.name.removeprefix("refs/heads/"): item for item in expected_refs
    }
    if suffix:
        unknown = tuple(
            item.branch
            for item in suffix
            if item.branch not in ref_by_branch
            or ref_by_branch[item.branch].old_sha
            == ref_by_branch[item.branch].proposed_sha
        )
        if unknown:
            raise ManifestError(
                "merge preview cannot approve unknown automatic suffix heads: "
                f"{unknown!r}"
            )
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
    effects.extend(
        (
            MutationEffect(
                EffectKind.REFRESH_TRUNK,
                f"ref:{native_stack.trunk}",
                "tree",
                trunk_tree_before,
                trunk_tree_after,
            ),
            MutationEffect(
                EffectKind.SYNC_STACK,
                f"stack:{native_stack.identity or 'absent'}",
                "open_order",
                native_stack.open_order,
                tuple(item.branch for item in suffix),
            ),
        )
    )
    predecessor = native_stack.trunk
    for pull_request in suffix:
        expected_ref = ref_by_branch[pull_request.branch]
        effects.extend(
            (
                MutationEffect(
                    EffectKind.PUSH_REF,
                    f"ref:{pull_request.branch}",
                    "sha",
                    expected_ref.old_sha,
                    expected_ref.proposed_sha,
                ),
                MutationEffect(
                    EffectKind.UPDATE_PR,
                    f"pr:{pull_request.number}",
                    "record",
                    pull_request.record,
                    _expected_pr_after(
                        pull_request,
                        expected_head=expected_ref.proposed_sha,
                        expected_base=predecessor,
                    ),
                ),
                MutationEffect(
                    EffectKind.SYNC_STACK,
                    f"stack:{native_stack.identity or 'absent'}:{pull_request.branch}",
                    "head",
                    expected_ref.old_sha,
                    expected_ref.proposed_sha,
                ),
            )
        )
        predecessor = pull_request.branch
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
        merge_method=merge_method,
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
        merge_method=None,
        effects=effects,
        evidence=tuple(evidence),
        authority=authority,
    )
    manifest.validate_complete()
    return manifest


def _matches_after(effect: MutationEffect, value: object) -> bool:
    if effect.kind is not EffectKind.CREATE_PR or effect.field != "record":
        return _exact_value_equal(value, effect.after)
    expected = effect.after
    if not isinstance(expected, tuple) or not isinstance(value, tuple):
        return False
    if len(expected) != len(value):
        return False
    if expected[0] is not None:
        return _exact_value_equal(value, expected)
    assigned = value[0]
    return (
        isinstance(assigned, int)
        and not isinstance(assigned, bool)
        and assigned > 0
        and _exact_value_equal(value[1:], expected[1:])
    )


def classify_readback(
    manifest: MutationManifest,
    observation: TransitionObservation,
) -> TransitionResult:
    observed = observation.as_mapping()
    missing = MISSING_OBSERVATION
    targets: list[TargetReadback] = []
    for effect in manifest.effects:
        value = observed.get(effect.key, missing)
        if _exact_value_equal(effect.before, effect.after) and _matches_after(
            effect, value
        ):
            disposition = TargetDisposition.UNCHANGED
        elif _matches_after(effect, value):
            disposition = TargetDisposition.CHANGED_AS_EXPECTED
        elif _exact_value_equal(value, effect.before):
            disposition = TargetDisposition.UNCHANGED
        else:
            disposition = TargetDisposition.CHANGED_UNEXPECTEDLY
        targets.append(
            TargetReadback(effect=effect, observed=value, disposition=disposition)
        )

    dispositions = {target.disposition for target in targets}
    if (
        manifest.operation is StackOperation.MERGE
        and manifest.merge_mode is MergeMode.QUEUE
        and TargetDisposition.CHANGED_UNEXPECTEDLY not in dispositions
    ):
        queue_effect = next(
            effect for effect in manifest.effects if effect.kind is EffectKind.QUEUE_PR
        )
        merge_effect = next(
            effect for effect in manifest.effects if effect.kind is EffectKind.MERGE_PR
        )
        automatic = tuple(
            effect
            for effect in manifest.effects
            if effect not in {queue_effect, merge_effect}
        )
        queue_value = observed.get(queue_effect.key, missing)
        merge_value = observed.get(merge_effect.key, missing)
        if (
            merge_value == merge_effect.after
            and queue_value in {queue_effect.before, queue_effect.after}
            and all(
                _matches_after(effect, observed.get(effect.key, missing))
                for effect in automatic
            )
        ):
            return TransitionResult(
                state=TransitionState.COMPLETED,
                operation=manifest.operation,
                identities=manifest.identities,
                evidence=manifest.evidence,
                targets=tuple(targets),
            )
        if (
            queue_value == queue_effect.after
            and merge_value == merge_effect.before
            and all(
                observed.get(effect.key, missing) == effect.before
                for effect in automatic
            )
        ):
            return TransitionResult(
                state=TransitionState.ADMITTED,
                operation=manifest.operation,
                identities=manifest.identities,
                evidence=manifest.evidence,
                targets=tuple(targets),
                next_action=(
                    "retain this approved fence through landing or cancellation; "
                    "do not admit the next pull request before fresh suffix gates"
                ),
                retained_manifest=manifest,
            )
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
    elif incomplete_mutations:
        state = TransitionState.PARTIAL
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
            "readback left pending mutations unchanged or diverged; generate a "
            "fresh manifest before retry"
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
        elif effect.kind is EffectKind.READY_PR:
            pr = prs_by_branch.get(identity)
            if pr is None and identity.isdigit():
                pr = prs_by_number.get(int(identity))
            observed = None if pr is None or pr.state == "ABSENT" else pr.draft
        elif effect.kind in {EffectKind.REGISTER_STACK, EffectKind.SYNC_STACK}:
            if effect.field == "identity":
                observed = (
                    current.expected_native_stack.identity
                    if current.expected_native_stack.registered
                    else None
                )
            elif effect.field == "registered":
                observed = current.expected_native_stack.registered
            elif effect.field == "order":
                observed = current.expected_native_stack.order
            elif effect.field == "open_order":
                observed = current.expected_native_stack.open_order
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
            if effect.field == "sha":
                observed = current.expected_native_stack.trunk_head
            elif effect.field == "tree":
                observed = current.expected_native_stack.trunk_tree
            else:
                raise ManifestError(f"unsupported trunk readback field: {effect.field}")
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
            retained_manifest=manifest,
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
    if manifest_to_json(current) != manifest_to_json(manifest):
        return TransitionResult(
            state=TransitionState.BLOCKED,
            operation=manifest.operation,
            identities=manifest.identities,
            evidence=manifest.evidence,
            blocker="manifest changed during pre-execution reread",
            next_action="review and approve a newly generated manifest",
            fresh_manifest_required=True,
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
                blocker=result.blocker
                or "post-command readback was partial or divergent",
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
