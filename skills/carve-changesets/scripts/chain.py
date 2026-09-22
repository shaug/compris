#!/usr/bin/env python3
"""Changeset chain creation, comparison, and validation."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from command_argv import display_argv, execute_argv, validate_argv
from common import (
    CommandError,
    branch_exists,
    branch_name_for,
    checkout_restore,
    commit_with_message,
    delete_branch,
    diff_name_status,
    diff_stat,
    ensure_branches_exist,
    ensure_clean_tree,
    ensure_git_repo,
    git,
    unique_temp_branch,
)
from metadata import ChangesetMetadata, SourceIdentity, stamp_commit_message
from patch_apply import (
    apply_patch_file,
    apply_patch_text,
    build_diff,
    parse_hunk_selectors,
    select_hunks_for_changeset,
)


@dataclass
class DiffEntry:
    status: str
    path: str
    old_path: Optional[str] = None


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in patterns)


def changed_files_between(base: str, source: str) -> List[DiffEntry]:
    raw = diff_name_status(base, source)
    entries: List[DiffEntry] = []
    if not raw:
        return entries

    for line in raw.splitlines():
        parts = line.split("\t")
        if not parts:
            continue
        status = parts[0]
        code = status[0]
        if code == "R" and len(parts) >= 3:
            entries.append(DiffEntry(status=code, path=parts[2], old_path=parts[1]))
        elif len(parts) >= 2:
            entries.append(DiffEntry(status=code, path=parts[1]))
    return entries


def select_entries(
    entries: Sequence[DiffEntry], include: Sequence[str], exclude: Sequence[str]
) -> List[DiffEntry]:
    if not include:
        return []

    selected = [
        e
        for e in entries
        if _matches_any(e.path, include)
        or (e.old_path and _matches_any(e.old_path, include))
    ]
    if not exclude:
        return selected

    filtered: List[DiffEntry] = []
    for e in selected:
        if _matches_any(e.path, exclude):
            continue
        if e.old_path and _matches_any(e.old_path, exclude):
            continue
        filtered.append(e)
    return filtered


@dataclass
class ApplySummary:
    mode: str
    message: str


def _commit_changeset(
    *,
    remote: str,
    source_branch: str,
    source_sha: str,
    index: int,
    changeset: Dict,
) -> None:
    commit_message = changeset.get("commit_message")
    slug = str(changeset.get("slug", f"cs-{index}")).strip() or f"cs-{index}"
    if not isinstance(commit_message, str) or not commit_message.strip():
        commit_message = f"changeset {index}: {slug}"
    stamped = stamp_commit_message(
        commit_message,
        ChangesetMetadata(
            slug=slug,
            source_lineage=(SourceIdentity(remote, source_branch, source_sha),),
        ),
    )
    commit_with_message(stamped)


def _apply_changeset_paths(
    *,
    remote: str,
    base_branch: str,
    source_branch: str,
    source_sha: str,
    index: int,
    changeset: Dict,
) -> ApplySummary:
    include = changeset.get("include_paths", [])
    exclude = changeset.get("exclude_paths", [])

    diff_entries = changed_files_between(base_branch, source_branch)
    selected = select_entries(diff_entries, include, exclude)

    if not selected:
        print(f"[WARN] Changeset {index}: no files matched include/exclude rules.")
        return ApplySummary(mode="paths", message="no paths matched")

    checkout_paths: List[str] = []
    delete_paths: List[str] = []

    for entry in selected:
        if entry.status == "D":
            delete_paths.append(entry.path)
            continue
        if (
            entry.old_path
            and entry.old_path != entry.path
            and entry.old_path not in delete_paths
        ):
            delete_paths.append(entry.old_path)
        checkout_paths.append(entry.path)

    for path in checkout_paths:
        git("checkout", source_branch, "--", path)

    for path in delete_paths:
        git("rm", "-f", "--ignore-unmatch", path)

    git("add", "-A")
    git("reset", "-q", "--", ".carve-changesets")

    diff_cached = git("diff", "--cached", "--quiet", check=False)
    if diff_cached.returncode == 0:
        print(f"[WARN] Changeset {index}: no staged changes after apply.")
        return ApplySummary(
            mode="paths",
            message=(
                f"{len(checkout_paths)} paths checked out, {len(delete_paths)} paths removed"
            ),
        )

    _commit_changeset(
        remote=remote,
        source_branch=source_branch,
        source_sha=source_sha,
        index=index,
        changeset=changeset,
    )
    return ApplySummary(
        mode="paths",
        message=(
            f"{len(checkout_paths)} paths checked out, {len(delete_paths)} paths removed"
        ),
    )


def _apply_changeset_patch(
    *,
    remote: str,
    source_branch: str,
    source_sha: str,
    index: int,
    changeset: Dict,
    label: str,
) -> ApplySummary:
    patch_file = changeset.get("patch_file")
    if not isinstance(patch_file, str) or not patch_file.strip():
        raise CommandError(f"{label}: patch_file must be a non-empty string.")
    apply_patch_file(patch_file, label=label)

    diff_cached = git("diff", "--cached", "--quiet", check=False)
    if diff_cached.returncode == 0:
        print(f"[WARN] Changeset {index}: no staged changes after apply.")
        return ApplySummary(
            mode="patch", message="patch applied with no staged changes"
        )

    _commit_changeset(
        remote=remote,
        source_branch=source_branch,
        source_sha=source_sha,
        index=index,
        changeset=changeset,
    )
    return ApplySummary(mode="patch", message="patch applied and committed")


def _apply_changeset_hunks(
    *,
    remote: str,
    base_branch: str,
    source_branch: str,
    source_sha: str,
    index: int,
    changeset: Dict,
    label: str,
) -> ApplySummary:
    selectors = changeset.get("hunk_selectors", [])
    include = changeset.get("include_paths", [])
    exclude = changeset.get("exclude_paths", [])
    allow_partial = changeset.get("allow_partial_files", True)

    parsed = parse_hunk_selectors(selectors, changeset_label=label)
    diff_files = build_diff(base_branch, source_branch)
    selected = select_hunks_for_changeset(
        diff_files,
        parsed,
        include_paths=include,
        exclude_paths=exclude,
        allow_partial_files=bool(allow_partial),
        changeset_label=label,
    )
    apply_patch_text(selected.text, label=label)

    diff_cached = git("diff", "--cached", "--quiet", check=False)
    if diff_cached.returncode == 0:
        print(f"[WARN] Changeset {index}: no staged changes after apply.")
        return ApplySummary(
            mode="hunks",
            message=f"{selected.hunks} hunks selected in {selected.files} files",
        )

    _commit_changeset(
        remote=remote,
        source_branch=source_branch,
        source_sha=source_sha,
        index=index,
        changeset=changeset,
    )
    return ApplySummary(
        mode="hunks",
        message=f"{selected.hunks} hunks selected in {selected.files} files",
    )


def apply_changeset(
    *,
    remote: str = "origin",
    base_branch: str,
    source_branch: str,
    source_sha: str,
    index: int,
    changeset: Dict,
) -> ApplySummary:
    mode = str(changeset.get("mode", "paths")).strip() or "paths"
    label = f"Changeset {index}"
    if mode == "paths":
        return _apply_changeset_paths(
            remote=remote,
            base_branch=base_branch,
            source_branch=source_branch,
            source_sha=source_sha,
            index=index,
            changeset=changeset,
        )
    if mode == "patch":
        return _apply_changeset_patch(
            remote=remote,
            source_branch=source_branch,
            source_sha=source_sha,
            index=index,
            changeset=changeset,
            label=label,
        )
    if mode == "hunks":
        return _apply_changeset_hunks(
            remote=remote,
            base_branch=base_branch,
            source_branch=source_branch,
            source_sha=source_sha,
            index=index,
            changeset=changeset,
            label=label,
        )
    raise CommandError(
        f"{label}: unsupported mode '{mode}'. Use 'paths', 'patch', or 'hunks'."
    )


def create_chain(plan: Dict, *, remote: str = "origin") -> List[str]:
    ensure_git_repo()
    ensure_clean_tree()

    base = plan["base_branch"]
    source = plan["source_branch"]
    changesets = plan["changesets"]
    total = len(changesets)

    chain = [branch_name_for(source, i) for i in range(1, total + 1)]
    ensure_branches_exist([base, source])
    source_sha = git("rev-parse", source).stdout.strip()

    existing_prefix = 0
    for idx, name in enumerate(chain, start=1):
        exists = branch_exists(name)
        if exists and idx == existing_prefix + 1:
            existing_prefix = idx
            continue
        if exists and idx > existing_prefix + 1:
            missing = branch_name_for(source, existing_prefix + 1)
            raise CommandError(
                f"Found existing branch {name} but missing earlier branch {missing}."
            )

    start_index = existing_prefix + 1
    if existing_prefix > 0:
        print(
            f"[INFO] Reusing existing changeset branches through index {existing_prefix}."
        )
        print(
            "[INFO] create-chain is append-only; delete a branch explicitly if it must be recreated."
        )

    with checkout_restore() as original:
        print(f"[INFO] Starting from current branch: {original}")
        prev_branch = base if existing_prefix == 0 else chain[existing_prefix - 1]
        for idx in range(start_index, total + 1):
            cs = changesets[idx - 1]
            name = chain[idx - 1]
            print(f"\n[STEP] Creating {name} from {prev_branch}")
            git("checkout", "-B", name, prev_branch)

            summary = apply_changeset(
                remote=remote,
                base_branch=base,
                source_branch=source,
                source_sha=source_sha,
                index=idx,
                changeset=cs,
            )
            print(f"[OK] Applied changeset {idx} ({summary.mode}): {summary.message}")
            prev_branch = name

    print("[OK] Changeset branch chain created.")
    return chain


def compare_chain(plan: Dict) -> Tuple[str, str]:
    ensure_git_repo()
    ensure_clean_tree()

    base = plan["base_branch"]
    source = plan["source_branch"]
    total = len(plan["changesets"])

    chain = [branch_name_for(source, i) for i in range(1, total + 1)]
    ensure_branches_exist([base, source, *chain])

    temp_branch = unique_temp_branch("pcs-temp-compare")
    print(f"[INFO] Creating temporary comparison branch: {temp_branch}")

    with checkout_restore() as original:
        try:
            git("checkout", "-B", temp_branch, base)
            for name in chain:
                print(f"[STEP] Merging {name} into {temp_branch}")
                git("merge", "--no-ff", "--no-edit", name)

            diffstat = diff_stat(temp_branch, source)
            namestatus = diff_name_status(temp_branch, source)
        finally:
            git("checkout", original)
            delete_branch(temp_branch)
            print(f"\n[INFO] Restored original branch: {original}")

    return diffstat, namestatus


def validate_chain(plan: Dict, *, test_argv: object) -> None:
    """Merge changesets in order into a temp branch and run tests after each merge."""
    if isinstance(test_argv, list) and not test_argv:
        raise CommandError(
            "validate-chain requires an explicitly approved --test-argv or "
            "plan.test_argv."
        )
    effective_test_argv = validate_argv(test_argv, label="approved test argv")

    ensure_git_repo()
    ensure_clean_tree()

    base = plan["base_branch"]
    source = plan["source_branch"]
    total = len(plan["changesets"])
    chain = [branch_name_for(source, i) for i in range(1, total + 1)]
    ensure_branches_exist([base, source, *chain])

    temp_branch = unique_temp_branch("pcs-temp-validate")
    print(f"[INFO] Creating temporary validation branch: {temp_branch}")

    with checkout_restore() as original:
        try:
            git("checkout", "-B", temp_branch, base)
            for idx, name in enumerate(chain, start=1):
                print(f"\n[STEP] Merging {name} ({idx} of {total})")
                git("merge", "--no-ff", "--no-edit", name)
                print(
                    f"[STEP] Running tests after changeset {idx}: "
                    f"{display_argv(effective_test_argv)}"
                )
                if git("diff", "--quiet", check=False).returncode != 0:
                    raise CommandError(
                        "Working tree became dirty during validate-chain."
                    )
                result = execute_argv(effective_test_argv)
                if result.returncode != 0:
                    raise CommandError(f"Test command failed after changeset {idx}.")
        finally:
            git("checkout", original)
            delete_branch(temp_branch)
            print(f"\n[INFO] Restored original branch: {original}")

    print("[OK] validate-chain completed successfully.")
