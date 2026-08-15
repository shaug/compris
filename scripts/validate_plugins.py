#!/usr/bin/env python3
"""Validate the repository's two plugin packages and marketplace catalogs."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

PLUGIN_NAME = "compris"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
REQUIRED_SKILLS = {
    "babysit-pr",
    "carve-changesets",
    "implement-epic",
    "implement-ticket",
    "ready-ticket",
    "review-code-change",
    "review-code-simplicity",
    "review-correctness",
    "review-fix-loop",
    "review-solution-simplicity",
}
REVIEW_SKILLS = {
    "review-code-change",
    "review-code-simplicity",
    "review-correctness",
    "review-solution-simplicity",
}
REVIEW_BUNDLE_FILES = {
    "CONTRACT.md",
    "review-packet.schema.json",
    "review-result.schema.json",
    "validate.py",
}
# The lenses that judge shape load the canonical doctrine rather than restating
# it, so a package that ships one without the other ships a dangling citation.
DOCTRINE_BUNDLING_SKILLS = {"review-solution-simplicity", "carve-changesets"}
DOCTRINE_NAME = "cognitive-shaping-doctrine.md"


class PluginValidationError(ValueError):
    """Raised when plugin packaging is incomplete or internally inconsistent."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PluginValidationError(message)


def _load_object(path: Path) -> dict[str, Any]:
    _require(path.is_file(), f"missing {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PluginValidationError(f"invalid JSON in {path}: {error}") from error
    _require(isinstance(value, dict), f"{path} must contain a JSON object")
    return value


def _single_marketplace_entry(
    marketplace: dict[str, Any], path: Path
) -> dict[str, Any]:
    _require(
        marketplace.get("name") == PLUGIN_NAME, f"wrong marketplace name in {path}"
    )
    plugins = marketplace.get("plugins")
    _require(
        isinstance(plugins, list) and len(plugins) == 1,
        f"{path} must expose one plugin",
    )
    entry = plugins[0]
    _require(isinstance(entry, dict), f"{path} plugin entry must be an object")
    _require(entry.get("name") == PLUGIN_NAME, f"wrong plugin entry name in {path}")
    return entry


def validate(root: Path) -> None:
    root = root.resolve()
    claude_manifest_path = root / ".claude-plugin" / "plugin.json"
    codex_manifest_path = root / ".codex-plugin" / "plugin.json"
    claude_manifest = _load_object(claude_manifest_path)
    codex_manifest = _load_object(codex_manifest_path)

    for path, manifest in (
        (claude_manifest_path, claude_manifest),
        (codex_manifest_path, codex_manifest),
    ):
        _require(manifest.get("name") == PLUGIN_NAME, f"wrong plugin name in {path}")
        _require(
            isinstance(manifest.get("description"), str)
            and manifest["description"].strip(),
            f"missing plugin description in {path}",
        )
        _require(manifest.get("skills") == "./skills/", f"wrong skills path in {path}")
        version = manifest.get("version")
        _require(
            isinstance(version, str) and SEMVER.fullmatch(version),
            f"invalid version in {path}",
        )

    claude_marketplace_path = root / ".claude-plugin" / "marketplace.json"
    claude_entry = _single_marketplace_entry(
        _load_object(claude_marketplace_path), claude_marketplace_path
    )
    _require(
        claude_entry.get("source") == "./",
        "Claude plugin source must be the repository root",
    )

    codex_marketplace_path = root / ".agents" / "plugins" / "marketplace.json"
    codex_entry = _single_marketplace_entry(
        _load_object(codex_marketplace_path), codex_marketplace_path
    )
    _require(
        codex_entry.get("source") == {"source": "local", "path": "./"},
        "Codex plugin source must be the repository root",
    )
    _require(
        codex_entry.get("policy")
        == {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "Codex marketplace policy must keep the plugin installable",
    )
    _require(
        isinstance(codex_entry.get("category"), str),
        "Codex plugin category is required",
    )

    for path, entry in (
        (claude_marketplace_path, claude_entry),
        (codex_marketplace_path, codex_entry),
    ):
        version = entry.get("version")
        _require(
            isinstance(version, str) and SEMVER.fullmatch(version),
            f"invalid version in {path}",
        )

    all_versions = {
        claude_manifest_path: claude_manifest["version"],
        codex_manifest_path: codex_manifest["version"],
        claude_marketplace_path: claude_entry["version"],
        codex_marketplace_path: codex_entry["version"],
    }
    _require(
        len(set(all_versions.values())) == 1,
        "plugin and marketplace versions must match across "
        + ", ".join(str(path) for path in all_versions),
    )

    installed_skills = {
        path.parent.name
        for path in (root / "skills").glob("*/SKILL.md")
        if path.is_file()
    }
    missing_skills = sorted(REQUIRED_SKILLS - installed_skills)
    _require(
        not missing_skills,
        f"plugin is missing required skills: {', '.join(missing_skills)}",
    )

    for skill in REQUIRED_SKILLS:
        _require(
            (root / "skills" / skill / "agents" / "openai.yaml").is_file(),
            f"missing OpenAI adapter metadata for {skill}",
        )

    _require(
        (root / "skills" / "babysit-pr" / "scripts" / "gh_pr_watch.py").is_file(),
        "plugin is missing the babysit-pr watcher",
    )
    for skill in REVIEW_SKILLS:
        bundle = root / "skills" / skill / "references" / "review-suite"
        missing_bundle_files = sorted(
            name for name in REVIEW_BUNDLE_FILES if not (bundle / name).is_file()
        )
        _require(
            not missing_bundle_files,
            f"{skill} review-suite bundle is missing: {', '.join(missing_bundle_files)}",
        )
    for skill in DOCTRINE_BUNDLING_SKILLS:
        _require(
            (root / "skills" / skill / "references" / DOCTRINE_NAME).is_file(),
            f"{skill} is missing the bundled {DOCTRINE_NAME}",
        )


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        validate(root)
    except PluginValidationError as error:
        print(f"plugin validation failed: {error}", file=sys.stderr)
        return 1
    print("Validated Claude and Codex plugin packaging for compris")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
