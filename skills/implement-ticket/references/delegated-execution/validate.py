#!/usr/bin/env python3
"""Validate delegated implement-ticket protocol objects."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SCHEMAS = {
    "capability": HERE / "capability.schema.json",
    "invocation": HERE / "invocation.schema.json",
    "checkpoint-request": HERE / "checkpoint-request.schema.json",
    "checkpoint-response": HERE / "checkpoint-response.schema.json",
    "result": HERE / "result.schema.json",
}

CANDIDATE_REQUIRED_ACTIONS = {
    "repository.candidate.push",
    "pull_request.create",
    "pull_request.update",
    "review.reply",
    "review.resolve",
    "changeset.carve",
    "pull_request.merge",
    "repository.branch.delete",
    "deployment.execute",
}
PUBLICATION_ACTIONS = CANDIDATE_REQUIRED_ACTIONS | {
    "deployment.execute",
    "production.mutate",
    "destructive.execute",
}


def _path(parent: str, key: object) -> str:
    if isinstance(key, int):
        return f"{parent}[{key}]"
    return f"{parent}.{key}" if parent else str(key)


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def _resolve_ref(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    reference = schema.get("$ref")
    if not reference:
        return schema
    if not reference.startswith("#/$defs/"):
        raise ValueError(f"unsupported schema reference: {reference}")
    name = reference.removeprefix("#/$defs/")
    return root["$defs"][name]


def validate_schema(
    value: Any,
    schema: dict[str, Any],
    root: dict[str, Any],
    at: str = "$",
) -> list[str]:
    """Validate the JSON Schema subset used by this contract."""
    schema = _resolve_ref(schema, root)
    errors: list[str] = []
    expected = schema.get("type")
    if expected:
        choices = expected if isinstance(expected, list) else [expected]
        if not any(_matches_type(value, choice) for choice in choices):
            return [f"{at}: expected {' or '.join(choices)}"]

    if "const" in schema and value != schema["const"]:
        errors.append(f"{at}: expected constant {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{at}: expected one of {schema['enum']!r}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{at}: string is too short")
        if pattern := schema.get("pattern"):
            if re.fullmatch(pattern, value) is None:
                errors.append(f"{at}: does not match {pattern!r}")
    if isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{at}: must be at least {schema['minimum']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{at}: expected at least {schema['minItems']} item(s)")
        if schema.get("uniqueItems"):
            encoded = [json.dumps(item, sort_keys=True) for item in value]
            if len(encoded) != len(set(encoded)):
                errors.append(f"{at}: expected unique items")
        if item_schema := schema.get("items"):
            for index, item in enumerate(value):
                errors.extend(
                    validate_schema(item, item_schema, root, _path(at, index))
                )
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{at}: missing required property {key!r}")
        if schema.get("additionalProperties") is False:
            for key in value.keys() - properties.keys():
                errors.append(f"{_path(at, key)}: unknown property")
        for key, child in value.items():
            if key in properties:
                errors.extend(
                    validate_schema(child, properties[key], root, _path(at, key))
                )
    return errors


def _validate_invocation(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    accepted = value.get("accepted_terminal_states", [])
    desired = value.get("desired_outcome")
    if desired not in accepted:
        errors.append("$.desired_outcome: must appear in accepted_terminal_states")
    if "blocked" not in accepted:
        errors.append("$.accepted_terminal_states: must include blocked")
    requirements = value.get("acceptance_requirements", [])
    criteria = [entry["criterion"] for entry in requirements]
    duplicate_criteria = sorted(
        {criterion for criterion in criteria if criteria.count(criterion) > 1}
    )
    if duplicate_criteria:
        errors.append(
            "$.acceptance_requirements: duplicate criteria "
            + ", ".join(duplicate_criteria)
        )
    return errors


def _validate_checkpoint_request(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    phase = value.get("phase")
    candidate = value.get("candidate")
    deployment = value.get("deployment")
    if value.get("action") in CANDIDATE_REQUIRED_ACTIONS and candidate is None:
        errors.append("$.candidate: action requires exact candidate")
    if phase == "candidate_published":
        if candidate is None:
            errors.append("$.candidate: candidate_published requires candidate")
        if value.get("action") != "repository.candidate.push":
            errors.append(
                "$.action: candidate_published requires repository.candidate.push"
            )
    if phase == "deployment_observed":
        if candidate is None or deployment is None:
            errors.append(
                "$.deployment: deployment_observed requires candidate and deployment"
            )
        elif deployment["candidate_sha"] != candidate["head_sha"]:
            errors.append("$.deployment.candidate_sha: does not match candidate")
        if value.get("action") != "deployment.execute":
            errors.append("$.action: deployment_observed requires deployment.execute")
    elif deployment is not None:
        errors.append("$.deployment: only deployment_observed permits deployment")
    return errors


def _validate_checkpoint_response(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    decision = value.get("decision")
    reason = value.get("reason")
    prior = value.get("prior_continuation_token")
    continuation = value.get("continuation_token")
    if decision == "deny" and not reason:
        errors.append("$.reason: deny requires a reason")
    if decision == "allow" and reason is not None:
        errors.append("$.reason: allow requires null")
    if decision == "allow" and continuation == prior:
        errors.append("$.continuation_token: allow must rotate the token")
    if decision == "deny" and continuation != prior:
        errors.append("$.continuation_token: deny must preserve the prior token")
    if decision == "deny" and value.get("observed_deployment") is not None:
        errors.append("$.observed_deployment: deny requires null")
    return errors


def _validate_result(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    terminal = value.get("terminal_state")
    implementation = value.get("implementation_state")
    candidate = value.get("candidate")
    handoff = value.get("handoff", {})
    transferable = handoff.get("transferable")
    reason = handoff.get("reason")
    blocking_reason = value.get("blocking_reason")
    authority_used = set(value.get("authority_used", []))
    acceptance = value.get("acceptance_evidence", [])
    tracker_transition = value.get("tracker_transition", {})

    for collection in ("validation", "reviews"):
        names = [observation["name"] for observation in value[collection]]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            errors.append(
                f"$.{collection}: duplicate observation names " + ", ".join(duplicates)
            )

    criteria = [entry["criterion"] for entry in acceptance]
    duplicate_criteria = sorted(
        {criterion for criterion in criteria if criteria.count(criterion) > 1}
    )
    if duplicate_criteria:
        errors.append(
            "$.acceptance_evidence: duplicate criteria " + ", ".join(duplicate_criteria)
        )

    if terminal in {"ready_pr", "ready_prs", "merged"} and not acceptance:
        errors.append("$.acceptance_evidence: delivery terminal requires evidence")
    if terminal in {"ready_pr", "ready_prs", "merged"}:
        pre_merge_incomplete = [
            entry["criterion"]
            for entry in acceptance
            if entry["required"]
            and entry["stage"] == "pre_merge"
            and entry["status"] != "pass"
        ]
        if pre_merge_incomplete:
            errors.append(
                "$.acceptance_evidence: required pre-merge evidence incomplete for "
                + ", ".join(pre_merge_incomplete)
            )
    if terminal == "merged":
        incomplete = [
            entry["criterion"]
            for entry in acceptance
            if entry["required"] and entry["status"] != "pass"
        ]
        if incomplete:
            errors.append(
                "$.acceptance_evidence: merged requires complete evidence for "
                + ", ".join(incomplete)
            )
        ticket = value.get("ticket", {})
        if tracker_transition.get("provider") != ticket.get("provider"):
            errors.append("$.tracker_transition.provider: does not match ticket")
        if tracker_transition.get("ticket_id") != ticket.get("id"):
            errors.append("$.tracker_transition.ticket_id: does not match ticket")
        if tracker_transition.get("state") != "closed":
            errors.append("$.tracker_transition.state: merged requires closed tracker")
        transition_mode = tracker_transition.get("mode")
        if transition_mode not in {"manual", "automatic"}:
            errors.append(
                "$.tracker_transition.mode: merged requires verified manual or automatic transition"
            )
        elif transition_mode == "manual" and "ticket.update" not in authority_used:
            errors.append(
                "$.authority_used: manual tracker transition requires ticket.update"
            )
        elif (
            transition_mode == "automatic"
            and "tracker.auto_close.authorize" not in authority_used
        ):
            errors.append(
                "$.authority_used: automatic tracker transition requires "
                "tracker.auto_close.authorize"
            )
    missing_source = [
        entry["criterion"]
        for entry in acceptance
        if entry["status"] == "pass" and not entry["source"]
    ]
    if missing_source:
        errors.append(
            "$.acceptance_evidence: passing evidence requires source for "
            + ", ".join(missing_source)
        )
    if implementation == "published":
        if candidate is None or transferable is not True:
            errors.append(
                "$.candidate: published implementation requires transferable candidate"
            )
        if "repository.candidate.push" not in authority_used:
            errors.append(
                "$.authority_used: published implementation requires "
                "repository.candidate.push"
            )
    elif candidate is not None or transferable is not False:
        errors.append(
            "$.candidate: none or local implementation forbids transferable candidate"
        )
    if transferable and reason is not None:
        errors.append("$.handoff.reason: transferable handoff requires null")
    if not transferable and not reason:
        errors.append("$.handoff.reason: non-transferable handoff requires reason")

    if terminal == "blocked":
        if not blocking_reason:
            errors.append("$.blocking_reason: blocked requires a reason")
    elif blocking_reason is not None:
        errors.append(f"$.blocking_reason: {terminal} requires null")

    if terminal == "requires_epic" and implementation != "none":
        errors.append("$.implementation_state: requires_epic requires none")
    if implementation == "none" and authority_used:
        errors.append("$.authority_used: no implementation requires no actions")
    if implementation == "local":
        excess = sorted(authority_used & PUBLICATION_ACTIONS)
        if excess:
            errors.append(
                "$.authority_used: local implementation contradicts publication "
                + ", ".join(excess)
            )
    if terminal in {"ready_pr", "ready_prs", "merged"}:
        if implementation != "published" or candidate is None:
            errors.append(
                "$.implementation_state: delivery terminal requires published candidate"
            )
    if candidate is not None:
        stale_acceptance = [
            entry["criterion"]
            for entry in acceptance
            if entry["status"] == "pass"
            and entry["candidate_sha"] is not None
            and entry["candidate_sha"] != candidate["head_sha"]
        ]
        if stale_acceptance:
            errors.append(
                "$.acceptance_evidence: candidate mismatch for "
                + ", ".join(stale_acceptance)
            )
        missing_identity = [
            entry["criterion"]
            for entry in acceptance
            if entry["status"] == "pass"
            and not entry["candidate_sha"]
            and not entry["deployed_sha"]
        ]
        if missing_identity:
            errors.append(
                "$.acceptance_evidence: passing evidence requires candidate or deployed SHA for "
                + ", ".join(missing_identity)
            )
        publication = candidate["publication"]
        kind = publication["kind"]
        pull_requests = publication["pull_requests"]
        if pull_requests and not authority_used.intersection(
            {"pull_request.create", "pull_request.update"}
        ):
            errors.append(
                "$.authority_used: pull request publication requires create or update"
            )
        if terminal == "ready_pr":
            if kind != "ordinary" or len(pull_requests) != 1:
                errors.append(
                    "$.candidate.publication: ready_pr requires one ordinary PR"
                )
            elif pull_requests[0]["state"] != "open":
                errors.append("$.candidate.publication: ready_pr requires open PR")
            elif pull_requests[0]["head_sha"] != candidate["head_sha"]:
                errors.append(
                    "$.candidate.publication: ready_pr head must match candidate"
                )
            elif pull_requests[0]["head_ref"] != candidate["remote_ref"]:
                errors.append(
                    "$.candidate.publication: ready_pr head ref must match candidate"
                )
            elif pull_requests[0]["base_sha"] != candidate["base_sha"]:
                errors.append(
                    "$.candidate.publication: ready_pr base must match candidate"
                )
        if terminal == "ready_prs" and (kind != "stack" or len(pull_requests) < 2):
            errors.append(
                "$.candidate.publication: ready_prs requires a multi-PR stack"
            )
        if terminal == "ready_prs" and any(
            pull_request["state"] != "open" for pull_request in pull_requests
        ):
            errors.append("$.candidate.publication: ready_prs requires open PRs")
        if terminal == "ready_prs":
            for field in ("id", "url", "head_sha"):
                values = [pull_request[field] for pull_request in pull_requests]
                if len(values) != len(set(values)):
                    errors.append(
                        "$.candidate.publication: ready_prs requires unique "
                        f"pull request {field} values"
                    )
            expected_base = candidate["base_sha"]
            expected_base_ref = None
            for index, pull_request in enumerate(pull_requests):
                if pull_request["base_sha"] != expected_base:
                    errors.append(
                        "$.candidate.publication: ready_prs base chain is invalid"
                    )
                    break
                if index > 0 and pull_request["base_ref"] != expected_base_ref:
                    errors.append(
                        "$.candidate.publication: ready_prs ref chain is invalid"
                    )
                    break
                expected_base = pull_request["head_sha"]
                expected_base_ref = pull_request["head_ref"]
        if terminal == "merged" and any(
            pull_request["state"] != "merged" for pull_request in pull_requests
        ):
            errors.append("$.candidate.publication: merged requires merged PRs")
        if terminal == "merged" and not pull_requests:
            errors.append("$.candidate.publication: merged requires at least one PR")
        if terminal in {"ready_prs", "merged"} and pull_requests:
            if pull_requests[-1]["head_sha"] != candidate["head_sha"]:
                errors.append(
                    "$.candidate.publication: final PR head must match candidate"
                )
            if pull_requests[-1]["head_ref"] != candidate["remote_ref"]:
                errors.append(
                    "$.candidate.publication: final PR head ref must match candidate"
                )
        for collection in ("validation", "reviews"):
            stale = [
                observation["name"]
                for observation in value[collection]
                if observation["candidate_sha"] not in {None, candidate["head_sha"]}
            ]
            if stale:
                errors.append(
                    f"$.{collection}: candidate mismatch for " + ", ".join(stale)
                )
    return errors


SEMANTIC_VALIDATORS = {
    "capability": lambda value: [],
    "invocation": _validate_invocation,
    "checkpoint-request": _validate_checkpoint_request,
    "checkpoint-response": _validate_checkpoint_response,
    "result": _validate_result,
}


def validate(kind: str, value: dict[str, Any]) -> list[str]:
    """Validate one delegated execution protocol object."""
    schema = json.loads(SCHEMAS[kind].read_text())
    errors = validate_schema(value, schema, schema)
    if not errors:
        errors.extend(SEMANTIC_VALIDATORS[kind](value))
    return errors


def validate_checkpoint_exchange(
    request: dict[str, Any],
    response: dict[str, Any],
) -> list[str]:
    """Validate a response against the exact checkpoint request."""
    errors = validate("checkpoint-request", request)
    errors.extend(validate("checkpoint-response", response))
    if errors:
        return errors
    comparisons = (
        ("invocation_id", "invocation_id"),
        ("sequence", "request_sequence"),
        ("continuation_token", "prior_continuation_token"),
    )
    for request_field, response_field in comparisons:
        if request[request_field] != response[response_field]:
            errors.append(f"$.{response_field}: does not match request {request_field}")
    acknowledged = response["acknowledged_candidate_sha"]
    observed_deployment = response["observed_deployment"]
    if response["decision"] == "deny":
        if acknowledged is not None:
            errors.append("$.acknowledged_candidate_sha: deny requires null")
    elif request["phase"] == "candidate_published":
        if acknowledged != request["candidate"]["head_sha"]:
            errors.append(
                "$.acknowledged_candidate_sha: does not match published candidate"
            )
    elif acknowledged is not None:
        errors.append(
            "$.acknowledged_candidate_sha: non-publication response requires null"
        )
    if response["decision"] == "allow" and request["phase"] == "deployment_observed":
        if observed_deployment != request["deployment"]:
            errors.append(
                "$.observed_deployment: does not match caller-verified deployment"
            )
    elif observed_deployment is not None:
        errors.append(
            "$.observed_deployment: only deployment_observed allow may include it"
        )
    return errors


def validate_checkpoint_progress(
    last_sequence: int,
    current_token: str,
    request: dict[str, Any],
    response: dict[str, Any],
) -> list[str]:
    """Validate one exchange against caller-persisted checkpoint state."""
    errors = validate_checkpoint_exchange(request, response)
    if request.get("sequence") != last_sequence + 1:
        errors.append("$.sequence: must advance caller state by exactly one")
    if request.get("continuation_token") != current_token:
        errors.append("$.continuation_token: does not match caller state")
    return errors


def validate_result_for_invocation(
    invocation: dict[str, Any],
    result: dict[str, Any],
    observed_deployment: dict[str, Any] | None = None,
    observed_tracker: dict[str, Any] | None = None,
    consumed_authority: list[str] | None = None,
) -> list[str]:
    """Validate a terminal result against its invocation and caller observations."""
    errors = validate("invocation", invocation)
    errors.extend(validate("result", result))
    if observed_deployment is not None:
        response_schema = json.loads(SCHEMAS["checkpoint-response"].read_text())
        errors.extend(
            validate_schema(
                observed_deployment,
                response_schema["properties"]["observed_deployment"],
                response_schema,
                "$.observed_deployment",
            )
        )
    result_schema = json.loads(SCHEMAS["result"].read_text())
    if observed_tracker is not None:
        errors.extend(
            validate_schema(
                observed_tracker,
                result_schema["properties"]["tracker_transition"],
                result_schema,
                "$.observed_tracker",
            )
        )
    if consumed_authority is not None:
        errors.extend(
            validate_schema(
                consumed_authority,
                result_schema["properties"]["authority_used"],
                result_schema,
                "$.consumed_authority",
            )
        )
    if errors:
        return errors
    if result["invocation_id"] != invocation["invocation_id"]:
        errors.append("$.invocation_id: does not match invocation")
    if result["terminal_state"] not in invocation["accepted_terminal_states"]:
        errors.append("$.terminal_state: caller does not accept this state")
    if result["ticket"] != invocation["ticket"]:
        errors.append("$.ticket: does not match invocation")
    if result["terminal_state"] == "merged":
        if observed_tracker is None:
            errors.append("$.observed_tracker: merged requires caller observation")
        elif result["tracker_transition"] != observed_tracker:
            errors.append(
                "$.tracker_transition: does not match caller-observed tracker state"
            )
        if consumed_authority is None:
            errors.append(
                "$.consumed_authority: merged requires caller authority ledger"
            )
        elif set(result["authority_used"]) != set(consumed_authority):
            errors.append("$.authority_used: does not match caller authority ledger")
    expected_repository = {
        "identity": invocation["repository"]["identity"],
        "base_ref": invocation["repository"]["base_ref"],
        "base_sha": invocation["repository"]["base_sha"],
    }
    if result["repository"] != expected_repository:
        errors.append("$.repository: does not match invocation")
    candidate = result["candidate"]
    if candidate is not None:
        candidate_expectations = {
            "repository": invocation["repository"]["identity"],
            "remote_url": invocation["repository"]["remote_url"],
            "base_sha": invocation["repository"]["base_sha"],
        }
        for field, expected in candidate_expectations.items():
            if candidate[field] != expected:
                errors.append(f"$.candidate.{field}: does not match invocation")
        pull_requests = candidate["publication"]["pull_requests"]
        if (
            pull_requests
            and pull_requests[0]["base_ref"] != invocation["repository"]["base_ref"]
        ):
            errors.append(
                "$.candidate.publication: first PR base_ref does not match invocation"
            )
    if result["terminal_state"] != "requires_epic":
        requirements = {
            item["criterion"]: item for item in invocation["acceptance_requirements"]
        }
        evidence = {item["criterion"]: item for item in result["acceptance_evidence"]}
        missing_criteria = sorted(set(requirements) - set(evidence))
        if missing_criteria:
            errors.append(
                "$.acceptance_evidence: missing invocation criteria "
                + ", ".join(missing_criteria)
            )
        unexpected_criteria = sorted(set(evidence) - set(requirements))
        if unexpected_criteria:
            errors.append(
                "$.acceptance_evidence: criteria not present in invocation "
                + ", ".join(unexpected_criteria)
            )
        deployment = observed_deployment or invocation["starting_deployment"]
        for criterion in sorted(set(requirements) & set(evidence)):
            requirement = requirements[criterion]
            entry = evidence[criterion]
            for field in ("required", "evidence_category", "stage"):
                if entry[field] != requirement[field]:
                    errors.append(
                        f"$.acceptance_evidence: {field} mismatch for {criterion}"
                    )
            for field in ("environment", "url"):
                expected = requirement[field]
                if expected is not None and entry[field] != expected:
                    errors.append(
                        f"$.acceptance_evidence: {field} mismatch for {criterion}"
                    )
            if entry["status"] == "pass" and entry["source"] != requirement["source"]:
                errors.append(f"$.acceptance_evidence: source mismatch for {criterion}")
            if entry["status"] != "pass":
                continue
            if entry["stage"] == "post_merge":
                pull_requests = (
                    candidate["publication"]["pull_requests"]
                    if candidate is not None
                    else []
                )
                if not pull_requests or any(
                    pull_request["state"] != "merged" for pull_request in pull_requests
                ):
                    errors.append(
                        "$.acceptance_evidence: post-merge evidence requires merged "
                        f"candidate for {criterion}"
                    )
            if requirement["identity"] == "candidate":
                if candidate is None or entry["candidate_sha"] != candidate["head_sha"]:
                    errors.append(
                        "$.acceptance_evidence: required candidate identity mismatch "
                        f"for {criterion}"
                    )
                continue
            if entry["deployed_sha"] is None:
                errors.append(
                    "$.acceptance_evidence: required deployment identity missing "
                    f"for {criterion}"
                )
                continue
            if deployment is None:
                errors.append(
                    "$.acceptance_evidence: passing deployment evidence lacks "
                    f"caller-observed deployment for {criterion}"
                )
                continue
            if (
                candidate is None
                or deployment["candidate_sha"] != candidate["head_sha"]
            ):
                errors.append(
                    "$.acceptance_evidence: deployment candidate mismatch "
                    f"for {criterion}"
                )
                continue
            deployment_fields = {
                "deployed_sha": "deployed_sha",
                "environment": "environment",
                "url": "url",
            }
            for evidence_field, deployment_field in deployment_fields.items():
                if entry[evidence_field] != deployment[deployment_field]:
                    errors.append(
                        "$.acceptance_evidence: current deployment "
                        f"{evidence_field} mismatch for {criterion}"
                    )
    allowed = set(invocation["authority"]["allow"])
    excess = sorted(set(result["authority_used"]) - allowed)
    if excess:
        errors.append("$.authority_used: exceeds invocation: " + ", ".join(excess))
    if result["terminal_state"] in {"ready_pr", "ready_prs", "merged"}:
        candidate_sha = candidate["head_sha"]
        observations = {item["name"]: item for item in result["validation"]}
        for command in invocation["validation"]:
            observation = observations.get(command)
            if observation is None:
                errors.append(f"$.validation: missing required command {command}")
            elif (
                observation["outcome"] != "passed"
                or observation["candidate_sha"] != candidate_sha
            ):
                errors.append(
                    f"$.validation: {command} did not pass at exact candidate"
                )
        if invocation["review"]["independent"]:
            current_reviews = [
                item
                for item in result["reviews"]
                if item["outcome"] == "passed"
                and item["candidate_sha"] == candidate_sha
            ]
            if not current_reviews:
                errors.append(
                    "$.reviews: independent review did not pass at exact candidate"
                )
        if invocation["review"]["unresolved_feedback_required"]:
            feedback = result["feedback"]
            if (
                feedback is None
                or feedback["candidate_sha"] != candidate_sha
                or feedback["unresolved_material_count"] != 0
            ):
                errors.append(
                    "$.feedback: unresolved material feedback is not zero at "
                    "exact candidate"
                )
    return errors


def validate_result_checkpoint_state(
    invocation: dict[str, Any],
    result: dict[str, Any],
    last_sequence: int,
    current_token: str,
    observed_deployment: dict[str, Any] | None = None,
    observed_tracker: dict[str, Any] | None = None,
    consumed_authority: list[str] | None = None,
) -> list[str]:
    """Validate a terminal result against live observations and the ledger tail."""
    errors = validate_result_for_invocation(
        invocation,
        result,
        observed_deployment,
        observed_tracker,
        consumed_authority,
    )
    if errors:
        return errors
    if result["checkpoint"]["last_sequence"] != last_sequence:
        errors.append("$.checkpoint.last_sequence: does not match caller ledger")
    if result["checkpoint"]["continuation_token"] != current_token:
        errors.append("$.checkpoint.continuation_token: does not match caller ledger")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "kind",
        choices=sorted(SCHEMAS),
        help="Protocol object kind",
    )
    parser.add_argument("path", type=Path, help="JSON object to validate")
    parser.add_argument(
        "--invocation",
        type=Path,
        help="Validate a result against this invocation",
    )
    parser.add_argument(
        "--request",
        type=Path,
        help="Validate a checkpoint response against this request",
    )
    parser.add_argument(
        "--observed-tracker",
        type=Path,
        help="Caller-observed final tracker transition for a merged result",
    )
    parser.add_argument(
        "--consumed-authority",
        type=Path,
        help="Caller authorization ledger for a merged result",
    )
    args = parser.parse_args()

    try:
        value = json.loads(args.path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        print(f"{args.path}: {error}", file=sys.stderr)
        return 2
    if not isinstance(value, dict):
        print("$: expected object", file=sys.stderr)
        return 1
    if args.invocation:
        if args.kind != "result":
            parser.error("--invocation requires kind=result")
        invocation = json.loads(args.invocation.read_text())
        observed_tracker = (
            json.loads(args.observed_tracker.read_text())
            if args.observed_tracker
            else None
        )
        consumed_authority = (
            json.loads(args.consumed_authority.read_text())
            if args.consumed_authority
            else None
        )
        errors = validate_result_for_invocation(
            invocation,
            value,
            observed_tracker=observed_tracker,
            consumed_authority=consumed_authority,
        )
    elif args.request:
        if args.kind != "checkpoint-response":
            parser.error("--request requires kind=checkpoint-response")
        request = json.loads(args.request.read_text())
        errors = validate_checkpoint_exchange(request, value)
    else:
        errors = validate(args.kind, value)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
