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

# The doctrine is compris's own. It names no upstream project, because there is
# no external owner to attribute and an outward-facing citation would imply one.
FOREIGN_SOURCES = ("atelier",)

# Fixed wording. A second wording is how two codifications start drifting,
# which is the failure this document exists to end.
MENTAL_MODEL_STANDARD = compact(
    """
    Line counts may inform judgment but are not universal correctness gates.
    The test is whether a reviewer can construct an accurate mental model of
    the change and evaluate it independently.
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
# able to say a line-count gate is refused; what it may not do is state one.
NUMERIC_GATE_PATTERNS = (
    r"(?:at most|no more than|fewer than|under|up to|a maximum of|a limit of)"
    r"\s+[\d,]+\s+(?:new or changed |changed |added )?lines",
    r"a few hundred (?:new or changed )?lines",
    r"[\d,]+[- ]line (?:limit|cap|threshold|maximum|budget|target)",
    r"preferred range",
)


def normalize(markdown: str) -> str:
    """Compact `markdown`, dropping the blockquote markers `>` introduces.

    The standard is set as a blockquote, and wrapping it puts a `>` at the head
    of every line; leaving those in would make the assertion depend on where
    the formatter happened to break the quote.
    """
    return compact(re.sub(r"^\s*>\s?", "", markdown, flags=re.MULTILINE))


class CognitiveShapingDoctrineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = normalize(DOCTRINE.read_text())

    def test_compris_is_named_the_sole_owner_of_the_doctrine(self):
        self.assertIn("compris is the sole owner", self.doc)
        self.assertIn("A doctrine with two homes has no home", self.doc)

    def test_the_doctrine_attributes_itself_to_no_outside_project(self):
        for foreign in FOREIGN_SOURCES:
            with self.subTest(source=foreign):
                self.assertNotIn(foreign, self.doc.lower())

    def test_the_mental_model_standard_is_carried_intact(self):
        self.assertIn(MENTAL_MODEL_STANDARD, self.doc)

    def test_every_breakdown_rule_is_accounted_for(self):
        for rule in BREAKDOWN_RULES:
            self.assertIn(rule, self.doc)

    def test_the_logical_to_realized_vocabulary_is_recorded(self):
        self.assertIn("initiative", self.doc)
        self.assertIn("changeset", self.doc)
        self.assertIn("A leaf ticket is a child of an epic", self.doc)
        for mapping in ("| initiative | epic |", "| changeset | pull request |"):
            self.assertIn(mapping, self.doc)

    def test_enforcement_is_policy_controlled_and_separate_from_judgment(self):
        self.assertIn("The shaper always judges", self.doc)
        self.assertIn(
            "the consuming project decides whether an exceeds verdict gates",
            self.doc,
        )

    def test_recorded_machine_generated_evidence_is_excluded_from_judgment(self):
        self.assertIn(
            "Recorded machine-generated evidence is excluded from shape judgment",
            self.doc,
        )
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
