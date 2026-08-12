"""No terminal state reaches an eval harness without a skill's prose defining it.

A terminal state that exists only in the harness cannot be measured. A model
given the skill prompt has no way to produce a string the prose never names, so
the case is unreachable at the real-model tier and passes only under a
deterministic executor written knowing the expected string — which grades the
simulation rather than the prose the evaluation exists to check.

This test spans every skill, so it lives in the repository-root suite rather
than inside any one skill's, exactly as `test_suite_invocation.py` does for an
invariant no single skill owns. Every surface is discovered by glob rather than
named, so a skill that grows a corpus or an executor is covered on arrival:

- each `evals/expectations.json` and `evals/forward_expectations.json`, whose
  per-case outcome must be defined by the prose of the skill that case targets;
- each `scripts/evals/claude_executor.py`, whose closed vocabulary is what a
  real-model executor shows the evaluated model; and
- each `scripts/evals/fixture_executor.py`, whose deterministic stand-in must
  emit nothing its skill's prose and its sibling vocabulary do not both allow.

Those globs are rooted at `skills/*` and match the three shapes above, which is
this module's scope boundary: the invariant binds a harness a skill owns, where
that skill's own prose is what must define the state. Harnesses of another shape
or another root are not reached — `review-suite/scripts/evals/`,
`triggering/executors/`, and `review-fix-loop`'s corpus, which is a Python
module rather than one of the JSON corpora named above.

Corpora record an outcome under three different keys, and an unrecognized
fourth would exempt a whole corpus while every assertion here still passed —
so `corpus_outcomes` raises on a case it cannot read rather than returning
nothing, and `test_every_corpus_yields_outcomes` fails the suite on a corpus
that yields none.

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
import tempfile
import unittest
from collections.abc import Iterable
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPOSITORY_ROOT / "skills"

# The flat keys a corpus uses for the outcome its target skill must report.
# `review-code-change` reports an aggregate verdict instead, nested one level
# down, so the nested path is read as well.
OUTCOME_KEYS = ("terminal_state", "workflow_state")
NESTED_OUTCOME_PATH = ("result", "verdict")


def display(path: Path) -> str:
    """A repository-relative path when possible, so failures name one location."""
    try:
        return str(path.relative_to(REPOSITORY_ROOT))
    except ValueError:
        return str(path)


def skill_prose(skill: str) -> str:
    """Every normative document a skill ships: its SKILL.md and references."""
    root = SKILLS_ROOT / skill
    documents = [root / "SKILL.md", *sorted(root.glob("references/**/*.md"))]
    return "\n".join(path.read_text() for path in documents if path.is_file())


def undefined_states(states: Iterable[str], prose: str) -> set[str]:
    """Return the claimed states the given prose never defines.

    A state counts as defined only in its backticked form, which is how every
    skill in this repository writes one. Bare-word matching would accept the
    English words "blocked" and "merged" wherever they appear as prose and
    report coverage a reader could not act on.
    """
    return {state for state in states if f"`{state}`" not in prose}


def corpora() -> list[Path]:
    """Every case corpus that records an expected outcome."""
    return sorted(
        path
        for name in ("expectations.json", "forward_expectations.json")
        for path in SKILLS_ROOT.glob(f"*/evals/{name}")
    )


def corpus_outcomes(path: Path) -> list[tuple[str, str, str | None]]:
    """One corpus's `(target skill, case id, outcome)` triples, in file order.

    A list rather than a mapping: keying by target and case id would silently
    collapse a repeated pair into one entry, dropping a case from every
    assertion below — the same invisible exemption this module exists to close.

    Raises on a case recording its outcome somewhere this function cannot read.
    Returning `None` there instead would exempt the corpus silently, for the
    same reason.
    """
    owner = path.parents[1].name
    outcomes: list[tuple[str, str, str | None]] = []
    for case in json.loads(path.read_text()):
        target = case.get("target_skill", owner)
        for key in OUTCOME_KEYS:
            if key in case:
                outcome = case[key]
                break
        else:
            nested = case
            for key in NESTED_OUTCOME_PATH:
                if not isinstance(nested, dict) or key not in nested:
                    raise AssertionError(
                        f"{display(path)}: case "
                        f"{case['case_id']!r} records its outcome under no key "
                        f"this test reads ({', '.join(OUTCOME_KEYS)}, or "
                        f"{'.'.join(NESTED_OUTCOME_PATH)})"
                    )
                nested = nested[key]
            outcome = nested
        outcomes.append((target, case["case_id"], outcome))
    return outcomes


def declared_vocabulary(executor: Path) -> set[str]:
    """The closed terminal-state vocabulary an executor shows the model."""
    module = ast.parse(executor.read_text())
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "TERMINAL_STATES"
            for target in node.targets
        ):
            return set(ast.literal_eval(node.value))
    raise AssertionError(f"{display(executor)} declares no TERMINAL_STATES")


def emitted_states(executor: Path) -> set[str]:
    """Every terminal state an executor can emit, read from its source.

    Reading the source rather than running it keeps the check exhaustive: a
    branch no packet reaches still has to draw from the shared vocabulary.
    """
    module = ast.parse(executor.read_text())
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


def executor_targets(executor: Path) -> list[str]:
    """Every skill an executor's packets may target.

    A forward corpus is shared: `implement-ticket`'s targets `implement-epic`
    too, so both executors there legitimately handle a state only the epic
    skill's prose defines. Attributing them to the owning skill alone would
    report that as an undefined state.
    """
    owner = executor.parents[2].name
    corpus = SKILLS_ROOT / owner / "evals" / "forward_expectations.json"
    if not corpus.is_file():
        return [owner]
    return sorted({target for target, _, _ in corpus_outcomes(corpus)})


class TerminalStateProseCoverageTests(unittest.TestCase):
    def test_the_detector_reports_a_state_no_prose_defines(self):
        # Without this, every assertion below would still pass if the detector
        # silently returned nothing — the exact shape of vacuous coverage this
        # file exists to prevent.
        self.assertEqual(
            {"invented_state"},
            undefined_states(
                {"documented_state", "invented_state"},
                "ends in `documented_state` when the gate passes",
            ),
        )
        self.assertEqual(
            set(),
            undefined_states(
                {"documented_state"},
                "ends in `documented_state` when the gate passes",
            ),
        )

    def test_the_detector_requires_the_backticked_form(self):
        self.assertEqual(
            {"merged"},
            undefined_states(
                {"merged"},
                "the candidate is merged once every gate passes",
            ),
        )

    def test_an_unreadable_case_outcome_fails_rather_than_exempts(self):
        corpus = Path(self.enterContext(tempfile.TemporaryDirectory()))
        path = corpus / "skills" / "a-skill" / "evals" / "expectations.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps([{"case_id": "renamed-key", "outcome": "blocked"}]))
        with self.assertRaises(AssertionError) as raised:
            corpus_outcomes(path)
        self.assertIn("renamed-key", str(raised.exception))

    def test_every_harness_surface_is_discovered(self):
        # A glob that silently matched nothing would make every coverage
        # assertion below vacuous.
        self.assertGreater(len(corpora()), 1)
        self.assertTrue(sorted(SKILLS_ROOT.glob("*/scripts/evals/claude_executor.py")))
        self.assertTrue(sorted(SKILLS_ROOT.glob("*/scripts/evals/fixture_executor.py")))

    def test_every_corpus_yields_outcomes(self):
        # A corpus whose every case read as `None` would pass the coverage
        # assertion by having nothing to check.
        for corpus in corpora():
            with self.subTest(corpus=display(corpus)):
                outcomes = corpus_outcomes(corpus)
                self.assertTrue(outcomes)
                self.assertTrue([o for _, _, o in outcomes if o is not None])

    def test_every_corpus_outcome_is_defined_by_its_target_skill(self):
        for corpus in corpora():
            claimed: dict[str, set[str]] = {}
            for target, case_id, outcome in corpus_outcomes(corpus):
                with self.subTest(corpus=corpus.parents[1].name, case=case_id):
                    self.assertIsInstance(
                        outcome,
                        (str, type(None)),
                        "an expected outcome is a documented label or null",
                    )
                if isinstance(outcome, str):
                    claimed.setdefault(target, set()).add(outcome)
            for target, states in sorted(claimed.items()):
                with self.subTest(corpus=display(corpus), target=target):
                    self.assertEqual(
                        set(), undefined_states(states, skill_prose(target))
                    )

    def test_every_declared_vocabulary_is_defined_across_its_targets(self):
        for executor in sorted(SKILLS_ROOT.glob("*/scripts/evals/claude_executor.py")):
            # The executor offers one vocabulary to every packet regardless of
            # target, so it is defined collectively rather than by any one skill.
            targets = executor_targets(executor)
            with self.subTest(executor=display(executor)):
                self.assertEqual(
                    set(),
                    undefined_states(
                        declared_vocabulary(executor),
                        "\n".join(skill_prose(s) for s in targets),
                    ),
                )

    def test_every_fixture_executor_stays_inside_its_skills_vocabulary(self):
        for executor in sorted(SKILLS_ROOT.glob("*/scripts/evals/fixture_executor.py")):
            targets = executor_targets(executor)
            emitted = emitted_states(executor)
            sibling = executor.parent / "claude_executor.py"
            with self.subTest(executor=display(executor)):
                self.assertTrue(emitted)
                self.assertEqual(
                    set(),
                    undefined_states(
                        emitted, "\n".join(skill_prose(s) for s in targets)
                    ),
                )
                if sibling.is_file():
                    # A state only the simulation can produce grades the
                    # simulation: a real-model packet is never offered it.
                    self.assertEqual(set(), emitted - declared_vocabulary(sibling))

    def test_every_forward_corpus_stays_inside_its_declared_vocabulary(self):
        for corpus in sorted(SKILLS_ROOT.glob("*/evals/forward_expectations.json")):
            executor = (
                SKILLS_ROOT
                / corpus.parents[1].name
                / "scripts"
                / "evals"
                / "claude_executor.py"
            )
            if not executor.is_file():
                continue
            claimed = {
                outcome
                for _, _, outcome in corpus_outcomes(corpus)
                if isinstance(outcome, str)
            }
            with self.subTest(corpus=display(corpus)):
                self.assertEqual(set(), claimed - declared_vocabulary(executor))


if __name__ == "__main__":
    unittest.main()
