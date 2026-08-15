"""Load-bearing contract invariants for the carve-changesets skill prose.

Checks stable identifiers only — bundled file layout and the named consumption
disciplines its review communication runs on — not phrasing. Mechanics are
covered by the sibling modules in this directory.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]

DOCTRINE_NAME = "cognitive-shaping-doctrine.md"

# The generic rules the contract codified before the doctrine was bound. Each
# one now has a canonical home; leaving any behind rebuilds the second home the
# binding exists to remove, and a second home drifts.
RETIRED_GENERIC_RULES = (
    "A few hundred new or changed lines is the preferred range",
    "Raw deletion volume carries less cognitive cost",
    "Larger changesets are acceptable for demonstrably mechanical refactors",
    "Cohesiveness and independent reviewability override line count",
    "additive foundations before consumers, modifications, removals, or"
    " user-visible cutovers",
    "internal, non-exposed behavior before public API or user-visible behavior",
)

# Calibration figures belong to the doctrine. Any line-count figure left in the
# contract is a second copy whether it reads as a gate or as a preference, so
# this matches the figure itself rather than the enforcing verb.
LINE_COUNT_FIGURES = (
    r"(?:a few|several|couple of)\s+hundred",
    r"[\d,]+\s+(?:new or changed |changed |added )?lines\b",
    r"line[- ]count",
)

# What the doctrine does not carry and the chain still needs. These are
# properties of an ordered chain of merges, not of shape in general.
CARVING_SPECIFIC_CONSTRAINTS = (
    "safe intermediate state",
    "Feature-flag policy",
    "Database migration rules",
    "excluded from the chain",
    "name the rename and the minimal accompanying behavior",
)


def compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


class CarveChangesetsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = compact((SKILL_ROOT / "SKILL.md").read_text())
        cls.spec = compact((SKILL_ROOT / "references" / "SPEC.md").read_text())
        cls.handoff = compact(
            (SKILL_ROOT / "references" / "review-fix-loop-handoff.md").read_text()
        )
        cls.suite_handoffs = compact(
            (SKILL_ROOT / "references" / "suite-handoffs.md").read_text()
        )

    def test_review_communication_references_the_bundled_disciplines(self):
        self.assertIn("consumption-disciplines.md", self.skill)
        self.assertIn("Review communication runs on", self.skill)

    def test_the_four_disciplines_are_named_at_the_seam(self):
        for discipline in (
            "verify each finding against the codebase before implementing it",
            "clarify every unclear finding before implementing any",
            "never perform agreement in a reply",
            "implement blocking before simple before complex",
        ):
            self.assertIn(discipline, self.skill)

    def test_skill_delegates_the_per_changeset_review_and_fix_loop(self):
        self.assertIn("review-fix-loop", self.skill)
        self.assertIn("publication.policy: local_commit", self.skill)
        self.assertIn("review-fix-loop-handoff.md", self.skill)
        self.assertNotIn(
            "Construct and run the required `review-code-change`", self.skill
        )

    def test_changeset_review_dispatch_carries_integrity_tier_and_turn_count(self):
        self.assertIn(
            "receives evidence and contracts, never conclusions", self.handoff
        )
        self.assertIn("stop and rewrite it", self.handoff)
        self.assertIn("returns confirmation, not review", self.handoff)
        self.assertIn("capability tier adequate for judgment", self.handoff)
        self.assertIn("Prefer one well-briefed review per changeset", self.handoff)

    def test_handoff_sequences_invocations_in_chain_order(self):
        self.assertIn("One invocation per changeset, in chain order", self.handoff)
        self.assertIn(
            "changeset *i*'s invocation is not constructed until changeset *i - 1*'s",
            self.handoff,
        )

    def test_handoff_maps_every_terminal_state(self):
        for state in ("converged", "changes_remaining", "blocked"):
            self.assertIn(f"`{state}`", self.handoff)
        for reason in (
            "cycle_budget_exhausted",
            "scope_decision_required",
            "reviewer_integrity_failure",
        ):
            self.assertIn(reason, self.handoff)

    def test_published_pr_lifecycle_is_unchanged_and_retained(self):
        self.assertIn("babysit-pr", self.suite_handoffs)
        self.assertIn("must not run a", self.suite_handoffs)
        self.assertNotIn(
            "review-code-change` and `babysit-pr` skills", self.suite_handoffs
        )

    def test_tier_guidance_names_no_product_or_model(self):
        for banned in ("gpt", "claude-", "opus", "sonnet", "haiku", "gemini"):
            self.assertNotIn(banned, self.skill.lower())
            self.assertNotIn(banned, self.handoff.lower())

    def test_the_bundled_copy_exists(self):
        self.assertTrue(
            (
                SKILL_ROOT
                / "references"
                / "review-suite"
                / "consumption-disciplines.md"
            ).is_file()
        )

    def test_the_skill_loads_the_bundled_canonical_doctrine(self):
        self.assertIn(DOCTRINE_NAME, self.skill)
        self.assertTrue(
            (SKILL_ROOT / "references" / DOCTRINE_NAME).is_file(),
            f"references/{DOCTRINE_NAME} is missing; run `just sync-contracts`",
        )

    def test_a_missing_doctrine_fails_closed_rather_than_falling_back(self):
        """Without this the skill degrades silently to no shape standard at
        all, which is worse than the local heuristics it replaced."""
        self.assertIn("doctrine is unavailable", self.skill)
        for improvisation in (
            "restate",
            "local replacement",
        ):
            self.assertIn(improvisation, self.skill.lower())

    def test_generic_shape_and_ordering_judgment_defers_to_the_doctrine(self):
        self.assertIn(DOCTRINE_NAME, self.spec)
        self.assertIn("canonical", self.spec)

    def test_no_retired_generic_rule_survives_in_the_contract(self):
        for rule in RETIRED_GENERIC_RULES:
            with self.subTest(rule=rule):
                self.assertNotIn(rule, self.spec)

    def test_the_contract_states_no_line_count_figure_of_its_own(self):
        for pattern in LINE_COUNT_FIGURES:
            with self.subTest(pattern=pattern):
                self.assertIsNone(
                    re.search(pattern, self.spec, flags=re.IGNORECASE),
                    f"the contract restates a size figure matching {pattern!r}",
                )

    def test_carving_specific_constraints_survive_the_retirement(self):
        """The doctrine judges shape. It says nothing about keeping each
        intermediate merge safe, which is the whole of carving."""
        for constraint in CARVING_SPECIFIC_CONSTRAINTS:
            with self.subTest(constraint=constraint):
                self.assertIn(constraint, self.spec)

    def test_an_evaluated_run_receives_the_doctrine_as_a_contract_document(self):
        """A citation the run never loads is not a binding. The eval harness is
        where 'a run applies the doctrine' becomes observable."""
        runner = (SKILL_ROOT / "scripts" / "evals" / "runner.py").read_text()
        self.assertIn(DOCTRINE_NAME, runner)

    def test_rationalization_table_covers_the_certified_seed_entry(self):
        self.assertIn("The equivalence check passed last time", self.skill)
        self.assertIn(
            "Each propagation step rewrites a different downstream suffix "
            "against a different current base",
            self.skill,
        )


if __name__ == "__main__":
    unittest.main()
