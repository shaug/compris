"""Content invariants for the canonical cognitive prose contract.

`docs/cognitive-prose.md` states how prose compris emits is written. These
tests hold the claims a later editor could quietly drop: the seven sections a
reader is promised, the sourcing rule that separates an observed prohibition
from an invented one, and the recorded gap where the rationalization table
would go.

Repository-wide rather than skill-scoped, so these live here alongside
`test_cognitive_shaping_doctrine.py` and
`test_cognitive_driven_development_doc.py`.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from helpers import compact, sync_block_skills  # noqa: E402

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CANONICAL = REPOSITORY_ROOT / "docs" / "cognitive-prose.md"
BUNDLING_SKILLS = ("implement-ticket", "carve-changesets", "ready-ticket")

REQUIRED_SECTIONS = (
    "## The standard",
    "## Scope",
    "## The opening move",
    "## The reader's question order",
    "## The prohibitions",
    "## Scale",
    "## The exemplar pair",
)


def _section(heading: str) -> str:
    """Return the body of one second-level section, heading excluded."""
    text = CANONICAL.read_text()
    start = text.index(heading) + len(heading)
    remainder = text[start:]
    end = remainder.find("\n## ")
    return remainder if end == -1 else remainder[:end]


def _table_rows(section: str) -> list[list[str]]:
    """Return the data rows of the first Markdown table in `section`."""
    lines = [line for line in section.splitlines() if line.strip().startswith("|")]
    rows = [line for line in lines if not re.fullmatch(r"\s*\|[\s|:-]*\|\s*", line)]
    return [
        [cell.strip() for cell in row.strip().strip("|").split("|")] for row in rows[1:]
    ]


class CognitiveProseContractTests(unittest.TestCase):
    def test_the_contract_states_the_standard(self) -> None:
        standard = compact(_section("## The standard"))
        text = compact(CANONICAL.read_text())
        self.assertIn(
            "written for the human accountable to the codebase",
            text,
        )
        self.assertIn("never merely efficient", text)
        self.assertIn("token-efficient and human-hostile", standard)

    def test_the_contract_carries_every_required_section(self) -> None:
        text = CANONICAL.read_text()
        for heading in REQUIRED_SECTIONS:
            with self.subTest(section=heading):
                self.assertIn(f"\n{heading}\n", text)

    def test_the_required_sections_appear_in_the_promised_order(self) -> None:
        text = CANONICAL.read_text()
        positions = [text.index(f"\n{heading}\n") for heading in REQUIRED_SECTIONS]
        self.assertEqual(positions, sorted(positions))

    def test_the_contract_carries_no_section_beyond_the_promised_seven(self) -> None:
        # A new section is a change to what the document promises a reader, so
        # it belongs in REQUIRED_SECTIONS rather than arriving silently.
        found = re.findall(r"^## .+$", CANONICAL.read_text(), flags=re.MULTILINE)
        self.assertEqual(found, [heading for heading in REQUIRED_SECTIONS])

    def test_every_prohibition_names_a_source(self) -> None:
        # docs/skill-authoring.md admits only sourced entries. An invented
        # prohibition carries none of the format's evidentiary weight, so the
        # table is only trustworthy if every row cites where it was observed.
        rows = _table_rows(_section("## The prohibitions"))
        self.assertGreaterEqual(len(rows), 4)
        for row in rows:
            with self.subTest(prohibition=row[0]):
                self.assertRegex(row[-1], r"\[#\d+\]")

    def test_the_contract_records_the_rationalization_table_as_unwritten(self) -> None:
        # The voice half is deliberately incomplete. Saying so is what keeps a
        # reader from treating the prohibitions as fully armed.
        prohibitions = compact(_section("## The prohibitions"))
        self.assertIn("rationalization table is deliberately unwritten", prohibitions)

    def test_every_link_is_absolute(self) -> None:
        # A bundled copy sits in skills/<skill>/references/ with none of this
        # repository's layout beside it, so a relative link dangles there.
        text = CANONICAL.read_text()
        targets = re.findall(r"^\[[^\]]+\]:\s*(\S+)", text, flags=re.MULTILINE)
        self.assertGreaterEqual(len(targets), 4)
        for target in targets:
            with self.subTest(target=target):
                self.assertTrue(target.startswith("https://"))
        self.assertEqual(re.findall(r"\]\((?!https://)([^)]+)\)", text), [])


class BundledProseContractTests(unittest.TestCase):
    """`just sync-contracts` copies the contract into each consuming skill so
    each stays self-contained when installed outside this repository. These
    fail when a copy drifts from the canonical file."""

    def test_every_consuming_skill_bundles_an_identical_copy(self) -> None:
        for skill in BUNDLING_SKILLS:
            bundled = (
                REPOSITORY_ROOT / "skills" / skill / "references" / "cognitive-prose.md"
            )
            with self.subTest(skill=skill):
                self.assertTrue(
                    bundled.exists(),
                    f"{bundled} is missing; run `just sync-contracts`",
                )
                self.assertEqual(
                    CANONICAL.read_bytes(),
                    bundled.read_bytes(),
                    f"{bundled} drifted from {CANONICAL}; run `just sync-contracts`",
                )

    def test_no_bundled_copy_carries_a_link_it_cannot_resolve(self) -> None:
        # The canonical file is already all-absolute by test_every_link_is_absolute.
        # This asserts the property survives bundling, where nothing from this
        # repository's layout sits beside the copy.
        for skill in BUNDLING_SKILLS:
            bundle = REPOSITORY_ROOT / "skills" / skill / "references"
            text = (bundle / "cognitive-prose.md").read_text()
            for target in re.findall(r"\]\(([^)#][^)]*)\)", text):
                if target.startswith("https://"):
                    continue
                with self.subTest(skill=skill, target=target):
                    self.assertTrue(
                        (bundle / target).exists(),
                        f"{skill} bundles a link to {target}, which it does not ship",
                    )

    def test_no_unlisted_skill_bundles_the_contract(self) -> None:
        # A stray copy in a skill the recipe does not sync would drift silently
        # the first time the canonical text changed.
        found = {
            path.parents[1].name
            for path in (REPOSITORY_ROOT / "skills").glob(
                "*/references/cognitive-prose.md"
            )
        }
        self.assertEqual(found, set(BUNDLING_SKILLS))

    def test_the_sync_recipe_copies_the_contract_to_exactly_these_skills(self) -> None:
        """Every drift failure above tells a reader to run `just sync-contracts`.
        That recipe has to refresh exactly these copies or the advice is a dead
        end, and a skill dropped from it keeps a stale copy nothing else checks.

        `helpers.sync_block_skills` scopes the read to the block that copies
        this contract and states why equality rather than membership is what
        makes the check real.
        """
        self.assertEqual(sync_block_skills("docs/cognitive-prose.md"), BUNDLING_SKILLS)


if __name__ == "__main__":
    unittest.main()
