from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from helpers import REPOSITORY_ROOT, copy_fixture  # noqa: E402


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPOSITORY_ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bump_version = _load("bump_version", "scripts/bump_version.py")
validate_plugins = _load("validate_plugins", "scripts/validate_plugins.py")


class BumpVersionTests(unittest.TestCase):
    def copy_fixture(self, destination: Path) -> None:
        copy_fixture(destination)

    def read_version(self, root: Path, rel: str, *, entry: bool = False) -> str:
        manifest = json.loads((root / rel).read_text(encoding="utf-8"))
        if entry:
            return manifest["plugins"][0]["version"]
        return manifest["version"]

    def test_resolve_current_version_reads_the_two_plugin_manifests(self) -> None:
        self.assertEqual(
            bump_version.resolve_current_version(REPOSITORY_ROOT),
            self.read_version(REPOSITORY_ROOT, ".claude-plugin/plugin.json"),
        )

    def test_resolve_current_version_rejects_disagreement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_fixture(root)
            codex_path = root / ".codex-plugin" / "plugin.json"
            manifest = json.loads(codex_path.read_text(encoding="utf-8"))
            manifest["version"] = "9.9.9"
            codex_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(
                bump_version.VersionBumpError, "disagree on the current version"
            ):
                bump_version.resolve_current_version(root)

    def test_bump_kinds_compute_the_expected_target(self) -> None:
        self.assertEqual(bump_version._bump((0, 1, 0), "patch"), "0.1.1")
        self.assertEqual(bump_version._bump((0, 1, 5), "minor"), "0.2.0")
        self.assertEqual(bump_version._bump((0, 1, 5), "major"), "1.0.0")

    def test_compute_target_version_prefers_explicit_to(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_fixture(root)
            self.assertEqual(
                bump_version.compute_target_version(root, bump=None, to="1.2.3"),
                "1.2.3",
            )

    def test_compute_target_version_rejects_a_malformed_explicit_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_fixture(root)
            with self.assertRaisesRegex(
                bump_version.VersionBumpError, "not a valid semver version"
            ):
                bump_version.compute_target_version(root, bump=None, to="v1.2")

    def test_compute_target_version_requires_to_or_bump(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_fixture(root)
            with self.assertRaisesRegex(
                bump_version.VersionBumpError, "either --to or --bump is required"
            ):
                bump_version.compute_target_version(root, bump=None, to=None)

    def test_compute_updates_seeds_a_missing_marketplace_version_after_name(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_fixture(root)
            marketplace_path = root / ".claude-plugin" / "marketplace.json"
            catalog = json.loads(marketplace_path.read_text(encoding="utf-8"))
            catalog["plugins"][0].pop("version", None)
            marketplace_path.write_text(json.dumps(catalog), encoding="utf-8")

            updates = bump_version.compute_updates(root, "0.2.0")
            rendered = json.loads(updates[marketplace_path])
            entry = rendered["plugins"][0]
            keys = list(entry.keys())
            self.assertEqual(entry["version"], "0.2.0")
            self.assertEqual(keys.index("version"), keys.index("name") + 1)

    def test_compute_updates_preserves_position_of_an_existing_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_fixture(root)
            plugin_path = root / ".claude-plugin" / "plugin.json"
            updates = bump_version.compute_updates(root, "0.9.0")
            rendered = json.loads(updates[plugin_path])
            keys = list(rendered.keys())
            self.assertEqual(rendered["version"], "0.9.0")
            self.assertEqual(keys.index("version"), keys.index("name") + 1)

    def test_write_atomically_updates_all_four_surfaces_together(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_fixture(root)
            updates = bump_version.compute_updates(root, "0.5.0")
            bump_version.write_atomically(updates)

            validate_plugins.validate(root)  # no drift after a real bump
            for rel, entry in (
                (".claude-plugin/plugin.json", False),
                (".codex-plugin/plugin.json", False),
                (".claude-plugin/marketplace.json", True),
                (".agents/plugins/marketplace.json", True),
            ):
                self.assertEqual(self.read_version(root, rel, entry=entry), "0.5.0")

    def test_replace_atomic_never_touches_the_real_file_when_the_write_itself_fails(
        self,
    ) -> None:
        """A failure partway through the write, not just on open, must never
        truncate or otherwise corrupt the real target file."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "surface.json"
            original = '{"version": "0.1.0"}\n'
            target.write_text(original, encoding="utf-8")

            real_fdopen = bump_version.os.fdopen

            def flaky_fdopen(fd, *args, **kwargs):
                handle = real_fdopen(fd, *args, **kwargs)

                def flaky_write(content):
                    raise OSError("simulated disk failure mid-write")

                handle.write = flaky_write
                return handle

            with patch.object(bump_version.os, "fdopen", flaky_fdopen):
                with self.assertRaises(OSError):
                    bump_version._replace_atomic(target, '{"version": "0.2.0"}\n')

            self.assertEqual(target.read_text(encoding="utf-8"), original)
            leftover = [entry for entry in root.iterdir() if entry != target]
            self.assertEqual(leftover, [], "the failed temp file must be cleaned up")

    def test_write_atomically_restores_originals_when_a_later_write_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_fixture(root)
            updates = bump_version.compute_updates(root, "0.6.0")
            claude_path = root / ".claude-plugin" / "plugin.json"
            codex_path = root / ".codex-plugin" / "plugin.json"
            original_claude = claude_path.read_text(encoding="utf-8")
            original_codex = codex_path.read_text(encoding="utf-8")

            real_replace_atomic = bump_version._replace_atomic

            def flaky_replace_atomic(path: Path, content: str) -> None:
                if path == codex_path:
                    raise OSError("simulated disk failure")
                return real_replace_atomic(path, content)

            with patch.object(bump_version, "_replace_atomic", flaky_replace_atomic):
                with self.assertRaises(OSError):
                    bump_version.write_atomically(updates)

            self.assertEqual(claude_path.read_text(encoding="utf-8"), original_claude)
            self.assertEqual(codex_path.read_text(encoding="utf-8"), original_codex)


if __name__ == "__main__":
    unittest.main()
