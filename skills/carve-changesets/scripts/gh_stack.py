#!/usr/bin/env python3
"""Narrow, profile-gated subprocess boundary for ``gh stack``."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

GH_STACK_ENV = {"GH_PAGER": "cat", "GH_PROMPT_DISABLED": "1"}
REVIEWED_PROFILE_PATH = (
    Path(__file__).resolve().parent
    / "tests"
    / "fixtures"
    / "gh-stack"
    / "profile-reviewed.json"
)


class GhStackError(RuntimeError):
    """The native stack command or its checked-in contract was unusable."""


class StackCapability(str, Enum):
    LOCAL_INIT = "local_init"
    VIEW_JSON = "view_json"
    LOCAL_REBASE_NO_TRUNK = "local_rebase_no_trunk"
    FENCED_PUSH = "fenced_push"
    FENCED_SUBMIT = "fenced_submit"
    FENCED_SYNC = "fenced_sync"
    FENCED_MERGE = "fenced_merge"
    EXPLICIT_PULL_REQUEST_BODIES = "explicit_pull_request_bodies"
    DURABLE_QUEUE_FENCE = "durable_queue_fence"
    PHASED_TRUNK_REFRESH = "phased_trunk_refresh"


@dataclass(frozen=True)
class GhStackProfile:
    version: str
    source_revision: str
    capabilities: frozenset[StackCapability]


@dataclass(frozen=True)
class GhStackProfileBlocker:
    reason: str
    observed_version: str
    observed_surfaces: tuple[tuple[str, str], ...]
    mismatched_surfaces: tuple[str, ...]
    probe_errors: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ProfileProbeResult:
    status: str
    observed_version: str
    observed_surfaces: tuple[tuple[str, str], ...]
    profile: GhStackProfile | None
    blocker: GhStackProfileBlocker | None


class Runner(Protocol):
    def __call__(self, argv: Sequence[str], *, env: Mapping[str, str]) -> str: ...


def _run(
    argv: Sequence[str], *, env: Mapping[str, str], cwd: Path | str | None = None
) -> str:
    completed = subprocess.run(
        list(argv),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, **env},
        cwd=cwd,
    )
    return completed.stdout


def _normalize_surface(output: str) -> str:
    lines = output.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    return "\n".join(line.rstrip() for line in lines).strip() + "\n"


def _surface_digest(output: str) -> str:
    return hashlib.sha256(_normalize_surface(output).encode()).hexdigest()


def _probe_error(exc: OSError | subprocess.CalledProcessError) -> str:
    if isinstance(exc, subprocess.CalledProcessError):
        detail = f"exit {exc.returncode}"
        if isinstance(exc.stderr, str) and exc.stderr.strip():
            detail += f": {exc.stderr.strip()}"
        return detail
    return str(exc)


def _load_reviewed_profile() -> dict[str, object]:
    try:
        profile = json.loads(REVIEWED_PROFILE_PATH.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise GhStackError(
            f"reviewed gh stack profile is unreadable: {REVIEWED_PROFILE_PATH}"
        ) from exc
    if not isinstance(profile, dict):
        raise GhStackError("reviewed gh stack profile must be a JSON object")
    return profile


def _profile_commands(profile: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    commands = profile.get("commands")
    if not isinstance(commands, dict) or not commands:
        raise GhStackError("reviewed gh stack profile has no command surfaces")
    normalized: dict[str, Mapping[str, object]] = {}
    for name, details in commands.items():
        if not isinstance(name, str) or not isinstance(details, dict):
            raise GhStackError("reviewed gh stack command surfaces are malformed")
        digest = details.get("help_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise GhStackError(f"reviewed gh stack {name!r} surface has no SHA-256")
        normalized[name] = details
    return normalized


def reviewed_preview_profile(
    source_revision: str,
    *,
    reviewed_profile: Mapping[str, object] | None = None,
) -> GhStackProfile:
    contract = reviewed_profile or _load_reviewed_profile()
    expected_revision = contract.get("source_revision")
    version = contract.get("version")
    if source_revision != expected_revision:
        raise GhStackError(
            f"unreviewed gh stack source revision {source_revision!r}; "
            f"expected {expected_revision!r}"
        )
    if not isinstance(version, str) or not version:
        raise GhStackError("reviewed gh stack profile has no normalized version")
    _profile_commands(contract)
    return GhStackProfile(
        version=version,
        source_revision=source_revision,
        capabilities=frozenset(
            {
                StackCapability.LOCAL_INIT,
                StackCapability.VIEW_JSON,
                StackCapability.LOCAL_REBASE_NO_TRUNK,
            }
        ),
    )


class GhStackClient:
    def __init__(
        self,
        runner: Runner | None = None,
        *,
        cwd: Path | str | None = None,
    ) -> None:
        self._runner = runner or (lambda argv, *, env: _run(argv, env=env, cwd=cwd))

    def _capture(self, args: Sequence[str]) -> str:
        if isinstance(args, (str, bytes)):
            raise TypeError("gh stack arguments must be a sequence of tokens")
        tokens = list(args)
        if not all(isinstance(token, str) and token for token in tokens):
            raise TypeError("gh stack arguments must be non-empty string tokens")
        return self._runner(["gh", "stack", *tokens], env=GH_STACK_ENV)

    def view_json(self, *, allow_state_refresh: bool) -> dict[str, object]:
        if not allow_state_refresh:
            raise GhStackError(
                "gh stack view --json may refresh saved stack state; "
                "local-state authority is required"
            )
        try:
            raw_payload = self._capture(("view", "--json"))
        except (OSError, subprocess.CalledProcessError) as exc:
            raise GhStackError(
                f"gh stack view --json failed: {_probe_error(exc)}"
            ) from exc
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            raise GhStackError("gh stack view --json returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise GhStackError("gh stack view --json must return an object")
        return payload

    def init(self, *, base: str, branches: Sequence[str]) -> None:
        self._capture(("init", "--base", base, *branches))

    def rebase_no_trunk_upstack(self, branch: str) -> None:
        self._capture(("rebase", "--no-trunk", "--upstack", branch))


def probe_profile(
    *,
    runner: Runner | None = None,
    cwd: Path | str | None = None,
    reviewed_profile: Mapping[str, object] | None = None,
) -> ProfileProbeResult:
    contract = reviewed_profile or _load_reviewed_profile()
    commands = _profile_commands(contract)
    client = GhStackClient(runner=runner, cwd=cwd)
    try:
        observed_version = _normalize_surface(client._capture(("--version",))).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        blocker = GhStackProfileBlocker(
            reason="version_probe_failed",
            observed_version="",
            observed_surfaces=(),
            mismatched_surfaces=(),
            probe_errors=(("--version", _probe_error(exc)),),
        )
        return ProfileProbeResult(
            status="blocked",
            observed_version="",
            observed_surfaces=(),
            profile=None,
            blocker=blocker,
        )

    observed: list[tuple[str, str]] = []
    probe_errors: list[tuple[str, str]] = []
    for command in sorted(commands):
        try:
            output = client._capture((command, "--help"))
        except (OSError, subprocess.CalledProcessError) as exc:
            probe_errors.append((command, _probe_error(exc)))
        else:
            observed.append((command, _surface_digest(output)))
    observed_surfaces = tuple(observed)
    mismatched = tuple(
        command
        for command, digest in observed_surfaces
        if digest != commands[command]["help_sha256"]
    )
    if probe_errors:
        blocker = GhStackProfileBlocker(
            reason="surface_probe_failed",
            observed_version=observed_version,
            observed_surfaces=observed_surfaces,
            mismatched_surfaces=mismatched,
            probe_errors=tuple(probe_errors),
        )
        return ProfileProbeResult(
            status="blocked",
            observed_version=observed_version,
            observed_surfaces=observed_surfaces,
            profile=None,
            blocker=blocker,
        )

    expected_version = contract.get("version")
    if observed_version != expected_version or mismatched:
        reason = (
            "unknown_version"
            if observed_version != expected_version
            else "surface_mismatch"
        )
        blocker = GhStackProfileBlocker(
            reason=reason,
            observed_version=observed_version,
            observed_surfaces=observed_surfaces,
            mismatched_surfaces=mismatched,
        )
        return ProfileProbeResult(
            status="blocked",
            observed_version=observed_version,
            observed_surfaces=observed_surfaces,
            profile=None,
            blocker=blocker,
        )

    source_revision = contract.get("source_revision")
    if not isinstance(source_revision, str):
        raise GhStackError("reviewed gh stack profile has no source revision")
    profile = reviewed_preview_profile(source_revision, reviewed_profile=contract)
    return ProfileProbeResult(
        status="supported",
        observed_version=observed_version,
        observed_surfaces=observed_surfaces,
        profile=profile,
        blocker=None,
    )
