"""Contract invariants for the README's "Using beside peer skills" section.

Checks stable identifiers only — the five composition rules, the seam table's
ticket references, and the landed/planned markers — not phrasing.

The seam table's status column is declared in the two tuples below and asserted
against the table in both directions, so the table and the tuples must be edited
together: a row whose marker disagrees with the tuple its ticket is declared in
fails, in either direction. Nothing here reads tracker state — a ticket belongs
in LANDED_SEAM_TICKETS once the row's claimed seam is true as of the commit that
edits this file (its own merge commit, for a ticket landing alongside its row),
not once GitHub shows the issue closed. Moving a ticket between the tuples is
the edit this module exists to force when that commit lands.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from helpers import compact

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
README = REPOSITORY_ROOT / "README.md"

# Seams the row claims are landed as of this file's own edit, and seams it
# claims are still planned. #128 belongs here because this commit is the one
# that makes its row's claim true, not because the tracker shows it closed.
LANDED_SEAM_TICKETS = ("#124", "#125", "#126", "#127", "#128", "#131")
PLANNED_SEAM_TICKETS = ("#134",)

# One ticket-to-status lookup, so the two directional tests below share it
# rather than each re-deriving their own view of the same two tuples.
SEAM_STATUS = {
    **dict.fromkeys(LANDED_SEAM_TICKETS, "Landed"),
    **dict.fromkeys(PLANNED_SEAM_TICKETS, "Planned"),
}


def last_cell(row: str) -> str:
    """The table's status column, with mdformat's column padding removed."""
    return [cell.strip() for cell in row.strip().strip("|").split("|")][-1]


class PeerCompositionSectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        text = README.read_text()
        cls.section = text.split("## Using beside peer skills", 1)[1].split("\n## ", 1)[
            0
        ]
        cls.compact = compact(cls.section)
        cls.seam_rows = [
            line
            for line in cls.section.splitlines()
            if line.startswith("| ") and "issues/" in line
        ]

    def test_the_section_exists_with_its_division_of_labor(self):
        self.assertIn("Division of labor", self.compact)
        self.assertIn("Peers own in-phase methodology", self.compact)
        self.assertIn("Awareness mechanism", self.compact)
        self.assertIn("no install probe", self.compact)
        self.assertIn("never a `blocked` condition", self.compact)

    def test_all_five_composition_rules_are_present(self):
        for rule in (
            "satisfies brainstorming's design-approval gate",
            "Exactly one executor owns a unit of work",
            "Review production is house-owned inside the pipeline",
            "Only the pull-request option composes at the merge boundary",
            "Known overlaps are documented, not dodged",
        ):
            self.assertIn(rule, self.compact)

    def test_every_rule_states_its_rationale(self):
        self.assertEqual(5, self.compact.count("*Why:*"))

    def test_the_merge_boundary_matches_the_peers_three_option_menu(self):
        self.assertIn(
            "merge locally, push and create a pull request, or keep the branch",
            self.compact,
        )
        self.assertIn("only the pull-request option composes", self.compact)

    def test_the_guarantee_of_standalone_function_is_stated(self):
        self.assertIn("Nothing here degrades when a peer is absent", self.compact)

    def test_the_seam_table_marks_every_row_landed_or_planned(self):
        """Row-driven: catches a row citing a ticket in neither declared tuple,
        as well as a marker outside the closed Landed/Planned vocabulary."""
        self.assertGreaterEqual(len(self.seam_rows), 10)
        for row in self.seam_rows:
            with self.subTest(row=row[:60]):
                self.assertIn(
                    last_cell(row),
                    ("Landed", "Planned"),
                    "each seam row must end in a Landed or Planned marker",
                )
                match = re.search(r"issues/(\d+)\)", row)
                self.assertIsNotNone(match, "each seam row must cite an issue")
                self.assertIn(
                    f"#{match.group(1)}",
                    SEAM_STATUS,
                    f"#{match.group(1)} is not a declared seam ticket",
                )

    def test_each_seam_row_matches_its_declared_status(self):
        """Ticket-driven, the complementary direction: without this, rewriting
        every row to Planned, or marking an open-ticket seam Landed, both leave
        the suite green."""
        for ticket, status in SEAM_STATUS.items():
            link = f"issues/{ticket.lstrip('#')})"
            matching = [row for row in self.seam_rows if link in row]
            with self.subTest(ticket=ticket):
                self.assertTrue(matching, f"no seam row cites {ticket}")
                for row in matching:
                    self.assertEqual(
                        status,
                        last_cell(row),
                        f"{ticket} is {status.lower()} and its row must say so",
                    )

    def test_the_landed_overlap_audit_cites_its_actual_evidence(self):
        self.assertIn("landed the", self.compact)
        self.assertIn("issues/136", self.section)
        self.assertIn("did not reproduce on retest", self.compact)
        self.assertIn("triggering/known-overlaps.json", self.compact)
        # The two genuinely unmeasured tiers are named as gaps, not glossed over.
        self.assertIn("headless tier", self.compact)
        self.assertIn("triggering/composition-cases.json", self.compact)

    def test_the_registry_is_named_as_the_authority(self):
        self.assertIn("docs/skill-authoring.md", self.section)
        self.assertIn(
            "is the authority when this summary and the registry disagree",
            self.compact,
        )


if __name__ == "__main__":
    unittest.main()
