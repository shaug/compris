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
import json
import re
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

# How long a scenario stands down before redrawing after every one of its
# concurrent samples failed at once.
SCENARIO_RETRY_PAUSE_SECONDS = 30

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
    "access_credential",
    "access_no_credential",
    "adopt_verified_canonical_pr",
    "allow_acceptance_completion",
    "assert_review_converged",
    "author_missing_author_content",
    "avoid_irrelevant_ui_gates",
    "bind_installed_implement_ticket",
    "build_acceptance_ledger",
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
    "preserve_tracker_pr_host_separation",
    "preserve_user_authority",
    "publish_inline",
    "rebuild_remote_gates",
    "record_guardrail_evidence",
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
    "report_delivery_acceptance_separately",
    "report_mid_stack_redesign",
    "report_missing_reopen_authority",
    "report_needs_author_input",
    "report_partial_split_merge",
    "report_partial_publication",
    "report_unchecked_ticket_assumption",
    "reopen_auto_closed_ticket",
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
            ' "acceptance_ledger": <one derived evidence record per authored criterion>}',
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

    # The model occasionally ends its turn (stop_reason "end_turn", not a
    # token-limit stop) with the JSON object incomplete -- e.g. missing the
    # final closing brace, or an unescaped quote inside a string value. This
    # is a malformed *response*, not a boundary-detection bug in
    # extract_json_object; retrying with a fresh, independent sample clears
    # it almost every time. A single flaky response must not sink an entire
    # run of many sequential cases.
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


def claimed(value) -> str | None:
    """One single-valued answer, as a string or as no answer at all.

    A sample may answer `["blocked"]` or `1` where a name belongs. Downstream
    these two fields are counted and compared — `Counter` keys, `min()` — so a
    non-string reaches that arithmetic as a `TypeError`, which is a non-zero
    executor exit, which ends the whole corpus run and files a stage of sixty
    scenarios as `attempted`. Rendering the claim keeps it gradable as the one
    mismatch it is; `None` stays `None`, because no answer and a wrongly shaped
    answer are different results and only the first is an absence.
    """
    if value is None or isinstance(value, str):
        return value
    return str(value)


def normalize(observed: dict) -> dict:
    actions = observed.get("actions")
    if not isinstance(actions, list):
        actions = []
    ledger = observed.get("acceptance_ledger")
    if not isinstance(ledger, list):
        ledger = []
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
    }


# A vote key for an answer the model did not give. The counts become JSON
# object keys, and `json.dump(..., sort_keys=True)` cannot order `None` against
# a string, so one unusable sample would otherwise crash the whole corpus run
# at output time. No real terminal state or skill name spells `none`.
NO_ANSWER = "none"


def _modal(votes: Counter) -> tuple[str, int]:
    """The most-voted answer and its count, ties broken by sorted order."""
    top = max(votes.values())
    return min(answer for answer, count in votes.items() if count == top), top


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
        status, _ = _modal(statuses[criterion])
        multiplicity, _ = _modal(multiplicities[criterion])
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
    majority = repetitions // 2 + 1
    skill_votes = Counter(item["target_skill"] or NO_ANSWER for item in samples)
    state_votes = Counter(item["terminal_state"] or NO_ANSWER for item in samples)
    action_votes = Counter(action for item in samples for action in item["actions"])
    winning_skill, _ = _modal(skill_votes)
    winning_state, agreement = _modal(state_votes)
    ledger, ledger_votes = _combine_ledger(samples, majority)
    return {
        "target_skill": None if winning_skill == NO_ANSWER else winning_skill,
        "terminal_state": None if winning_state == NO_ANSWER else winning_state,
        "actions": sorted(
            action for action, count in action_votes.items() if count >= majority
        ),
        "acceptance_ledger": ledger,
        "repetitions": repetitions,
        "agreement": agreement / repetitions,
        "votes": {
            "target_skill": dict(skill_votes),
            "terminal_state": dict(state_votes),
            "actions": dict(action_votes),
            "acceptance_ledger": ledger_votes,
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


def draw(prompt: str, claude_bin: str, model: str) -> dict | None:
    """One sample, or `None` when this draw could not be taken at all.

    A sample the runtime refused — a non-zero `claude` exit, or three malformed
    responses in a row — is a missing sample, not an answer. Letting it end the
    process would sink every case already sampled in this run and leave the
    recorder to file the whole stage as `attempted`, the status reserved for an
    environment without model access. `combine` votes over what was actually
    drawn, and `failed_samples` reports what was not.
    """
    try:
        return run_claude(prompt, claude_bin, model)
    except RuntimeError:
        return None


def draw_batch(prompt: str, claude_bin: str, model: str, repetitions: int) -> list:
    """One round of independent samples, minus the ones the runtime refused.

    The samples are independent by construction, so they are drawn
    concurrently: this corpus is four times the size of its sibling's, and
    drawing five sequential samples for each case would put a recorded stage
    into the hours. Every round goes through here, so the redraw below is as
    concurrent as the first round and is counted the same way.
    """
    with ThreadPoolExecutor(max_workers=repetitions) as pool:
        observed = pool.map(
            lambda _: draw(prompt, claude_bin, model), range(repetitions)
        )
    return [item for item in observed if item is not None]


def main() -> int:
    args = parse_args()
    if args.repetitions < 1:
        raise SystemExit("--repetitions must be at least 1")
    payload = json.load(sys.stdin)
    prompt = build_prompt(payload)
    drawn = draw_batch(prompt, args.claude_bin, args.model, args.repetitions)
    failed = args.repetitions - len(drawn)
    if not drawn:
        # Every concurrent sample failing at once reads as a burst — throttling,
        # an overloaded backend — rather than as an unusable environment, and
        # this scenario is one of sixty in a run that has already spent half an
        # hour. Stand down briefly and redraw once; a second empty draw is the
        # environment, and the recorder files the whole stage as `attempted`.
        time.sleep(SCENARIO_RETRY_PAUSE_SECONDS)
        drawn = draw_batch(prompt, args.claude_bin, args.model, args.repetitions)
        failed += args.repetitions - len(drawn)
    if not drawn:
        raise RuntimeError(
            f"every one of the {args.repetitions} samples failed for this "
            f"scenario, twice, {SCENARIO_RETRY_PAUSE_SECONDS}s apart"
        )
    result = combine([normalize(item) for item in drawn])
    result["failed_samples"] = failed
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
