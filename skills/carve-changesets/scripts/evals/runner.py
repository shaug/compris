#!/usr/bin/env python3
"""Run result-blind forward evals or the deterministic integration self-test."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = THIS_DIR.parent
SKILL_ROOT = SCRIPTS_DIR.parent
DEFAULT_CASES = SKILL_ROOT / "evals" / "cases.json"
DEFAULT_EXPECTATIONS = SKILL_ROOT / "evals" / "expectations.json"
DEFAULT_INTEGRATION_CASES = SKILL_ROOT / "evals" / "integration_cases.json"
DEFAULT_EXECUTOR = THIS_DIR / "fixture_executor.py"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from command_argv import parse_argv_json  # noqa: E402
from common import DEFAULT_PLAN_PATH  # noqa: E402

from evals.grader import GradeResult, grade_repo  # noqa: E402
from evals.helpers import cleanup_repo, init_eval_repo  # noqa: E402


def load_json(path: Path):
    return json.loads(path.read_text())


def skill_prompt() -> str:
    return (SKILL_ROOT / "SKILL.md").read_text()


def contract_documents() -> dict[str, str]:
    return {
        "SPEC.md": (SKILL_ROOT / "references" / "SPEC.md").read_text(),
        # SPEC.md cites the doctrine for shape and ordering rather than
        # restating it, so a run that does not receive the doctrine is missing
        # the rules it is graded against, not merely a reference.
        "cognitive-shaping-doctrine.md": (
            SKILL_ROOT / "references" / "cognitive-shaping-doctrine.md"
        ).read_text(),
        "suite-handoffs.md": (
            SKILL_ROOT / "references" / "suite-handoffs.md"
        ).read_text(),
    }


def build_payload(case: dict) -> dict:
    """Build one raw scenario packet without fixture identity or grader data."""

    scenario = {
        key: value for key, value in case.items() if key not in {"id", "request"}
    }
    return {
        "target_skill": "carve-changesets",
        "skill_prompt": skill_prompt(),
        "contract_documents": contract_documents(),
        "request": case["request"],
        "scenario": scenario,
    }


def run_executor(command: list[str], payload: dict) -> dict:
    completed = subprocess.run(
        command,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            f"executor exited {completed.returncode}: {completed.stderr.strip()}"
        )
    try:
        observed = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("executor did not return one JSON result") from error
    if not isinstance(observed, dict):
        raise RuntimeError("executor did not return one JSON object")
    return observed


def grade_forward(case_id: str, observed: dict, expected: dict) -> list[str]:
    failures: list[str] = []
    if observed.get("terminal_state") != expected.get("terminal_state"):
        failures.append(
            f"terminal_state: expected {expected.get('terminal_state')!r}, "
            f"got {observed.get('terminal_state')!r}"
        )
    if observed.get("target_skill") != "carve-changesets":
        failures.append(
            "target_skill: expected 'carve-changesets', "
            f"got {observed.get('target_skill')!r}"
        )
    observed_actions = set(observed.get("actions") or [])
    missing = sorted(set(expected.get("required_actions") or []) - observed_actions)
    if missing:
        failures.append(f"missing actions: {', '.join(missing)}")
    forbidden = sorted(set(expected.get("forbidden_actions") or []) & observed_actions)
    if forbidden:
        failures.append(f"forbidden actions: {', '.join(forbidden)}")
    return [f"{case_id}: {failure}" for failure in failures]


def evaluate_forward(
    cases_path: Path, expectations_path: Path, command: list[str]
) -> tuple[dict[str, dict], list[str]]:
    cases = load_json(cases_path)
    expectations = {item["case_id"]: item for item in load_json(expectations_path)}
    if {case["id"] for case in cases} != set(expectations):
        raise ValueError("forward case and expectation IDs differ")

    observations: dict[str, dict] = {}
    failures: list[str] = []
    for case in cases:
        observed = run_executor(command, build_payload(case))
        observations[case["id"]] = observed
        failures.extend(grade_forward(case["id"], observed, expectations[case["id"]]))
    return observations, failures


def run_integration_case(case: dict, *, test_argv: list[str]) -> dict:
    repo_dir, _plan, source_hash = init_eval_repo()
    original_cwd = Path.cwd()
    try:
        os.chdir(repo_dir)
        grade: GradeResult = grade_repo(
            plan_path=repo_dir / DEFAULT_PLAN_PATH,
            expected_source_hash=source_hash,
            test_argv=test_argv,
            auto_create_chain=bool(case.get("auto_create_chain", True)),
        )
        expected_checks = set(case.get("objective_checks") or [])
        missing_checks = sorted(expected_checks - set(grade.checks))
        failures = list(grade.failures)
        if missing_checks:
            failures.append("missing objective checks: " + ", ".join(missing_checks))
        return {
            "id": case["id"],
            "ok": grade.ok and not missing_checks,
            "checks": grade.checks,
            "failures": failures,
        }
    finally:
        os.chdir(original_cwd)
        cleanup_repo(repo_dir)


def evaluate_integration(cases_path: Path, *, test_argv: list[str]) -> dict[str, dict]:
    return {
        case["id"]: run_integration_case(case, test_argv=test_argv)
        for case in load_json(cases_path)
    }


def write_outputs(output_dir: Path | None, results: dict[str, dict]) -> None:
    if output_dir is None:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    for case_id, result in results.items():
        (output_dir / f"{case_id}.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--expectations", type=Path, default=DEFAULT_EXPECTATIONS)
    parser.add_argument(
        "--executor",
        default=f"{shlex.quote(sys.executable)} {shlex.quote(str(DEFAULT_EXECUTOR))}",
        help="Fresh-process evaluator command; receives result-blind JSON on stdin",
    )
    parser.add_argument(
        "--integration-self-test",
        action="store_true",
        help="Run only the deterministic helper integration self-test",
    )
    parser.add_argument(
        "--integration-cases", type=Path, default=DEFAULT_INTEGRATION_CASES
    )
    test_command = parser.add_mutually_exclusive_group()
    test_command.add_argument(
        "--test-argv",
        default='["python3", "-c", "print(\\"ok\\")"]',
        help="Approved argv JSON used by the objective chain grader",
    )
    test_command.add_argument(
        "--test-cmd",
        dest="legacy_test_cmd",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.legacy_test_cmd is not None:
        parser.error(
            "--test-cmd is no longer supported; use --test-argv with a JSON argv array"
        )
    if args.integration_self_test:
        results = evaluate_integration(
            args.integration_cases,
            test_argv=parse_argv_json(args.test_argv, label="--test-argv"),
        )
        failures = [
            f"{case_id}: {failure}"
            for case_id, result in results.items()
            for failure in result["failures"]
        ]
        mode = "integration_self_test"
    else:
        results, failures = evaluate_forward(
            args.cases, args.expectations, shlex.split(args.executor)
        )
        mode = "forward"

    write_outputs(args.output_dir, results)
    failed_ids = {item.split(":", 1)[0] for item in failures}
    summary = {
        "mode": mode,
        "total": len(results),
        "passed": len(results) - len(failed_ids),
        "failed": len(failed_ids),
        "failures": failures,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
