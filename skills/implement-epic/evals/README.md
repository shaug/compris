# Implement-epic evaluations

`cases.json` describes scenario inputs and `expectations.json` records the
required terminal state and actions for each case. The general pair is consumed
by `scripts/tests/test_orchestration_contract.py` as contract data and can be
replayed manually or through a compatible headless agent harness. Dependency
provenance cases are also mirrored into the shared fresh-process forward corpus;
run them with `just eval-implement-epic`. Give an evaluated agent only scenario
inputs; never show it expectations.

`workflow_state` draws only on the states "Report the epic result" defines:
`blocked`, `mixed_ticket_results`, or `null` for an authorized parent closeout,
which that section reports through closeout evidence rather than a single-word
label. A case's own scenario is carried by `required_actions`, not by a bespoke
state label — a label the prose never defines is unreachable for a model given
only the prompt, so the case would grade a deterministic stand-in instead of the
prose. `scripts/tests/test_terminal_state_prose_coverage.py` at the repository
root enforces that across every skill's corpus.
