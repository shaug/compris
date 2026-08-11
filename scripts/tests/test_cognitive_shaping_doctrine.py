"""Load-bearing contract invariants for docs/cognitive-shaping-doctrine.md.

Checks stable identifiers in the doctrine's own normative text, not phrasing.
The document is repository-wide rather than skill-scoped, so its own tests live
here rather than inside any one skill's test suite, exactly as
`test_skill_authoring_doc.py` does for the authoring standard.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from helpers import compact

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOCTRINE = REPOSITORY_ROOT / "docs" / "cognitive-shaping-doctrine.md"

# The doctrine is compris's own claim. It names no upstream project, because
# there is no external owner to attribute and a citation would imply one.
FOREIGN_SOURCES = ("atelier",)

MENTAL_MODEL_STANDARD = compact(
    """
    A unit of work is correctly shaped when a reviewer can construct an
    accurate mental model of the change and evaluate it independently.
    """
)

# All eight. The doctrine must account for every one; dropping any is how a
# rule set quietly becomes a summary of itself.
BREAKDOWN_RULES = (
    "Keep an initiative executable as one ticket when it is already reviewable",
    "Avoid one-child decomposition without a real reason",
    "Separate unrelated concern domains",
    "Prefer additive foundations before disruptive transitions",
    "Separate mechanical restructuring from behavioral change when that helps review",
    "Keep validation with the behavior it proves",
    "Identify re-split triggers before implementation",
    "Create follow-up work when implementation or review reveals new scope",
)

# Threshold constructions, not the words "line count". The doctrine has to be
# able to refuse a line-count gate; what it may not do is state one.
NUMERIC_GATE_PATTERNS = (
    r"(?:at most|no more than|fewer than|under|up to|a maximum of|a limit of)"
    r"\s+[\d,]+\s+(?:new or changed |changed |added )?lines",
    r"a few hundred (?:new or changed )?lines",
    r"[\d,]+[- ]line (?:limit|cap|threshold|maximum|budget|target)",
    r"preferred range",
)


class CognitiveShapingDoctrineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = compact(DOCTRINE.read_text())

    def test_the_doctrine_identifies_compris_as_its_owner(self):
        self.assertIn("This is compris's doctrine of cognitive shaping", self.doc)

    def test_the_doctrine_attributes_itself_to_no_outside_project(self):
        for foreign in FOREIGN_SOURCES:
            with self.subTest(source=foreign):
                self.assertNotIn(foreign, self.doc.lower())

    def test_the_doctrine_states_the_mental_model_standard(self):
        self.assertIn(MENTAL_MODEL_STANDARD, self.doc)

    def test_every_breakdown_rule_is_accounted_for(self):
        for rule in BREAKDOWN_RULES:
            with self.subTest(rule=rule):
                self.assertIn(rule, self.doc)

    def test_the_logical_to_realized_vocabulary_is_recorded(self):
        self.assertIn("A leaf ticket is a child of an epic", self.doc)
        for mapping in ("| initiative | epic |", "| changeset | pull request |"):
            with self.subTest(mapping=mapping):
                self.assertIn(mapping, self.doc)

    def test_enforcement_is_policy_controlled_and_separate_from_judgment(self):
        self.assertIn("Shape is always judged", self.doc)
        self.assertIn(
            "Whether an oversized verdict gates anything is the consuming"
            " project's decision",
            self.doc,
        )

    def test_recorded_machine_generated_evidence_is_excluded_from_judgment(self):
        self.assertIn("Recorded machine-generated evidence", self.doc)
        self.assertIn("is excluded", self.doc)
        self.assertIn("eval results", self.doc)

    def test_no_numeric_line_count_gate_is_presented_as_correctness_policy(self):
        for pattern in NUMERIC_GATE_PATTERNS:
            with self.subTest(pattern=pattern):
                self.assertIsNone(
                    re.search(pattern, self.doc, flags=re.IGNORECASE),
                    f"doctrine states a numeric size gate matching {pattern!r}",
                )


if __name__ == "__main__":
    unittest.main()
