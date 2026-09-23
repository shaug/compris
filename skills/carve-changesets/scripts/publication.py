"""Read-only provenance checks shared by remote publication boundaries."""

from __future__ import annotations

from collections.abc import Sequence

from common import CommandError, git
from metadata import MetadataError, SourceIdentity, parse_commit_message


def _remote_identity_head(identity: SourceIdentity) -> str:
    result = git(
        "ls-remote",
        "--heads",
        identity.remote,
        f"refs/heads/{identity.branch}",
        check=False,
    )
    if result.returncode != 0:
        raise CommandError(
            f"Unable to resolve recorded source {identity.remote}/{identity.branch}."
        )
    line = result.stdout.strip()
    if not line:
        raise CommandError(
            f"Recorded source {identity.remote}/{identity.branch} is unavailable."
        )
    return line.split()[0]


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
    for identity in expected_lineage:
        if identity.remote != remote:
            raise CommandError(
                f"Recorded source {identity.branch!r} records remote "
                f"{identity.remote!r}, not selected remote {remote!r}."
            )
        published = _remote_identity_head(identity)
        if published != identity.sha:
            raise CommandError(
                f"Recorded source {remote}/{identity.branch} moved from "
                f"{identity.sha} to {published}."
            )
