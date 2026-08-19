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

Following the micro-test protocol in `docs/skill-authoring.md`, and matching
`triggering/executors/description_executor.py`, each scenario is asked
`--repetitions` times (default 5) in independent processes. The majority
terminal state wins, an action is reported when a majority of samples chose it,
and the per-sample counts travel with the answer so a 3/5 result is never
recorded as though it were 5/5.

Usage:
    python3 run_forward.py --executor "python3 claude_executor.py"
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter

# How a sample with no usable terminal state votes. Never a real answer.
NO_TERMINAL_STATE = "none"

TERMINAL_STATES = (
    "ticket_ready",
    "draft_ready",
    "decomposition_recommended",
    "graph_created",
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
    "bundle_mechanical_restructuring_with_behavioral_change",
    "choose_no_answer_on_requesters_behalf",
    "choose_no_tracker_on_requesters_behalf",
    "cite_bare_file_line_without_quoted_text",
    "cite_volatile_collection_by_location",
    "claim_graph_created_despite_relationship_failure",
    "claim_readiness_with_a_placeholder_present",
    "claim_success_without_readback",
    "close_open_decision_without_requester",
    "continue_after_unreported_partial_write",
    "count_generated_evidence_toward_size",
    "create_before_authority_is_granted",
    "create_native_relationships",
    "create_or_modify_ticket_or_relationship",
    "create_the_approved_graph",
    "decompose_to_a_single_child",
    "defer_validation_to_a_separate_leaf",
    "draft_a_complete_body_for_every_leaf",
    "elicit_only_tracker_shaped_residue",
    "elicit_public_surface_behavior",
    "exclude_recorded_generated_evidence_from_size",
    "fill_every_template_slot",
    "gather_the_missing_design",
    "give_one_next_action",
    "infer_the_missing_design",
    "invent_unrequested_requirement",
    "invoke_load_bearing_without_consent",
    "keep_reviewable_initiative_as_one_ticket",
    "keep_validation_with_the_behavior_it_proves",
    "meet_the_ticket_ready_readiness_target",
    "mention_peer_absence_as_caveat",
    "name_a_re_split_trigger_per_leaf",
    "name_each_independently_valuable_part",
    "name_every_graph_node_and_edge",
    "name_the_absent_design_part",
    "name_the_unresolved_decision_as_blocking_reason",
    "perform_no_tracker_mutation",
    "present_draft_graph_for_approval",
    "quote_cited_repository_text",
    "reject_internal_call_criterion",
    "reject_placeholder_in_scan",
    "relitigate_settled_design_decision",
    "report_every_landed_item",
    "report_every_missing_edge",
    "report_the_exact_mismatch",
    "require_design_ceremony_beyond_the_scale_of_the_work",
    "reread_and_verify_graph_before_success",
    "rerun_all_four_scans_after_edit",
    "restate_architectural_fact_as_value",
    "restate_volatile_collection_membership_as_value",
    "return_complete_body_to_caller",
    "return_to_elicitation_for_missing_value",
    "record_boundary_between_parts",
    "record_why_each_part_independently_valuable",
    "separate_mechanical_restructuring_from_behavioral_change",
    "separate_unrelated_concern_domains",
    "stop_creating_after_partial_write",
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


RESULT_ATTEMPTS = 3


def run_claude(
    prompt: str, claude_bin: str, model: str | None, attempts: int = RESULT_ATTEMPTS
) -> dict:
    command = [claude_bin, "-p", "--output-format", "json"]
    if model:
        command.extend(["--model", model])

    # The model occasionally ends its turn with the JSON object incomplete --
    # a missing closing brace, or an unescaped quote inside a string value.
    # That is a malformed *response*, not a boundary-detection bug in
    # extract_json_object, and a fresh independent sample clears it almost
    # every time. Without this loop one flaky sample sinks a whole recorded
    # run, which is now `--repetitions` times as many samples as it was.
    last_error: ValueError | None = None
    for _ in range(attempts):
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
        try:
            return extract_json_object(result_text)
        except ValueError as error:
            last_error = error
    raise RuntimeError(
        f"executor model returned malformed JSON after {attempts} attempts: {last_error}"
    )


def sample(observed: dict) -> tuple[str | None, frozenset[str]]:
    """One sample reduced to the two things the grader is defined on."""
    actions = observed.get("actions")
    if not isinstance(actions, list):
        actions = []
    state = observed.get("terminal_state")
    return (
        str(state) if isinstance(state, str) else None,
        frozenset(
            str(action) for action in actions if str(action) in ACTION_VOCABULARY
        ),
    )


def combine(samples: list[tuple[str | None, frozenset[str]]]) -> dict:
    """Majority-vote independent samples into one gradable answer.

    The terminal state is the modal answer. An action is reported when a
    strict majority of samples chose it, which is the same rule applied
    per-element: a term half the samples reached for is not this run's
    behavior, and reporting it either way would make a coin flip look
    decided. `votes` keeps every count so the variance stays legible after
    the majority has collapsed it.

    A sample carrying no usable terminal state votes under `NO_TERMINAL_STATE`
    rather than under `None`, exactly as
    `triggering/executors/description_executor.py` already votes an absent
    answer. The counts become dict keys, and `json.dump(..., sort_keys=True)`
    cannot order `None` against a string: keying it raw turns one unusable
    sample into a crash that ends the whole corpus run, where the graded
    `terminal_state` below still reports `None` and grades as the single-case
    mismatch it is. No real terminal state spells `none`, so the sentinel is
    unambiguous.
    """
    repetitions = len(samples)
    state_votes = Counter(state or NO_TERMINAL_STATE for state, _ in samples)
    winning_state, agreement = state_votes.most_common(1)[0]
    action_votes = Counter(action for _, actions in samples for action in actions)
    majority = repetitions // 2 + 1
    return {
        "terminal_state": (
            None if winning_state == NO_TERMINAL_STATE else winning_state
        ),
        "actions": sorted(
            action for action, count in action_votes.items() if count >= majority
        ),
        "repetitions": repetitions,
        "agreement": agreement / repetitions,
        "votes": {
            "terminal_state": dict(state_votes),
            "actions": dict(action_votes),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument(
        "--model",
        default=None,
        help="Optional model override passed to `claude --model`",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=5,
        help="Independent samples per scenario; the majority answer is graded",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.repetitions < 1:
        raise SystemExit("--repetitions must be at least 1")
    payload = json.load(sys.stdin)
    prompt = build_prompt(payload)
    samples = [
        sample(run_claude(prompt, args.claude_bin, args.model))
        for _ in range(args.repetitions)
    ]
    json.dump(combine(samples), sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
