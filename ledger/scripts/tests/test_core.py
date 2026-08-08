"""Behavioral tests for the canonical ledger core, exercised once here.

Mirrors `review-suite/scripts/tests/test_contracts.py`'s precedent for this
repository's canonical-source-plus-bundled-copy pattern: the full generic
behavior (workspace derivation and self-exclusion, append-only I/O, malformed-
line tolerance, the action-scoped dedup guard) lives in one place, exercised
against arbitrary parameters rather than any one skill's own vocabulary. Each
consuming skill's own `scripts/tests/test_ledger.py` covers only what is
genuinely skill-specific: its `unit_key_for` composition and collision
disambiguation, its CLI wiring, and (for `babysit-pr`) its watcher-state
reconciliation — never a second copy of this file's coverage.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "core.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "ledger_canonical_core", MODULE_PATH
)
CORE = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
# The dataclass below resolves its field types through
# `sys.modules[cls.__module__]`, so the module must be registered before
# `exec_module` runs it.
sys.modules[MODULE_SPEC.name] = CORE
MODULE_SPEC.loader.exec_module(CORE)

WORKSPACE_DIRNAME = ".arbitrary-skill"
ID_FIELD = "test_id"


class TempRootTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)


class DigestTests(unittest.TestCase):
    def test_collision_safe_digest_is_deterministic(self) -> None:
        self.assertEqual(
            CORE.collision_safe_digest("feature/x"),
            CORE.collision_safe_digest("feature/x"),
        )

    def test_collision_safe_digest_is_eight_hex_chars(self) -> None:
        digest = CORE.collision_safe_digest("anything")
        self.assertEqual(len(digest), 8)
        int(digest, 16)  # raises ValueError if not valid hex

    def test_collision_safe_digest_disambiguates_slash_boundary(self) -> None:
        # Without folding this digest into a key before slugifying, two
        # distinct values differing only in where a `/` falls would collide.
        first = CORE.slugify(f"a/b#{CORE.collision_safe_digest('a/b')}")
        second = CORE.slugify(f"a-b#{CORE.collision_safe_digest('a-b')}")
        self.assertNotEqual(first, second)


class ParseEvidenceTests(unittest.TestCase):
    def test_none_returns_empty_dict(self) -> None:
        self.assertEqual(CORE.parse_evidence_json(None), {})

    def test_valid_object_round_trips(self) -> None:
        self.assertEqual(CORE.parse_evidence_json('{"pr": 181}'), {"pr": 181})

    def test_rejects_non_object(self) -> None:
        with self.assertRaises(ValueError):
            CORE.parse_evidence_json("[1, 2, 3]")


class SlugifyTests(unittest.TestCase):
    def test_slugifies_mixed_case_and_punctuation(self) -> None:
        self.assertEqual(CORE.slugify("Mixed/Case_Value"), "mixed-case_value")

    def test_collapses_slash_runs(self) -> None:
        self.assertEqual(CORE.slugify("a/b/c"), "a-b-c")

    def test_rejects_empty_slug(self) -> None:
        with self.assertRaises(ValueError):
            CORE.slugify("   ")


class WorkspaceTests(TempRootTestCase):
    def test_ensure_workspace_creates_self_excluding_gitignore(self) -> None:
        directory = CORE.ensure_workspace(self.root, WORKSPACE_DIRNAME, "unit-a")
        self.assertTrue(directory.is_dir())
        gitignore = directory / ".gitignore"
        self.assertEqual(gitignore.read_text(encoding="utf-8"), "*\n")

    def test_ensure_workspace_is_idempotent(self) -> None:
        CORE.ensure_workspace(self.root, WORKSPACE_DIRNAME, "unit-a")
        directory = CORE.workspace_dir(self.root, WORKSPACE_DIRNAME, "unit-a")
        (directory / ".gitignore").write_text("custom\n", encoding="utf-8")
        CORE.ensure_workspace(self.root, WORKSPACE_DIRNAME, "unit-a")
        self.assertEqual(
            (directory / ".gitignore").read_text(encoding="utf-8"), "custom\n"
        )

    def test_distinct_unit_keys_get_distinct_workspaces(self) -> None:
        first = CORE.workspace_dir(self.root, WORKSPACE_DIRNAME, "unit-a")
        second = CORE.workspace_dir(self.root, WORKSPACE_DIRNAME, "unit-b")
        self.assertNotEqual(first, second)

    def test_workspace_lives_under_the_supplied_dirname(self) -> None:
        directory = CORE.workspace_dir(self.root, WORKSPACE_DIRNAME, "unit-a")
        self.assertEqual(directory.parent.name, WORKSPACE_DIRNAME)


class WriteTests(TempRootTestCase):
    def test_record_session_start_writes_one_line(self) -> None:
        record = CORE.record_session_start(
            self.root, WORKSPACE_DIRNAME, "unit-a", session_id="s1"
        )
        path = CORE.ledger_path(self.root, WORKSPACE_DIRNAME, "unit-a")
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0]), record)
        self.assertEqual(record["kind"], "session")

    def test_record_entry_appends_without_truncating(self) -> None:
        CORE.record_session_start(
            self.root, WORKSPACE_DIRNAME, "unit-a", session_id="s1"
        )
        CORE.record_entry(
            self.root,
            WORKSPACE_DIRNAME,
            "unit-a",
            id_field=ID_FIELD,
            id_value="item-1",
            action="did_something",
            terminal_result="done",
            head_sha="abc123",
            evidence={"k": "v"},
        )
        path = CORE.ledger_path(self.root, WORKSPACE_DIRNAME, "unit-a")
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        second = json.loads(lines[1])
        self.assertEqual(second["kind"], "entry")
        self.assertEqual(second[ID_FIELD], "item-1")
        self.assertEqual(second["terminal_result"], "done")
        self.assertEqual(second["evidence"], {"k": "v"})

    def test_record_entry_coerces_id_value_to_string(self) -> None:
        record = CORE.record_entry(
            self.root,
            WORKSPACE_DIRNAME,
            "unit-a",
            id_field=ID_FIELD,
            id_value=42,
            action="did_something",
        )
        self.assertEqual(record[ID_FIELD], "42")
        self.assertIsInstance(record[ID_FIELD], str)

    def test_record_entry_uses_the_supplied_id_field_name(self) -> None:
        record = CORE.record_entry(
            self.root,
            WORKSPACE_DIRNAME,
            "unit-a",
            id_field="a_totally_different_field",
            id_value="x",
            action="did_something",
        )
        self.assertIn("a_totally_different_field", record)
        self.assertNotIn(ID_FIELD, record)


class ReadTests(TempRootTestCase):
    def test_read_empty_ledger_returns_empty_result(self) -> None:
        result = CORE.read_ledger(self.root, WORKSPACE_DIRNAME, "unit-a")
        self.assertEqual(result.sessions, [])
        self.assertEqual(result.entries, [])
        self.assertEqual(result.skipped_lines, [])

    def test_read_round_trips_sessions_and_entries(self) -> None:
        CORE.record_session_start(
            self.root, WORKSPACE_DIRNAME, "unit-a", session_id="s1"
        )
        CORE.record_entry(
            self.root,
            WORKSPACE_DIRNAME,
            "unit-a",
            id_field=ID_FIELD,
            id_value="1",
            action="a",
        )
        CORE.record_entry(
            self.root,
            WORKSPACE_DIRNAME,
            "unit-a",
            id_field=ID_FIELD,
            id_value="2",
            action="a",
        )
        result = CORE.read_ledger(self.root, WORKSPACE_DIRNAME, "unit-a")
        self.assertEqual(len(result.sessions), 1)
        self.assertEqual(len(result.entries), 2)
        self.assertEqual(result.skipped_lines, [])

    def test_read_skips_malformed_trailing_line_without_losing_prior_lines(
        self,
    ) -> None:
        CORE.record_session_start(
            self.root, WORKSPACE_DIRNAME, "unit-a", session_id="s1"
        )
        CORE.record_entry(
            self.root,
            WORKSPACE_DIRNAME,
            "unit-a",
            id_field=ID_FIELD,
            id_value="1",
            action="a",
        )
        path = CORE.ledger_path(self.root, WORKSPACE_DIRNAME, "unit-a")
        with path.open("a", encoding="utf-8") as handle:
            handle.write('{"kind": "entry", "test_id": "2"' + "\n")  # truncated JSON
        result = CORE.read_ledger(self.root, WORKSPACE_DIRNAME, "unit-a")
        self.assertEqual(len(result.sessions), 1)
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.skipped_lines, [3])

    def test_read_skips_unknown_kind(self) -> None:
        path = CORE.ledger_path(self.root, WORKSPACE_DIRNAME, "unit-a")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"kind": "mystery"}\n', encoding="utf-8")
        result = CORE.read_ledger(self.root, WORKSPACE_DIRNAME, "unit-a")
        self.assertEqual(result.entries, [])
        self.assertEqual(result.skipped_lines, [1])


class AlreadyRecordedCompleteTests(TempRootTestCase):
    COMPLETED = frozenset({"done", "converged"})

    def test_true_for_completed_terminal_result(self) -> None:
        CORE.record_entry(
            self.root,
            WORKSPACE_DIRNAME,
            "unit-a",
            id_field=ID_FIELD,
            id_value="1",
            action="a",
            terminal_result="done",
        )
        result = CORE.read_ledger(self.root, WORKSPACE_DIRNAME, "unit-a")
        entry = CORE.already_recorded_complete(
            result.entries, ID_FIELD, "1", self.COMPLETED
        )
        self.assertIsNotNone(entry)

    def test_false_for_excluded_terminal_result(self) -> None:
        CORE.record_entry(
            self.root,
            WORKSPACE_DIRNAME,
            "unit-a",
            id_field=ID_FIELD,
            id_value="1",
            action="a",
            terminal_result="blocked",
        )
        result = CORE.read_ledger(self.root, WORKSPACE_DIRNAME, "unit-a")
        self.assertIsNone(
            CORE.already_recorded_complete(
                result.entries, ID_FIELD, "1", self.COMPLETED
            )
        )

    def test_none_when_never_recorded(self) -> None:
        result = CORE.read_ledger(self.root, WORKSPACE_DIRNAME, "unit-a")
        self.assertIsNone(
            CORE.already_recorded_complete(
                result.entries, ID_FIELD, "1", self.COMPLETED
            )
        )

    def test_uses_latest_entry_not_first(self) -> None:
        CORE.record_entry(
            self.root,
            WORKSPACE_DIRNAME,
            "unit-a",
            id_field=ID_FIELD,
            id_value="1",
            action="a",
            terminal_result="blocked",
        )
        CORE.record_entry(
            self.root,
            WORKSPACE_DIRNAME,
            "unit-a",
            id_field=ID_FIELD,
            id_value="1",
            action="a",
            terminal_result="done",
            head_sha="head-2",
        )
        result = CORE.read_ledger(self.root, WORKSPACE_DIRNAME, "unit-a")
        entry = CORE.already_recorded_complete(
            result.entries, ID_FIELD, "1", self.COMPLETED
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry["head_sha"], "head-2")

    def test_action_filter_scopes_the_search_not_just_the_latest_entry(self) -> None:
        # A later entry from a *different* action must never mask an earlier
        # completed entry from the action actually being asked about — the
        # filter must scope the search itself, not merely check whichever
        # entry happens to be globally latest.
        CORE.record_entry(
            self.root,
            WORKSPACE_DIRNAME,
            "unit-a",
            id_field=ID_FIELD,
            id_value="1",
            action="phase_one",
            terminal_result="done",
            head_sha="head-1",
        )
        CORE.record_entry(
            self.root,
            WORKSPACE_DIRNAME,
            "unit-a",
            id_field=ID_FIELD,
            id_value="1",
            action="phase_two",
            terminal_result="blocked",
        )
        result = CORE.read_ledger(self.root, WORKSPACE_DIRNAME, "unit-a")
        # Unscoped: the latest entry (phase_two/blocked) is not "complete".
        self.assertIsNone(
            CORE.already_recorded_complete(
                result.entries, ID_FIELD, "1", self.COMPLETED
            )
        )
        # Scoped to phase_one: the earlier completed entry is found.
        entry = CORE.already_recorded_complete(
            result.entries,
            ID_FIELD,
            "1",
            self.COMPLETED,
            action_filter=lambda e: e.get("action") == "phase_one",
        )
        self.assertIsNotNone(entry)
        self.assertEqual(entry["head_sha"], "head-1")

    def test_action_filter_excludes_a_non_matching_entry_entirely(self) -> None:
        CORE.record_entry(
            self.root,
            WORKSPACE_DIRNAME,
            "unit-a",
            id_field=ID_FIELD,
            id_value="1",
            action="phase_two",
            terminal_result="done",
        )
        result = CORE.read_ledger(self.root, WORKSPACE_DIRNAME, "unit-a")
        self.assertIsNone(
            CORE.already_recorded_complete(
                result.entries,
                ID_FIELD,
                "1",
                self.COMPLETED,
                action_filter=lambda e: e.get("action") == "phase_one",
            )
        )


if __name__ == "__main__":
    unittest.main()
