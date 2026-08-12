from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from helpers import REPOSITORY_ROOT, copy_fixture  # noqa: E402

SPEC = importlib.util.spec_from_file_location(
    "validate_plugins", REPOSITORY_ROOT / "scripts" / "validate_plugins.py"
)
assert SPEC is not None and SPEC.loader is not None
validate_plugins = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_plugins)


class ValidatePluginsTests(unittest.TestCase):
    def copy_fixture(self, destination: Path) -> None:
        copy_fixture(destination)

    def test_repository_plugin_package_is_complete(self) -> None:
        validate_plugins.validate(REPOSITORY_ROOT)

    def test_manifest_versions_must_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_fixture(root)
            manifest_path = root / ".codex-plugin" / "plugin.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["version"] = "0.2.0"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(
                validate_plugins.PluginValidationError, "versions must match"
            ):
                validate_plugins.validate(root)

    def test_required_bundled_resource_cannot_disappear(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_fixture(root)
            watcher = root / "skills" / "babysit-pr" / "scripts" / "gh_pr_watch.py"
            watcher.unlink()

            with self.assertRaisesRegex(
                validate_plugins.PluginValidationError, "missing the babysit-pr watcher"
            ):
                validate_plugins.validate(root)

    def test_marketplace_entries_require_a_valid_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_fixture(root)
            marketplace_path = root / ".claude-plugin" / "marketplace.json"
            catalog = json.loads(marketplace_path.read_text(encoding="utf-8"))
            catalog["plugins"][0].pop("version", None)
            marketplace_path.write_text(json.dumps(catalog), encoding="utf-8")

            with self.assertRaisesRegex(
                validate_plugins.PluginValidationError, "invalid version"
            ):
                validate_plugins.validate(root)

    def test_marketplace_version_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_fixture(root)
            marketplace_path = root / ".agents" / "plugins" / "marketplace.json"
            catalog = json.loads(marketplace_path.read_text(encoding="utf-8"))
            catalog["plugins"][0]["version"] = "9.9.9"
            marketplace_path.write_text(json.dumps(catalog), encoding="utf-8")

            with self.assertRaisesRegex(
                validate_plugins.PluginValidationError, "versions must match"
            ):
                validate_plugins.validate(root)


if __name__ == "__main__":
    unittest.main()
