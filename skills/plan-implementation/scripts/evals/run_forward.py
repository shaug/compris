#!/usr/bin/env python3
"""Run result-blind plan-implementation forward evaluations in fresh processes.

Mirrors implement-ticket's forward-eval harness
(`../../implement-ticket/scripts/evals/run_forward.py`): build a result-blind
packet, hand it to a fresh-process executor, grade the closed-vocabulary
answer against `forward_expectations.json`. Scoped to this one skill rather
than generalized across skills, per this repository's skill-local convention.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = SKILL_ROOT / "evals" / "forward_cases.json"
DEFAULT_EXPECTATIONS = SKILL_ROOT / "evals" / "forward_expectations.json"
DEFAULT_EXECUTOR = Path(__file__).with_name("fixture_executor.py")


def load_json(path: Path):
    return json.loads(path.read_text())


def skill_prompt() -> str:
    return (SKILL_ROOT / "SKILL.md").read_text()


def build_payload(case: dict) -> dict:
    """Build the evaluator packet without fixture identity or grader data."""
    return {
        "skill_prompt": skill_prompt(),
        "request": case["request"],
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
    forbidden_actions = sorted(
        set(expected.get("forbidden_actions") or []) & observed_actions
    )
    if forbidden_actions:
        failures.append(f"forbidden actions: {', '.join(forbidden_actions)}")
    return [f"{case_id}: {failure}" for failure in failures]


def evaluate(cases_path: Path, expectations_path: Path, command: list[str]):
    cases = load_json(cases_path)
    expectations = {item["case_id"]: item for item in load_json(expectations_path)}
    if {case["id"] for case in cases} != set(expectations):
        raise ValueError("forward case and expectation IDs differ")

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
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command = shlex.split(args.executor)
    observations, failures = evaluate(args.cases, args.expectations, command)

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
