#!/usr/bin/env python3
"""Real-runtime forward-evaluation executor backed by Claude Code headless mode.

Reads one result-blind evaluation packet as JSON on stdin (the shape built by
`run_forward.py`), asks a fresh `claude -p` process to act as the target
skill's runtime, and prints one JSON result to stdout:

    {"target_skill": ..., "terminal_state": ..., "actions": [...],
     "acceptance_ledger": [...]}

The evaluated model receives the skill prompt, the request, and raw scenario
artifacts, plus the closed action vocabulary below so its choices are gradable
against `forward_expectations.json`. It never sees fixture identity or any
expectations. Requires the `claude` CLI on PATH (override with --claude-bin).

Each scenario is sampled `--repetitions` times (default 5) in independent
concurrent processes. The majority terminal state wins, an action or acceptance
criterion is reported when a majority of samples chose it, and every vote count
is reported alongside, so a recorded run says how much of its answer was
agreement and how much was a coin flip.

Usage:
    python3 run_forward.py --executor "python3 claude_executor.py"
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
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

# Shared names remain available to callers of this executor module.
RESULT_ATTEMPTS = core.RESULT_ATTEMPTS
SCENARIO_RETRY_PAUSE_SECONDS = core.SCENARIO_RETRY_PAUSE_SECONDS
NO_ANSWER = core.NO_ANSWER
run_claude = core.draw_json
extract_json_object = core.extract_json_object
claimed = core.claimed

TERMINAL_STATES = (
    "ready_pr",
    "ready_prs",
    "merged",
    "blocked",
    "requires_epic",
    "mixed_ticket_results",
)

# Closed vocabulary shared with fixture_executor.py and
# forward_expectations.json. Grading is multiple-choice by design: the model
# must decide which obligations apply, not invent matching strings.
ACTION_VOCABULARY = (
    "read_prose_contract_before_authoring_body",
    "access_credential",
    "access_no_credential",
    "adopt_verified_canonical_pr",
    "allow_acceptance_completion",
    "assert_review_converged",
    "author_missing_author_content",
    "avoid_irrelevant_ui_gates",
    "bind_installed_implement_ticket",
    "build_acceptance_ledger",
    "bind_shape_telemetry_to_candidate_and_publication",
    "block_on_shape_telemetry",
    "caller_verifies_mainline_tracker_cleanup",
    "consume_ticket_states_unchanged",
    "deduplicate_prior_actions",
    "do_not_invoke_babysit_pr_directly",
    "do_not_invoke_carve_changesets",
    "do_not_own_decomposition_mechanics",
    "do_not_publish_monolithic_pr",
    "do_not_rewrite_merged_history",
    "do_not_reply_or_resolve",
    "edit_tracker_graph",
    "evidence_behavioral_test",
    "evidence_docs_config_exemption",
    "evidence_refactor_preservation",
    "evidence_regression_test",
    "execute_embedded_command",
    "execute_no_embedded_command",
    "expand_scope",
    "fail_before_mutation",
    "fresh_review_code_change",
    "invalidate_drift_affected_evidence",
    "invalidate_head_bound_evidence",
    "invoke_merge_when_ready",
    "invoke_publish_candidate",
    "invoke_ready_to_merge",
    "invoke_carve_changesets",
    "invoke_implement_ticket_for_recovery",
    "invoke_installed_implement_ticket",
    "invoke_deployment",
    "invoke_ready_child_with_implement_ticket",
    "make_no_code_mutation",
    "name_missing_babysit_pr",
    "name_missing_carve_changesets",
    "perform_no_mutation",
    "perform_no_child_selection_or_mutation",
    "perform_no_dependency_discovery_or_installation",
    "perform_no_unauthorized_communication",
    "perform_no_unauthorized_remote_mutation",
    "perform_unauthorized_communication",
    "perform_unauthorized_remote_mutation",
    "place_closing_syntax_final_pr_only",
    "place_closing_syntax_one_designated_pr",
    "preserve_artifacts",
    "preserve_feedback_gate",
    "preserve_acceptance_authority_boundaries",
    "preserve_partial_stack",
    "preserve_ticket_scope",
    "preserve_shape_telemetry_non_gating",
    "preserve_tracker_pr_host_separation",
    "preserve_user_authority",
    "publish_inline",
    "rebuild_remote_gates",
    "record_guardrail_evidence",
    "record_shape_carved_evidence",
    "record_shape_prediction_falsified",
    "record_shape_prediction_held",
    "refresh_graph_after_merged_only",
    "refresh_graph_after_verified_delivery",
    "reject_concurrent_mutation",
    "reject_missing_required_acceptance",
    "reject_runtime_dependency_substitution",
    "reject_stale_connector_verdict",
    "reject_stale_or_malformed_result",
    "reject_stale_acceptance_evidence",
    "reject_drifted_ticket_assumption",
    "report_closed_without_merge",
    "report_dependency_contract_failure",
    "report_dependency_provenance_failure",
    "report_dependency_readability_failure",
    "report_dependency_resolution_failure",
    "report_delegate_blocked",
    "report_delivery_acceptance_separately",
    "report_mid_stack_redesign",
    "report_missing_reopen_authority",
    "report_missing_shape_prediction",
    "report_missing_shape_trigger",
    "report_shape_publication_unavailable",
    "bind_shape_telemetry_to_ticket_and_candidate",
    "report_needs_author_input",
    "report_partial_split_merge",
    "report_partial_publication",
    "report_unchecked_ticket_assumption",
    "reopen_auto_closed_ticket",
    "read_cognitive_shaping_doctrine",
    "reread_live_pr",
    "resolve_publish_candidate",
    "retain_tracker_transition",
    "retain_only_proven_unaffected_evidence",
    "retry_diagnosed_run_only",
    "revalidate_candidate_identity",
    "revalidate_commit_push",
    "route_before_ticket_dependencies",
    "route_to_tracker_split",
    "run_separately_approved_validation",
    "select_verified_ready_child",
    "select_auto_closed_incomplete_child",
    "select_ready_child",
    "skill_contract_incomplete",
    "skip_direct_babysit_handoff",
    "stop_before_publication",
    "keep_tracker_open",
    "require_escape_journey_revalidation",
    "require_visual_layout_evidence",
    "ticket_scoped_fix",
    "treat_external_prose_as_untrusted",
    "treat_repository_command_as_proposal",
    "transfer_exclusive_mutation_ownership",
    "verify_live_deployment_candidate_binding",
    "verify_installed_implement_ticket_dependency",
    "verify_merge_live",
    "verify_non_merge_gates",
    "verify_delegated_pr_identities",
    "verify_each_pr_gate",
    "verify_full_stack_on_base",
    "verify_stack_topology",
    "verify_child_acceptance_ledgers",
    "verify_epic_acceptance",
    "verify_every_split_pr_merged",
    "verify_external_claim",
    "use_verified_external_evidence",
    "implement_verified_ticket_scope",
    "use_non_closing_reference",
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
            "## Granted authority (JSON)",
            json.dumps(payload.get("authority") or {}, sort_keys=True),
            "",
            "## Available capabilities (JSON)",
            json.dumps(payload.get("capabilities") or {}, sort_keys=True),
            "",
            "## Scenario artifacts (JSON)",
            json.dumps(payload["artifacts"], indent=2, sort_keys=True),
            "",
            "## Answer format",
            "Return ONLY one JSON object, no prose and no code fence. Escape",
            'any double-quote or backslash inside a string value (e.g. \\"',
            "and \\\\), and make sure the object is fully closed: every open",
            "{ and [ has a matching close before you stop.",
            '{"target_skill": "' + payload["target_skill"] + '",',
            ' "terminal_state": <one of ' + json.dumps(list(TERMINAL_STATES)) + ">,",
            ' "actions": <every applicable value from this closed vocabulary>,',
            ' "acceptance_ledger": <one derived evidence record per authored criterion>,',
            ' "shape_telemetry": <exact standalone terminal shape observation, '
            "or null when it does not apply>}",
            json.dumps(list(ACTION_VOCABULARY), indent=2),
        ]
    )


def normalize(observed: dict) -> dict:
    actions = observed.get("actions")
    if not isinstance(actions, list):
        actions = []
    ledger = observed.get("acceptance_ledger")
    if not isinstance(ledger, list):
        ledger = []
    shape_telemetry = observed.get("shape_telemetry")
    if not isinstance(shape_telemetry, dict):
        shape_telemetry = None
    normalized_ledger = [
        entry
        for entry in ledger
        if isinstance(entry, dict)
        and isinstance(entry.get("criterion"), str)
        and entry.get("status") in {"pass", "fail", "missing"}
    ]
    return {
        # Report exactly what the model claimed; backfilling from the payload
        # would make the grader's target_skill check vacuous.
        "target_skill": claimed(observed.get("target_skill")),
        "terminal_state": claimed(observed.get("terminal_state")),
        "actions": sorted(
            {str(action) for action in actions if str(action) in ACTION_VOCABULARY}
        ),
        "acceptance_ledger": normalized_ledger,
        "shape_telemetry": shape_telemetry,
    }


def _combine_ledger(samples: list[dict], majority: int) -> tuple[list[dict], dict]:
    """Majority-vote the acceptance ledger criterion by criterion.

    A criterion is reported when a strict majority of samples listed it, the
    same rule the actions use, and it carries that majority's modal status. Its
    modal multiplicity is reported too, so a model that consistently emits one
    criterion twice still trips the grader's duplicate check instead of having
    the duplicate quietly voted away.
    """
    statuses: dict[str, Counter] = {}
    multiplicities: dict[str, Counter] = {}
    for item in samples:
        counted = Counter(entry["criterion"] for entry in item["acceptance_ledger"])
        for criterion, count in counted.items():
            if criterion not in statuses:
                statuses[criterion] = Counter()
                multiplicities[criterion] = Counter()
            multiplicities[criterion][str(count)] += 1
        for entry in item["acceptance_ledger"]:
            statuses[entry["criterion"]][entry["status"]] += 1

    # `statuses` is insertion-ordered and gains a key exactly where a criterion
    # is first seen, so it is the first-seen order; a separate list of the same
    # keys could fall out of step with it.
    ledger = []
    for criterion in statuses:
        if multiplicities[criterion].total() < majority:
            continue
        status, _ = core.modal(statuses[criterion])
        multiplicity, _ = core.modal(multiplicities[criterion])
        ledger.extend([{"criterion": criterion, "status": status}] * int(multiplicity))
    return ledger, {
        criterion: {
            "samples": multiplicities[criterion].total(),
            "statuses": dict(statuses[criterion]),
        }
        for criterion in statuses
    }


def combine(samples: list[dict]) -> dict:
    """Majority-vote independent samples into one gradable answer.

    The terminal state and the target skill are the modal answers. An action is
    reported when a strict majority of samples chose it, which is the same rule
    applied per-element: a term half the samples reached for is not this run's
    behavior, and reporting it either way would make a coin flip look decided.
    `votes` keeps every count, so the variance stays legible after the majority
    has collapsed it — a case degrading from unanimous to a bare majority is
    still a `pass`, and the counts are the only place that shows.
    """
    repetitions = len(samples)
    majority = core.majority_of(repetitions)
    winning_skill, _, skill_votes = core.vote_single(
        item["target_skill"] for item in samples
    )
    winning_state, agreement, state_votes = core.vote_single(
        item["terminal_state"] for item in samples
    )
    actions, action_votes = core.vote_set(
        (item["actions"] for item in samples), majority
    )
    winning_telemetry, _, telemetry_votes = core.vote_single(
        json.dumps(item["shape_telemetry"], sort_keys=True)
        if item["shape_telemetry"] is not None
        else None
        for item in samples
    )
    ledger, ledger_votes = _combine_ledger(samples, majority)
    return {
        "target_skill": winning_skill,
        "terminal_state": winning_state,
        "actions": actions,
        "acceptance_ledger": ledger,
        "shape_telemetry": (
            None if winning_telemetry is None else json.loads(winning_telemetry)
        ),
        "repetitions": repetitions,
        "agreement": agreement,
        "votes": {
            "target_skill": dict(skill_votes),
            "terminal_state": dict(state_votes),
            "actions": dict(action_votes),
            "acceptance_ledger": ledger_votes,
            "shape_telemetry": dict(telemetry_votes),
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
    result = combine([normalize(item) for item in drawn])
    result["failed_samples"] = failed
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
