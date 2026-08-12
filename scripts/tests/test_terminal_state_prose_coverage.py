"""No terminal state reaches an eval harness without a skill's prose defining it.

A terminal state that exists only in the harness cannot be measured. A model
given the skill prompt has no way to produce a string the prose never names, so
the case is unreachable at the real-model tier and passes only under a
deterministic executor written knowing the expected string — which grades the
simulation rather than the prose the evaluation exists to check.

This test spans every skill, so it lives in the repository-root suite rather
than inside any one skill's, exactly as `test_suite_invocation.py` does for an
invariant no single skill owns.

Two harness surfaces claim a terminal state, and both are covered:

- a skill's own `evals/expectations.json`, whose per-case state must be defined
  by the prose of the skill that case targets; and
- the shared forward harness under `skills/implement-ticket/scripts/evals/`,
  whose closed vocabulary is what a real-model executor shows the evaluated
  model, and whose deterministic stand-in must not emit anything outside it.

One expectation value is deliberately not a string: `implement-epic` reports an
authorized parent closeout through the closeout evidence its own reference
requires "rather than a separate single-word label", so its corpus records
`null` there instead of inventing a label its prose declines to define. `null`
is the only permitted non-string, and `skills/implement-epic/scripts/tests/
test_orchestration_contract.py` pins which case carries it.
"""

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPOSITORY_ROOT / "skills"
FORWARD_EVALS = SKILLS_ROOT / "implement-ticket" / "scripts" / "evals"
FORWARD_CORPUS = (
    SKILLS_ROOT / "implement-ticket" / "evals" / "forward_expectations.json"
)
CLAUDE_EXECUTOR = FORWARD_EVALS / "claude_executor.py"
FIXTURE_EXECUTOR = FORWARD_EVALS / "fixture_executor.py"

# The per-case key each corpus uses for the state its target skill must report.
STATE_KEYS = ("terminal_state", "workflow_state")


def skill_prose(skill: str) -> str:
    """Every normative document a skill ships: its SKILL.md and references."""
    root = SKILLS_ROOT / skill
    documents = [root / "SKILL.md", *sorted(root.glob("references/**/*.md"))]
    return "\n".join(path.read_text() for path in documents if path.is_file())


def undefined_states(
    claimed: dict[str, set[str]], prose: dict[str, str]
) -> dict[str, set[str]]:
    """Return, per skill, the claimed states that skill's own prose never defines.

    A state counts as defined only in its backticked form, which is how every
    skill in this repository writes one. Bare-word matching would accept the
    English words "blocked" and "merged" wherever they appear as prose and
    report coverage a reader could not act on.
    """
    return {
        skill: missing
        for skill, states in claimed.items()
        if (missing := {s for s in states if f"`{s}`" not in prose.get(skill, "")})
    }


def corpus_states() -> dict[Path, dict[str, object]]:
    """Every `evals/expectations.json` case's claimed state, keyed by corpus."""
    corpora = {}
    for path in sorted(SKILLS_ROOT.glob("*/evals/expectations.json")):
        cases = json.loads(path.read_text())
        corpora[path] = {
            case["case_id"]: next(
                (case[key] for key in STATE_KEYS if key in case), None
            )
            for case in cases
        }
    return corpora


def forward_corpus_states_by_target() -> dict[str, set[str]]:
    """The shared forward corpus's states, attributed to the skill each targets."""
    claimed: dict[str, set[str]] = {}
    for case in json.loads(FORWARD_CORPUS.read_text()):
        claimed.setdefault(case["target_skill"], set()).add(case["terminal_state"])
    return claimed


def declared_vocabulary() -> set[str]:
    """The closed terminal-state vocabulary `claude_executor.py` shows the model."""
    module = ast.parse(CLAUDE_EXECUTOR.read_text())
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "TERMINAL_STATES"
            for target in node.targets
        ):
            return set(ast.literal_eval(node.value))
    raise AssertionError(f"{CLAUDE_EXECUTOR} declares no TERMINAL_STATES vocabulary")


