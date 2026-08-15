#!/usr/bin/env python3
"""Real-runtime forward-evaluation executor backed by Claude Code headless mode.

Reads one result-blind evaluation packet as JSON on stdin (the shape built by
`run_forward.py`), asks a fresh `claude -p` process to reason about how a
fully compliant ready-ticket run must terminate, and prints one JSON result:

    {"terminal_state": ..., "actions": [...]}

The evaluated model receives the skill prompt, the request, and the scenario
artifacts, plus the closed action vocabulary below so its choices are gradable
against `forward_expectations.json`. It never sees fixture identity or any
expectations. Requires the `claude` CLI on PATH (override with --claude-bin).

Usage:
    python3 run_forward.py --executor "python3 claude_executor.py"
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

TERMINAL_STATES = (
    "ticket_ready",
    "draft_ready",
    "decomposition_recommended",
    "requires_brainstorming",
    "blocked",
)

# Closed vocabulary shared with fixture_executor.py and
# forward_expectations.json. Grading is multiple-choice by design: the model
# must decide which obligations apply, not invent matching strings.
ACTION_VOCABULARY = (
    "accept_sufficient_design_without_further_design_questions",
    "ask_no_question_wait_for_no_answer",
    "assert_criterion_on_internals",
    "choose_no_answer_on_requesters_behalf",
    "choose_no_tracker_on_requesters_behalf",
    "claim_readiness_with_a_placeholder_present",
    "close_open_decision_without_requester",
    "create_or_modify_ticket_or_relationship",
    "elicit_only_tracker_shaped_residue",
    "elicit_public_surface_behavior",
    "fill_every_template_slot",
    "gather_the_missing_design",
    "give_one_next_action",
    "infer_the_missing_design",
    "invent_unrequested_requirement",
    "invoke_load_bearing_without_consent",
    "meet_the_ticket_ready_readiness_target",
    "mention_peer_absence_as_caveat",
    "name_each_independently_valuable_part",
    "name_the_absent_design_part",
    "name_the_unresolved_decision_as_blocking_reason",
    "perform_no_tracker_mutation",
    "reject_internal_call_criterion",
    "reject_placeholder_in_scan",
    "relitigate_settled_design_decision",
    "require_design_ceremony_beyond_the_scale_of_the_work",
    "rerun_all_four_scans_after_edit",
    "return_complete_body_to_caller",
    "return_to_elicitation_for_missing_value",
    "record_boundary_between_parts",
    "record_why_each_part_independently_valuable",
    "hand_recommendation_back_to_operator",
)


def build_prompt(payload: dict) -> str:
    return "\n".join(
        [
            "You are the runtime executing the agent skill below for one",
            "scenario. Decide how a fully compliant runtime must terminate",
            "and which obligations apply. Do not perform any real tool",
            "actions; reason from the artifacts alone.",
            "",
            "## Skill",
            payload["skill_prompt"],
            "",
            "## Request",
            payload["request"],
            "",
            "## Scenario artifacts (JSON)",
            json.dumps(payload["artifacts"], indent=2, sort_keys=True),
            "",
            "## Answer format",
            "Return ONLY one JSON object, no prose and no code fence:",
            '{"terminal_state": <one of ' + json.dumps(list(TERMINAL_STATES)) + ">,",
            ' "actions": <every applicable value from this closed vocabulary>}',
            json.dumps(list(ACTION_VOCABULARY), indent=2),
        ]
    )


def extract_json_object(text: str) -> dict:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("executor model returned no JSON object")
    return json.loads(candidate[start : end + 1])


def run_claude(prompt: str, claude_bin: str, model: str | None) -> dict:
    command = [claude_bin, "-p", "--output-format", "json"]
    if model:
        command.extend(["--model", model])
    completed = subprocess.run(
        command,
        input=prompt,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            f"claude exited {completed.returncode}: {completed.stderr.strip()}"
        )
    envelope = json.loads(completed.stdout)
    result_text = envelope.get("result")
    if not isinstance(result_text, str):
        raise RuntimeError("claude --output-format json returned no result text")
    return extract_json_object(result_text)


def normalize(observed: dict) -> dict:
    actions = observed.get("actions")
    if not isinstance(actions, list):
        actions = []
    return {
        "terminal_state": observed.get("terminal_state"),
        "actions": sorted(
            {str(action) for action in actions if str(action) in ACTION_VOCABULARY}
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument(
        "--model",
        default=None,
        help="Optional model override passed to `claude --model`",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = json.load(sys.stdin)
    observed = run_claude(build_prompt(payload), args.claude_bin, args.model)
    json.dump(normalize(observed), sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
