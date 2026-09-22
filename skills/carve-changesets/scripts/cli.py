#!/usr/bin/env python3
"""The single command-line interface for carve-changesets."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from chain import compare_chain, create_chain, validate_chain
from command_argv import parse_argv_json
from common import (
    DEFAULT_PLAN_PATH,
    CommandError,
    discover_test_command,
    ensure_clean_tree,
    init_plan,
    load_plan,
    validate_plan,
)
from db_compare import db_compare
from github import pr_create, pull_request_by_number, pull_requests_for_source
from patch_apply import build_diff
from plan_checks import strict_apply_check, validate_plan_strict
from preflight import preflight
from propagate import merge_propagate_from_live, propagate_from_live, push_chain
from recovery import recover_suffix_from_live
from rehydrate import RehydrationError, adopt_legacy_chain, discover_changeset_heads
from squash_check import squash_check
from squash_ref import _resolve_base_source, create_squashed_ref
from status import status_from_live
from validate import ChainValidation, validate_live_chain

READ_ONLY = "read-only"
LOCAL_MUTATING = "local-mutating"
REMOTE_MUTATING = "remote-mutating"

COMMAND_MUTATION_CLASSES = {
    "preflight": LOCAL_MUTATING,
    "init-plan": LOCAL_MUTATING,
    "validate": LOCAL_MUTATING,
    "status": READ_ONLY,
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
            result = validate_live_chain(chain, remote=args.remote)
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
            allow_stack_state_refresh=args.allow_stack_state_refresh,
        )
    )


def _print_live_diagnostics(result: ChainValidation) -> None:
    for diagnostic in result.diagnostics:
        print(
            f"[{diagnostic.severity.upper()}] {diagnostic.code}: {diagnostic.message}"
        )


def cmd_create_chain(args: argparse.Namespace) -> None:
    create_chain(load_and_validate(Path(args.plan)))


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
    result = validate_live_chain(chain, remote=args.remote)
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
    pr_create(plan, indices=indices, dry_run=args.dry_run, remote=args.remote)


def cmd_push_chain(args: argparse.Namespace) -> None:
    push_chain(
        load_and_validate(Path(args.plan)),
        remote=args.remote,
        dry_run=args.dry_run,
    )


def cmd_propagate(args: argparse.Namespace) -> None:
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


def cmd_merge_propagate(args: argparse.Namespace) -> None:
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


def cmd_recover_suffix(args: argparse.Namespace) -> None:
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
    cmd_preflight(args)
    plan_path = Path(args.plan)
    if not plan_path.exists() or args.force_init:
        args.force = args.force or args.force_init
        cmd_init_plan(args)
    if args.create_chain:
        create_chain(load_and_validate(plan_path))
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
    _add_remote_dry_run(item)
    item.set_defaults(func=cmd_pr_create)

    item = _command(sub, "push-chain", "Push changeset branches with exact leases.")
    _add_plan(item)
    item.add_argument("--remote", default="origin")
    _add_remote_dry_run(item)
    item.set_defaults(func=cmd_push_chain)

    item = _command(
        sub,
        "propagate",
        "Verify a merged changeset and propagate its downstream suffix.",
    )
    _add_propagation_options(item)
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
    item.set_defaults(func=cmd_run)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        if args.mutation_class != READ_ONLY:
            ensure_clean_tree()
        return 0
    except (CommandError, RehydrationError) as exc:
        print(f"[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
