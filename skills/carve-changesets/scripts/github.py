#!/usr/bin/env python3
"""Single structured chokepoint for every carve-changesets ``gh`` call."""

from __future__ import annotations

import json
import re
import subprocess
from typing import Dict, Iterable, List, Sequence
from urllib.parse import urlparse

from common import (
    CommandError,
    base_for_changeset,
    branch_name_for,
    ensure_clean_tree,
    ensure_git_repo,
    git,
    message_file,
)
from metadata import (
    ChangesetMetadata,
    MetadataError,
    embed_pr_metadata,
    parse_commit_message,
    parse_pr_metadata,
)
from publication import verify_lineage_for_publication
from rehydrate import PullRequestRecord

_PR_JSON_FIELDS = (
    "number,headRefName,headRefOid,baseRefName,state,body,title,mergeCommit,"
    "isCrossRepository"
)


def _format_error(command: Sequence[str], error: subprocess.CalledProcessError) -> str:
    stdout = (error.stdout or "").strip()
    stderr = (error.stderr or "").strip()
    details = [f"GitHub CLI command failed: {' '.join(command)}"]
    if stdout:
        details.append(f"stdout: {stdout}")
    if stderr:
        details.append(f"stderr: {stderr}")
    return "\n".join(details)


def gh_capture(
    args: Sequence[str], *, allowed_returncodes: Iterable[int] = ()
) -> tuple[str, str]:
    """Run ``gh`` with list argv and return captured stdout and stderr."""

    command = ["gh", *args]
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise CommandError("GitHub CLI ('gh') not found on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        if exc.returncode in set(allowed_returncodes):
            return exc.stdout or "", exc.stderr or ""
        raise CommandError(_format_error(command, exc)) from exc
    return result.stdout, result.stderr or ""


def gh_json(args: Sequence[str], *, allowed_returncodes: Iterable[int] = ()) -> object:
    """Run ``gh`` and decode one JSON response."""

    stdout, _ = gh_capture(args, allowed_returncodes=allowed_returncodes)
    if not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise CommandError(
            f"Failed to parse JSON from GitHub CLI command: {' '.join(args)}"
        ) from exc


def github_repo_for_remote(remote: str) -> str:
    """Resolve one selected git remote to an exact gh HOST/OWNER/REPO target."""

    remotes = git("remote").stdout.splitlines()
    if remote not in remotes:
        raise CommandError(f"Git remote {remote!r} does not exist.")
    configured = git("config", "--get-all", f"remote.{remote}.url").stdout.splitlines()
    urls = [url.strip() for url in configured if url.strip()]
    if len(urls) != 1:
        raise CommandError(
            f"Git remote {remote!r} must have exactly one fetch URL; found {len(urls)}."
        )
    raw_url = urls[0]
    host = ""
    path = ""
    if "://" in raw_url:
        parsed = urlparse(raw_url)
        host = parsed.hostname or ""
        path = parsed.path
    else:
        scp_match = re.fullmatch(r"(?:[^@/]+@)?([^:/]+):(.+)", raw_url)
        if scp_match is not None:
            host, path = scp_match.groups()
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) != 2 or not host:
        raise CommandError(
            f"Git remote {remote!r} URL is not an exact GitHub repository: {raw_url}"
        )
    owner, repo = parts
    repo = repo.removesuffix(".git")
    if not owner or not repo:
        raise CommandError(
            f"Git remote {remote!r} URL is not an exact GitHub repository: {raw_url}"
        )
    return f"{host.lower()}/{owner}/{repo}"


def ensure_gh_ready(repository: str) -> None:
    host = repository.split("/", 1)[0]
    gh_capture(("auth", "status", "--hostname", host))


def pr_title_for(feature_title: str, index: int, total: int) -> str:
    return f"{feature_title} ({index} of {total})"


def pr_body_for(plan: Dict, index: int, total: int, changeset: Dict) -> str:
    notes = changeset.get("pr_notes", []) or []
    lines = [
        "## Overall Feature",
        plan["feature_title"].strip(),
        "",
        f"## This Changeset ({index} of {total})",
        str(changeset.get("description", "")).strip()
        or "Describe the intent of this changeset.",
        "",
        "## Scaffolding, Flags, And Intentional Incompleteness",
    ]
    if notes and all(isinstance(note, str) and note.strip() for note in notes):
        lines.extend(f"- {note.strip()}" for note in notes)
    else:
        lines.append("- None documented.")
    branch = branch_name_for(plan["source_branch"], index)
    message = git("show", "-s", "--format=%B", branch).stdout
    return embed_pr_metadata(
        "\n".join(lines).strip() + "\n", parse_commit_message(message)
    )


