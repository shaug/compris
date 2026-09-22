"""Render live changeset chain status without local recordkeeping files."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from gh_stack import GhStackClient
from native_stack import parse_native_stack, reconcile_native_stack
from rehydrate import Chain, PullRequestRecord, RehydrationError, _git, rehydrate_chain


def render_status(chain: Chain) -> str:
    """Render branches, heads, PRs, bases, and merge state as a compact table."""

    rows = [("INDEX", "SLUG", "BRANCH", "HEAD", "PR", "BASE", "STATE")]
    for changeset in chain.changesets:
        pr = f"#{changeset.pr_number}" if changeset.pr_number is not None else "-"
        state = changeset.pr_state or "MATERIALIZED"
        rows.append(
            (
                str(changeset.metadata.index),
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
    allow_stack_state_refresh: bool = False,
    stack_client: GhStackClient | None = None,
) -> str:
    """Render native truth when refresh is authorized, otherwise passive evidence."""

    repo = Path(cwd)
    if not allow_stack_state_refresh:
        return _render_passive_evidence(
            source_branch=source_branch,
            pull_requests=pull_requests,
            cwd=repo,
            remote=remote,
        )

    client = stack_client or GhStackClient()
    before = _checkout_identity(repo)
    try:
        payload = client.view_json(allow_state_refresh=True)
    finally:
        after = _checkout_identity(repo)
        if after != before:
            raise RehydrationError(
                "gh stack view --json moved the checkout: "
                f"before {before[0]}@{before[1]}; after {after[0]}@{after[1]}."
            )
    trunk = payload.get("trunk")
    if not isinstance(trunk, str) or not trunk:
        raise RehydrationError("Native stack view has no trunk branch.")
    trunk_head = _git(repo, "rev-parse", f"refs/remotes/{remote}/{trunk}").strip()
    snapshot = parse_native_stack(payload, trunk_head=trunk_head)
    remote_heads = {
        layer.branch: _git(
            repo, "rev-parse", f"refs/remotes/{remote}/{layer.branch}"
        ).strip()
        for layer in snapshot.open_suffix
    }
    pull_requests_by_number = {pr.number: pr for pr in pull_requests}
    if len(pull_requests_by_number) != len(pull_requests):
        raise RehydrationError(
            "GitHub evidence contains duplicate pull-request numbers."
        )
    reconciled = reconcile_native_stack(
        snapshot,
        remote_heads=remote_heads,
        pull_requests=pull_requests_by_number,
    )
    chain = rehydrate_chain(
        source_branch=source_branch,
        native_snapshot=reconciled,
        pull_requests=pull_requests,
        cwd=repo,
    )
    return (
        "NATIVE LOCAL TOPOLOGY  available (refreshed with authority)\n"
        + render_status(chain)
    )


def _checkout_identity(cwd: Path) -> tuple[str, str]:
    branch = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD").strip()
    head = _git(cwd, "rev-parse", "HEAD").strip()
    return branch, head


def _render_passive_evidence(
    *,
    source_branch: str,
    pull_requests: Sequence[PullRequestRecord],
    cwd: Path,
    remote: str,
) -> str:
    ref_output = _git(
        cwd,
        "for-each-ref",
        "--format=%(refname)%00%(objectname)",
        "refs/heads",
        f"refs/remotes/{remote}",
    )
    prefix = f"{source_branch}-"
    refs: dict[str, dict[str, str]] = {}
    local_prefix = "refs/heads/"
    remote_prefix = f"refs/remotes/{remote}/"
    for line in ref_output.splitlines():
        ref, separator, head = line.partition("\0")
        if not separator:
            continue
        kind = "local"
        if ref.startswith(remote_prefix):
            branch = ref.removeprefix(remote_prefix)
            kind = "remote"
        elif ref.startswith(local_prefix):
            branch = ref.removeprefix(local_prefix)
        else:
            continue
        if branch.startswith(prefix):
            refs.setdefault(branch, {})[kind] = head

    prs = {pr.head_branch: pr for pr in pull_requests}
    rows = [("BRANCH", "LOCAL HEAD", "REMOTE HEAD", "PR", "PR HEAD", "BASE", "STATE")]
    for branch in sorted(set(refs) | set(prs)):
        pr = prs.get(branch)
        heads = refs.get(branch, {})
        rows.append(
            (
                branch,
                heads.get("local", "unavailable")[:12],
                heads.get("remote", "unavailable")[:12],
                f"#{pr.number}" if pr is not None else "-",
                pr.head_sha[:12] if pr is not None else "-",
                pr.base_branch if pr is not None else "-",
                pr.state.upper() if pr is not None else "-",
            )
        )
    widths = [max(len(row[column]) for row in rows) for column in range(len(rows[0]))]
    table = "\n".join(
        "  ".join(
            value.ljust(widths[column]) for column, value in enumerate(row)
        ).rstrip()
        for row in rows
    )
    return (
        "NATIVE LOCAL TOPOLOGY  unavailable (stack-state refresh not authorized)\n"
        "SIDE-EFFECT-FREE GIT/GITHUB EVIDENCE\n" + table
    )
