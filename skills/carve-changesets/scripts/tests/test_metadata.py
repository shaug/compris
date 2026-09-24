from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import helpers  # noqa: E402,F401
from metadata import (  # noqa: E402
    ChangesetMetadata,
    MetadataError,
    SourceIdentity,
    embed_pr_metadata,
    normalize_legacy_commit_metadata,
    normalize_legacy_pr_metadata,
    parse_commit_message,
    parse_pr_metadata,
    render_pr_metadata,
    stamp_commit_message,
)


class MetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.metadata = ChangesetMetadata(
            slug="api-foundation",
            index=2,
            source_branch="feature/report",
            source_sha="a" * 40,
        )

    def test_commit_message_round_trips_through_git_interpret_trailers(self) -> None:
        message = stamp_commit_message("feat: add API foundation", self.metadata)

        self.assertIn("Changeset-Slug: api-foundation", message)
        self.assertEqual(self.metadata, parse_commit_message(message))

    def test_stable_identity_centralizes_native_and_legacy_rules(self) -> None:
        native = ChangesetMetadata(
            slug="api-foundation",
            source_lineage=(SourceIdentity("origin", "feature/report", "a" * 40),),
        )
        successor = ChangesetMetadata(
            slug="api-foundation",
            source_lineage=(
                *native.source_lineage,
                SourceIdentity("origin", "feature/report-v2", "b" * 40),
            ),
            recovery_from_head="c" * 40,
        )
        other_legacy_position = ChangesetMetadata(
            slug="api-foundation",
            index=3,
            source_branch="feature/report",
            source_sha="a" * 40,
        )

        self.assertTrue(native.same_changeset_as(successor))
        self.assertTrue(self.metadata.same_changeset_as(self.metadata))
        self.assertFalse(self.metadata.same_changeset_as(other_legacy_position))
        self.assertFalse(native.same_changeset_as(self.metadata))

    def test_parse_commit_message_rejects_missing_trailer(self) -> None:
        with self.assertRaisesRegex(MetadataError, "Changeset-Source"):
            parse_commit_message(
                "feat: incomplete\n\nChangeset-Slug: incomplete\nChangeset-Index: 1\n"
            )

    def test_pr_metadata_survives_human_body_edits(self) -> None:
        body = embed_pr_metadata("## Summary\n\nOriginal prose.\n", self.metadata)
        edited = "Reviewer context added.\n\n" + body.replace("Original", "Improved")

        self.assertEqual(self.metadata, parse_pr_metadata(edited))

    def test_embedding_replaces_one_existing_block(self) -> None:
        old = ChangesetMetadata("old", 1, "feature/report", "b" * 40)
        body = f"Human prose.\n\n{render_pr_metadata(old)}\n"

        updated = embed_pr_metadata(body, self.metadata)

        self.assertEqual(1, updated.count("carve-changesets:metadata:v1"))
        self.assertEqual(self.metadata, parse_pr_metadata(updated))

    def test_pr_metadata_rejects_multiple_blocks(self) -> None:
        block = render_pr_metadata(self.metadata)
        with self.assertRaisesRegex(MetadataError, "multiple"):
            parse_pr_metadata(f"{block}\n{block}\n")

    def test_successor_metadata_round_trips_in_commit_and_pr(self) -> None:
        successor = ChangesetMetadata(
            slug="api-foundation",
            index=2,
            source_branch="feature/report-corrected",
            source_sha="c" * 40,
            source_lineage=(
                SourceIdentity("feature/report", "a" * 40),
                SourceIdentity("feature/report-corrected", "c" * 40),
            ),
            recovery_from_head="b" * 40,
        )

        message = stamp_commit_message("fix: accept review correction", successor)
        body = embed_pr_metadata("Human prose.\n", successor)

        self.assertIn("Changeset-Lineage:", message)
        self.assertIn("carve-changesets:metadata:v2", body)
        self.assertEqual(successor, parse_commit_message(message))
        self.assertEqual(successor, parse_pr_metadata(body))

    def test_successor_metadata_rejects_missing_or_repeated_lineage(self) -> None:
        with self.assertRaisesRegex(MetadataError, "recovery-from"):
            ChangesetMetadata(
                "part-2",
                2,
                "feature/report-corrected",
                "c" * 40,
                (
                    SourceIdentity("feature/report", "a" * 40),
                    SourceIdentity("feature/report-corrected", "c" * 40),
                ),
            )
        with self.assertRaisesRegex(MetadataError, "repeat"):
            ChangesetMetadata(
                "part-2",
                2,
                "feature/report",
                "a" * 40,
                (
                    SourceIdentity("feature/report", "a" * 40),
                    SourceIdentity("feature/report", "a" * 40),
                ),
                "b" * 40,
            )

    def test_v3_omits_position_and_pr_metadata_block(self) -> None:
        metadata = ChangesetMetadata(
            slug="payments",
            source_lineage=(
                SourceIdentity(
                    remote="upstream",
                    branch="feature/payments",
                    sha="a" * 40,
                ),
            ),
        )

        message = stamp_commit_message("feat: extract payment model", metadata)
        body = embed_pr_metadata("Human-readable context.\n", metadata)

        self.assertIn("Changeset-Slug: payments", message)
        self.assertIn(
            f"Changeset-Source: upstream feature/payments @ {'a' * 40}", message
        )
        self.assertNotIn("Changeset-Index", message)
        self.assertNotIn("carve-changesets:metadata", body)
        self.assertEqual(metadata, parse_commit_message(message))

    def test_v3_embedding_removes_one_legacy_block_and_preserves_prose(self) -> None:
        native = ChangesetMetadata(
            slug="payments",
            source_lineage=(SourceIdentity("upstream", "feature/payments", "a" * 40),),
        )
        legacy = embed_pr_metadata(
            "Before metadata.\n\nAfter metadata.\n",
            self.metadata,
        )

        updated = embed_pr_metadata(legacy, native)

        self.assertEqual("Before metadata.\n\nAfter metadata.\n", updated)
        self.assertNotIn("carve-changesets:metadata", updated)

    def test_v3_requires_non_empty_unique_remote_source_lineage(self) -> None:
        with self.assertRaisesRegex(MetadataError, "lineage.*non-empty"):
            ChangesetMetadata(slug="payments", source_lineage=())
        with self.assertRaisesRegex(MetadataError, "remote.*empty"):
            SourceIdentity(remote="", branch="feature/payments", sha="a" * 40)
        identity = SourceIdentity(
            remote="upstream", branch="feature/payments", sha="a" * 40
        )
        with self.assertRaisesRegex(MetadataError, "repeat"):
            ChangesetMetadata(slug="payments", source_lineage=(identity, identity))

    def test_source_identity_requires_a_literal_git_branch_name(self) -> None:
        for branch in ("feature/*", "feature//payments", "-feature/payments"):
            with self.subTest(branch=branch):
                with self.assertRaisesRegex(MetadataError, "valid literal"):
                    SourceIdentity("origin", branch, "a" * 40)

    def test_source_identity_rejects_checkout_shorthand(self) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "commit", "--allow-empty", "-m", "base"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(repo), "switch", "-q", "-c", "previous"],
                check=True,
            )
            subprocess.run(["git", "-C", str(repo), "switch", "-q", "main"], check=True)
            try:
                os.chdir(repo)
                with self.assertRaisesRegex(MetadataError, "valid literal"):
                    SourceIdentity("origin", "@{-1}", "a" * 40)
            finally:
                os.chdir(original_cwd)

    def test_v3_successor_requires_exact_recovery_provenance(self) -> None:
        lineage = (
            SourceIdentity("origin", "feature/payments", "a" * 40),
            SourceIdentity("origin", "feature/payments-v2", "c" * 40),
        )

        with self.assertRaisesRegex(MetadataError, "recovery-from"):
            ChangesetMetadata(slug="payments", source_lineage=lineage)

        metadata = ChangesetMetadata(
            slug="payments",
            source_lineage=lineage,
            recovery_from_head="b" * 40,
        )
        message = stamp_commit_message("fix: recover payments", metadata)

        self.assertIn("Changeset-Lineage:", message)
        self.assertIn(f"Changeset-Recovery-From: {'b' * 40}", message)
        self.assertNotIn("Changeset-Index", message)
        self.assertEqual(metadata, parse_commit_message(message))

    def test_v3_restamp_replaces_single_source_with_successor(self) -> None:
        original = ChangesetMetadata(
            slug="payments",
            source_lineage=(SourceIdentity("origin", "feature/payments", "a" * 40),),
        )
        successor = ChangesetMetadata(
            slug="payments",
            source_lineage=(
                *original.source_lineage,
                SourceIdentity("origin", "feature/payments-v2", "c" * 40),
            ),
            recovery_from_head="b" * 40,
        )

        message = stamp_commit_message("fix: payment model", original)
        restamped = stamp_commit_message(message, successor)

        self.assertNotIn("Changeset-Source:", restamped)
        self.assertNotIn("Changeset-Index:", restamped)
        self.assertEqual(successor, parse_commit_message(restamped))

    def test_v3_restamp_removes_legacy_position(self) -> None:
        native = ChangesetMetadata(
            slug="api-foundation",
            source_lineage=(SourceIdentity("upstream", "feature/report", "a" * 40),),
        )

        legacy_message = stamp_commit_message("feat: layer", self.metadata)
        restamped = stamp_commit_message(legacy_message, native)

        self.assertNotIn("Changeset-Index:", restamped)
        self.assertEqual(native, parse_commit_message(restamped))

    def test_legacy_pr_block_normalizes_without_rewrite(self) -> None:
        body = """Human prose.

<!-- carve-changesets:metadata:v2
{"index":2,"recovery_from_head":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","slug":"payments","source_branch":"feature/payments-v2","source_lineage":[{"branch":"feature/payments","sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},{"branch":"feature/payments-v2","sha":"cccccccccccccccccccccccccccccccccccccccc"}],"source_sha":"cccccccccccccccccccccccccccccccccccccccc"}
-->
"""

        normalized = normalize_legacy_pr_metadata(body, remote="upstream")

        self.assertEqual(2, normalized.legacy_position)
        self.assertEqual(2, normalized.marker_version)
        self.assertEqual("payments", normalized.metadata.slug)
        self.assertEqual("upstream", normalized.metadata.active_source.remote)
        self.assertEqual(body, normalized.original)

    def test_legacy_commit_trailers_normalize_without_rewrite(self) -> None:
        message = stamp_commit_message("feat: legacy layer", self.metadata)

        normalized = normalize_legacy_commit_metadata(message, remote="upstream")

        self.assertEqual(2, normalized.legacy_position)
        self.assertEqual(1, normalized.marker_version)
        self.assertEqual("upstream", normalized.metadata.active_source.remote)
        self.assertEqual(message, normalized.original)

    def test_legacy_v1_pr_normalization_preserves_selected_remote(self) -> None:
        body = embed_pr_metadata("Human prose.\n", self.metadata)

        normalized = normalize_legacy_pr_metadata(body, remote="upstream")

        self.assertEqual("upstream", normalized.metadata.active_source.remote)
        self.assertEqual(body, normalized.original)


if __name__ == "__main__":
    unittest.main()