def _print_command(command: Sequence[str]) -> None:
    print(" ".join(subprocess.list2cmdline([part]) for part in command))


def _local_remote_head(branch: str, remote: str) -> str:
    local_result = git(
        "rev-parse", "--verify", f"refs/heads/{branch}^{{commit}}", check=False
    )
    if local_result.returncode != 0:
        raise CommandError(f"Local changeset branch {branch!r} does not exist.")
    local_head = local_result.stdout.strip()
    remote_result = git(
        "ls-remote", "--heads", remote, f"refs/heads/{branch}", check=False
    )
    if remote_result.returncode != 0:
        detail = (remote_result.stderr or remote_result.stdout or "").strip()
        raise CommandError(
            f"Could not resolve {remote} changeset branch {branch!r}: {detail}"
        )
    fields = remote_result.stdout.strip().split()
    if len(fields) != 2 or fields[1] != f"refs/heads/{branch}":
        raise CommandError(
            f"Remote changeset branch {remote}/{branch} does not exist; run push-chain first."
        )
    remote_head = fields[0]
    if local_head != remote_head:
        raise CommandError(
            f"Changeset branch {branch} is not publication-ready: local head "
            f"{local_head} differs from {remote} head {remote_head}."
        )
    return local_head


def _verify_created_pr(
    created: object,
    *,
    head: str,
    expected_head: str,
    expected_base: str,
    expected_metadata: ChangesetMetadata,
) -> Dict:
    if not isinstance(created, dict):
        raise CommandError(f"PR for {head} was created but could not be verified.")
    if str(created.get("headRefOid") or "") != expected_head:
        raise CommandError(
            f"Created PR for {head} has head {created.get('headRefOid')}; "
            f"expected {expected_head}."
        )
    if str(created.get("baseRefName") or "") != expected_base:
        raise CommandError(
            f"Created PR for {head} has base {created.get('baseRefName')!r}; "
            f"expected {expected_base!r}."
        )
    if expected_metadata.version in {1, 2}:
        try:
            actual_metadata = parse_pr_metadata(str(created.get("body") or ""))
        except MetadataError as exc:
            raise CommandError(
                f"Created PR for {head} has invalid changeset metadata: {exc}"
            ) from exc
        if actual_metadata != expected_metadata:
            raise CommandError(
                f"Created PR for {head} metadata does not match its exact changeset commit."
            )
    if not created.get("number") or not created.get("url"):
        raise CommandError(f"Created PR for {head} is missing its number or URL.")
    return created


def pr_create(
    plan: Dict, *, indices: List[int], dry_run: bool, remote: str = "origin"
) -> None:
    ensure_git_repo()
    ensure_clean_tree()
    repository = github_repo_for_remote(remote)

    base = plan["base_branch"]
    source = plan["source_branch"]
    changesets = plan["changesets"]
    total = len(changesets)
    for index in indices:
        if index < 1 or index > total:
            raise CommandError(f"--index must be between 1 and {total}.")
    expected_heads = (
        {
            branch_name_for(source, index): _local_remote_head(
                branch_name_for(source, index), remote
            )
            for index in indices
        }
        if not dry_run
        else {}
    )
    if not dry_run:
        verify_lineage_for_publication(tuple(expected_heads), remote=remote)
        ensure_gh_ready(repository)
    for index in indices:
        head = branch_name_for(source, index)
        pr_base = base_for_changeset(base, source, index)
        title = pr_title_for(plan["feature_title"], index, total)
        body = pr_body_for(plan, index, total, changesets[index - 1])
        expected_metadata = parse_commit_message(
            git("show", "-s", "--format=%B", head).stdout
        )
        with message_file(body) as body_path:
            args = (
                "pr",
                "create",
                "-R",
                repository,
                "--base",
                pr_base,
                "--head",
                head,
                "--title",
                title,
                "--body-file",
                body_path,
            )
            print(f"[STEP] PR for changeset {index}: {head} -> {pr_base}")
            if dry_run:
                print("[DRY-RUN] Would run:")
                _print_command(("gh", *args))
                continue
            expected_head = expected_heads[head]
            gh_capture(args)
        created = _verify_created_pr(
            gh_json(
                (
                    "pr",
                    "view",
                    head,
                    "-R",
                    repository,
                    "--json",
                    "number,url,headRefOid,baseRefName,body",
                )
            ),
            head=head,
            expected_head=expected_head,
            expected_base=pr_base,
            expected_metadata=expected_metadata,
        )
        print(f"[OK] PR #{created['number']} created: {created['url']}")

    if dry_run:
        print("[OK] Dry-run complete. Re-run with --no-dry-run to execute.")


