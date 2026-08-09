#!/usr/bin/env python3
"""Bump the compris plugin version across every enumerated manifest surface.

Four files carry the plugin's version: the two plugin manifests
(`.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`) at their own
top level, and the two marketplace catalogs (`.claude-plugin/marketplace.json`,
`.agents/plugins/marketplace.json`) on their single `compris` plugin entry.
`scripts/validate_plugins.py` (wired into `just lint`) rejects drift across
all four; this script is the only tool that should ever change one of them.

Usage:
    python3 scripts/bump_version.py --bump patch
    python3 scripts/bump_version.py --bump minor
    python3 scripts/bump_version.py --bump major
    python3 scripts/bump_version.py --to 0.3.0
    python3 scripts/bump_version.py --bump patch --dry-run

Cutting a git tag or GitHub release is a separate, operator-only step outside
this script's scope — see docs/release-process.md.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

# Surfaces where the version lives at the manifest's own top level.
TOP_LEVEL_VERSION_SURFACES = (
    Path(".claude-plugin/plugin.json"),
    Path(".codex-plugin/plugin.json"),
)
# Surfaces where the version lives on the catalog's single `compris` plugin
# entry, not the catalog object itself.
MARKETPLACE_ENTRY_VERSION_SURFACES = (
    Path(".claude-plugin/marketplace.json"),
    Path(".agents/plugins/marketplace.json"),
)


class VersionBumpError(ValueError):
    """Raised when the current or target version state cannot be bumped safely."""


def _parse_semver(version: str) -> tuple[int, int, int]:
    match = SEMVER.fullmatch(version)
    if not match:
        raise VersionBumpError(f"not a valid semver version: {version!r}")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def _bump(version: tuple[int, int, int], part: str) -> str:
    major, minor, patch = version
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise VersionBumpError(f"unknown bump kind: {part!r}")


def resolve_current_version(root: Path) -> str:
    """The version the two plugin manifests currently agree on.

    Only the top-level plugin manifests are consulted here: a marketplace
    catalog may not carry a version yet on a first run — this script is what
    seeds it — so it cannot anchor "the current version".
    """
    versions: dict[Path, str] = {}
    for rel in TOP_LEVEL_VERSION_SURFACES:
        path = root / rel
        manifest = json.loads(path.read_text(encoding="utf-8"))
        version = manifest.get("version")
        if not isinstance(version, str):
            raise VersionBumpError(f"missing version in {rel}")
        versions[rel] = version
    distinct = set(versions.values())
    if len(distinct) != 1:
        raise VersionBumpError(
            "plugin manifests disagree on the current version before bump: "
            + ", ".join(f"{rel}={version}" for rel, version in versions.items())
        )
    return next(iter(distinct))


def compute_target_version(root: Path, *, bump: str | None, to: str | None) -> str:
    if to is not None:
        _parse_semver(to)
        return to
    if bump is None:
        raise VersionBumpError("either --to or --bump is required")
    current = resolve_current_version(root)
    return _bump(_parse_semver(current), bump)


def _rendered_top_level(path: Path, version: str) -> str:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["version"] = version
    return json.dumps(manifest, indent=2) + "\n"


def _with_version_after_name(entry: dict, version: str) -> dict:
    if "version" in entry:
        entry["version"] = version
        return entry
    ordered: dict = {}
    inserted = False
    for key, value in entry.items():
        ordered[key] = value
        if key == "name" and not inserted:
            ordered["version"] = version
            inserted = True
    if not inserted:
        ordered = {"version": version, **entry}
    return ordered


def _rendered_marketplace_entry(path: Path, version: str) -> str:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    plugins = catalog.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != 1:
        raise VersionBumpError(f"{path} must expose exactly one plugin entry")
    entry = plugins[0]
    if not isinstance(entry, dict):
        raise VersionBumpError(f"{path} plugin entry must be an object")
    plugins[0] = _with_version_after_name(entry, version)
    return json.dumps(catalog, indent=2) + "\n"


def compute_updates(root: Path, version: str) -> dict[Path, str]:
    """The post-bump text of every enumerated surface, without writing anything."""
    _parse_semver(version)
    updates: dict[Path, str] = {}
    for rel in TOP_LEVEL_VERSION_SURFACES:
        updates[root / rel] = _rendered_top_level(root / rel, version)
    for rel in MARKETPLACE_ENTRY_VERSION_SURFACES:
        updates[root / rel] = _rendered_marketplace_entry(root / rel, version)
    return updates


def _replace_atomic(path: Path, content: str) -> None:
    """Write `content` to `path` via a sibling temp file and `os.replace`.

    Matches this repository's established atomic-write idiom
    (`skills/review-fix-loop/scripts/local_execution.py`'s
    `write_checkpoint_atomic`): the real target is only ever touched by the
    final rename, so a failure while writing the temp file — including one
    partway through the write itself, not just on open — never truncates or
    otherwise corrupts the real file.
    """
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".tmp-{path.name}-", suffix=".json"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise


def write_atomically(updates: dict[Path, str]) -> None:
    """Write every surface, restoring already-written files if a later write fails.

    Each surface is written via `_replace_atomic`, so a failure while writing
    any one surface never touches that surface's own real file. All four
    surfaces are meant to move together, though: a failure between two
    separate replaces is still possible, so this also restores every surface
    this call already replaced, matching the still-published original content
    — a partial bump never lands and stays exactly the drift
    `validate_plugins.py` exists to catch.
    """
    originals: dict[Path, str] = {
        path: path.read_text(encoding="utf-8") for path in updates
    }
    written: list[Path] = []
    try:
        for path, content in updates.items():
            _replace_atomic(path, content)
            written.append(path)
    except OSError:
        for path in written:
            _replace_atomic(path, originals[path])
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--to", help="exact target version, e.g. 0.3.0")
    parser.add_argument(
        "--bump",
        choices=("major", "minor", "patch"),
        help="bump kind relative to the version the plugin manifests currently agree on",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the target version and affected files without writing",
    )
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    try:
        version = compute_target_version(root, bump=args.bump, to=args.to)
        updates = compute_updates(root, version)
    except VersionBumpError as error:
        print(f"version bump failed: {error}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"would bump compris to {version}:")
        for path in updates:
            print(f"  {path.relative_to(root)}")
        return 0

    write_atomically(updates)
    print(f"bumped compris to {version} across {len(updates)} manifest(s):")
    for path in updates:
        print(f"  {path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
