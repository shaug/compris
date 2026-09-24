"""Read-only provenance checks shared by remote publication boundaries."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from common import CommandError, git
from metadata import MetadataError, SourceIdentity, parse_commit_message


def remote_identity_head(
    identity: SourceIdentity, *, cwd: Path | str | None = None
) -> str:
    expected_ref = f"refs/heads/{identity.branch}"
    location = () if cwd is None else ("-C", str(cwd))
    result = git(
        *location,
        "ls-remote",
        "--heads",
        identity.remote,
        expected_ref,
        check=False,
    )
    if result.returncode != 0:
        raise CommandError(
            f"Unable to resolve recorded source {identity.remote}/{identity.branch}."
        )
    lines = result.stdout.splitlines()
    if not lines:
        raise CommandError(
            f"Recorded source {identity.remote}/{identity.branch} is unavailable."
        )
    matches: list[str] = []
    for line in lines:
        fields = line.split("\t")
        if len(fields) != 2 or fields[1] != expected_ref:
            raise CommandError(
                f"Recorded source {identity.remote}/{identity.branch} did not "
                "resolve to one exact branch ref."
            )
        matches.append(fields[0])
    if len(matches) != 1:
        raise CommandError(
            f"Recorded source {identity.remote}/{identity.branch} did not "
            "resolve to one exact branch ref."
        )
    return matches[0]


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
        if len(metadata.source_lineage) > 1:
            raise CommandError(
                "Successor source lineage must be published through recover-suffix "
                "so its existing pull request and exact recovery provenance are "
                "preserved."
            )
        if expected_lineage is None:
            expected_lineage = metadata.source_lineage
        elif metadata.source_lineage != expected_lineage:
            raise CommandError(
                "Selected changeset branches do not carry one consistent source lineage."
            )

    if expected_lineage is None:
        raise CommandError("No changeset branches were selected for publication.")
    for identity in expected_lineage:
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
