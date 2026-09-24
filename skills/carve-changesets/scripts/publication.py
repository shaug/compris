"""Read-only provenance checks shared by remote publication boundaries."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from common import CommandError, git
from metadata import MetadataError, SourceIdentity, parse_commit_message


def remote_branch_head(
    remote: str, branch: str, *, cwd: Path | str | None = None
) -> str | None:
    """Resolve one exact remote branch head, or None when it is absent."""

    expected_ref = f"refs/heads/{branch}"
    location = () if cwd is None else ("-C", str(cwd))
    result = git(
        *location,
        "ls-remote",
        "--heads",
        remote,
        expected_ref,
        check=False,
    )
    if result.returncode != 0:
        raise CommandError(f"Unable to resolve exact remote branch {remote}/{branch}.")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return None
    if len(lines) != 1:
        raise CommandError(
            f"Recorded source {remote}/{branch} did not resolve to one exact "
            "branch ref."
        )
    fields = lines[0].split()
    if (
        len(fields) != 2
        or fields[1] != expected_ref
        or re.fullmatch(r"[0-9a-f]{40}", fields[0]) is None
    ):
        raise CommandError(
            f"Recorded source {remote}/{branch} did not resolve to one exact "
            "branch ref."
        )
    return fields[0]


def remote_identity_head(
    identity: SourceIdentity, *, cwd: Path | str | None = None
) -> str:
    head = remote_branch_head(identity.remote, identity.branch, cwd=cwd)
    if head is None:
        raise CommandError(
            f"Recorded source {identity.remote}/{identity.branch} is unavailable."
        )
    return head


def verify_remote_lineage(lineage: Sequence[SourceIdentity], *, remote: str) -> None:
    """Prove an established lineage still resolves at every recorded head."""

    if not lineage:
        raise CommandError("No source lineage was selected for publication.")
    for identity in lineage:
        if identity.remote != remote:
            raise CommandError(
                f"Recorded source {identity.branch!r} records remote "
                f"{identity.remote!r}, not selected remote {remote!r}."
            )
        published = remote_identity_head(identity)
        if published != identity.sha:
            raise CommandError(
                f"Recorded source {remote}/{identity.branch} moved from "
                f"{identity.sha} to {published}."
            )


def verify_lineage_for_publication(heads: Sequence[str], *, remote: str) -> None:
    """Prove selected heads share remotely reconstructible source lineage."""

    expected_lineage: tuple[SourceIdentity, ...] | None = None
    for head in heads:
        message = git("show", "-s", "--format=%B", head).stdout
        try:
            metadata = parse_commit_message(message, remote=remote)
        except MetadataError as exc:
            raise CommandError(
                f"Changeset branch {head} has invalid source identity: {exc}"
            ) from exc
        if expected_lineage is None:
            expected_lineage = metadata.source_lineage
        elif metadata.source_lineage != expected_lineage:
            raise CommandError(
                "Selected changeset branches do not carry one consistent source lineage."
            )

    if expected_lineage is None:
        raise CommandError("No changeset branches were selected for publication.")
    verify_remote_lineage(expected_lineage, remote=remote)
