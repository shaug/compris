# Ready-ticket evaluations

`cases.json` holds scenario inputs and `expectations.json` records the required
terminal result and actions for each case. The pair is consumed by
`scripts/tests/test_authoring_contract.py` as contract data and can be replayed
manually or through a compatible headless agent harness. Give an evaluated agent
only the scenario inputs; never show it the expectations.

Every case is result-blind: no case carries a `workflow_state` or a
`required_actions` field, and no case narrates the outcome its scenario is meant
to produce. The six terminal results — `ticket_ready`, `draft_ready`,
`decomposition_recommended`, `graph_created`, `requires_brainstorming`, and
`blocked` — are each covered, and the contract test fails if the expectation set
ever drifts from exactly those six.

## Baseline pressure test and forward evals

`baseline/` holds #137's RED (no-skill) and GREEN (skill-loaded) transcripts,
the mapping from verbatim baseline wording to `SKILL.md`'s rationalization
table, and a paired before/after comparison. See
[`baseline/README.md`](baseline/README.md).

`forward_cases.json` / `forward_expectations.json` are result-blind forward-eval
cases in the shape `../implement-ticket/evals/forward_cases.json` established,
run through `scripts/evals/run_forward.py` with a real-model or
deterministic-fixture executor and recorded per the #135 eval-evidence
convention. Two of the cases in `forward_cases.json` are the strongest scenarios
from the baseline pressure test; the rest round out coverage of all five
terminal results, including both approved-design scales, a missing design, a
sufficient design whose residue cannot be resolved, and the form a body cites
repository state in.

Those two baseline scenarios changed answer with #197 rather than changing
grade: both are missing-design scenarios, so the approved-design boundary routes
them to `requires_brainstorming` where they were previously only `blocked`. A
before/after diff across that commit compares two different questions for them,
and their movement is not evidence about the prose either way.