def fixture_emitted_states() -> set[str]:
    """Every terminal state `fixture_executor.py` can emit, read from its source.

    Reading the source rather than running it keeps the check exhaustive: a
    branch no packet reaches still has to draw from the shared vocabulary.
    """
    module = ast.parse(FIXTURE_EXECUTOR.read_text())
    emitted: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "terminal_state"
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                ):
                    emitted.add(value.value)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str) and any(
                isinstance(target, ast.Name) and target.id == "terminal_state"
                for target in node.targets
            ):
                emitted.add(node.value.value)
    return emitted


class TerminalStateProseCoverageTests(unittest.TestCase):
    def test_the_detector_reports_a_state_no_prose_defines(self):
        # Without this, every assertion below would still pass if the detector
        # silently returned nothing — the exact shape of vacuous coverage this
        # file exists to prevent.
        self.assertEqual(
            {"a-skill": {"invented_state"}},
            undefined_states(
                {"a-skill": {"documented_state", "invented_state"}},
                {"a-skill": "ends in `documented_state` when the gate passes"},
            ),
        )
        self.assertEqual(
            {},
            undefined_states(
                {"a-skill": {"documented_state"}},
                {"a-skill": "ends in `documented_state` when the gate passes"},
            ),
        )

    def test_the_detector_requires_the_backticked_form(self):
        self.assertEqual(
            {"a-skill": {"merged"}},
            undefined_states(
                {"a-skill": {"merged"}},
                {"a-skill": "the candidate is merged once every gate passes"},
            ),
        )

    def test_the_harness_surfaces_are_non_empty(self):
        # A glob or parse that silently matched nothing would make the coverage
        # assertions vacuous.
        corpora = corpus_states()
        self.assertGreater(len(corpora), 1)
        for path, cases in corpora.items():
            with self.subTest(corpus=path.relative_to(REPOSITORY_ROOT)):
                self.assertTrue(cases)
        self.assertTrue(forward_corpus_states_by_target())
        self.assertTrue(declared_vocabulary())
        self.assertTrue(fixture_emitted_states())

    def test_every_skill_corpus_state_is_defined_by_that_skill(self):
        for path, cases in corpus_states().items():
            skill = path.parents[1].name
            states = set()
            for case_id, state in cases.items():
                with self.subTest(corpus=skill, case=case_id):
                    self.assertIsInstance(
                        state,
                        (str, type(None)),
                        "an expected state is a documented label or null",
                    )
                if isinstance(state, str):
                    states.add(state)
            with self.subTest(corpus=skill):
                self.assertEqual(
                    {}, undefined_states({skill: states}, {skill: skill_prose(skill)})
                )

    def test_every_forward_corpus_state_is_defined_by_its_target_skill(self):
        claimed = forward_corpus_states_by_target()
        prose = {skill: skill_prose(skill) for skill in claimed}
        self.assertEqual({}, undefined_states(claimed, prose))

    def test_the_shared_vocabulary_is_defined_across_the_targeted_skills(self):
        # The executors offer one vocabulary to every packet regardless of
        # target, so it is defined collectively rather than by any one skill.
        targets = sorted(forward_corpus_states_by_target())
        collective = " and ".join(targets)
        self.assertEqual(
            {},
            undefined_states(
                {collective: declared_vocabulary()},
                {collective: "\n".join(skill_prose(skill) for skill in targets)},
            ),
        )

    def test_both_executors_and_the_forward_corpus_share_one_vocabulary(self):
        vocabulary = declared_vocabulary()
        corpus = set().union(*forward_corpus_states_by_target().values())
        self.assertEqual(set(), corpus - vocabulary)
        self.assertEqual(set(), fixture_emitted_states() - vocabulary)


if __name__ == "__main__":
    unittest.main()
