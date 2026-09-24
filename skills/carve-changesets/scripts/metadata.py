"""Durable semantic identity carried by changeset commit trailers."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import Callable, Sequence

TRAILER_SLUG = "Changeset-Slug"
TRAILER_INDEX = "Changeset-Index"
TRAILER_SOURCE = "Changeset-Source"
TRAILER_LINEAGE = "Changeset-Lineage"
TRAILER_RECOVERY_FROM = "Changeset-Recovery-From"
METADATA_MARKER_V1 = "carve-changesets:metadata:v1"
METADATA_MARKER_V2 = "carve-changesets:metadata:v2"

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_BLOCK_RE = re.compile(
    rf"<!--\s*(?P<marker>{re.escape(METADATA_MARKER_V1)}|"
    rf"{re.escape(METADATA_MARKER_V2)})\s*\n(?P<payload>.*?)\n\s*-->",
    re.DOTALL,
)


class MetadataError(ValueError):
    """Raised when durable changeset identity is absent or contradictory."""


GitRunner = Callable[[Sequence[str], str], str]


@dataclass(frozen=True, init=False)
class SourceIdentity:
    """One remotely verifiable immutable source in an ordered lineage."""

    remote: str
    branch: str
    sha: str

    def __init__(
        self,
        *args: str,
        remote: str | None = None,
        branch: str | None = None,
        sha: str | None = None,
    ) -> None:
        if args:
            if any(value is not None for value in (remote, branch, sha)):
                raise TypeError(
                    "SourceIdentity accepts positional or keyword values, not both"
                )
            if len(args) == 2:
                branch, sha = args
                remote = "origin"
            elif len(args) == 3:
                remote, branch, sha = args
            else:
                raise TypeError(
                    "SourceIdentity expects branch/SHA or remote/branch/SHA"
                )
        if remote is None or branch is None or sha is None:
            raise TypeError("SourceIdentity requires remote, branch, and sha")
        object.__setattr__(self, "remote", remote)
        object.__setattr__(self, "branch", branch)
        object.__setattr__(self, "sha", sha)
        self._validate()

    def _validate(self) -> None:
        if not self.remote.strip():
            raise MetadataError("Source identity remote must not be empty.")
        if any(character.isspace() for character in self.remote):
            raise MetadataError("Source identity remote must not contain whitespace.")
        if not self.branch.strip():
            raise MetadataError("Source identity branch must not be empty.")
        if " @ " in self.branch:
            raise MetadataError("Source identity branch must not contain ' @ '.")
        try:
            branch_check = subprocess.run(
                ["git", "check-ref-format", "--branch", self.branch],
                text=True,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise MetadataError("Git is required to validate source branches.") from exc
        if branch_check.returncode != 0 or branch_check.stdout.strip() != self.branch:
            raise MetadataError(
                "Source identity branch must be a valid literal Git branch name."
            )
        if not _SHA_RE.fullmatch(self.sha):
            raise MetadataError(
                "Source identity SHA must be a full lowercase 40-character SHA."
            )

    @property
    def trailer(self) -> str:
        return f"{self.remote} {self.branch} @ {self.sha}"

    @property
    def legacy_trailer(self) -> str:
        return f"{self.branch} @ {self.sha}"


@dataclass(frozen=True, init=False)
class ChangesetMetadata:
    """Semantic identity for native v3, with optional read-only legacy evidence."""

    slug: str
    source_lineage: tuple[SourceIdentity, ...]
    recovery_from_head: str | None
    legacy_position: int | None
    marker_version: int

    def __init__(
        self,
        slug: str,
        index: int | None = None,
        source_branch: str | None = None,
        source_sha: str | None = None,
        source_lineage: tuple[SourceIdentity, ...] = (),
        recovery_from_head: str | None = None,
        *,
        legacy_position: int | None = None,
        marker_version: int | None = None,
    ) -> None:
        legacy_arguments = any(
            value is not None for value in (index, source_branch, source_sha)
        )
        if legacy_position is not None and index is not None:
            raise MetadataError("Legacy position was supplied more than once.")
        position = index if index is not None else legacy_position
        lineage = tuple(source_lineage)
        if legacy_arguments:
            if index is None or source_branch is None or source_sha is None:
                raise MetadataError(
                    "Legacy metadata requires index, source branch, and source SHA."
                )
            if not lineage:
                lineage = (SourceIdentity(source_branch, source_sha),)
            active = lineage[-1]
            if (active.branch, active.sha) != (source_branch, source_sha):
                raise MetadataError(
                    "Changeset source identity must equal the final source-lineage entry."
                )
            resolved_version = marker_version or (2 if len(lineage) > 1 else 1)
        else:
            resolved_version = marker_version or 3

        object.__setattr__(self, "slug", slug)
        object.__setattr__(self, "source_lineage", lineage)
        object.__setattr__(self, "recovery_from_head", recovery_from_head)
        object.__setattr__(self, "legacy_position", position)
        object.__setattr__(self, "marker_version", resolved_version)
        self._validate()

    def _validate(self) -> None:
        if not self.slug.strip():
            raise MetadataError("Changeset slug must not be empty.")
        if self.marker_version not in {1, 2, 3}:
            raise MetadataError("Changeset metadata version must be 1, 2, or 3.")
        if self.marker_version in {1, 2}:
            if self.legacy_position is None or self.legacy_position < 1:
                raise MetadataError("Changeset index must be a positive integer.")
        elif self.legacy_position is not None:
            raise MetadataError("Native v3 metadata must not carry a position.")
        if not self.source_lineage:
            raise MetadataError("Changeset source lineage must be non-empty.")
        if len(set(self.source_lineage)) != len(self.source_lineage):
            raise MetadataError("Changeset source lineage must not repeat an identity.")
        branches = [
            (identity.remote, identity.branch) for identity in self.source_lineage
        ]
        if len(set(branches)) != len(branches):
            raise MetadataError(
                "Changeset source lineage must not reuse a remote branch with a different SHA."
            )
        if len(self.source_lineage) == 1 and self.recovery_from_head is not None:
            raise MetadataError(
                "A single-source changeset must not carry recovery-from metadata."
            )
        if len(self.source_lineage) > 1 and not self.recovery_from_head:
            raise MetadataError(
                "A successor-source changeset requires an exact recovery-from head."
            )
        if self.recovery_from_head is not None and not _SHA_RE.fullmatch(
            self.recovery_from_head
        ):
            raise MetadataError(
                "Changeset recovery-from head must be a full lowercase 40-character SHA."
            )

    @property
    def index(self) -> int:
        if self.legacy_position is None:
            raise MetadataError("Native v3 metadata has no durable position.")
        return self.legacy_position

    @property
    def source_branch(self) -> str:
        return self.active_source.branch

    @property
    def source_sha(self) -> str:
        return self.active_source.sha

    @property
    def source_trailer(self) -> str:
        return self.active_source.legacy_trailer

    @property
    def root_source(self) -> SourceIdentity:
        return self.source_lineage[0]

    @property
    def active_source(self) -> SourceIdentity:
        return self.source_lineage[-1]

    @property
    def version(self) -> int:
        return self.marker_version

    def same_changeset_as(self, other: ChangesetMetadata) -> bool:
        """Return whether two metadata records identify one stable changeset."""

        same_legacy_position = (
            self.legacy_position == other.legacy_position
            if self.legacy_position is not None or other.legacy_position is not None
            else True
        )
        return (
            self.slug == other.slug
            and same_legacy_position
            and self.root_source == other.root_source
        )


@dataclass(frozen=True)
class LegacyMetadataEvidence:
    """Normalized semantic identity plus untouched positional history."""

    metadata: ChangesetMetadata
    legacy_position: int
    marker_version: int
    original: str


def _identity_payload(
    identity: SourceIdentity, *, include_remote: bool
) -> dict[str, str]:
    payload = {"branch": identity.branch, "sha": identity.sha}
    if include_remote:
        payload["remote"] = identity.remote
    return payload


def _lineage_json(lineage: Sequence[SourceIdentity], *, include_remote: bool) -> str:
    return json.dumps(
        [
            _identity_payload(identity, include_remote=include_remote)
            for identity in lineage
        ],
        separators=(",", ":"),
        sort_keys=True,
    )


def _parse_lineage(
    value: object,
    *,
    context: str,
    remote: str | None,
) -> tuple[SourceIdentity, ...]:
    if not isinstance(value, list) or not value:
        raise MetadataError(f"{context} source_lineage must be a non-empty array.")
    expected = {"remote", "branch", "sha"} if remote is None else {"branch", "sha"}
    lineage: list[SourceIdentity] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict) or set(item) != expected:
            fields = ", ".join(sorted(expected))
            raise MetadataError(
                f"{context} source_lineage entry {index} must contain only {fields}."
            )
        if not all(isinstance(item[field], str) for field in expected):
            raise MetadataError(
                f"{context} source_lineage entry {index} fields must be strings."
            )
        lineage.append(
            SourceIdentity(
                remote=remote if remote is not None else item["remote"],
                branch=item["branch"],
                sha=item["sha"],
            )
        )
    return tuple(lineage)


def _run_git_interpret_trailers(args: Sequence[str], input_text: str) -> str:
    try:
        result = subprocess.run(
            ["git", "interpret-trailers", *args],
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise MetadataError("Git is required to manage changeset trailers.") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise MetadataError(f"git interpret-trailers failed: {detail}")
    return result.stdout


def stamp_commit_message(
    message: str,
    metadata: ChangesetMetadata,
    *,
    runner: GitRunner = _run_git_interpret_trailers,
) -> str:
    """Return a commit message stamped by ``git interpret-trailers``."""

    if not message.strip():
        raise MetadataError("Commit message must not be empty.")
    cleanup = ["--if-exists=replace", "--if-missing=doNothing", "--trim-empty"]
    for trailer in (
        TRAILER_SLUG,
        TRAILER_INDEX,
        TRAILER_SOURCE,
        TRAILER_LINEAGE,
        TRAILER_RECOVERY_FROM,
    ):
        cleanup.extend(("--trailer", f"{trailer}:"))
    clean_message = runner(tuple(cleanup), message.rstrip() + "\n")
    trailers = [
        "--if-exists=replace",
        "--if-missing=add",
        "--trailer",
        f"{TRAILER_SLUG}: {metadata.slug}",
    ]
    if metadata.version == 3:
        if len(metadata.source_lineage) == 1:
            trailers.extend(
                ("--trailer", f"{TRAILER_SOURCE}: {metadata.active_source.trailer}")
            )
        else:
            trailers.extend(
                (
                    "--trailer",
                    f"{TRAILER_LINEAGE}: "
                    f"{_lineage_json(metadata.source_lineage, include_remote=True)}",
                    "--trailer",
                    f"{TRAILER_RECOVERY_FROM}: {metadata.recovery_from_head}",
                )
            )
    else:
        trailers.extend(
            (
                "--trailer",
                f"{TRAILER_INDEX}: {metadata.index}",
                "--trailer",
                f"{TRAILER_SOURCE}: {metadata.source_trailer}",
            )
        )
        if metadata.version == 2:
            trailers.extend(
                (
                    "--trailer",
                    f"{TRAILER_LINEAGE}: "
                    f"{_lineage_json(metadata.source_lineage, include_remote=False)}",
                    "--trailer",
                    f"{TRAILER_RECOVERY_FROM}: {metadata.recovery_from_head}",
                )
            )
    return runner(tuple(trailers), clean_message)


def _trailer_values(message: str, *, runner: GitRunner) -> dict[str, list[str]]:
    parsed = runner(("--parse",), message)
    values: dict[str, list[str]] = {}
    for line in parsed.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values.setdefault(key.strip(), []).append(value.strip())
    return values


def _require_one(values: dict[str, list[str]], key: str) -> str:
    if not values.get(key):
        raise MetadataError(f"Missing required changeset trailer(s): {key}")
    if len(values[key]) != 1:
        raise MetadataError(f"Ambiguous duplicate changeset trailer(s): {key}")
    return values[key][0]


def _parse_legacy_commit_values(
    values: dict[str, list[str]], *, remote: str
) -> ChangesetMetadata:
    slug = _require_one(values, TRAILER_SLUG)
    index_text = _require_one(values, TRAILER_INDEX)
    source_text = _require_one(values, TRAILER_SOURCE)
    try:
        index = int(index_text)
    except ValueError as exc:
        raise MetadataError(
            f"Changeset-Index must be a positive integer, got {index_text!r}."
        ) from exc
    source_branch, separator, source_sha = source_text.rpartition(" @ ")
    if not separator:
        raise MetadataError(
            "Changeset-Source must use '<source-branch> @ <source-sha>'."
        )
    optional = (TRAILER_LINEAGE, TRAILER_RECOVERY_FROM)
    duplicates = [key for key in optional if len(values.get(key, [])) > 1]
    if duplicates:
        raise MetadataError(
            "Ambiguous duplicate changeset trailer(s): " + ", ".join(duplicates)
        )
    has_lineage = bool(values.get(TRAILER_LINEAGE))
    has_recovery = bool(values.get(TRAILER_RECOVERY_FROM))
    if has_lineage != has_recovery:
        raise MetadataError(
            "Successor metadata requires both Changeset-Lineage and "
            "Changeset-Recovery-From."
        )
    lineage = (SourceIdentity(remote, source_branch, source_sha),)
    recovery_from: str | None = None
    if has_lineage:
        try:
            payload = json.loads(values[TRAILER_LINEAGE][0])
        except json.JSONDecodeError as exc:
            raise MetadataError(
                f"Changeset-Lineage contains invalid JSON: {exc.msg}."
            ) from exc
        lineage = _parse_lineage(payload, context="Commit", remote=remote)
        recovery_from = values[TRAILER_RECOVERY_FROM][0]
    return ChangesetMetadata(
        slug=slug,
        index=index,
        source_branch=source_branch,
        source_sha=source_sha,
        source_lineage=lineage,
        recovery_from_head=recovery_from,
        marker_version=2 if has_lineage else 1,
    )


def _parse_native_commit_values(values: dict[str, list[str]]) -> ChangesetMetadata:
    slug = _require_one(values, TRAILER_SLUG)
    has_source = bool(values.get(TRAILER_SOURCE))
    has_lineage = bool(values.get(TRAILER_LINEAGE))
    has_recovery = bool(values.get(TRAILER_RECOVERY_FROM))
    if has_source and (has_lineage or has_recovery):
        raise MetadataError(
            "Native metadata must use one source or successor lineage, not both."
        )
    if has_source:
        source_text = _require_one(values, TRAILER_SOURCE)
        source_prefix, separator, source_sha = source_text.rpartition(" @ ")
        remote, whitespace, branch = source_prefix.partition(" ")
        if not separator or not whitespace or not branch:
            raise MetadataError(
                "Native Changeset-Source must use '<remote> <branch> @ <source-sha>'."
            )
        lineage = (SourceIdentity(remote, branch, source_sha),)
        recovery_from = None
    elif has_lineage and has_recovery:
        lineage_text = _require_one(values, TRAILER_LINEAGE)
        recovery_from = _require_one(values, TRAILER_RECOVERY_FROM)
        try:
            payload = json.loads(lineage_text)
        except json.JSONDecodeError as exc:
            raise MetadataError(
                f"Changeset-Lineage contains invalid JSON: {exc.msg}."
            ) from exc
        lineage = _parse_lineage(payload, context="Commit", remote=None)
    else:
        raise MetadataError(
            "Native metadata requires Changeset-Source or both "
            "Changeset-Lineage and Changeset-Recovery-From."
        )
    return ChangesetMetadata(
        slug=slug,
        source_lineage=lineage,
        recovery_from_head=recovery_from,
    )


def parse_commit_message(
    message: str,
    *,
    remote: str = "origin",
    runner: GitRunner = _run_git_interpret_trailers,
) -> ChangesetMetadata:
    """Parse native v3 or normalize legacy v1/v2 commit identity."""

    values = _trailer_values(message, runner=runner)
    if values.get(TRAILER_INDEX):
        return _parse_legacy_commit_values(values, remote=remote)
    return _parse_native_commit_values(values)


def normalize_legacy_commit_metadata(
    message: str,
    *,
    remote: str,
    runner: GitRunner = _run_git_interpret_trailers,
) -> LegacyMetadataEvidence:
    """Normalize legacy commit trailers without rewriting their original text."""

    metadata = _parse_legacy_commit_values(
        _trailer_values(message, runner=runner), remote=remote
    )
    return LegacyMetadataEvidence(
        metadata=metadata,
        legacy_position=metadata.index,
        marker_version=metadata.version,
        original=message,
    )


def render_pr_metadata(metadata: ChangesetMetadata) -> str:
    """Render a legacy block; native v3 deliberately has no PR-body block."""

    if metadata.version == 3:
        raise MetadataError("Native v3 metadata is carried only by commit trailers.")
    fields: dict[str, object] = {
        "index": metadata.index,
        "slug": metadata.slug,
        "source_branch": metadata.source_branch,
        "source_sha": metadata.source_sha,
    }
    marker = METADATA_MARKER_V1
    if metadata.version == 2:
        marker = METADATA_MARKER_V2
        fields["source_lineage"] = [
            _identity_payload(identity, include_remote=False)
            for identity in metadata.source_lineage
        ]
        fields["recovery_from_head"] = metadata.recovery_from_head
    payload = json.dumps(fields, separators=(",", ":"), sort_keys=True)
    return f"<!-- {marker}\n{payload}\n-->"


def embed_pr_metadata(body: str, metadata: ChangesetMetadata) -> str:
    """Preserve human prose for v3; append or replace legacy metadata blocks."""

    matches = list(_BLOCK_RE.finditer(body))
    if len(matches) > 1:
        raise MetadataError("PR body contains multiple changeset metadata blocks.")
    if metadata.version == 3:
        if not matches:
            return body
        match = matches[0]
        before = body[: match.start()].rstrip()
        after = body[match.end() :].strip()
        prose = "\n\n".join(part for part in (before, after) if part)
        return prose + ("\n" if prose else "")
    block = render_pr_metadata(metadata)
    if matches:
        match = matches[0]
        return body[: match.start()] + block + body[match.end() :]
    separator = "\n" if not body or body.endswith("\n") else "\n\n"
    return body + separator + block + "\n"


def normalize_legacy_pr_metadata(body: str, *, remote: str) -> LegacyMetadataEvidence:
    """Normalize one v1/v2 PR block without changing the supplied body."""

    matches = list(_BLOCK_RE.finditer(body))
    if not matches:
        if "carve-changesets:metadata" in body:
            raise MetadataError(
                "Malformed carve-changesets PR metadata block; restore the v1/v2 delimiters."
            )
        raise MetadataError("PR body is missing the carve-changesets metadata block.")
    if len(matches) > 1:
        raise MetadataError("PR body contains multiple changeset metadata blocks.")
    try:
        payload = json.loads(matches[0].group("payload"))
    except json.JSONDecodeError as exc:
        raise MetadataError(
            f"PR metadata block contains invalid JSON: {exc.msg}."
        ) from exc
    if not isinstance(payload, dict):
        raise MetadataError("PR metadata block must contain a JSON object.")
    marker = matches[0].group("marker")
    version = 2 if marker == METADATA_MARKER_V2 else 1
    expected = {"slug", "index", "source_branch", "source_sha"}
    if version == 2:
        expected |= {"source_lineage", "recovery_from_head"}
    missing = sorted(expected - payload.keys())
    extra = sorted(payload.keys() - expected)
    if missing:
        raise MetadataError("PR metadata is missing field(s): " + ", ".join(missing))
    if extra:
        raise MetadataError("PR metadata has unknown field(s): " + ", ".join(extra))
    if not isinstance(payload["slug"], str):
        raise MetadataError("PR metadata field 'slug' must be a string.")
    if not isinstance(payload["index"], int) or isinstance(payload["index"], bool):
        raise MetadataError("PR metadata field 'index' must be an integer.")
    if not isinstance(payload["source_branch"], str):
        raise MetadataError("PR metadata field 'source_branch' must be a string.")
    if not isinstance(payload["source_sha"], str):
        raise MetadataError("PR metadata field 'source_sha' must be a string.")
    lineage = (SourceIdentity(remote, payload["source_branch"], payload["source_sha"]),)
    recovery_from: str | None = None
    if version == 2:
        lineage = _parse_lineage(
            payload["source_lineage"], context="PR metadata", remote=remote
        )
        if not isinstance(payload["recovery_from_head"], str):
            raise MetadataError(
                "PR metadata field 'recovery_from_head' must be a string."
            )
        recovery_from = payload["recovery_from_head"]
    metadata = ChangesetMetadata(
        slug=payload["slug"],
        index=payload["index"],
        source_branch=payload["source_branch"],
        source_sha=payload["source_sha"],
        source_lineage=lineage,
        recovery_from_head=recovery_from,
        marker_version=version,
    )
    return LegacyMetadataEvidence(
        metadata=metadata,
        legacy_position=metadata.index,
        marker_version=version,
        original=body,
    )


def parse_pr_metadata(body: str, *, remote: str = "origin") -> ChangesetMetadata:
    """Return normalized legacy PR evidence for compatibility consumers."""

    return normalize_legacy_pr_metadata(body, remote=remote).metadata
