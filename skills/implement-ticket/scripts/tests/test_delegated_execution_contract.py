"""Tests for the optional delegated implement-ticket protocol."""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path
from types import ModuleType

SKILL_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = SKILL_ROOT / "references" / "delegated-execution"
SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40


def load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "delegated_execution_validator",
        CONTRACT_ROOT / "validate.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load delegated execution validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def invocation() -> dict[str, object]:
    return {
        "schema": "compris.implement-ticket/delegated-invocation/v2",
        "capability": "compris.implement-ticket/delegated-execution/v2",
        "invocation_id": "run-123",
        "ticket": {
            "provider": "github",
            "id": "123",
            "url": "https://github.com/example/project/issues/123",
            "observation": "sha256:ticket",
        },
        "repository": {
            "identity": "github:example/project",
            "remote_url": "git@github.com:example/project.git",
            "base_ref": "refs/heads/main",
            "base_sha": SHA_A,
        },
        "work": {
            "id": "external-work-123",
            "revision": 1,
            "approval_evidence": "coordinator-record:approved-123",
            "intent": "Add the approved behavior",
            "scope": ["one reviewable change"],
            "non_goals": ["merge"],
            "constraints": ["preserve compatibility"],
            "done_definition": ["one ready PR"],
        },
        "validation": ["just test", "just lint"],
        "review": {
            "independent": True,
            "unresolved_feedback_required": True,
        },
        "authority": {
            "allow": [
                "repository.candidate.create",
                "repository.candidate.push",
                "pull_request.create",
                "pull_request.update",
                "review.reply",
                "review.resolve",
            ]
        },
        "desired_outcome": "ready_pr",
        "accepted_terminal_states": [
            "ready_pr",
            "blocked",
            "requires_epic",
        ],
        "acceptance_requirements": [
            {
                "criterion": "Automated regression suite passes",
                "required": True,
                "evidence_category": "automated_test",
                "stage": "pre_merge",
                "identity": "candidate",
                "environment": "local",
                "url": None,
                "source": "just test",
            }
        ],
        "starting_deployment": None,
        "checkpoint": {
            "command": ["example-coordinator", "checkpoint"],
            "last_sequence": 0,
            "continuation_token": "token-0",
        },
    }


def candidate(kind: str = "ordinary") -> dict[str, object]:
    return {
        "repository": "github:example/project",
        "remote_url": "git@github.com:example/project.git",
        "remote_ref": "refs/heads/example-work",
        "base_sha": SHA_A,
        "head_sha": SHA_B,
        "publication": {
            "kind": kind,
            "pull_requests": [
                {
                    "id": "456",
                    "url": "https://github.com/example/project/pull/456",
                    "base_ref": "refs/heads/main",
                    "base_sha": SHA_A,
                    "head_ref": "refs/heads/example-work",
                    "head_sha": SHA_B,
                    "state": "open",
                }
            ],
        },
    }


def result() -> dict[str, object]:
    source = invocation()
    return {
        "schema": "compris.implement-ticket/delegated-result/v2",
        "capability": "compris.implement-ticket/delegated-execution/v2",
        "invocation_id": "run-123",
        "terminal_state": "ready_pr",
        "ticket": source["ticket"],
        "repository": {
            "identity": "github:example/project",
            "base_ref": "refs/heads/main",
            "base_sha": SHA_A,
        },
        "implementation_state": "published",
        "tracker_transition": {
            "provider": "github",
            "ticket_id": "123",
            "mode": "none",
            "state": "open",
            "observed_at": "2026-07-25T12:11:30Z",
        },
        "candidate": candidate(),
        "handoff": {"transferable": True, "reason": None},
        "checkpoint": {
            "last_sequence": 4,
            "continuation_token": "token-4",
        },
        "validation": [
            {
                "name": "just test",
                "outcome": "passed",
                "candidate_sha": SHA_B,
                "observed_at": "2026-07-25T12:00:00Z",
            }
        ],
        "reviews": [
            {
                "name": "review-code-change",
                "outcome": "passed",
                "candidate_sha": SHA_B,
                "observed_at": "2026-07-25T12:10:00Z",
            }
        ],
        "feedback": {
            "unresolved_material_count": 0,
            "candidate_sha": SHA_B,
            "observed_at": "2026-07-25T12:11:00Z",
        },
        "authority_used": [
            "repository.candidate.create",
            "repository.candidate.push",
            "pull_request.create",
        ],
        "acceptance_evidence": [
            {
                "criterion": "Automated regression suite passes",
                "required": True,
                "evidence_category": "automated_test",
                "stage": "pre_merge",
                "candidate_sha": SHA_B,
                "deployed_sha": None,
                "environment": "local",
                "url": None,
                "source": "just test",
                "status": "pass",
            }
        ],
        "unresolved_obligations": [],
        "blocking_reason": None,
        "next_action": "Caller may accept the ready PR",
    }