def pull_requests_for_source(
    source_branch: str, *, remote: str = "origin"
) -> list[PullRequestRecord]:
    """Return complete GitHub PR evidence needed by live rehydration."""

    repository = github_repo_for_remote(remote)
    payload = gh_json(
        (
            "pr",
            "list",
            "-R",
            repository,
            "--state",
            "all",
            "--limit",
            "100",
            "--json",
            _PR_JSON_FIELDS,
        )
    )
    if not isinstance(payload, list):
        raise CommandError("Unexpected GitHub PR list response.")
    prefix = f"{source_branch}-"
    records: list[PullRequestRecord] = []
    for item in payload:
        if not isinstance(item, dict):
            raise CommandError("Unexpected GitHub PR record.")
        head = str(item.get("headRefName") or "")
        suffix = head.removeprefix(prefix)
        if not head.startswith(prefix) or not suffix.isdigit() or int(suffix) < 1:
            continue
        records.append(_pull_request_record(item, context=f"changeset PR for {head}"))
    return records


def _merge_sha(item: Dict) -> str | None:
    value = item.get("mergeCommit")
    if not isinstance(value, dict):
        return None
    oid = str(value.get("oid") or "").strip()
    return oid or None


def _pull_request_record(item: object, *, context: str) -> PullRequestRecord:
    """Decode one selected gh PR payload with operation-specific errors."""

    if not isinstance(item, dict):
        raise CommandError(f"Unexpected GitHub response for {context}.")
    try:
        number = int(item["number"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CommandError(
            f"GitHub response for {context} has no valid PR number."
        ) from exc
    return PullRequestRecord(
        number=number,
        head_branch=str(item.get("headRefName") or ""),
        head_sha=str(item.get("headRefOid") or ""),
        base_branch=str(item.get("baseRefName") or ""),
        state=str(item.get("state") or ""),
        body=str(item.get("body") or ""),
        title=str(item.get("title") or ""),
        merge_sha=_merge_sha(item),
        is_cross_repository=bool(item.get("isCrossRepository", False)),
    )


def pull_request_by_number(number: int, *, remote: str = "origin") -> PullRequestRecord:
    """Read one exact PR using the same fields as chain discovery."""

    repository = github_repo_for_remote(remote)
    item = gh_json(
        (
            "pr",
            "view",
            str(number),
            "-R",
            repository,
            "--json",
            _PR_JSON_FIELDS,
        )
    )
    record = _pull_request_record(item, context=f"PR #{number}")
    actual_number = record.number
    if actual_number != number:
        raise CommandError(
            f"GitHub returned PR #{actual_number} while verifying requested PR #{number}."
        )
    return record


def merge_pull_request(
    number: int,
    *,
    expected_head: str,
    method: str,
    remote: str = "origin",
    dry_run: bool,
) -> None:
    """Merge one explicitly numbered PR in the selected remote repository."""

    method_flags = {"merge": "--merge", "squash": "--squash", "rebase": "--rebase"}
    if method not in method_flags:
        raise CommandError("Merge method must be 'merge', 'squash', or 'rebase'.")
    repository = github_repo_for_remote(remote)
    args = (
        "pr",
        "merge",
        str(number),
        "-R",
        repository,
        method_flags[method],
        "--match-head-commit",
        expected_head,
    )
    print(f"[STEP] Merging PR #{number} with method={method}")
    if dry_run:
        print("[DRY-RUN] Would run:")
        _print_command(("gh", *args))
        return
    ensure_gh_ready(repository)
    gh_capture(args)


def edit_pull_request(
    number: int,
    *,
    remote: str = "origin",
    base: str | None = None,
    title: str | None = None,
    body: str | None = None,
    dry_run: bool,
) -> None:
    """Edit one explicit PR; never infer a target from the checked-out branch."""

    if base is None and title is None and body is None:
        return
    repository = github_repo_for_remote(remote)

    def execute(body_path: str | None = None) -> None:
        args: list[str] = ["pr", "edit", str(number), "-R", repository]
        if base is not None:
            args.extend(("--base", base))
        if title is not None:
            args.extend(("--title", title))
        if body_path is not None:
            args.extend(("--body-file", body_path))
        print(f"[STEP] Updating PR #{number}")
        if dry_run:
            print("[DRY-RUN] Would run:")
            _print_command(("gh", *args))
            return
        ensure_gh_ready(repository)
        gh_capture(tuple(args))

    if body is None:
        execute()
        return
    with message_file(body) as body_path:
        execute(body_path)
