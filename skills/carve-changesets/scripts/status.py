"""Render live changeset chain status without local recordkeeping files."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Sequence

from gh_stack import GhStackClient, ProfileProbeResult, StackCapability, probe_profile
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
    pull_request_loader: Callable[[int], PullRequestRecord] | None = None,
    base_branch: str | None = None,
    cwd: Path | str = Path.cwd(),
    remote: str = "origin",
    read_remote: bool = True,
    allow_stack_state_refresh: bool = False,
    stack_client: GhStackClient | None = None,
    profile_probe: Callable[[], ProfileProbeResult] | None = None,
) -> str:
    """Render native truth when refresh is authorized, otherwise passive evidence."""

    repo = Path(cwd)
    if not allow_stack_state_refresh:
        return _render_passive_evidence(
            source_branch=source_branch,
            pull_requests=pull_requests,
            cwd=repo,
            remote=remote,
            read_remote=read_remote,
        )
    if not read_remote:
        raise RehydrationError(
            "--local-only and stack-state refresh are mutually exclusive; "
            "native reconciliation requires live remote and GitHub evidence."
        )

    observed_profile = (
        profile_probe() if profile_probe is not None else probe_profile(cwd=repo)
    )
    if (
        observed_profile.status != "supported"
        or observed_profile.profile is None
        or StackCapability.VIEW_JSON not in observed_profile.profile.capabilities
    ):
        reason = (
            observed_profile.blocker.reason
            if observed_profile.blocker is not None
            else "view_json_capability_unavailable"
        )
        raise RehydrationError(f"Native stack profile blocks state refresh: {reason}.")

    client = stack_client or GhStackClient(cwd=repo)
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
    trunk_heads = _live_remote_heads(repo, remote, (trunk,))
    trunk_head = trunk_heads.get(trunk)
    if trunk_head is None:
        raise RehydrationError(
            f"Selected remote {remote!r} has no live trunk branch {trunk!r}."
        )
    snapshot = parse_native_stack(payload, trunk_head=trunk_head)
    remote_branches = tuple(layer.branch for layer in snapshot.open_suffix)
    local_branches = tuple(layer.branch for layer in snapshot.layers)
    remote_heads = _live_remote_heads(repo, remote, remote_branches)
    local_heads = _local_heads(repo, local_branches)
    effective_pull_requests = list(pull_requests)
    if pull_request_loader is not None:
        effective_pull_requests = [
            pull_request_loader(layer.pull_request.number)
            for layer in snapshot.layers
            if layer.pull_request is not None
        ]
    pull_requests_by_number = {pr.number: pr for pr in effective_pull_requests}
    if len(pull_requests_by_number) != len(effective_pull_requests):
        raise RehydrationError(
            "GitHub evidence contains duplicate pull-request numbers."
        )
    reconciled = reconcile_native_stack(
        snapshot,
        remote_heads=remote_heads,
        pull_requests=pull_requests_by_number,
        local_heads=local_heads,
    )
    chain = rehydrate_chain(
        source_branch=source_branch,
        native_snapshot=reconciled,
        pull_requests=effective_pull_requests,
        base_branch=base_branch,
        cwd=repo,
    )
    return (
        "NATIVE LOCAL TOPOLOGY  available (refreshed with authority)\n"
        + render_status(chain)
    )


def _live_remote_heads(
    cwd: Path, remote: str, branches: Sequence[str]
) -> dict[str, str]:
    if not branches:
        return {}
    refs = tuple(f"refs/heads/{branch}" for branch in branches)
    output = _git(cwd, "ls-remote", "--refs", remote, *refs)
    requested = set(branches)
    heads: dict[str, str] = {}
    for line in output.splitlines():
        head, separator, ref = line.partition("\t")
        if not separator or not ref.startswith("refs/heads/"):
            continue
        branch = ref.removeprefix("refs/heads/")
        if branch in requested:
            heads[branch] = head
    return heads


def _local_heads(cwd: Path, branches: Sequence[str]) -> dict[str, str]:
    if not branches:
        return {}
    refs = tuple(f"refs/heads/{branch}" for branch in branches)
    output = _git(cwd, "for-each-ref", "--format=%(refname)%00%(objectname)", *refs)
    heads: dict[str, str] = {}
    for line in output.splitlines():
        ref, separator, head = line.partition("\0")
        if separator and ref.startswith("refs/heads/"):
            heads[ref.removeprefix("refs/heads/")] = head
    return heads


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
    read_remote: bool,
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
    branches = sorted(set(refs) | set(prs))
    live_remote_heads = (
        _live_remote_heads(cwd, remote, tuple(branches)) if read_remote else {}
    )
    for branch in branches:
        heads = refs.setdefault(branch, {})
        live_head = live_remote_heads.get(branch)
        if live_head is None:
            heads.pop("remote", None)
        else:
            heads["remote"] = live_head
    rows = [("BRANCH", "LOCAL HEAD", "REMOTE HEAD", "PR", "PR HEAD", "BASE", "STATE")]
    for branch in branches:
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