def record_tracker_transition(
    value: dict[str, object],
    source: dict[str, object] | None = None,
    mode: str = "manual",
) -> None:
    """Record tracker closure and the authority action that enabled it."""
    value["tracker_transition"] = {
        "provider": value["ticket"]["provider"],
        "ticket_id": value["ticket"]["id"],
        "mode": mode,
        "state": "closed",
        "observed_at": "2026-07-25T12:12:00Z",
    }
    action = "ticket.update" if mode == "manual" else "tracker.auto_close.authorize"
    value["authority_used"].append(action)
    if source is not None:
        source["authority"]["allow"].append(action)


def checkpoint_request(phase: str = "pre_external_mutation") -> dict[str, object]:
    published_candidate = candidate()
    published_candidate.pop("publication")
    return {
        "schema": "compris.implement-ticket/checkpoint-request/v2",
        "capability": "compris.implement-ticket/delegated-execution/v2",
        "invocation_id": "run-123",
        "continuation_token": "token-1",
        "sequence": 2,
        "phase": phase,
        "action": "repository.candidate.push",
        "ticket_observation": "sha256:ticket",
        "candidate": published_candidate,
        "deployment": None,
        "proposed_effect": "Publish the exact candidate",
    }


def checkpoint_response() -> dict[str, object]:
    return {
        "schema": "compris.implement-ticket/checkpoint-response/v2",
        "invocation_id": "run-123",
        "request_sequence": 2,
        "prior_continuation_token": "token-1",
        "continuation_token": "token-2",
        "decision": "allow",
        "reason": None,
        "acknowledged_candidate_sha": None,
        "observed_deployment": None,
    }


class DelegatedExecutionContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = load_validator()

    def test_all_contract_files_are_valid_json_or_documented_markdown(self) -> None:
        for path in CONTRACT_ROOT.glob("*.schema.json"):
            self.assertIsInstance(json.loads(path.read_text()), dict)
        manifest = json.loads((CONTRACT_ROOT / "capability.json").read_text())
        self.assertEqual([], self.validator.validate("capability", manifest))
        self.assertIn(
            "compris.implement-ticket/delegated-execution/v2",
            (CONTRACT_ROOT / "CONTRACT.md").read_text(),
        )

    def test_valid_invocation_and_result_match(self) -> None:
        source = invocation()
        value = result()
        value["validation"].append(
            {
                "name": "just lint",
                "outcome": "passed",
                "candidate_sha": SHA_B,
                "observed_at": "2026-07-25T12:01:00Z",
            }
        )
        self.assertEqual([], self.validator.validate("invocation", source))
        self.assertEqual(
            [],
            self.validator.validate_result_for_invocation(source, value),
        )

    def test_unknown_invocation_field_fails_closed(self) -> None:
        value = invocation()
        value["coordinator"] = "atelier"
        self.assertIn(
            "$.coordinator: unknown property",
            self.validator.validate("invocation", value),
        )

    def test_desired_outcome_must_be_accepted(self) -> None:
        value = invocation()
        value["accepted_terminal_states"] = ["blocked", "requires_epic"]
        self.assertIn(
            "$.desired_outcome: must appear in accepted_terminal_states",
            self.validator.validate("invocation", value),
        )

    def test_invocation_carries_checkpoint_resume_position(self) -> None:
        value = invocation()
        value["checkpoint"].pop("last_sequence")
        self.assertIn(
            "$.checkpoint: missing required property 'last_sequence'",
            self.validator.validate("invocation", value),
        )

    def test_candidate_publication_requires_exact_acknowledgement(self) -> None:
        request = checkpoint_request("candidate_published")
        response = checkpoint_response()
        response["acknowledged_candidate_sha"] = SHA_B
        self.assertEqual(
            [],
            self.validator.validate_checkpoint_exchange(request, response),
        )
        response["acknowledged_candidate_sha"] = SHA_A
        self.assertIn(
            "$.acknowledged_candidate_sha: does not match published candidate",
            self.validator.validate_checkpoint_exchange(request, response),
        )

    def test_deployment_observation_requires_caller_verified_candidate_binding(
        self,
    ) -> None:
        request = checkpoint_request("deployment_observed")
        request["action"] = "deployment.execute"
        request["deployment"] = {
            "candidate_sha": SHA_B,
            "deployed_sha": SHA_C,
            "environment": "production",
            "url": "https://example.test",
        }
        response = checkpoint_response()
        response["observed_deployment"] = copy.deepcopy(request["deployment"])

        self.assertEqual(
            [], self.validator.validate_checkpoint_exchange(request, response)
        )

        response["observed_deployment"]["candidate_sha"] = SHA_A
        self.assertIn(
            "$.observed_deployment: does not match caller-verified deployment",
            self.validator.validate_checkpoint_exchange(request, response),
        )

        request["deployment"]["candidate_sha"] = SHA_A
        self.assertIn(
            "$.deployment.candidate_sha: does not match candidate",
            self.validator.validate("checkpoint-request", request),
        )

    def test_checkpoint_identity_and_token_must_match(self) -> None:
        request = checkpoint_request()
        response = checkpoint_response()
        response["prior_continuation_token"] = "wrong"
        self.assertIn(
            "$.prior_continuation_token: does not match request continuation_token",
            self.validator.validate_checkpoint_exchange(request, response),
        )

    def test_checkpoint_progress_rejects_replay(self) -> None:
        request = checkpoint_request()
        response = checkpoint_response()
        self.assertEqual(
            [],
            self.validator.validate_checkpoint_progress(
                1,
                "token-1",
                request,
                response,
            ),
        )
        self.assertTrue(
            self.validator.validate_checkpoint_progress(
                2,
                "token-2",
                request,
                response,
            )
        )

    def test_allow_rotates_token_and_deny_explains_reason(self) -> None:
        response = checkpoint_response()
        response["continuation_token"] = "token-1"
        self.assertIn(
            "$.continuation_token: allow must rotate the token",
            self.validator.validate("checkpoint-response", response),
        )
        response["decision"] = "deny"
        response["continuation_token"] = "token-2"
        errors = self.validator.validate("checkpoint-response", response)
        self.assertIn("$.reason: deny requires a reason", errors)
        self.assertIn(
            "$.continuation_token: deny must preserve the prior token",
            errors,
        )
        response["reason"] = "Current authority changed"
        response["continuation_token"] = response["prior_continuation_token"]
        self.assertEqual([], self.validator.validate("checkpoint-response", response))

    def test_local_blocked_state_is_explicitly_not_transferable(self) -> None:
        value = result()
        value.update(
            {
                "terminal_state": "blocked",
                "implementation_state": "local",
                "candidate": None,
                "handoff": {
                    "transferable": False,
                    "reason": "Candidate push was not authorized",
                },
                "blocking_reason": "Candidate push was not authorized",
            }
        )
        value["authority_used"] = ["repository.candidate.create"]
        self.assertEqual([], self.validator.validate("result", value))

    def test_published_blocked_state_preserves_transferable_candidate(self) -> None:
        value = result()
        value["terminal_state"] = "blocked"
        value["blocking_reason"] = "Coordinator unavailable after publication"
        value["candidate"]["publication"]["pull_requests"] = []
        self.assertEqual([], self.validator.validate("result", value))

    def test_ready_pr_rejects_stack_or_local_only_candidate(self) -> None:
        value = result()
        value["candidate"] = candidate("stack")
        self.assertIn(
            "$.candidate.publication: ready_pr requires one ordinary PR",
            self.validator.validate("result", value),
        )
        value = result()
        value["implementation_state"] = "local"
        self.assertTrue(self.validator.validate("result", value))

    def test_result_cannot_exceed_invocation_authority(self) -> None:
        value = result()
        value["authority_used"].append("pull_request.merge")
        self.assertIn(
            "$.authority_used: exceeds invocation: pull_request.merge",
            self.validator.validate_result_for_invocation(invocation(), value),
        )

    def test_result_identity_must_match_invocation(self) -> None:
        value = copy.deepcopy(result())
        value["ticket"]["observation"] = "sha256:changed"
        self.assertIn(
            "$.ticket: does not match invocation",
            self.validator.validate_result_for_invocation(invocation(), value),
        )

    def test_terminal_checkpoint_must_match_caller_ledger_tail(self) -> None:
        source = invocation()
        source["validation"] = ["just test"]
        value = result()
        self.assertEqual(
            [],
            self.validator.validate_result_checkpoint_state(
                source,
                value,
                4,
                "token-4",
            ),
        )
        value["checkpoint"] = {
            "last_sequence": 0,
            "continuation_token": "token-0",
        }
        errors = self.validator.validate_result_checkpoint_state(
            source,
            value,
            4,
            "token-4",
        )
        self.assertIn(
            "$.checkpoint.last_sequence: does not match caller ledger",
            errors,
        )
        self.assertIn(
            "$.checkpoint.continuation_token: does not match caller ledger",
            errors,
        )

    def test_checkpoint_tail_accepts_live_candidate_bound_deployment(self) -> None:
        source = invocation()
        source["validation"] = ["just test"]
        source["desired_outcome"] = "merged"
        source["accepted_terminal_states"].append("merged")
        source["acceptance_requirements"].append(
            {
                "criterion": "Production deployment smoke passes",
                "required": True,
                "evidence_category": "deployed_integration",
                "stage": "post_merge",
                "identity": "deployment",
                "environment": "production",
                "url": "https://example.test",
                "source": "production smoke run",
            }
        )
        value = result()
        value["terminal_state"] = "merged"
        record_tracker_transition(value, source)
        value["candidate"]["publication"]["pull_requests"][0]["state"] = "merged"
        value["acceptance_evidence"].append(
            {
                "criterion": "Production deployment smoke passes",
                "required": True,
                "evidence_category": "deployed_integration",
                "stage": "post_merge",
                "candidate_sha": None,
                "deployed_sha": SHA_C,
                "environment": "production",
                "url": "https://example.test",
                "source": "production smoke run",
                "status": "pass",
            }
        )
        observed_deployment = {
            "candidate_sha": SHA_B,
            "deployed_sha": SHA_C,
            "environment": "production",
            "url": "https://example.test",
        }
        observed_tracker = copy.deepcopy(value["tracker_transition"])
        consumed_authority = list(value["authority_used"])

        self.assertEqual(
            [],
            self.validator.validate_result_checkpoint_state(
                source,
                value,
                4,
                "token-4",
                observed_deployment,
                observed_tracker,
                consumed_authority,
            ),
        )

        unauthorized = copy.deepcopy(source)
        unauthorized["authority"]["allow"].remove("ticket.update")
        self.assertIn(
            "$.authority_used: exceeds invocation: ticket.update",
            self.validator.validate_result_checkpoint_state(
                unauthorized,
                value,
                4,
                "token-4",
                observed_deployment,
                observed_tracker,
                consumed_authority,
            ),
        )

        unverified_tracker = copy.deepcopy(observed_tracker)
        unverified_tracker["observed_at"] = "2026-07-25T12:13:00Z"
        self.assertIn(
            "$.tracker_transition: does not match caller-observed tracker state",
            self.validator.validate_result_checkpoint_state(
                source,
                value,
                4,
                "token-4",
                observed_deployment,
                unverified_tracker,
                consumed_authority,
            ),
        )

        no_transition_authority = copy.deepcopy(value)
        no_transition_authority["authority_used"].remove("ticket.update")
        self.assertIn(
            "$.authority_used: manual tracker transition requires ticket.update",
            self.validator.validate_result_checkpoint_state(
                source,
                no_transition_authority,
                4,
                "token-4",
                observed_deployment,
                observed_tracker,
                no_transition_authority["authority_used"],
            ),
        )

        automatic_source = copy.deepcopy(source)
        automatic_source["authority"]["allow"].remove("ticket.update")
        automatic_source["authority"]["allow"].append("tracker.auto_close.authorize")
        automatic = copy.deepcopy(value)
        automatic["tracker_transition"]["mode"] = "automatic"
        automatic["authority_used"].remove("ticket.update")
        automatic["authority_used"].append("tracker.auto_close.authorize")
        automatic_tracker = copy.deepcopy(automatic["tracker_transition"])
        self.assertEqual(
            [],
            self.validator.validate_result_checkpoint_state(
                automatic_source,
                automatic,
                4,
                "token-4",
                observed_deployment,
                automatic_tracker,
                automatic["authority_used"],
            ),
        )
        self.assertIn(
            "$.observed_tracker: merged requires caller observation",
            self.validator.validate_result_checkpoint_state(
                source,
                value,
                4,
                "token-4",
                observed_deployment,
                consumed_authority=consumed_authority,
            ),
        )
        self.assertIn(
            "$.authority_used: does not match caller authority ledger",
            self.validator.validate_result_checkpoint_state(
                automatic_source,
                automatic,
                4,
                "token-4",
                observed_deployment,
                automatic_tracker,
                consumed_authority,
            ),
        )

    def test_candidate_must_match_invocation_repository(self) -> None:
        value = result()
        value["candidate"]["repository"] = "github:other/project"
        errors = self.validator.validate_result_for_invocation(invocation(), value)
        self.assertIn(
            "$.candidate.repository: does not match invocation",
            errors,
        )

    def test_ready_pr_base_ref_must_match_invocation(self) -> None:
        source = invocation()
        source["validation"] = ["just test"]
        value = result()
        value["candidate"]["publication"]["pull_requests"][0]["base_ref"] = (
            "refs/heads/unrelated"
        )
        self.assertIn(
            "$.candidate.publication: first PR base_ref does not match invocation",
            self.validator.validate_result_for_invocation(source, value),
        )

    def test_ready_pr_head_ref_must_match_candidate(self) -> None:
        value = result()
        value["candidate"]["publication"]["pull_requests"][0]["head_ref"] = (
            "refs/heads/unrelated"
        )
        self.assertIn(
            "$.candidate.publication: ready_pr head ref must match candidate",
            self.validator.validate("result", value),
        )

    def test_delivery_requires_all_requested_current_gates(self) -> None:
        errors = self.validator.validate_result_for_invocation(
            invocation(),
            result(),
        )
        self.assertIn("$.validation: missing required command just lint", errors)
        value = result()
        value["validation"].append(
            {
                "name": "just lint",
                "outcome": "failed",
                "candidate_sha": SHA_B,
                "observed_at": "2026-07-25T12:01:00Z",
            }
        )
        self.assertIn(
            "$.validation: just lint did not pass at exact candidate",
            self.validator.validate_result_for_invocation(invocation(), value),
        )

    def test_published_result_requires_publication_authority(self) -> None:
        value = result()
        value["authority_used"] = []
        errors = self.validator.validate("result", value)
        self.assertIn(
            "$.authority_used: published implementation requires "
            "repository.candidate.push",
            errors,
        )
        self.assertIn(
            "$.authority_used: pull request publication requires create or update",
            errors,
        )

    def test_duplicate_observation_names_fail_closed(self) -> None:
        value = result()
        contradictory = copy.deepcopy(value["validation"][0])
        contradictory["outcome"] = "failed"
        value["validation"].append(contradictory)
        self.assertIn(
            "$.validation: duplicate observation names just test",
            self.validator.validate("result", value),
        )

    def test_acceptance_evidence_is_required_and_candidate_bound(self) -> None:
        value = result()
        value.pop("acceptance_evidence")
        self.assertIn(
            "$: missing required property 'acceptance_evidence'",
            self.validator.validate("result", value),
        )
        value = result()
        value["acceptance_evidence"][0]["candidate_sha"] = SHA_A
        self.assertIn(
            "$.acceptance_evidence: candidate mismatch for Automated regression suite passes",
            self.validator.validate("result", value),
        )

    def test_ready_pr_requires_pre_merge_acceptance(self) -> None:
        value = result()
        value["acceptance_evidence"][0].update({"status": "missing", "source": None})
        self.assertIn(
            "$.acceptance_evidence: required pre-merge evidence incomplete for "
            "Automated regression suite passes",
            self.validator.validate("result", value),
        )

    def test_merged_requires_post_merge_acceptance(self) -> None:
        value = result()
        value["terminal_state"] = "merged"
        record_tracker_transition(value)
        value["candidate"]["publication"]["pull_requests"][0]["state"] = "merged"
        value["acceptance_evidence"].append(
            {
                "criterion": "Production deployment smoke passes",
                "required": True,
                "evidence_category": "deployed_integration",
                "stage": "post_merge",
                "candidate_sha": None,
                "deployed_sha": None,
                "environment": "production",
                "url": "https://example.test",
                "source": None,
                "status": "missing",
            }
        )
        self.assertIn(
            "$.acceptance_evidence: merged requires complete evidence for "
            "Production deployment smoke passes",
            self.validator.validate("result", value),
        )
        value["acceptance_evidence"][-1].update(
            {
                "candidate_sha": None,
                "deployed_sha": SHA_A,
                "source": "production smoke run",
                "status": "pass",
            }
        )
        self.assertEqual([], self.validator.validate("result", value))
        value["acceptance_evidence"][-1]["candidate_sha"] = SHA_A
        self.assertIn(
            "$.acceptance_evidence: candidate mismatch for "
            "Production deployment smoke passes",
            self.validator.validate("result", value),
        )

    def test_invocation_anchors_acceptance_contract_and_deployment(self) -> None:
        source = invocation()
        source["desired_outcome"] = "merged"
        source["accepted_terminal_states"].append("merged")
        source["acceptance_requirements"].append(
            {
                "criterion": "Production deployment smoke passes",
                "required": True,
                "evidence_category": "deployed_integration",
                "stage": "post_merge",
                "identity": "deployment",
                "environment": "production",
                "url": "https://example.test",
                "source": "production smoke run",
            }
        )
        source["starting_deployment"] = {
            "candidate_sha": SHA_B,
            "deployed_sha": SHA_C,
            "environment": "production",
            "url": "https://example.test",
        }
        value = result()
        value["terminal_state"] = "merged"
        record_tracker_transition(value, source)
        value["candidate"]["publication"]["pull_requests"][0]["state"] = "merged"
        value["validation"].append(
            {
                "name": "just lint",
                "outcome": "passed",
                "candidate_sha": SHA_B,
                "observed_at": "2026-07-25T12:01:00Z",
            }
        )
        value["acceptance_evidence"].append(
            {
                "criterion": "Production deployment smoke passes",
                "required": True,
                "evidence_category": "deployed_integration",
                "stage": "post_merge",
                "candidate_sha": None,
                "deployed_sha": SHA_C,
                "environment": "production",
                "url": "https://example.test",
                "source": "production smoke run",
                "status": "pass",
            }
        )
        observed_tracker = copy.deepcopy(value["tracker_transition"])
        consumed_authority = list(value["authority_used"])
        self.assertEqual(
            [],
            self.validator.validate_result_for_invocation(
                source,
                value,
                observed_tracker=observed_tracker,
                consumed_authority=consumed_authority,
            ),
        )

        dynamic_source = copy.deepcopy(source)
        dynamic_source["starting_deployment"] = None
        observed_deployment = copy.deepcopy(source["starting_deployment"])
        self.assertEqual(
            [],
            self.validator.validate_result_for_invocation(
                dynamic_source,
                value,
                observed_deployment,
                observed_tracker,
                consumed_authority,
            ),
        )
        self.assertIn(
            "$.acceptance_evidence: passing deployment evidence lacks "
            "caller-observed deployment for Production deployment smoke passes",
            self.validator.validate_result_for_invocation(
                dynamic_source,
                value,
                observed_tracker=observed_tracker,
                consumed_authority=consumed_authority,
            ),
        )
        observed_deployment["candidate_sha"] = SHA_A
        self.assertIn(
            "$.acceptance_evidence: deployment candidate mismatch for "
            "Production deployment smoke passes",
            self.validator.validate_result_for_invocation(
                dynamic_source,
                value,
                observed_deployment,
                observed_tracker,
                consumed_authority,
            ),
        )

        omitted = copy.deepcopy(value)
        omitted["acceptance_evidence"].pop()
        self.assertIn(
            "$.acceptance_evidence: missing invocation criteria "
            "Production deployment smoke passes",
            self.validator.validate_result_for_invocation(
                source,
                omitted,
                observed_tracker=observed_tracker,
                consumed_authority=consumed_authority,
            ),
        )
        for field, replacement, expected_error in (
            (
                "deployed_sha",
                None,
                "$.acceptance_evidence: passing evidence requires candidate or "
                "deployed SHA for Production deployment smoke passes",
            ),
            (
                "deployed_sha",
                SHA_A,
                "$.acceptance_evidence: current deployment deployed_sha mismatch for "
                "Production deployment smoke passes",
            ),
            (
                "environment",
                "staging",
                "$.acceptance_evidence: environment mismatch for "
                "Production deployment smoke passes",
            ),
            (
                "evidence_category",
                "browser_functional",
                "$.acceptance_evidence: evidence_category mismatch for "
                "Production deployment smoke passes",
            ),
            (
                "source",
                "delegate summary",
                "$.acceptance_evidence: source mismatch for "
                "Production deployment smoke passes",
            ),
        ):
            mismatched = copy.deepcopy(value)
            mismatched["acceptance_evidence"][-1][field] = replacement
            self.assertIn(
                expected_error,
                self.validator.validate_result_for_invocation(
                    source,
                    mismatched,
                    observed_tracker=observed_tracker,
                    consumed_authority=consumed_authority,
                ),
            )

    def test_postmerge_acceptance_may_bind_to_merged_candidate(self) -> None:
        source = invocation()
        source["desired_outcome"] = "merged"
        source["accepted_terminal_states"].append("merged")
        source["acceptance_requirements"].append(
            {
                "criterion": "Merged result is represented on main",
                "required": True,
                "evidence_category": "mainline_representation",
                "stage": "post_merge",
                "identity": "candidate",
                "environment": "repository",
                "url": None,
                "source": "git merge-base --is-ancestor",
            }
        )
        value = result()
        value["terminal_state"] = "merged"
        record_tracker_transition(value, source)
        value["candidate"]["publication"]["pull_requests"][0]["state"] = "merged"
        value["validation"].append(
            {
                "name": "just lint",
                "outcome": "passed",
                "candidate_sha": SHA_B,
                "observed_at": "2026-07-25T12:01:00Z",
            }
        )
        value["acceptance_evidence"].append(
            {
                "criterion": "Merged result is represented on main",
                "required": True,
                "evidence_category": "mainline_representation",
                "stage": "post_merge",
                "candidate_sha": SHA_B,
                "deployed_sha": None,
                "environment": "repository",
                "url": None,
                "source": "git merge-base --is-ancestor",
                "status": "pass",
            }
        )

        self.assertEqual(
            [],
            self.validator.validate_result_for_invocation(
                source,
                value,
                observed_tracker=copy.deepcopy(value["tracker_transition"]),
                consumed_authority=list(value["authority_used"]),
            ),
        )

    def test_ready_prs_require_unique_ordered_topology(self) -> None:
        value = result()
        value["terminal_state"] = "ready_prs"
        value["candidate"]["publication"]["kind"] = "stack"
        duplicate = copy.deepcopy(value["candidate"]["publication"]["pull_requests"][0])
        value["candidate"]["publication"]["pull_requests"].append(duplicate)
        errors = self.validator.validate("result", value)
        self.assertIn(
            "$.candidate.publication: ready_prs requires unique pull request id values",
            errors,
        )
        self.assertIn(
            "$.candidate.publication: ready_prs requires unique pull request head_sha "
            "values",
            errors,
        )
        value["candidate"]["publication"]["pull_requests"][0]["head_sha"] = SHA_C
        value["candidate"]["publication"]["pull_requests"][1].update(
            {
                "id": "789",
                "url": "https://github.com/example/project/pull/789",
                "base_ref": "refs/heads/stack-one",
                "base_sha": SHA_A,
                "head_ref": "refs/heads/stack-two",
                "head_sha": SHA_B,
            }
        )
        self.assertIn(
            "$.candidate.publication: ready_prs base chain is invalid",
            self.validator.validate("result", value),
        )
        value["candidate"]["publication"]["pull_requests"][1]["base_sha"] = SHA_C
        value["candidate"]["publication"]["pull_requests"][0]["head_ref"] = (
            "refs/heads/stack-one"
        )
        self.assertNotIn(
            "$.candidate.publication: ready_prs base chain is invalid",
            self.validator.validate("result", value),
        )
        value["candidate"]["publication"]["pull_requests"][1]["base_ref"] = (
            "refs/heads/unrelated"
        )
        self.assertIn(
            "$.candidate.publication: ready_prs ref chain is invalid",
            self.validator.validate("result", value),
        )
        value["candidate"]["publication"]["pull_requests"][1]["base_ref"] = (
            "refs/heads/stack-one"
        )
        value["candidate"]["publication"]["pull_requests"][1]["head_ref"] = (
            "refs/heads/unrelated"
        )
        self.assertIn(
            "$.candidate.publication: final PR head ref must match candidate",
            self.validator.validate("result", value),
        )

    def test_delivery_requires_review_and_zero_feedback(self) -> None:
        source = invocation()
        source["validation"] = ["just test"]
        value = result()
        value["reviews"] = []
        value["feedback"]["unresolved_material_count"] = 1
        errors = self.validator.validate_result_for_invocation(source, value)
        self.assertIn(
            "$.reviews: independent review did not pass at exact candidate",
            errors,
        )
        self.assertTrue(any(error.startswith("$.feedback:") for error in errors))

    def test_requires_epic_forbids_used_authority(self) -> None:
        value = result()
        value.update(
            {
                "terminal_state": "requires_epic",
                "implementation_state": "none",
                "candidate": None,
                "handoff": {
                    "transferable": False,
                    "reason": "Whole epic requires implement-epic",
                },
                "feedback": None,
                "authority_used": [],
            }
        )
        self.assertEqual([], self.validator.validate("result", value))
        value["authority_used"] = ["repository.candidate.create"]
        self.assertIn(
            "$.authority_used: no implementation requires no actions",
            self.validator.validate("result", value),
        )

    def test_push_checkpoint_requires_exact_candidate(self) -> None:
        value = checkpoint_request()
        value["candidate"] = None
        self.assertIn(
            "$.candidate: action requires exact candidate",
            self.validator.validate("checkpoint-request", value),
        )

    def test_skill_loads_and_enforces_delegated_contract(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text()
        result_reference = (SKILL_ROOT / "references/cleanup-and-result.md").read_text()
        self.assertIn("delegated execution contract", skill)
        self.assertIn("before every action", skill)
        self.assertIn("invocation's `last_sequence`", skill)
        self.assertIn("candidate_published", skill)
        self.assertIn("deployment_observed", skill)
        self.assertIn("versioned delegated-execution contract", result_reference)


class EvidenceSlotEncodingTests(unittest.TestCase):
    """The documented encodings must actually pass the bundled validator.

    Asserting against the validator rather than against its error strings is
    the point: prose describing rules the validator does not implement reads as
    verified while being false.
    """

    BASE_SHA = "a" * 40

    def setUp(self):
        self.validator = load_validator()
        self.invocation = invocation()
        self.result = result()
        self.head = self.result["candidate"]["head_sha"]
        self.baseline = set(
            self.validator.validate_result_for_invocation(self.invocation, self.result)
        )

    def added_errors(self, entries, extra_required=None):
        invocation_copy = copy.deepcopy(self.invocation)
        result_copy = copy.deepcopy(self.result)
        if extra_required:
            invocation_copy["validation"] = list(invocation_copy["validation"]) + [
                extra_required
            ]
        result_copy["validation"] = list(result_copy["validation"]) + entries
        errors = self.validator.validate_result_for_invocation(
            invocation_copy, result_copy
        )
        return sorted(set(errors) - self.baseline)

    def observation(self, name, outcome, candidate_sha):
        return {
            "name": name,
            "outcome": outcome,
            "candidate_sha": candidate_sha,
            "observed_at": "2026-08-04T00:00:00Z",
        }

    def test_single_entry_encoding_is_accepted(self):
        self.assertEqual(
            [],
            self.added_errors(
                [
                    self.observation(
                        "evidence_behavioral_test: failed at base, passed at head",
                        "passed",
                        self.head,
                    )
                ]
            ),
        )

    def test_two_entry_encoding_with_unbound_base_is_accepted(self):
        self.assertEqual(
            [],
            self.added_errors(
                [
                    self.observation(
                        f"evidence_behavioral_test failing at base {self.BASE_SHA}",
                        "failed",
                        None,
                    ),
                    self.observation(
                        "evidence_behavioral_test passing at head",
                        "passed",
                        self.head,
                    ),
                ]
            ),
        )

    def test_base_sha_binding_is_rejected(self):
        errors = self.added_errors(
            [
                self.observation(
                    "evidence_behavioral_test at base", "failed", self.BASE_SHA
                )
            ]
        )
        self.assertTrue(any("candidate mismatch" in error for error in errors), errors)

    def test_byte_identical_names_are_rejected(self):
        errors = self.added_errors(
            [
                self.observation("evidence_behavioral_test", "failed", None),
                self.observation("evidence_behavioral_test", "passed", self.head),
            ]
        )
        self.assertTrue(
            any("duplicate observation names" in error for error in errors), errors
        )

    def test_caller_named_slot_requires_the_exact_command_name(self):
        composed = self.added_errors(
            [
                self.observation(
                    "evidence_behavioral_test: failed at base, passed at head",
                    "passed",
                    self.head,
                )
            ],
            extra_required="evidence_behavioral_test",
        )
        self.assertTrue(
            any("evidence_behavioral_test" in error for error in composed), composed
        )
        self.assertEqual(
            [],
            self.added_errors(
                [self.observation("evidence_behavioral_test", "passed", self.head)],
                extra_required="evidence_behavioral_test",
            ),
        )


if __name__ == "__main__":
    unittest.main()
