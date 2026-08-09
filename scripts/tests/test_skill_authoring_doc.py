"""Load-bearing contract invariants for docs/skill-authoring.md itself.

Checks stable identifiers in the authoring standard's own normative text, not
phrasing. The document is repository-wide rather than skill-scoped, so its
own tests live here rather than inside any one skill's test suite.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from helpers import compact

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AUTHORING_DOC = REPOSITORY_ROOT / "docs" / "skill-authoring.md"


class SkillAuthoringDocTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = compact(AUTHORING_DOC.read_text())

    def test_rationalization_table_entries_require_a_retrievable_source(self):
        for required in (
            "in-repo retrievable source",
            "eval fixture failure",
            "GitHub PR review history entry",
            "recorded eval-results observation",
            "Review excludes a speculative entry",
        ):
            self.assertIn(required, self.doc)

    def test_admissible_evidence_rule_sits_beside_the_table_it_governs(self):
        self.assertLess(
            self.doc.index("write a prohibition plus a rationalization table"),
            self.doc.index("Admit only sourced entries to a rationalization table"),
        )

    def test_admissible_evidence_rule_reconciles_with_the_baseline_exemplar(self):
        self.assertIn("baseline transcript recorded under a skill's", self.doc)
        self.assertIn("Rationalizations that precede an unready body", self.doc)
        self.assertIn("skills/ready-ticket/evals/baseline/README.md", self.doc)


if __name__ == "__main__":
    unittest.main()
