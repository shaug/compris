"""Render live changeset chain status without local recordkeeping files."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from rehydrate import Chain, PullRequestRecord, adopt_legacy_chain


def render_status(chain: Chain) -> str:
    """Render branches, heads, PRs, bases, and merge state as a compact table."""

    rows = [("INDEX", "SLUG", "BRANCH", "HEAD", "PR", "BASE", "STATE")]
    for changeset in chain.changesets:
        pr = f"#{changeset.pr_number}" if changeset.pr_number is not None else "-"
        state = changeset.pr_state or "MATERIALIZED"
        rows.append(
            (
                str(changeset.position),
                changeset.metadata.slug,
                changeset.branch,
                changeset.head[:12],
                pr,
                changeset.base,
                state,
            )
        )
    widths = [max(len(row[column]) for row in rows) for column in range(len(rows[0]))]
    table = "\n".join(
        "  ".join(
            value.ljust(widths[column]) for column, value in enumerate(row)
        ).rstrip()
        for row in rows
    )
    lineage = " -> ".join(identity.trailer for identity in chain.source_lineage)
    return f"SOURCE LINEAGE  {lineage}\n{table}"


def status_from_live(
    *,
    source_branch: str,
    pull_requests: Sequence[PullRequestRecord] = (),
    base_branch: str | None = None,
    cwd: Path | str = Path.cwd(),
    remote: str = "origin",
) -> str:
    """Rehydrate and render status using only supplied GitHub records and git refs."""

    return render_status(
        adopt_legacy_chain(
            source_branch=source_branch,
            pull_requests=pull_requests,
            base_branch=base_branch,
            cwd=cwd,
            remote=remote,
        )
    )
