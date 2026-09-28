#!/usr/bin/env python3
"""The single command-line interface for carve-changesets."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from chain import (
    _complete_unpublished_native_layers,
    compare_chain,
    materialize_native_stack,
    validate_chain,
)
from command_argv import parse_argv_json
from common import (
    DEFAULT_PLAN_PATH,
    CommandError,
    branch_name_for,
    discover_test_command,
    ensure_clean_tree,
    git,
    init_plan,
    load_plan,
    validate_plan,
)
from db_compare import db_compare
from gh_stack import (
    REVIEWED_PROFILE_PATH,
    GhStackClient,
    GhStackError,
    GhStackProfile,
    StackCapability,
    probe_profile,
    reviewed_preview_profile,
)
from github import (
    github_repo_for_remote,
    pr_body_for,
    pr_create,
    pr_title_for,
    pull_request_by_number,
    pull_requests_for_source,
)
from metadata import SourceIdentity, embed_pr_metadata
from native_stack import (
    NativeStackError,
    NativeStackSnapshot,
    parse_native_stack,
    reconcile_native_stack,
)
from patch_apply import build_diff
from plan_checks import strict_apply_check, validate_plan_strict
from preflight import preflight
from propagate import (
    REMOTE_REF_ABSENT,
    _rehydrate_live,
    _target,
    _updated_title,
    merge_propagate_from_live,
    propagate_from_live,
    push_chain,
    push_changeset_branch,
)
from publication import remote_branch_head, verify_lineage_for_publication
from recovery import project_suffix_recovery_from_live, recover_suffix_from_live
from rehydrate import RehydrationError, adopt_legacy_chain, discover_changeset_heads
from squash_check import squash_check
from squash_ref import _resolve_base_source, create_squashed_ref
from status import status_from_live
from transitions import (
    ZERO_SHA,
    AuthorityGrant,
    EffectKind,
    ExpectedLineageRef,
    ExpectedNativeLayer,
    ExpectedNativeStack,
    ExpectedPullRequest,
    ExpectedRef,
    ManifestError,
    MergeMode,
    StackOperation,
    TransitionObservation,
    TransitionPhase,
    TransitionResult,
    TransitionState,
    execute_transition,
    manifest_from_json,
    manifest_to_json,
    preview_merge,
    preview_publish,
    preview_push,
    preview_recovery,
    preview_repair,
    required_capabilities,
    transition_result_to_json,
)
from validate import ChainValidation, validate_live_chain

READ_ONLY = "read-only"
LOCAL_MUTATING = "local-mutating"
REMOTE_MUTATING = "remote-mutating"


class StructuredTransitionError(CommandError):
    """A structured transition result was already emitted on stdout."""


COMMAND_MUTATION_CLASSES = {
    "preflight": LOCAL_MUTATING,
    "init-plan": LOCAL_MUTATING,
    "validate": LOCAL_MUTATING,
    "status": LOCAL_MUTATING,
    "create-chain": LOCAL_MUTATING,
    "compare": LOCAL_MUTATING,
    "validate-chain": LOCAL_MUTATING,
    "pr-create": REMOTE_MUTATING,
    "push-chain": REMOTE_MUTATING,
    "propagate": REMOTE_MUTATING,
    "merge-propagate": REMOTE_MUTATING,
    "recover-suffix": REMOTE_MUTATING,
    "db-compare": LOCAL_MUTATING,
    "hunk-preview": READ_ONLY,
    "squash-ref": LOCAL_MUTATING,
    "squash-check": LOCAL_MUTATING,
    "run": LOCAL_MUTATING,
}


def load_and_validate(plan_path: Path) -> Dict:
    plan = load_plan(plan_path)
    valid, errors = validate_plan(plan)
    if not valid:
        for error in errors:
            print(f"[ERROR] {error}")
        raise CommandError("Plan validation failed.")
    return plan


def _print_discovered_test_command() -> None:
    discovery = discover_test_command("")
    command = str(discovery.get("command") or "").strip()
    if command:
        print(f"[HINT] Discovered test command proposal: {command}")
    else:
        for suggestion in discovery.get("suggestions", []):
            print(f"[HINT] Test command proposal: {suggestion}")
    print("[NEXT] Pass approved argv explicitly as JSON with --test-argv.")


def _reject_legacy_flag(
    args: argparse.Namespace, *, attribute: str, old_flag: str, new_flag: str
) -> None:
    if getattr(args, attribute, None) is not None:
        raise CommandError(
            f"{old_flag} is no longer supported because command strings are "
            f"ambiguous. Use {new_flag} with a JSON argv array; use "
            '["sh", "-lc", "<approved shell command>"] only when shell '
            "semantics are intentional."
        )


def _parse_optional_argv(raw: Optional[str], *, label: str) -> List[str]:
    if raw is None:
        return []
    return parse_argv_json(raw, label=label)


def cmd_preflight(args: argparse.Namespace) -> None:
    _reject_legacy_flag(
        args,
        attribute="legacy_test_cmd",
        old_flag="--test-cmd",
        new_flag="--test-argv",
    )
    test_argv = _parse_optional_argv(args.test_argv, label="--test-argv")
    preflight(
        base=args.base,
        source=args.source,
        test_argv=test_argv,
        skip_tests=args.skip_tests,
        skip_merge_check=args.skip_merge_check,
        allow_source_behind_base=args.allow_source_behind_base,
        confirm_source_behind_base=args.confirm_source_behind_base,
        allow_recordkeeping_tracked=args.allow_recordkeeping_tracked,
    )


def cmd_init_plan(args: argparse.Namespace) -> None:
    _reject_legacy_flag(
        args,
        attribute="legacy_test_cmd",
        old_flag="--test-cmd",
        new_flag="--test-argv",
    )
    test_argv = _parse_optional_argv(args.test_argv, label="--test-argv")
    if not test_argv:
        _print_discovered_test_command()
    init_plan(
        plan_path=Path(args.plan),
        base=args.base,
        source=args.source,
        title=args.title,
        changesets=args.changesets,
        test_argv=test_argv,
        force=args.force,
    )
    print(f"[OK] Wrote plan template: {args.plan}")


def cmd_validate(args: argparse.Namespace) -> None:
    plan = load_plan(Path(args.plan))
    valid, errors = validate_plan(plan)
    if not valid:
        raise CommandError("Plan is invalid: " + "; ".join(errors))
    if args.strict:
        strict_ok, strict_errors, strict_warnings = validate_plan_strict(plan)
        for warning in strict_warnings:
            print(f"[WARN] {warning}")
        if not strict_ok:
            raise CommandError(
                "Strict plan validation failed: " + "; ".join(strict_errors)
            )
        strict_apply_check(plan)
        live_heads = discover_changeset_heads(
            Path.cwd(), plan["source_branch"], args.remote
        )
        if live_heads:
            pull_requests = (
                []
                if args.local_only
                else pull_requests_for_source(plan["source_branch"], remote=args.remote)
            )
            chain = adopt_legacy_chain(
                source_branch=plan["source_branch"],
                base_branch=plan["base_branch"],
                pull_requests=pull_requests,
                remote=args.remote,
            )
            result = validate_live_chain(
                chain,
                remote=args.remote,
                verify_live_remote=not args.local_only,
            )
            _print_live_diagnostics(result)
            if not result.valid:
                raise CommandError("Strict live chain validation failed.")
        print("[OK] Strict validation passed.")
        return
    print("[OK] Plan validation passed.")


def cmd_status(args: argparse.Namespace) -> None:
    pull_requests = (
        []
        if args.local_only or args.allow_stack_state_refresh
        else pull_requests_for_source(args.source, remote=args.remote)
    )
    pull_request_loader = None
    if args.allow_stack_state_refresh and not args.local_only:

        def load_pull_request(number: int):
            return pull_request_by_number(number, remote=args.remote)

        pull_request_loader = load_pull_request
    print(
        status_from_live(
            source_branch=args.source,
            base_branch=args.base,
            pull_requests=pull_requests,
            pull_request_loader=pull_request_loader,
            remote=args.remote,
            read_remote=not args.local_only,
            allow_stack_state_refresh=args.allow_stack_state_refresh,
        )
    )


def _print_live_diagnostics(result: ChainValidation) -> None:
    for diagnostic in result.diagnostics:
        print(
            f"[{diagnostic.severity.upper()}] {diagnostic.code}: {diagnostic.message}"
        )


def cmd_create_chain(args: argparse.Namespace) -> None:
    plan = load_and_validate(Path(args.plan))
    result = materialize_native_stack(
        plan,
        remote=args.remote,
        allow_local_stack_state=args.ack_local_stack_state,
        resume_argv=(
            "python3",
            str(Path(__file__).resolve()),
            "create-chain",
            "--plan",
            args.plan,
            "--remote",
            args.remote,
            "--ack-local-stack-state",
        ),
    )
    print(f"TRUTH PHASE  {result.truth_phase.value}")
    print(f"ACTIVE SOURCE  {result.active_source.trailer}")
    for layer in result.snapshot.layers:
        print(f"LAYER  {layer.branch} head={layer.head} base={layer.base}")
    print(f"CHAIN READY  {str(result.chain_ready).lower()}")
    approved_tests = list(plan.get("test_argv", []))
    if approved_tests:
        validate_argv = (
            "python3",
            str(Path(__file__).resolve()),
            "validate-chain",
            "--plan",
            args.plan,
            "--remote",
            args.remote,
            "--test-argv",
            json.dumps(approved_tests),
        )
        print(f"NEXT VALIDATE  {shlex.join(validate_argv)}")
    else:
        print("NEXT VALIDATE  blocked: plan.test_argv has no approved command")
    for layer in result.snapshot.layers:
        print(
            "NEXT REVIEW  "
            f"layer={layer.branch} comparison_base={layer.base} head={layer.head} "
            "skill=review-code-change"
        )
    compare_argv = (
        "python3",
        str(Path(__file__).resolve()),
        "compare",
        "--plan",
        args.plan,
    )
    print(f"NEXT EQUIVALENCE  {shlex.join(compare_argv)}")


def cmd_compare(args: argparse.Namespace) -> None:
    diffstat, names = compare_chain(load_and_validate(Path(args.plan)))
    print("[INFO] Diffstat vs source branch:")
    print(diffstat or "[OK] No diffstat differences detected.")
    print("[INFO] Name-status vs source branch:")
    print(names or "[OK] No name-status differences detected.")


def cmd_validate_chain(args: argparse.Namespace) -> None:
    _reject_legacy_flag(
        args,
        attribute="legacy_test_cmd",
        old_flag="--test-cmd",
        new_flag="--test-argv",
    )
    plan = load_and_validate(Path(args.plan))
    test_argv = (
        _parse_optional_argv(args.test_argv, label="--test-argv")
        if args.test_argv is not None
        else list(plan.get("test_argv", []))
    )
    validate_chain(plan, test_argv=test_argv)
    pull_requests = (
        []
        if args.local_only
        else pull_requests_for_source(plan["source_branch"], remote=args.remote)
    )
    chain = adopt_legacy_chain(
        source_branch=plan["source_branch"],
        base_branch=plan["base_branch"],
        pull_requests=pull_requests,
        remote=args.remote,
    )
    result = validate_live_chain(
        chain,
        remote=args.remote,
        verify_live_remote=not args.local_only,
    )
    _print_live_diagnostics(result)
    if not result.valid:
        raise CommandError("Live chain validation failed.")
    print("[OK] Live chain ancestry and source equivalence passed.")


def cmd_pr_create(args: argparse.Namespace) -> None:
    plan = load_and_validate(Path(args.plan))
    total = len(plan["changesets"])
    indices: List[int] = (
        list(range(1, total + 1)) if args.index is None else [args.index]
    )
    if not hasattr(args, "execute"):
        pr_create(plan, indices=indices, dry_run=args.dry_run, remote=args.remote)
        return
    if not args.execute:
        print(
            manifest_to_json(
                _publish_manifest(
                    plan,
                    remote=args.remote,
                    indices=indices,
                    allow_stack_state_refresh=args.allow_stack_state_refresh,
                    ready_for_review=args.ready_for_review,
                )
            ),
            end="",
        )
        return
    approved = _read_manifest(args.manifest)
    profile, blocked = _execution_preflight(
        approved,
        acknowledgements=(
            (args.ack_submit, "--ack-submit"),
            (
                not args.ready_for_review or args.ack_ready_for_review,
                "--ack-ready-for-review",
            ),
        ),
    )
    if blocked is not None:
        _finish_transition(blocked)
    assert profile is not None
    result = _execute_for_cli(
        approved,
        profile=profile,
        reread=lambda: _publish_manifest(
            plan,
            remote=args.remote,
            indices=indices,
            allow_stack_state_refresh=args.allow_stack_state_refresh,
            ready_for_review=args.ready_for_review,
        ),
        executor=_execute_publish_manifest,
        readback=lambda: _live_observation(
            approved,
            source=plan["source_branch"],
            base=plan["base_branch"],
            remote=args.remote,
        ),
    )
    _finish_transition(result)


def _native_snapshot_for_transition(
    *, source: str, base: str, remote: str, reconcile: bool = True
) -> NativeStackSnapshot:
    """Refresh and reconcile the authoritative native topology."""

    probe = probe_profile(cwd=Path.cwd())
    if (
        probe.status != "supported"
        or probe.profile is None
        or StackCapability.VIEW_JSON not in probe.profile.capabilities
    ):
        reason = probe.blocker.reason if probe.blocker is not None else probe.status
        raise CommandError(f"Native stack profile blocks transition preview: {reason}.")
    before = (
        git("symbolic-ref", "-q", "HEAD", check=False).stdout.strip(),
        git("rev-parse", "HEAD").stdout.strip(),
    )
    try:
        payload = GhStackClient(cwd=Path.cwd()).view_json(allow_state_refresh=True)
    finally:
        after = (
            git("symbolic-ref", "-q", "HEAD", check=False).stdout.strip(),
            git("rev-parse", "HEAD").stdout.strip(),
        )
        if after != before:
            raise CommandError(
                "gh stack view --json moved the checkout during transition preview"
            )
    trunk_head = remote_branch_head(remote, base)
    if trunk_head is None:
        raise CommandError(f"Selected native trunk {remote}/{base} is absent.")
    semantic_heads: dict[str, str] = {}
    raw_layers = payload.get("branches")
    if isinstance(raw_layers, list):
        for item in raw_layers:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            branch = item["name"]
            resolved = git(
                "rev-parse",
                "--verify",
                f"refs/heads/{branch}^{{commit}}",
                check=False,
            )
            if resolved.returncode == 0:
                semantic_heads[branch] = resolved.stdout.strip()
    snapshot = parse_native_stack(
        _complete_unpublished_native_layers(payload, semantic_heads),
        expected_trunk_branch=base,
        trunk_head=trunk_head,
    )
    if not snapshot.layers:
        raise CommandError(f"Native stack for {source!r} has no layers.")
    if not reconcile:
        return snapshot
    live_pull_requests = {
        layer.pull_request.number: pull_request_by_number(
            layer.pull_request.number, remote=remote
        )
        for layer in snapshot.layers
        if layer.pull_request is not None
    }
    remote_heads = {
        layer.branch: head
        for layer in snapshot.layers
        if (head := remote_branch_head(remote, layer.branch)) is not None
    }
    local_heads: dict[str, str] = {}
    for layer in snapshot.layers:
        resolved = git(
            "rev-parse",
            "--verify",
            f"refs/heads/{layer.branch}^{{commit}}",
            check=False,
        )
        if resolved.returncode == 0:
            local_heads[layer.branch] = resolved.stdout.strip()
    reconciled = reconcile_native_stack(
        snapshot,
        remote_heads=remote_heads,
        pull_requests=live_pull_requests,
        local_heads=local_heads,
    )
    observed = tuple(layer.branch for layer in reconciled.layers)
    if not observed:
        raise CommandError(f"Native stack for {source!r} has no layers.")
    return reconciled


def _require_stack_refresh_authority(allowed: bool) -> None:
    if not allowed:
        raise CommandError(
            "Transition preview requires --allow-stack-state-refresh before "
            "reading authoritative native topology."
        )


def _expected_native_stack(
    source: str, snapshot: NativeStackSnapshot
) -> ExpectedNativeStack:
    return ExpectedNativeStack(
        identity=source,
        registered=any(layer.pull_request is not None for layer in snapshot.layers),
        trunk=snapshot.trunk_branch,
        trunk_head=snapshot.trunk_head,
        trunk_tree=_commit_tree(snapshot.trunk_head, context="native trunk"),
        layers=tuple(
            ExpectedNativeLayer(
                branch=layer.branch,
                head=layer.head,
                base=layer.base,
                merged=layer.merged,
                queued=layer.queued,
                needs_rebase=layer.needs_rebase,
                pull_request=(
                    None if layer.pull_request is None else layer.pull_request.number
                ),
                pull_request_state=(
                    None if layer.pull_request is None else layer.pull_request.state
                ),
            )
            for layer in snapshot.layers
        ),
    )


def _push_manifest(plan: Dict, *, remote: str, allow_stack_state_refresh: bool = False):
    _require_stack_refresh_authority(allow_stack_state_refresh)
    source = plan["source_branch"]
    branches = tuple(
        branch_name_for(source, index)
        for index in range(1, len(plan["changesets"]) + 1)
    )
    repository = github_repo_for_remote(remote)
    refs: list[ExpectedRef] = []
    ref_evidence: list[str] = []
    for branch in branches:
        local = git(
            "rev-parse", "--verify", f"refs/heads/{branch}^{{commit}}", check=False
        )
        if local.returncode != 0:
            raise CommandError(f"Local changeset branch {branch!r} does not exist.")
        proposed = local.stdout.strip()
        old = remote_branch_head(remote, branch)
        refs.append(
            ExpectedRef(
                name=f"refs/heads/{branch}",
                old_sha=old or ZERO_SHA,
                proposed_sha=proposed,
            )
        )
        ref_evidence.append(f"{remote}/refs/heads/{branch}={old or 'absent'}")
    expected_heads = {
        expected_ref.name.removeprefix("refs/heads/"): expected_ref.proposed_sha
        for expected_ref in refs
    }
    source_lineage = verify_lineage_for_publication(
        branches,
        remote=remote,
        expected_heads=expected_heads,
    )
    evidence = [
        *(
            f"source lineage={identity.remote}/{identity.branch}@{identity.sha}"
            for identity in source_lineage
        ),
        *ref_evidence,
    ]
    base = plan["base_branch"]
    snapshot = _native_snapshot_for_transition(source=source, base=base, remote=remote)
    native_order = tuple(layer.branch for layer in snapshot.layers)
    if native_order != branches:
        raise CommandError(
            "Selected chain disagrees with authoritative native stack order: "
            f"selected {list(branches)!r}; native {list(native_order)!r}."
        )
    evidence.append(f"{remote}/refs/heads/{base}={snapshot.trunk_head}")
    evidence.append(f"native stack order={','.join(native_order)}")
    return preview_push(
        repository=repository,
        remote=remote,
        refs=refs,
        native_stack=_expected_native_stack(source, snapshot),
        authority=AuthorityGrant.push(
            repository=repository,
            remote=remote,
            branches=branches,
        ),
        evidence=evidence,
    )


def _publish_manifest(
    plan: Dict,
    *,
    remote: str,
    indices: Sequence[int] | None = None,
    allow_stack_state_refresh: bool = False,
    ready_for_review: bool = False,
):
    push = _push_manifest(
        plan,
        remote=remote,
        allow_stack_state_refresh=allow_stack_state_refresh,
    )
    live_by_branch = {}
    for item in pull_requests_for_source(plan["source_branch"], remote=remote):
        if item.head_branch in live_by_branch:
            raise CommandError(
                f"Multiple pull requests claim changeset branch {item.head_branch!r}."
            )
        live_by_branch[item.head_branch] = item
    total = len(plan["changesets"])
    selected_indices = (
        tuple(indices) if indices is not None else tuple(range(1, total + 1))
    )
    if any(index < 1 or index > total for index in selected_indices):
        raise CommandError(f"--index must be between 1 and {total}.")
    selected = set(selected_indices)
    expected_pull_requests: list[ExpectedPullRequest] = []
    for index, changeset in enumerate(plan["changesets"], start=1):
        if index not in selected:
            continue
        branch = branch_name_for(plan["source_branch"], index)
        live = live_by_branch.get(branch)
        expected_pull_requests.append(
            ExpectedPullRequest(
                number=None if live is None else live.number,
                branch=branch,
                head=None if live is None else live.head_sha,
                base=None if live is None else live.base_branch,
                state="ABSENT" if live is None else live.state.upper(),
                draft=None if live is None else live.draft,
                queued=None if live is None else live.queued,
                auto_merge=None if live is None else live.auto_merge,
                title=pr_title_for(plan["feature_title"], index, total),
                body=pr_body_for(plan, index, total, changeset),
                current_title=None if live is None else live.title,
                current_body=None if live is None else live.body,
                merge_state_status=(None if live is None else live.merge_state_status),
            )
        )
    return preview_publish(
        repository=github_repo_for_remote(remote),
        remote=remote,
        refs=tuple(
            expected_ref
            for expected_ref in push.expected_refs
            if expected_ref.name.removeprefix("refs/heads/")
            in {item.branch for item in expected_pull_requests}
        ),
        pull_requests=expected_pull_requests,
        native_stack=push.expected_native_stack,
        authority=AuthorityGrant.publish(
            repository=github_repo_for_remote(remote),
            remote=remote,
            branches=tuple(item.branch for item in expected_pull_requests),
            pull_requests=expected_pull_requests,
            ready_for_review=(
                tuple(
                    item.branch
                    for item in expected_pull_requests
                    if item.draft is not False
                )
                if ready_for_review
                else ()
            ),
        ),
        evidence=(
            *push.evidence,
            *(
                f"GitHub PR {item.branch}={item.state}"
                for item in expected_pull_requests
            ),
        ),
    )


def _live_manifest_inputs(
    *,
    source: str,
    base: str | None,
    remote: str,
    records,
    pull_requests,
    native_snapshot: NativeStackSnapshot,
):
    selected_base = base or "main"
    if native_snapshot.trunk_branch != selected_base:
        raise CommandError(
            f"Native trunk {native_snapshot.trunk_branch!r} disagrees with selected "
            f"base {selected_base!r}."
        )
    native_by_branch = {layer.branch: layer for layer in native_snapshot.layers}
    selected_branches = tuple(record.branch for record in records)
    missing = tuple(
        branch for branch in selected_branches if branch not in native_by_branch
    )
    if missing:
        raise CommandError(
            f"Selected layers are absent from authoritative native topology: {missing!r}."
        )
    trunk_head = native_snapshot.trunk_head
    refs: list[ExpectedRef] = []
    expected_pull_requests: list[ExpectedPullRequest] = []
    evidence: list[str] = [f"{remote}/refs/heads/{selected_base}={trunk_head}"]
    for record in records:
        old = remote_branch_head(remote, record.branch)
        native_head = native_by_branch[record.branch].head
        if record.head != native_head:
            raise CommandError(
                f"Live chain head for {record.branch} is {record.head}; native head is "
                f"{native_head}."
            )
        refs.append(
            ExpectedRef(
                name=f"refs/heads/{record.branch}",
                old_sha=old or ZERO_SHA,
                proposed_sha=native_head,
            )
        )
        evidence.append(f"{remote}/refs/heads/{record.branch}={old or 'absent'}")
        if record.pr_number is None or record.pr_number not in pull_requests:
            raise CommandError(
                f"Changeset {record.position} has no exact live pull-request state."
            )
        live = pull_requests[record.pr_number]
        expected_pull_requests.append(
            ExpectedPullRequest(
                number=live.number,
                branch=live.head_branch,
                head=live.head_sha,
                base=live.base_branch,
                state=live.state.upper(),
                draft=live.draft,
                queued=live.queued,
                auto_merge=live.auto_merge,
                title=live.title,
                body=live.body,
                current_title=live.title,
                current_body=live.body,
                merge_state_status=live.merge_state_status,
            )
        )
        evidence.append(
            f"GitHub PR #{live.number}={live.state.upper()}@{live.head_sha}"
        )
    return (
        tuple(refs),
        tuple(expected_pull_requests),
        _expected_native_stack(source, native_snapshot),
        tuple(evidence),
    )


def _commit_tree(commit: str, *, context: str) -> str:
    resolved = git("rev-parse", "--verify", f"{commit}^{{tree}}", check=False)
    if resolved.returncode != 0:
        raise CommandError(f"Cannot resolve exact {context} tree for {commit}.")
    return resolved.stdout.strip()


def _expected_pull_request_from_live(live) -> ExpectedPullRequest:
    return ExpectedPullRequest(
        number=live.number,
        branch=live.head_branch,
        head=live.head_sha,
        base=live.base_branch,
        state=live.state.upper(),
        draft=live.draft,
        queued=live.queued,
        auto_merge=live.auto_merge,
        title=live.title,
        body=live.body,
        current_title=live.title,
        current_body=live.body,
        merge_state_status=live.merge_state_status,
    )


def _require_exact_native_membership(records, snapshot: NativeStackSnapshot) -> None:
    selected = tuple(record.branch for record in records)
    native = tuple(layer.branch for layer in snapshot.layers)
    if selected != native:
        raise CommandError(
            "Source chain membership and order disagree with authoritative native "
            f"topology: source {selected!r}; native {native!r}."
        )


def _repair_manifest(args: argparse.Namespace):
    _require_stack_refresh_authority(args.allow_stack_state_refresh)
    chain, pull_requests = _rehydrate_live(
        source=args.source, base=args.base, remote=args.remote
    )
    target, _pull_request = _target(
        chain, pull_requests, pr_number=args.pr, index=args.index
    )
    suffix = chain.changesets[target.position :]
    if not suffix:
        raise CommandError("The selected merged layer has no suffix to repair.")
    native_snapshot = _native_snapshot_for_transition(
        source=args.source,
        base=args.base or chain.base_branch,
        remote=args.remote,
    )
    _require_exact_native_membership(chain.changesets, native_snapshot)
    native_by_branch = {layer.branch: layer for layer in native_snapshot.layers}
    needs_rebase = tuple(
        record.branch
        for record in suffix
        if record.branch not in native_by_branch
        or native_by_branch[record.branch].needs_rebase
    )
    if needs_rebase:
        raise CommandError(
            "Repair preview is blocked because exact rewritten heads cannot be "
            f"derived without materialization: {needs_rebase!r}."
        )
    refs, prs, stack, evidence = _live_manifest_inputs(
        source=args.source,
        base=args.base or chain.base_branch,
        remote=args.remote,
        records=suffix,
        pull_requests=pull_requests,
        native_snapshot=native_snapshot,
    )
    record_by_branch = {record.branch: record for record in suffix}
    live_by_number = {item.number: item for item in pull_requests.values()}
    prs = tuple(
        replace(
            item,
            title=_updated_title(
                live_by_number[item.number],
                index=record_by_branch[item.branch].position,
                total=len(chain.changesets),
            ),
        )
        for item in prs
    )
    phases = frozenset(
        {
            TransitionPhase.REBASE_NO_TRUNK,
            TransitionPhase.PUSH,
            TransitionPhase.SYNC,
        }
    )
    effects = frozenset(
        {
            EffectKind.REBASE_BRANCH,
            EffectKind.PUSH_REF,
            EffectKind.UPDATE_PR,
            EffectKind.SYNC_STACK,
        }
    )
    identities = tuple(item.branch for item in prs)
    return preview_repair(
        repository=github_repo_for_remote(args.remote),
        remote=args.remote,
        refs=refs,
        pull_requests=prs,
        native_stack=stack,
        authority=AuthorityGrant(
            operation=StackOperation.REPAIR,
            repository=github_repo_for_remote(args.remote),
            remote=args.remote,
            identities=identities,
            branches=identities,
            phases=phases,
            effect_kinds=effects,
        ),
        evidence=evidence,
    )


def _merge_manifest(args: argparse.Namespace):
    _require_stack_refresh_authority(args.allow_stack_state_refresh)
    chain, pull_requests = _rehydrate_live(
        source=args.source, base=args.base, remote=args.remote
    )
    target, selected_pr = _target(
        chain, pull_requests, pr_number=args.pr, index=args.index
    )
    native_snapshot = _native_snapshot_for_transition(
        source=args.source,
        base=args.base or chain.base_branch,
        remote=args.remote,
    )
    _require_exact_native_membership(chain.changesets, native_snapshot)
    native_open = native_snapshot.open_suffix
    open_branches = tuple(layer.branch for layer in native_open)
    if target.branch not in open_branches:
        raise CommandError(
            f"Merge target {target.branch!r} is not an open native layer "
            f"in {open_branches!r}."
        )
    mode = MergeMode(args.merge_mode)
    merge_method = args.method if mode is MergeMode.DIRECT else None
    boundary = open_branches.index(target.branch)
    if mode is MergeMode.QUEUE and boundary != 0:
        bottom = open_branches[0] if open_branches else "none"
        raise CommandError(
            f"Queue merge target {target.branch!r} is not the bottom open native "
            f"layer ({bottom!r})."
        )
    prefix_layers = (
        native_open[: boundary + 1] if mode is MergeMode.DIRECT else native_open[:1]
    )
    records_by_branch = {record.branch: record for record in chain.changesets}
    affected_records = tuple(
        records_by_branch[layer.branch] for layer in native_snapshot.layers
    )
    refs, prs, stack, evidence = _live_manifest_inputs(
        source=args.source,
        base=args.base or chain.base_branch,
        remote=args.remote,
        records=affected_records,
        pull_requests=pull_requests,
        native_snapshot=native_snapshot,
    )
    phases = (
        frozenset(
            {TransitionPhase.DIRECT_MERGE}
            | (
                {TransitionPhase.SYNC}
                if len(prefix_layers) < len(native_open)
                else set()
            )
        )
        if mode is MergeMode.DIRECT
        else frozenset({TransitionPhase.QUEUE_MERGE})
    )
    effects = {EffectKind.MERGE_PR, EffectKind.REFRESH_TRUNK, EffectKind.SYNC_STACK}
    if mode is MergeMode.QUEUE:
        effects.add(EffectKind.QUEUE_PR)
    if len(prefix_layers) < len(native_open):
        effects.update({EffectKind.PUSH_REF, EffectKind.UPDATE_PR})
    identities = tuple(item.branch for item in prs)
    pr_by_branch = {item.branch: item for item in prs}
    prefix_numbers = tuple(pr_by_branch[layer.branch].number for layer in prefix_layers)
    trunk_tree_before = _commit_tree(stack.trunk_head, context="current trunk")
    trunk_tree_after = _commit_tree(selected_pr.head_sha, context="landing trunk")
    return preview_merge(
        repository=github_repo_for_remote(args.remote),
        remote=args.remote,
        refs=refs,
        pull_requests=prs,
        native_stack=stack,
        prefix_numbers=prefix_numbers,
        merge_mode=mode,
        merge_method=merge_method,
        trunk_tree_before=trunk_tree_before,
        trunk_tree_after=trunk_tree_after,
        authority=AuthorityGrant(
            operation=StackOperation.MERGE,
            repository=github_repo_for_remote(args.remote),
            remote=args.remote,
            identities=identities,
            branches=(*identities, stack.trunk),
            phases=phases,
            effect_kinds=frozenset(effects),
            merge_method=merge_method,
        ),
        evidence=(
            *evidence,
            f"{args.remote}/refs/heads/{stack.trunk} tree={trunk_tree_before}",
            f"landing tree={trunk_tree_after}",
        ),
    )


def _merge_observation(
    approved,
    *,
    source: str,
    base: str | None,
    remote: str,
) -> TransitionObservation:
    _chain, pull_requests = _rehydrate_live(source=source, base=base, remote=remote)
    native_snapshot = _native_snapshot_for_transition(
        source=source,
        base=base or approved.expected_native_stack.trunk,
        remote=remote,
    )
    native_by_branch = {layer.branch: layer for layer in native_snapshot.layers}
    values: list[tuple[str, object]] = []
    for effect in approved.effects:
        identity = effect.target.partition(":")[2]
        if effect.kind in {EffectKind.MERGE_PR, EffectKind.QUEUE_PR}:
            number = int(identity)
            live = pull_requests.get(number)
            if live is None:
                live = pull_request_by_number(number, remote=remote)
            observed: object = (
                live.state.upper() if effect.field == "state" else live.queued
            )
        elif effect.kind is EffectKind.REFRESH_TRUNK and effect.field == "tree":
            observed = _commit_tree(
                native_snapshot.trunk_head, context="observed trunk"
            )
        elif effect.kind is EffectKind.SYNC_STACK and effect.field == "open_order":
            observed = tuple(
                layer.branch for layer in native_snapshot.layers if not layer.merged
            )
        elif effect.kind is EffectKind.SYNC_STACK and effect.field == "head":
            observed = native_by_branch[identity.rpartition(":")[2]].head
        elif effect.kind is EffectKind.PUSH_REF:
            observed = remote_branch_head(remote, identity) or ZERO_SHA
        elif effect.kind is EffectKind.UPDATE_PR:
            number = int(identity)
            live = pull_requests.get(number)
            if live is None:
                live = pull_request_by_number(number, remote=remote)
            observed = _expected_pull_request_from_live(live).record
        else:
            raise ManifestError(
                f"unsupported merge readback effect: {effect.kind.value}:{effect.field}"
            )
        values.append((effect.key, observed))
    return TransitionObservation(values=tuple(values))


def _recovery_manifest(args: argparse.Namespace):
    _require_stack_refresh_authority(args.allow_stack_state_refresh)
    projection = project_suffix_recovery_from_live(
        source=args.source,
        base=args.base,
        from_index=args.from_index,
        successor_branch=args.successor_source,
        successor_sha=args.successor_sha,
        remote=args.remote,
    )
    chain = projection.chain
    pull_requests = {item.number: item for item in projection.pull_requests}
    suffix = projection.suffix
    native_snapshot = _native_snapshot_for_transition(
        source=args.source,
        base=args.base,
        remote=args.remote,
    )
    _require_exact_native_membership(chain.changesets, native_snapshot)
    refs, prs, stack, evidence = _live_manifest_inputs(
        source=args.source,
        base=args.base,
        remote=args.remote,
        records=suffix,
        pull_requests=pull_requests,
        native_snapshot=native_snapshot,
    )
    refs = tuple(
        replace(
            item,
            proposed_sha=projection.candidates[item.name.removeprefix("refs/heads/")],
        )
        for item in refs
    )
    prs = tuple(
        replace(
            item,
            body=embed_pr_metadata(
                item.current_body or item.body,
                projection.metadata[item.branch],
            ),
        )
        for item in prs
    )
    lineage = tuple(
        ExpectedLineageRef(item.remote, item.branch, item.sha)
        for item in projection.target_lineage
    )
    identities = tuple(
        dict.fromkeys(
            (
                *(item.branch for item in prs),
                *(item.branch for item in lineage),
            )
        )
    )
    phases = frozenset(
        {
            TransitionPhase.TRUNK_REFRESH,
            TransitionPhase.REBASE_NO_TRUNK,
            TransitionPhase.PUSH,
            TransitionPhase.SYNC,
        }
    )
    effects = frozenset(
        {
            EffectKind.REFRESH_TRUNK,
            EffectKind.REBASE_BRANCH,
            EffectKind.PUSH_REF,
            EffectKind.UPDATE_PR,
            EffectKind.SYNC_STACK,
        }
    )
    repository = github_repo_for_remote(args.remote)
    return preview_recovery(
        repository=repository,
        remote=args.remote,
        refs=refs,
        pull_requests=prs,
        native_stack=stack,
        authority=AuthorityGrant(
            operation=StackOperation.RECOVER,
            repository=repository,
            remote=args.remote,
            identities=identities,
            branches=tuple(item.branch for item in prs),
            phases=phases,
            effect_kinds=effects,
        ),
        evidence=(
            *evidence,
            f"successor={args.remote}/{args.successor_source}@{args.successor_sha}",
            *(
                f"projected recovery head {branch}={head}"
                for branch, head in projection.candidates.items()
            ),
            *(
                f"source lineage={item.remote}/{item.branch}@{item.sha}"
                for item in lineage
            ),
        ),
        lineage=lineage,
        identities=identities,
    )


def _reviewed_profile():
    try:
        payload = json.loads(REVIEWED_PROFILE_PATH.read_text())
        source_revision = payload["source_revision"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise GhStackError("reviewed gh stack profile has no source revision") from exc
    if not isinstance(source_revision, str):
        raise GhStackError("reviewed gh stack profile source revision is invalid")
    return reviewed_preview_profile(source_revision, reviewed_profile=payload)


def _read_manifest(path: str | None):
    if path is None:
        raise CommandError("--execute requires --manifest with the approved preview")
    try:
        return manifest_from_json(Path(path).read_text())
    except OSError as exc:
        raise CommandError(f"Approved manifest is unreadable: {path}") from exc


def _blocked_manifest_result(
    manifest,
    *,
    blocker: str,
    next_action: str,
) -> TransitionResult:
    return TransitionResult(
        state=TransitionState.BLOCKED,
        operation=manifest.operation,
        identities=manifest.identities,
        evidence=manifest.evidence,
        blocker=blocker,
        next_action=next_action,
        retained_manifest=manifest,
    )


def _execution_preflight(
    manifest,
    *,
    acknowledgements: Sequence[tuple[bool, str]],
) -> tuple[GhStackProfile | None, TransitionResult | None]:
    missing_acknowledgements = tuple(
        flag for acknowledged, flag in acknowledgements if not acknowledged
    )
    if missing_acknowledgements:
        required = ", ".join(missing_acknowledgements)
        return None, _blocked_manifest_result(
            manifest,
            blocker=f"--execute requires {required}",
            next_action="confirm the exact authority grant and retry this manifest",
        )
    try:
        profile = _reviewed_profile()
    except GhStackError as exc:
        return None, _blocked_manifest_result(
            manifest,
            blocker=f"reviewed gh stack profile is unavailable: {exc}",
            next_action="install a repository-tested compatible gh-stack profile",
        )
    missing = (
        required_capabilities(
            manifest.operation,
            phases=manifest.enabled_phases,
            merge_mode=manifest.merge_mode,
        )
        - profile.capabilities
    )
    if missing:
        names = ", ".join(sorted(item.value for item in missing))
        return None, _blocked_manifest_result(
            manifest,
            blocker=(
                f"gh stack profile {profile.version} lacks: {names}; "
                "no state was refreshed"
            ),
            next_action="install a repository-tested compatible gh-stack profile",
        )
    return profile, None


def _execute_for_cli(*args, **kwargs) -> TransitionResult:
    with redirect_stdout(sys.stderr):
        return execute_transition(*args, **kwargs)


def _execute_push_manifest(manifest) -> None:
    """Apply only the exact ref leases approved by one push manifest."""

    manifest.validate_complete()
    if manifest.enabled_phases != (TransitionPhase.PUSH,):
        raise CommandError("push executor requires an exact push-only manifest")
    branches = tuple(
        expected_ref.name.removeprefix("refs/heads/")
        for expected_ref in manifest.expected_refs
    )
    expected_heads: dict[str, str] = {}
    for expected_ref in manifest.expected_refs:
        branch = expected_ref.name.removeprefix("refs/heads/")
        local = git(
            "rev-parse",
            "--verify",
            f"refs/heads/{branch}^{{commit}}",
            check=False,
        )
        if local.returncode != 0 or local.stdout.strip() != expected_ref.proposed_sha:
            observed = local.stdout.strip() if local.returncode == 0 else "absent"
            raise CommandError(
                f"Local branch {branch} is {observed}; approved manifest requires "
                f"{expected_ref.proposed_sha}."
            )
        expected_heads[branch] = expected_ref.proposed_sha
    verify_lineage_for_publication(
        branches,
        remote=manifest.remote,
        expected_heads=expected_heads,
    )
    for expected_ref in manifest.expected_refs:
        branch = expected_ref.name.removeprefix("refs/heads/")
        push_changeset_branch(
            branch,
            remote=manifest.remote,
            dry_run=False,
            expected_remote_head=(
                REMOTE_REF_ABSENT
                if expected_ref.old_sha == ZERO_SHA
                else expected_ref.old_sha
            ),
            local_ref=expected_ref.proposed_sha,
        )
        verify_lineage_for_publication(
            branches,
            remote=manifest.remote,
            expected_heads=expected_heads,
        )


def _approved_pr_text(manifest) -> dict[int, tuple[str, str]]:
    return {
        item.number: (item.title, item.body)
        for item in manifest.expected_pull_requests
        if item.number is not None
    }


def _approved_ref_transitions(manifest) -> dict[str, tuple[str, str]]:
    return {
        item.name.removeprefix("refs/heads/"): (item.old_sha, item.proposed_sha)
        for item in manifest.expected_refs
    }


def _execute_publish_manifest(_manifest) -> None:
    """Fail closed until native submit can consume every declared effect."""

    raise CommandError(
        "manifest-native submit executor is unavailable; no publish effect was applied"
    )


def _execute_merge_manifest(manifest) -> None:
    """Fail closed until native merge can bind mode and the complete PR prefix."""

    mode = "unselected" if manifest.merge_mode is None else manifest.merge_mode.value
    prefix = ", ".join(str(number) for number in manifest.merge_prefix) or "empty"
    raise CommandError(
        f"manifest-native {mode} merge executor is unavailable for exact prefix "
        f"{prefix}; no merge effect was applied"
    )


def _live_observation(
    approved,
    *,
    source: str,
    base: str | None,
    remote: str,
) -> TransitionObservation:
    """Read approved targets without requiring live state to form a new preview."""

    native = _native_snapshot_for_transition(
        source=source,
        base=base or approved.expected_native_stack.trunk,
        remote=remote,
        reconcile=False,
    )
    listed = pull_requests_for_source(source, remote=remote)
    prs_by_branch = {item.head_branch: item for item in listed}
    prs_by_number = {item.number: item for item in listed}

    def pull_request(identity: str):
        if identity.isdigit():
            number = int(identity)
            if number not in prs_by_number:
                prs_by_number[number] = pull_request_by_number(number, remote=remote)
            return prs_by_number[number]
        return prs_by_branch.get(identity)

    values: list[tuple[str, object]] = []
    for effect in approved.effects:
        identity = effect.target.partition(":")[2]
        if effect.kind is EffectKind.PUSH_REF:
            observed: object = remote_branch_head(remote, identity) or ZERO_SHA
        elif effect.kind is EffectKind.REBASE_BRANCH:
            resolved = git(
                "rev-parse",
                "--verify",
                f"refs/heads/{identity}^{{commit}}",
                check=False,
            )
            observed = resolved.stdout.strip() if resolved.returncode == 0 else ZERO_SHA
        elif effect.kind in {EffectKind.CREATE_PR, EffectKind.UPDATE_PR}:
            live = pull_request(identity)
            observed = (
                None if live is None else _expected_pull_request_from_live(live).record
            )
        elif effect.kind is EffectKind.DISABLE_AUTO_MERGE:
            live = pull_request(identity)
            observed = None if live is None else live.auto_merge
        elif effect.kind is EffectKind.READY_PR:
            live = pull_request(identity)
            observed = None if live is None else live.draft
        elif effect.kind in {EffectKind.REGISTER_STACK, EffectKind.SYNC_STACK}:
            if effect.field == "identity":
                observed = (
                    source
                    if any(layer.pull_request for layer in native.layers)
                    else None
                )
            elif effect.field == "registered":
                observed = any(layer.pull_request for layer in native.layers)
            elif effect.field == "order":
                observed = tuple(layer.branch for layer in native.layers)
            elif effect.field == "open_order":
                observed = tuple(
                    layer.branch for layer in native.layers if not layer.merged
                )
            elif effect.field == "head":
                branch = identity.rpartition(":")[2]
                observed = remote_branch_head(remote, branch) or ZERO_SHA
            else:
                raise ManifestError(
                    f"unsupported native-stack readback field: {effect.field}"
                )
        elif effect.kind in {EffectKind.MERGE_PR, EffectKind.QUEUE_PR}:
            live = pull_request(identity)
            observed = (
                None
                if live is None
                else live.state.upper()
                if effect.field == "state"
                else live.queued
            )
        elif effect.kind is EffectKind.REFRESH_TRUNK:
            observed = (
                native.trunk_head
                if effect.field == "sha"
                else _commit_tree(native.trunk_head, context="observed trunk")
            )
        else:  # pragma: no cover
            raise ManifestError(f"unsupported readback effect: {effect.kind.value}")
        values.append((effect.key, observed))
    return TransitionObservation(values=tuple(values))


def _push_observation(manifest) -> TransitionObservation:
    values: list[tuple[str, object]] = []
    for effect in manifest.effects:
        if effect.target.startswith("ref:") and effect.field == "sha":
            branch = effect.target.removeprefix("ref:")
            values.append(
                (effect.key, remote_branch_head(manifest.remote, branch) or ZERO_SHA)
            )
    return TransitionObservation(values=tuple(values))


def _print_transition_result(result: TransitionResult) -> None:
    print(transition_result_to_json(result), end="")


def _finish_transition(result: TransitionResult) -> None:
    _print_transition_result(result)
    if (
        result.blocker
        or result.state
        in {
            TransitionState.BLOCKED,
            TransitionState.PARTIAL,
            TransitionState.DIVERGED,
        }
        or result.fresh_manifest_required
    ):
        raise StructuredTransitionError(
            result.blocker
            or "transition readback requires a fresh manifest before continuing"
        )


def cmd_push_chain(args: argparse.Namespace) -> None:
    plan = load_and_validate(Path(args.plan))
    if not hasattr(args, "execute"):
        push_chain(plan, remote=args.remote, dry_run=args.dry_run)
        return
    if not args.execute:
        print(
            manifest_to_json(
                _push_manifest(
                    plan,
                    remote=args.remote,
                    allow_stack_state_refresh=args.allow_stack_state_refresh,
                )
            ),
            end="",
        )
        return
    approved = _read_manifest(args.manifest)
    profile, blocked = _execution_preflight(
        approved,
        acknowledgements=((args.ack_push, "--ack-push"),),
    )
    if blocked is not None:
        _finish_transition(blocked)
    assert profile is not None
    result = _execute_for_cli(
        approved,
        profile=profile,
        reread=lambda: _push_manifest(
            plan,
            remote=args.remote,
            allow_stack_state_refresh=args.allow_stack_state_refresh,
        ),
        executor=_execute_push_manifest,
        readback=lambda: _push_observation(approved),
    )
    _finish_transition(result)


def cmd_propagate(args: argparse.Namespace) -> None:
    if not hasattr(args, "execute"):
        propagate_from_live(
            source=args.source,
            base=args.base,
            pr_number=args.pr,
            index=args.index,
            strategy=args.strategy,
            remote=args.remote,
            dry_run=args.dry_run,
            authority_acknowledged=args.ack_merge_and_propagate,
        )
        return
    if not args.execute:
        print(manifest_to_json(_repair_manifest(args)), end="")
        return
    approved = _read_manifest(args.manifest)
    profile, blocked = _execution_preflight(
        approved,
        acknowledgements=((args.ack_repair, "--ack-repair"),),
    )
    if blocked is not None:
        _finish_transition(blocked)
    assert profile is not None
    result = _execute_for_cli(
        approved,
        profile=profile,
        reread=lambda: _repair_manifest(args),
        executor=lambda manifest: propagate_from_live(
            source=args.source,
            base=args.base,
            pr_number=args.pr,
            index=args.index,
            strategy=args.strategy,
            remote=args.remote,
            dry_run=False,
            authority_acknowledged=True,
            approved_pr_text=_approved_pr_text(manifest),
            approved_ref_transitions=_approved_ref_transitions(manifest),
        ),
        readback=lambda: _live_observation(
            approved,
            source=args.source,
            base=args.base,
            remote=args.remote,
        ),
    )
    _finish_transition(result)


def cmd_merge_propagate(args: argparse.Namespace) -> None:
    if not hasattr(args, "execute"):
        merge_propagate_from_live(
            source=args.source,
            base=args.base,
            pr_number=args.pr,
            index=args.index,
            strategy=args.strategy,
            method=args.method,
            remote=args.remote,
            dry_run=args.dry_run,
            authority_acknowledged=args.ack_merge_and_propagate,
        )
        return
    mode = MergeMode(args.merge_mode)
    acknowledgement = (
        args.ack_queue_merge if mode is MergeMode.QUEUE else args.ack_direct_merge
    )
    if not args.execute:
        print(manifest_to_json(_merge_manifest(args)), end="")
        return
    approved = _read_manifest(args.manifest)
    profile, blocked = _execution_preflight(
        approved,
        acknowledgements=(
            (
                acknowledgement,
                (
                    "--ack-queue-merge"
                    if mode is MergeMode.QUEUE
                    else "--ack-direct-merge"
                ),
            ),
        ),
    )
    if blocked is not None:
        _finish_transition(blocked)
    assert profile is not None
    result = _execute_for_cli(
        approved,
        profile=profile,
        reread=lambda: _merge_manifest(args),
        executor=_execute_merge_manifest,
        readback=lambda: _merge_observation(
            approved,
            source=args.source,
            base=args.base,
            remote=args.remote,
        ),
    )
    _finish_transition(result)


def cmd_recover_suffix(args: argparse.Namespace) -> None:
    if not hasattr(args, "execute"):
        recover_suffix_from_live(
            source=args.source,
            base=args.base,
            from_index=args.from_index,
            successor_branch=args.successor_source,
            successor_sha=args.successor_sha,
            remote=args.remote,
            dry_run=args.dry_run,
            authority_acknowledged=args.ack_suffix_recovery,
        )
        return
    if not args.execute:
        print(manifest_to_json(_recovery_manifest(args)), end="")
        return
    approved = _read_manifest(args.manifest)
    profile, blocked = _execution_preflight(
        approved,
        acknowledgements=((args.ack_suffix_recovery, "--ack-suffix-recovery"),),
    )
    if blocked is not None:
        _finish_transition(blocked)
    assert profile is not None
    result = _execute_for_cli(
        approved,
        profile=profile,
        reread=lambda: _recovery_manifest(args),
        executor=lambda manifest: recover_suffix_from_live(
            source=args.source,
            base=args.base,
            from_index=args.from_index,
            successor_branch=args.successor_source,
            successor_sha=args.successor_sha,
            remote=args.remote,
            dry_run=False,
            authority_acknowledged=True,
            approved_pr_text=_approved_pr_text(manifest),
            approved_ref_transitions=_approved_ref_transitions(manifest),
            approved_lineage=tuple(
                SourceIdentity(item.remote, item.branch, item.sha)
                for item in manifest.expected_lineage
            ),
        ),
        readback=lambda: _live_observation(
            approved,
            source=args.successor_source,
            base=args.base,
            remote=args.remote,
        ),
    )
    _finish_transition(result)


def cmd_db_compare(args: argparse.Namespace) -> None:
    _reject_legacy_flag(
        args,
        attribute="legacy_source_cmd",
        old_flag="--source-cmd",
        new_flag="--source-argv",
    )
    _reject_legacy_flag(
        args,
        attribute="legacy_chain_cmd",
        old_flag="--chain-cmd",
        new_flag="--chain-argv",
    )
    if args.source_argv is None or args.chain_argv is None:
        raise CommandError(
            "db-compare requires both --source-argv and --chain-argv JSON arrays."
        )
    source_argv = parse_argv_json(args.source_argv, label="--source-argv")
    chain_argv = parse_argv_json(args.chain_argv, label="--chain-argv")
    db_compare(
        load_and_validate(Path(args.plan)),
        source_argv=source_argv,
        chain_argv=chain_argv,
        keep_output_dir=(
            Path(args.keep_output_dir) if args.keep_output_dir is not None else None
        ),
    )


def cmd_hunk_preview(args: argparse.Namespace) -> None:
    base = args.base
    source = args.source
    plan_path = Path(args.plan)
    if plan_path.exists() and (not base or not source):
        plan = load_plan(plan_path)
        base = base or plan.get("base_branch", "")
        source = source or plan.get("source_branch", "")
    if not base or not source:
        raise CommandError("hunk-preview requires --base and --source or a plan.")
    matches = [
        item
        for item in build_diff(base, source)
        if args.file in (item.new_path, item.old_path)
    ]
    if not matches:
        raise CommandError(f"No diff hunks found for file: {args.file}")
    for item in matches:
        print(f"[FILE] {item.new_path or item.old_path}")
        for index, hunk in enumerate(item.hunks, start=1):
            if args.contains and not all(
                value in hunk.body_text for value in args.contains
            ):
                continue
            if args.excludes and any(
                value in hunk.body_text for value in args.excludes
            ):
                continue
            print(f"[HUNK {index}] {hunk.header}")
            print("\n".join(hunk.lines[1:]))


def cmd_squash_ref(args: argparse.Namespace) -> None:
    base, source = _resolve_base_source(
        plan_path=Path(args.plan), base=args.base, source=args.source
    )
    create_squashed_ref(
        base=base,
        source=source,
        reuse_existing=args.reuse_existing,
        recreate=args.recreate,
    )


def cmd_squash_check(args: argparse.Namespace) -> None:
    diffstat, names = squash_check(load_and_validate(Path(args.plan)))
    print("[INFO] Diffstat vs chain tip after squash-check rebase:")
    print(diffstat or "[OK] No diffstat differences detected.")
    print("[INFO] Name-status vs chain tip after squash-check rebase:")
    print(names or "[OK] No name-status differences detected.")


def cmd_run(args: argparse.Namespace) -> None:
    if args.create_chain and not args.ack_local_stack_state:
        raise CommandError(
            "Native materialization requires explicit authority for rerere, "
            "local stack state, branch creation, and checkout restoration; "
            "pass --ack-local-stack-state."
        )
    cmd_preflight(args)
    plan_path = Path(args.plan)
    if not plan_path.exists() or args.force_init:
        args.force = args.force or args.force_init
        cmd_init_plan(args)
    if args.create_chain:
        cmd_create_chain(args)
    else:
        print("[NEXT] Review the plan, then run create-chain.")


def _command(subparsers, name: str, help_text: str) -> argparse.ArgumentParser:
    mutation_class = COMMAND_MUTATION_CLASSES[name]
    parser = subparsers.add_parser(
        name,
        help=f"[{mutation_class}] {help_text}",
        description=f"Mutation class: {mutation_class}. {help_text}",
    )
    parser.set_defaults(mutation_class=mutation_class)
    return parser


def _add_plan(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--plan", default=str(DEFAULT_PLAN_PATH), help="Plan path")


def _add_preflight_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base", required=True, help="Base branch")
    parser.add_argument("--source", required=True, help="Source branch")
    test_command = parser.add_mutually_exclusive_group()
    test_command.add_argument(
        "--test-argv",
        default=None,
        help="Explicitly approved test argv as a JSON array of strings",
    )
    test_command.add_argument(
        "--test-cmd",
        dest="legacy_test_cmd",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-merge-check", action="store_true")
    parser.add_argument("--allow-source-behind-base", action="store_true")
    parser.add_argument("--confirm-source-behind-base", action="store_true")
    parser.add_argument("--allow-recordkeeping-tracked", action="store_true")


def _add_remote_dry_run(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", dest="dry_run", action="store_true")
    group.add_argument("--no-dry-run", dest="dry_run", action="store_false")
    parser.set_defaults(dry_run=True)


def _add_transition_options(
    parser: argparse.ArgumentParser,
    *authority_flags: tuple[str, str],
) -> None:
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute only an approved, freshly re-read operation manifest",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="Path to the exact approved manifest required with --execute",
    )
    parser.add_argument(
        "--allow-stack-state-refresh",
        action="store_true",
        help=(
            "Authorize the bounded local-state refresh required to observe and "
            "reconcile native topology for a transition manifest"
        ),
    )
    for flag, destination in authority_flags:
        parser.add_argument(
            flag,
            dest=destination,
            action="store_true",
            help=f"Acknowledge the operation-scoped {flag.removeprefix('--')} grant",
        )


def _add_propagation_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", required=True, help="Source branch")
    parser.add_argument("--base", default=None, help="Base branch")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--pr", type=int, help="Changeset pull request number")
    target.add_argument("--index", type=int, help="One-based changeset index")
    parser.add_argument(
        "--strategy", choices=("rebase", "cherry-pick"), default="rebase"
    )
    parser.add_argument("--remote", default="origin")
    parser.add_argument(
        "--ack-merge-and-propagate",
        action="store_true",
        help="Acknowledge explicit merge-and-propagate authority",
    )
    _add_remote_dry_run(parser)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Carve a review-ready source branch into intentional changesets.",
        epilog="Mutation classes are shown beside every operation; remote mutation is dry-run by default.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    item = _command(
        sub, "preflight", "Validate source/base readiness and approved tests."
    )
    _add_preflight_options(item)
    item.set_defaults(func=cmd_preflight)

    item = _command(sub, "init-plan", "Create an ephemeral decomposition plan.")
    _add_plan(item)
    item.add_argument("--base", required=True)
    item.add_argument("--source", required=True)
    item.add_argument("--title", required=True)
    item.add_argument("--changesets", type=int, default=3)
    test_command = item.add_mutually_exclusive_group()
    test_command.add_argument("--test-argv", default=None)
    test_command.add_argument(
        "--test-cmd",
        dest="legacy_test_cmd",
        default=None,
        help=argparse.SUPPRESS,
    )
    item.add_argument("--force", action="store_true")
    item.set_defaults(func=cmd_init_plan)

    item = _command(sub, "validate", "Validate the decomposition plan.")
    _add_plan(item)
    item.add_argument("--strict", action="store_true")
    item.add_argument("--remote", default="origin")
    item.add_argument("--local-only", action="store_true")
    item.set_defaults(func=cmd_validate)

    item = _command(sub, "status", "Render chain status from live git and GitHub.")
    item.add_argument("--source", required=True, help="Source branch")
    item.add_argument("--base", default=None, help="Base branch")
    item.add_argument("--remote", default="origin")
    item.add_argument("--local-only", action="store_true")
    item.add_argument(
        "--allow-stack-state-refresh",
        action="store_true",
        help="Authorize the bounded local-state refresh performed by gh stack view.",
    )
    item.set_defaults(func=cmd_status)

    item = _command(sub, "create-chain", "Materialize append-only changeset branches.")
    _add_plan(item)
    item.add_argument("--remote", default="origin")
    item.add_argument(
        "--ack-local-stack-state",
        action="store_true",
        help=(
            "Authorize rerere, local stack-state, branch, and checkout effects "
            "for native materialization"
        ),
    )
    item.set_defaults(func=cmd_create_chain)

    item = _command(sub, "compare", "Compare reconstructed chain output with source.")
    _add_plan(item)
    item.set_defaults(func=cmd_compare)

    item = _command(
        sub, "validate-chain", "Run approved step tests and live chain validation."
    )
    _add_plan(item)
    test_command = item.add_mutually_exclusive_group()
    test_command.add_argument("--test-argv", default=None)
    test_command.add_argument(
        "--test-cmd",
        dest="legacy_test_cmd",
        default=None,
        help=argparse.SUPPRESS,
    )
    item.add_argument("--remote", default="origin")
    item.add_argument("--local-only", action="store_true")
    item.set_defaults(func=cmd_validate_chain)

    item = _command(sub, "pr-create", "Publish correctly based changeset PRs.")
    _add_plan(item)
    item.add_argument("--index", type=int)
    item.add_argument("--remote", default="origin")
    item.add_argument(
        "--ready-for-review",
        action="store_true",
        help="Request ready pull requests instead of the default draft state",
    )
    item.add_argument(
        "--ack-ready-for-review",
        action="store_true",
        help="Acknowledge the separate draft-to-ready authority grant",
    )
    _add_remote_dry_run(item)
    _add_transition_options(item, ("--ack-submit", "ack_submit"))
    item.set_defaults(func=cmd_pr_create)

    item = _command(sub, "push-chain", "Push changeset branches with exact leases.")
    _add_plan(item)
    item.add_argument("--remote", default="origin")
    _add_remote_dry_run(item)
    _add_transition_options(item, ("--ack-push", "ack_push"))
    item.set_defaults(func=cmd_push_chain)

    item = _command(
        sub,
        "propagate",
        "Verify a merged changeset and propagate its downstream suffix.",
    )
    _add_propagation_options(item)
    _add_transition_options(item, ("--ack-repair", "ack_repair"))
    item.set_defaults(func=cmd_propagate)

    item = _command(
        sub,
        "merge-propagate",
        "Merge one changeset PR, verify it, and propagate downstream.",
    )
    _add_propagation_options(item)
    item.add_argument(
        "--method", choices=("merge", "squash", "rebase"), default="merge"
    )
    item.add_argument("--merge-mode", choices=("direct", "queue"), default="direct")
    _add_transition_options(
        item,
        ("--ack-direct-merge", "ack_direct_merge"),
        ("--ack-queue-merge", "ack_queue_merge"),
    )
    item.set_defaults(func=cmd_merge_propagate)

    item = _command(
        sub,
        "recover-suffix",
        "Restamp an owned unmerged suffix onto an immutable successor source.",
    )
    item.add_argument("--source", required=True, help="Original chain-root source")
    item.add_argument("--base", required=True, help="Current mainline base branch")
    item.add_argument(
        "--from-index", type=int, required=True, help="First unmerged changeset index"
    )
    item.add_argument(
        "--successor-source", required=True, help="Immutable successor source branch"
    )
    item.add_argument(
        "--successor-sha", required=True, help="Exact immutable successor commit SHA"
    )
    item.add_argument("--remote", default="origin")
    item.add_argument(
        "--ack-suffix-recovery",
        action="store_true",
        help="Acknowledge explicit suffix-recovery authority",
    )
    _add_remote_dry_run(item)
    _add_transition_options(item)
    item.set_defaults(func=cmd_recover_suffix)

    item = _command(sub, "db-compare", "Compare source and chain database schemas.")
    _add_plan(item)
    source_command = item.add_mutually_exclusive_group()
    source_command.add_argument("--source-argv")
    source_command.add_argument(
        "--source-cmd",
        dest="legacy_source_cmd",
        default=None,
        help=argparse.SUPPRESS,
    )
    chain_command = item.add_mutually_exclusive_group()
    chain_command.add_argument("--chain-argv")
    chain_command.add_argument(
        "--chain-cmd",
        dest="legacy_chain_cmd",
        default=None,
        help=argparse.SUPPRESS,
    )
    item.add_argument(
        "--keep-output-dir",
        "--out-dir",
        dest="keep_output_dir",
        default=None,
        metavar="PATH",
        help=(
            "Explicitly retain raw outputs at PATH; --out-dir is a legacy alias. "
            "The default uses an automatically removed restricted directory."
        ),
    )
    item.set_defaults(func=cmd_db_compare)

    item = _command(sub, "hunk-preview", "Preview explicit textual hunk selectors.")
    _add_plan(item)
    item.add_argument("--base", default="")
    item.add_argument("--source", default="")
    item.add_argument("--file", required=True)
    item.add_argument("--contains", action="append", default=[])
    item.add_argument("--excludes", action="append", default=[])
    item.set_defaults(func=cmd_hunk_preview)

    item = _command(sub, "squash-ref", "Create a local-only squashed source reference.")
    _add_plan(item)
    item.add_argument("--base", default="")
    item.add_argument("--source", default="")
    item.add_argument("--reuse-existing", action="store_true")
    item.add_argument("--recreate", action="store_true")
    item.set_defaults(func=cmd_squash_ref)

    item = _command(
        sub, "squash-check", "Compare a squashed source against the chain tip."
    )
    _add_plan(item)
    item.set_defaults(func=cmd_squash_check)

    item = _command(
        sub, "run", "Preflight, initialize a plan, and optionally materialize it."
    )
    _add_preflight_options(item)
    _add_plan(item)
    item.add_argument("--title", required=True)
    item.add_argument("--changesets", type=int, default=3)
    item.add_argument("--force", action="store_true")
    item.add_argument("--force-init", action="store_true")
    item.add_argument("--create-chain", action="store_true")
    item.add_argument("--remote", default="origin")
    item.add_argument(
        "--ack-local-stack-state",
        action="store_true",
        help=(
            "Authorize rerere, local stack-state, branch, and checkout effects "
            "for native materialization"
        ),
    )
    item.set_defaults(func=cmd_run)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.mutation_class == REMOTE_MUTATING:
            ensure_clean_tree()
        args.func(args)
        if args.mutation_class != READ_ONLY:
            ensure_clean_tree()
        return 0
    except (
        CommandError,
        GhStackError,
        ManifestError,
        NativeStackError,
        RehydrationError,
    ) as exc:
        destination = (
            sys.stderr if isinstance(exc, StructuredTransitionError) else sys.stdout
        )
        print(f"[ERROR] {exc}", file=destination)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
