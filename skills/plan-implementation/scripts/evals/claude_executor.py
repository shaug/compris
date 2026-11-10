#!/usr/bin/env python3
"""Real-runtime forward-evaluation executor backed by Claude Code headless mode.

Reads one result-blind evaluation packet as JSON on stdin (the shape built by
`run_forward.py`), asks a fresh `claude -p` process to reason about how a
fully compliant plan-implementation run must terminate, and prints one JSON result:

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
import importlib.util
import json
import sys
from pathlib import Path


def _load_core():
    """Load the sampling policy from this executor's own location."""
    core_path = Path(__file__).resolve().parent / "sampling_core.py"
    spec = importlib.util.spec_from_file_location("sampling_core", core_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


core = _load_core()

RESULT_ATTEMPTS = core.RESULT_ATTEMPTS
run_claude = core.draw_json
extract_json_object = core.extract_json_object

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
    "read_prose_contract_before_authoring_body",
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


def sample(observed: dict) -> tuple[str | None, frozenset[str]]:
    """One sample reduced to the two things the grader is defined on."""
    actions = observed.get("actions")
    if not isinstance(actions, list):
        actions = []
    state = observed.get("terminal_state")
    return (
        core.claimed(state),
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

    A missing terminal-state answer votes under the canonical sentinel and
    returns as None, keeping its counts serializable without inventing a claim.
    """
    repetitions = len(samples)
    winning_state, agreement, state_votes = core.vote_single(
        state for state, _ in samples
    )
    actions, action_votes = core.vote_set(
        (actions for _, actions in samples), core.majority_of(repetitions)
    )
    return {
        "terminal_state": winning_state,
        "actions": actions,
        "repetitions": repetitions,
        "agreement": agreement,
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
    drawn, failed = core.draw_with_tolerance(
        lambda: run_claude(prompt, args.claude_bin, args.model), args.repetitions
    )
    result = combine([sample(observed) for observed in drawn])
    result["failed_samples"] = failed
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
