#!/usr/bin/env python3
"""Recall-versus-recognition probe for the forward corpus's missing-action class.

`claude_executor.py` grades free recall: it hands the model the whole closed
action vocabulary and asks for *every applicable value*. A required obligation
absent from that answer is graded exactly like a forbidden obligation present in
it, even though one is a recall miss over a ~110-item list and the other is a
positive judgment error. This probe separates the two.

For one case it re-presents the identical result-blind packet, then asks a
recognition question over a balanced item set instead of asking for free recall:

- the case's `required_actions`, which a compliant runtime must answer `true`;
  and
- the case's `forbidden_actions`, which it must answer `false`.

The forbidden items are the control. Without them a `true` on the previously
missed obligation would be indistinguishable from yea-saying, since the probe
necessarily discloses that the item is under consideration. Items are shuffled
with a per-case deterministic seed so the order carries no signal and the run
reproduces.

Read the per-case verdict as:

- `recall_gap` — the missed obligation is recognized and the controls are
  rejected, so free recall, not judgment, produced the failure.
- `judgment_gap` — the missed obligation is rejected under recognition too. The
  elicitation is not what produced the failure.
- `uninformative` — the controls were not rejected, so the model is agreeing
  with whatever it is shown and the recognition answer carries no information.
- `controls_only` — the case was probed with an empty missed list, to ask the
  converse question: does the model assert a *forbidden* obligation applies when
  it is named? A forbidden item accepted here is a positive judgment error, not
  the over-emission that free recall's "every applicable value" invites.

`--rename OLD=NEW` presents one vocabulary item under a different name, holding
everything else fixed. It is the single-variable test for whether a term's own
wording, rather than the prose behind it, is what the model is answering.

This probe is a diagnostic, not a candidate executor change: it is shown the
case's own expectations, so it can never run result-blind. The shippable
elicitation change it informs has to stay blind to them.

Usage:
    python3 recognition_probe.py --model claude-opus-5 --out results.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from claude_executor import run_claude  # noqa: E402
from run_forward import build_payload, load_json  # noqa: E402

SKILL_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = SKILL_ROOT / "evals" / "forward_cases.json"
DEFAULT_EXPECTATIONS = SKILL_ROOT / "evals" / "forward_expectations.json"


def build_probe_prompt(payload: dict, items: list[str]) -> str:
    return "\n".join(
        [
            "You are the runtime executing the agent skill below for one",
            "scenario. Decide which obligations a fully compliant runtime must",
            "satisfy. Do not perform any real tool actions; reason from the",
            "artifacts alone.",
            "",
            "## Skill",
            payload["skill_prompt"],
            "",
            "## Request",
            payload["request"],
            "",
            "## Granted authority (JSON)",
            json.dumps(payload.get("authority") or {}, sort_keys=True),
            "",
            "## Available capabilities (JSON)",
            json.dumps(payload.get("capabilities") or {}, sort_keys=True),
            "",
            "## Scenario artifacts (JSON)",
            json.dumps(payload["artifacts"], indent=2, sort_keys=True),
            "",
            "## Question",
            "For each obligation name below, decide whether a fully compliant",
            "runtime executing this skill for this scenario is obliged to",
            "perform it. Some of the names listed do apply and some do not;",
            "judge each one independently against the skill prose and the",
            "artifacts.",
            "",
            "## Answer format",
            "Return ONLY one JSON object, no prose and no code fence, with one",
            "boolean per name and no names beyond those listed:",
            '{"answers": {"<name>": true, "<name>": false, ...}}',
            "",
            "## Obligation names",
            json.dumps(items, indent=2),
        ]
    )


def probe_case(
    case: dict,
    expectation: dict,
    claude_bin: str,
    model: str | None,
    missed: list[str],
    renames: dict[str, str] | None = None,
) -> dict:
    renames = renames or {}
    required = sorted(expectation.get("required_actions") or [])
    forbidden = sorted(expectation.get("forbidden_actions") or [])

    # A missed name absent from required_actions is never presented, so it can
    # only come back unanswered — which scores as `judgment_gap`, the verdict
    # meaning "the elicitation is not what produced this failure". A typo would
    # therefore read as a finding rather than as the mistake it is, in an
    # instrument whose verdicts are the evidence. Fail on it, as an unknown case
    # id already does.
    unexpected = sorted(set(missed) - set(required))
    if unexpected:
        raise ValueError(
            f"{case['id']}: missed actions absent from required_actions: "
            + ", ".join(unexpected)
        )
    items = [renames.get(name, name) for name in required + forbidden]
    random.Random(case["id"]).shuffle(items)

    payload = build_payload(case)
    observed = run_claude(
        build_probe_prompt(payload, items), claude_bin, model, attempts=3
    )
    answers = observed.get("answers")
    if not isinstance(answers, dict):
        answers = {}
    answers = {name: bool(value) for name, value in answers.items() if name in items}

    def answer_for(name: str) -> bool | None:
        return answers.get(renames.get(name, name))

    unanswered = sorted(set(items) - set(answers))
    controls_rejected = [name for name in forbidden if answer_for(name) is False]
    controls_accepted = [name for name in forbidden if answer_for(name) is True]
    missed_recognized = [name for name in missed if answer_for(name) is True]
    missed_rejected = [name for name in missed if answer_for(name) is not True]

    if not missed:
        verdict = "controls_only"
    elif forbidden and controls_accepted:
        verdict = "uninformative"
    elif missed_rejected:
        verdict = "judgment_gap"
    else:
        verdict = "recall_gap"

    return {
        "case_id": case["id"],
        "target_skill": case["target_skill"],
        "missed_under_free_recall": missed,
        "renames": renames,
        "presented_items": items,
        "answers": answers,
        "unanswered": unanswered,
        "controls_total": len(forbidden),
        "controls_rejected": controls_rejected,
        "controls_accepted": controls_accepted,
        "missed_recognized": missed_recognized,
        "missed_rejected": missed_rejected,
        "verdict": verdict,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--expectations", type=Path, default=DEFAULT_EXPECTATIONS)
    parser.add_argument(
        "--missed",
        type=Path,
        required=True,
        help='JSON mapping case_id -> ["action", ...] missed under free recall',
    )
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--rename",
        action="append",
        default=[],
        metavar="OLD=NEW",
        help="Present one vocabulary item under a different name, holding "
        "everything else fixed. Repeatable.",
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = {case["id"]: case for case in load_json(args.cases)}
    expectations = {item["case_id"]: item for item in load_json(args.expectations)}
    missed_by_case = json.loads(args.missed.read_text())
    renames = dict(item.split("=", 1) for item in args.rename)

    results = []
    for case_id, missed in sorted(missed_by_case.items()):
        if case_id not in cases:
            raise SystemExit(f"unknown case: {case_id}")
        result = probe_case(
            cases[case_id],
            expectations[case_id],
            args.claude_bin,
            args.model,
            missed,
            renames,
        )
        results.append(result)
        print(
            f"{case_id}: {result['verdict']} "
            f"(recognized {len(result['missed_recognized'])}/{len(missed)}, "
            f"controls rejected {len(result['controls_rejected'])}/"
            f"{result['controls_total']})",
            file=sys.stderr,
        )

    payload = {
        "schema": "recognition-probe/1",
        "model": args.model,
        "cases": results,
        "renames": renames,
        "totals": {
            verdict: sum(1 for item in results if item["verdict"] == verdict)
            for verdict in (
                "recall_gap",
                "judgment_gap",
                "uninformative",
                "controls_only",
            )
        },
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload["totals"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
