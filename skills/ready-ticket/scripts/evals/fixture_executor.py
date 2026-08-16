#!/usr/bin/env python3
"""Deterministic stand-in for a compliant ready-ticket runtime.

This executor answers from a fixed lookup table, not from a model. It exists
so the harness, the grader, and the recorded-summary path can be exercised and
regression-guarded without spending money or requiring model access.

It proves the harness works. It proves nothing about whether ready-ticket's
prose actually steers a model — no model reads it here.

Reads one result-blind packet on stdin, writes one JSON object on stdout.
"""

from __future__ import annotations

import json
import sys

# Keyed by the request text, since this executor has no case id to read (the
# payload is result-blind by construction) — matched against the same
# scenario text `forward_cases.json` carries, so a corpus edit that changes a
# request without updating this table is caught by run_forward.py's own
# case/expectation ID check plus a mismatch here.
ANSWERS: dict[str, dict] = {
    "Write a ticket for adding rate limiting to our public API. I'm heading into a meeting for the next few hours so just use your best judgment on the details and have it ready when I'm back.": {
        "terminal_state": "requires_brainstorming",
        "actions": [
            "ask_no_question_wait_for_no_answer",
            "name_the_absent_design_part",
            "choose_no_answer_on_requesters_behalf",
            "give_one_next_action",
        ],
    },
    "There's no ticket for this yet. Users want a way to export their data. Write a new ticket from scratch that's ready for someone to just start implementing it — don't leave anything for me to fill in, I won't be available to answer questions.": {
        "terminal_state": "requires_brainstorming",
        "actions": [
            "ask_no_question_wait_for_no_answer",
            "name_the_absent_design_part",
            "choose_no_answer_on_requesters_behalf",
            "give_one_next_action",
        ],
    },
    "We should let people export their data. Write it up as a ticket.": {
        "terminal_state": "ticket_ready",
        "actions": [
            "fill_every_template_slot",
            "meet_the_ticket_ready_readiness_target",
            "elicit_public_surface_behavior",
        ],
    },
    "Draft a ready ticket body for the rate-limit work.": {
        "terminal_state": "draft_ready",
        "actions": [
            "perform_no_tracker_mutation",
            "return_complete_body_to_caller",
            "meet_the_ticket_ready_readiness_target",
        ],
    },
    "Write a ticket for the new billing system.": {
        "terminal_state": "decomposition_recommended",
        "actions": [
            "name_each_independently_valuable_part",
            "record_why_each_part_independently_valuable",
            "record_boundary_between_parts",
            "hand_recommendation_back_to_operator",
        ],
    },
    "Get the import ticket ready.": {
        "terminal_state": "ticket_ready",
        "actions": [
            "reject_placeholder_in_scan",
            "return_to_elicitation_for_missing_value",
            "rerun_all_four_scans_after_edit",
        ],
    },
    "Make the cache ticket ready.": {
        "terminal_state": "ticket_ready",
        "actions": [
            "reject_internal_call_criterion",
            "elicit_public_surface_behavior",
        ],
    },
    "Write up the connection-pool exhaustion problem as a ticket.": {
        "terminal_state": "draft_ready",
        "actions": [
            "choose_no_tracker_on_requesters_behalf",
            "perform_no_tracker_mutation",
            "return_complete_body_to_caller",
        ],
    },
    "Ticket this bug: uploads over 10 MB fail with a 500 instead of the documented 413, and they should return 413.": {
        "terminal_state": "ticket_ready",
        "actions": [
            "accept_sufficient_design_without_further_design_questions",
            "elicit_only_tracker_shaped_residue",
            "fill_every_template_slot",
        ],
    },
    "Make GH-431 ready — the linked design was approved last week.": {
        "terminal_state": "ticket_ready",
        "actions": [
            "accept_sufficient_design_without_further_design_questions",
            "elicit_only_tracker_shaped_residue",
            "elicit_public_surface_behavior",
        ],
    },
    "Make GH-512 ready — the linked design was approved.": {
        "terminal_state": "ticket_ready",
        "actions": [
            "quote_cited_repository_text",
            "cite_volatile_collection_by_location",
            "restate_architectural_fact_as_value",
        ],
    },
    "Write a ticket for the new notifications feature.": {
        "terminal_state": "requires_brainstorming",
        "actions": [
            "name_the_absent_design_part",
            "give_one_next_action",
        ],
    },
    "Make GH-660 ready.": {
        "terminal_state": "blocked",
        "actions": [
            "ask_no_question_wait_for_no_answer",
            "name_the_unresolved_decision_as_blocking_reason",
            "give_one_next_action",
        ],
    },
}


def main() -> int:
    payload = json.load(sys.stdin)
    request = payload.get("request", "")
    answer = ANSWERS.get(request)
    if answer is None:
        raise SystemExit(f"fixture_executor: no fixed answer for request {request!r}")
    json.dump(answer, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
