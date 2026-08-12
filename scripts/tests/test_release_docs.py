"""Structural checks for the release-tooling docs #138 adds.

Checks stable identifiers, not phrasing: the RELEASE-NOTES.md format section
and its first (dry-run) entry, and release-process.md's version-surface table
and operator-only tagging authority.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from helpers import compact  # noqa: E402

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RELEASE_NOTES = REPOSITORY_ROOT / "RELEASE-NOTES.md"
RELEASE_PROCESS = REPOSITORY_ROOT / "docs" / "release-process.md"


class ReleaseNotesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = RELEASE_NOTES.read_text()
        cls.compact = compact(cls.text)

    def test_the_file_documents_its_own_format(self) -> None:
        self.assertIn("## Format", self.text)
        self.assertIn("What changed", self.compact)
        self.assertIn("Why", self.compact)
        self.assertIn("Evidence", self.compact)

    def test_it_is_distinct_from_the_daily_changelog(self) -> None:
        self.assertIn("CHANGELOG.md", self.compact)
        self.assertIn("not the daily", self.compact)

    def test_the_first_entry_describes_the_tooling_itself_as_a_dry_run(self) -> None:
        self.assertIn("bump_version.py", self.compact)
        self.assertIn("validate_plugins.py", self.compact)
        self.assertIn("dry run", self.compact.lower())
        self.assertIn("no git tag was cut", self.compact.lower())

    def test_entries_cite_the_eval_evidence_norm(self) -> None:
        self.assertIn("#135", self.compact)

    def test_it_points_at_the_release_process_doc(self) -> None:
        self.assertIn("docs/release-process.md", self.compact)


class ReleaseProcessDocTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = RELEASE_PROCESS.read_text()
        cls.compact = compact(cls.text)

    def test_all_four_version_surfaces_are_named(self) -> None:
        for surface in (
            ".claude-plugin/plugin.json",
            ".codex-plugin/plugin.json",
            ".claude-plugin/marketplace.json",
            ".agents/plugins/marketplace.json",
        ):
            self.assertIn(surface, self.text)

    def test_the_bump_script_usage_is_documented(self) -> None:
        self.assertIn("scripts/bump_version.py", self.text)
        self.assertIn("--bump patch", self.text)
        self.assertIn("--dry-run", self.text)

    def test_operator_only_tagging_authority_is_stated(self) -> None:
        self.assertIn("Cutting the git tag and GitHub release is not", self.compact)
        self.assertIn("No automation in this repository creates a tag", self.compact)

    def test_it_references_the_narrative_release_notes_file(self) -> None:
        self.assertIn("RELEASE-NOTES.md", self.text)


if __name__ == "__main__":
    unittest.main()
