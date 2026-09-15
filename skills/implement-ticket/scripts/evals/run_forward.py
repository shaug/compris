#!/usr/bin/env python3
"""Run result-blind implement-ticket forward evaluations in fresh processes."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = SKILL_ROOT.parents[1]
DEFAULT_CASES = SKILL_ROOT / "evals" / "forward_cases.json"
DEFAULT_EXPECTATIONS = SKILL_ROOT / "evals" / "forward_expectations.json"
DEFAULT_EXECUTOR = Path(__file__).with_name("fixture_executor.py")


def load_json(path: Path):
    return json.loads(path.read_text())


def skill_prompt(target_skill: str) -> str:
    path = REPOSITORY_ROOT / "skills" / target_skill / "SKILL.md"
    return path.read_text()


def build_payload(case: dict) -> dict:
    """Build the evaluator packet without fixture identity or grader data."""
    return {
        "target_skill": case["target_skill"],
        "skill_prompt": skill_prompt(case["target_skill"]),
        "request": case["request"],
        "authority": case.get("authority", {}),
        "capabilities": case.get("capabilities", {}),
        "artifacts": case["artifacts"],
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
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("executor did not return one JSON result") from error


def grade(case_id: str, observed: dict, expected: dict) -> list[str]:
    failures = []
    if observed.get("terminal_state") != expected.get("terminal_state"):
        failures.append(
            f"terminal_state: expected {expected.get('terminal_state')!r}, "
            f"got {observed.get('terminal_state')!r}"
        )
    observed_actions = set(observed.get("actions") or [])
    missing_actions = sorted(
        set(expected.get("required_actions") or []) - observed_actions
    )
    if missing_actions:
        failures.append(f"missing actions: {', '.join(missing_actions)}")
    # Forbidden actions keep an executor from passing by emitting the whole
    # action vocabulary on every case.
    forbidden_actions = sorted(
        set(expected.get("forbidden_actions") or []) & observed_actions
    )
    if forbidden_actions:
        failures.append(f"forbidden actions: {', '.join(forbidden_actions)}")
    if observed.get("target_skill") != expected.get("target_skill"):
        failures.append(
            f"target_skill: expected {expected.get('target_skill')!r}, "
            f"got {observed.get('target_skill')!r}"
        )
    if (
        expected.get("target_skill") == "implement-ticket"
        and expected.get("terminal_state") != "requires_epic"
    ):
        telemetry = observed.get("shape_telemetry")
        required_fields = {
            "ticket_id",
            "prediction",
            "candidate_sha",
            "publication_candidate_sha",
            "actual",
            "comparison",
        }
        if not isinstance(telemetry, dict):
            failures.append("shape_telemetry: missing standalone terminal observation")
        elif missing_fields := sorted(required_fields - set(telemetry)):
            failures.append(
                "shape_telemetry: missing fields " + ", ".join(missing_fields)
            )
    if "acceptance_statuses" in expected:
        ledger = observed.get("acceptance_ledger") or []
        criteria = [
            entry.get("criterion") for entry in ledger if isinstance(entry, dict)
        ]
        duplicates = sorted(
            {criterion for criterion in criteria if criteria.count(criterion) > 1}
        )
        if duplicates:
            failures.append(
                "acceptance_ledger: duplicate criteria " + ", ".join(duplicates)
            )
        observed_statuses = {
            entry.get("criterion"): entry.get("status")
            for entry in ledger
            if isinstance(entry, dict) and isinstance(entry.get("criterion"), str)
        }
        if observed_statuses != expected["acceptance_statuses"]:
            failures.append(
                "acceptance_statuses: expected "
                f"{expected['acceptance_statuses']!r}, got {observed_statuses!r}"
            )
    return [f"{case_id}: {failure}" for failure in failures]


def evaluate(
    cases_path: Path,
    expectations_path: Path,
    command: list[str],
    target_skill: str | None = None,
):
    cases = load_json(cases_path)
    expectations = {item["case_id"]: item for item in load_json(expectations_path)}
    if {case["id"] for case in cases} != set(expectations):
        raise ValueError("forward case and expectation IDs differ")
    if target_skill:
        cases = [case for case in cases if case["target_skill"] == target_skill]
        expectations = {
            case_id: expected
            for case_id, expected in expectations.items()
            if expected["target_skill"] == target_skill
        }
        if not cases:
            raise ValueError(f"no forward cases target {target_skill}")

    observations = {}
    failures = []
    for case in cases:
        payload = build_payload(case)
        observed = run_executor(command, payload)
        observations[case["id"]] = observed
        failures.extend(grade(case["id"], observed, expectations[case["id"]]))
    return observations, failures


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--expectations", type=Path, default=DEFAULT_EXPECTATIONS)
    parser.add_argument(
        "--executor",
        default=f"{shlex.quote(sys.executable)} {shlex.quote(str(DEFAULT_EXECUTOR))}",
        help="Fresh-process evaluator command; receives one result-blind JSON packet on stdin",
    )
    parser.add_argument(
        "--target-skill",
        choices=("implement-ticket", "implement-epic"),
        help="Run only cases targeting one skill after validating the full corpus",
    )
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command = shlex.split(args.executor)
    observations, failures = evaluate(
        args.cases, args.expectations, command, target_skill=args.target_skill
    )

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for case_id, result in observations.items():
            (args.output_dir / f"{case_id}.json").write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n"
            )

    summary = {
        "total": len(observations),
        "passed": len(observations) - len({item.split(":", 1)[0] for item in failures}),
        "failed": len({item.split(":", 1)[0] for item in failures}),
        "failures": failures,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
