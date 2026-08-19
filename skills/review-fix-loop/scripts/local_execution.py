#!/usr/bin/env python3
"""Local execution substrate for `review-fix-loop`.

Implements the parts of `design/review-fix-loop.md`'s "Local ownership and
checkpointing" section that issue #97 owns: common-git-common-directory
locking, isolated (git-worktree-based) remediation attempts, durable
checkpoint persistence and resume reconciliation, verified fast-forward-only
canonical promotion, and recovery of an interrupted attempt. It deliberately
does not run a reviewer, select a fix, or publish to a remote (issues #98,
#99, and #100).

This module has no third-party dependencies, matching the convention used by
`scripts/validate.py` (the #96 contract leaf) and by the repository's
review-suite validator: a skill folder is the unit of distribution. It loads
`validate.py` from this same directory via `importlib` rather than
duplicating any of its schema or cross-field checks, per this ticket's
dependency to "build on top of it; do not duplicate or rewrite the existing
contract/validation code."

## Where local state lives

Every invocation-scoped file this module writes — locks, durable checkpoints,
and preserved failed-attempt artifacts — lives under
`<git-common-directory>/review-fix-loop/`. The common directory (typically
`.git`, or a linked worktree's pointer target) is shared by every worktree of
one repository and is never tracked by Git itself, so this satisfies the
design's "skill-local ignored directory" requirement without depending on any
one worktree's lifetime or `.gitignore` entries. Isolated attempt worktrees
default to `<git-common-directory>/review-fix-loop/attempts/`, but callers may
pass any `attempts_root`.
"""

from __future__ import annotations

import contextlib
import dataclasses
import errno
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterator, Sequence

HERE = Path(__file__).resolve().parent

_VALIDATE_SPEC = importlib.util.spec_from_file_location(
    "review_fix_loop_validate", HERE / "validate.py"
)
assert _VALIDATE_SPEC and _VALIDATE_SPEC.loader
validate = importlib.util.module_from_spec(_VALIDATE_SPEC)
_VALIDATE_SPEC.loader.exec_module(validate)

ROOT_NAMESPACE = "review-fix-loop"
LOCK_SUBDIR = "locks"
CHECKPOINT_SUBDIR = "checkpoints"
PRESERVED_ATTEMPTS_SUBDIR = "preserved-attempts"
ATTEMPTS_SUBDIR = "attempts"

ATTEMPT_BRANCH_PREFIX = "review-fix-loop/attempt/"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LocalExecutionError(RuntimeError):
    """Base class for every local-execution failure in this module."""


class CommandError(LocalExecutionError):
    """A git or subprocess command failed."""


class CandidateBusyError(LocalExecutionError):
    """Another process already holds a required local-ref or remote-target lock."""


class CandidateIntegrityFailureError(LocalExecutionError):
    """Live Git state cannot be uniquely reconciled with recorded state."""


class CheckpointMismatchError(LocalExecutionError):
    """A checkpoint cannot be reconciled with its invocation or live state."""


class InvalidCheckpointError(LocalExecutionError):
    """A checkpoint document failed contract validation."""


class StaleBaseError(LocalExecutionError):
    """The canonical head advanced past an attempt's recorded base before promotion."""


class DirtyWorktreeError(LocalExecutionError):
    """A required worktree is not clean."""


class UnsafeCleanupError(LocalExecutionError):
    """Refused to remove a worktree or branch outside the attempt namespace."""


# ---------------------------------------------------------------------------
# Git primitives
# ---------------------------------------------------------------------------


def run(cmd: Sequence[str], *, cwd: Path | str | None = None, check: bool = True):
    """Run a command and return the completed process, mirroring the shared
    `carve-changesets/scripts/common.py` convention used elsewhere in this
    repository."""
    try:
        result = subprocess.run(
            list(cmd),
            cwd=str(cwd) if cwd is not None else None,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CommandError(f"command not found: {cmd[0]}") from exc

    if check and result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        detail = stderr or stdout or f"exit code {result.returncode}"
        raise CommandError(f"command failed: {' '.join(cmd)}\n{detail}")
    return result


def git(*args: str, cwd: Path | str | None = None, check: bool = True):
    return run(("git", *args), cwd=cwd, check=check)


def git_common_dir(repo_path: Path | str) -> Path:
    """Resolve the absolute Git common directory for `repo_path`.

    Locks, checkpoints, and preserved attempts are keyed by this path so that
    every worktree of one repository — canonical or attempt — contends on the
    same state, per the design's "same Git common directory" requirement.
    """
    output = git("rev-parse", "--git-common-dir", cwd=repo_path).stdout.strip()
    path = Path(output)
    if not path.is_absolute():
        path = Path(repo_path) / path
    return path.resolve()


def repo_toplevel(repo_path: Path | str) -> Path:
    return Path(
        git("rev-parse", "--show-toplevel", cwd=repo_path).stdout.strip()
    ).resolve()


def current_head(repo_path: Path | str) -> str:
    return git("rev-parse", "HEAD", cwd=repo_path).stdout.strip()


def current_branch(repo_path: Path | str) -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo_path).stdout.strip()


def branch_exists(repo_path: Path | str, name: str) -> bool:
    result = git(
        "show-ref",
        "--verify",
        "--quiet",
        f"refs/heads/{name}",
        cwd=repo_path,
        check=False,
    )
    return result.returncode == 0


def worktree_status(repo_path: Path | str) -> dict[str, list[str]]:
    """Return the tracked/staged/unstaged/untracked/ignored worktree shape
    already defined by `invocation.candidate.worktree` and
    `checkpoint.worktree` in `references/*.schema.json`. This module populates
    that existing shape from live `git status`; it does not define a new one.
    """
    output = git("status", "--porcelain=v1", "--ignored", cwd=repo_path).stdout
    staged: list[str] = []
    unstaged: list[str] = []
    untracked: list[str] = []
    ignored: list[str] = []
    for line in output.splitlines():
        if not line:
            continue
        code, path = line[:2], line[3:]
        if code == "??":
            untracked.append(path)
        elif code == "!!":
            ignored.append(path)
        else:
            if code[0] not in (" ", "?"):
                staged.append(path)
            if code[1] not in (" ", "?"):
                unstaged.append(path)
    tracked = [
        line for line in git("ls-files", cwd=repo_path).stdout.splitlines() if line
    ]
    return {
        "tracked": tracked,
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "ignored": ignored,
    }


def is_clean(status: dict[str, list[str]]) -> bool:
    """Whether a worktree is "clean" per the design: staged, unstaged, and
    untracked must be empty. `ignored` is deliberately exempt — an ignored
    file is not an uncommitted change."""
    return not status["staged"] and not status["unstaged"] and not status["untracked"]


@contextlib.contextmanager
def _message_file(message: str) -> Iterator[str]:
    """Yield a temporary file containing a commit message, avoiding shell
    interpolation for arbitrary (possibly untrusted) commit text."""
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix="review-fix-loop-commit-", delete=False
    ) as handle:
        handle.write(message.rstrip() + "\n")
        path = handle.name
    try:
        yield path
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(path)


# ---------------------------------------------------------------------------
# Common-directory locking
# ---------------------------------------------------------------------------


def _sanitize_component(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "-", value).strip("-") or "x"


def _lock_key(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]


def local_ref_lock_path(common_dir: Path, ref: str) -> Path:
    """Lock path for the canonical-local-ref lock keyed by common directory
    and candidate ref. Held for the complete invocation; prevents two local
    branches (any policy) from mutating the same ref concurrently."""
    return (
        common_dir
        / ROOT_NAMESPACE
        / LOCK_SUBDIR
        / f"local-ref-{_lock_key(str(common_dir), ref)}.lock"
    )


def remote_target_lock_path(
    common_dir: Path, repository_identity: str, remote_ref: str
) -> Path:
    """Lock path for the `update_pr` remote-target lock keyed by common
    directory, authenticated head-repository identity, and fully qualified
    remote head ref. Prevents two local branches in one common directory from
    targeting the same PR ref concurrently."""
    key = _lock_key(str(common_dir), repository_identity, remote_ref)
    return common_dir / ROOT_NAMESPACE / LOCK_SUBDIR / f"remote-target-{key}.lock"


class _FlockHandle:
    """A single non-blocking, process-lifetime `flock`-backed lock.

    The operating system releases the lock automatically if the holding
    process exits or crashes (design: "The operating system releases them
    when the process exits"), so this class never has to implement its own
    expiry or lease-renewal logic.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fd: int | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                raise CandidateBusyError(f"lock already held: {self.path}") from exc
            raise
        self._fd = fd

    def release(self) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None


@dataclasses.dataclass
class CandidateLocks:
    local: _FlockHandle
    remote: _FlockHandle | None


@contextlib.contextmanager
def acquire_candidate_locks(
    common_dir: Path,
    local_ref: str,
    *,
    remote_target: tuple[str, str] | None = None,
) -> Iterator[CandidateLocks]:
    """Acquire the local-ref lock and, if `remote_target` is given, the
    `update_pr` remote-target lock — in that fixed order — and release them
    in the reverse order on exit.

    Every acquisition is non-blocking: a busy lock raises `CandidateBusyError`
    immediately instead of waiting. Because no invocation ever waits on a
    lock, two invocations can never form a circular wait regardless of which
    local ref and remote target they each name — this is what makes "lock
    ordering avoids self-induced deadlocks for multi-target `update_pr` work"
    true by construction rather than by convention alone. If the remote lock
    is busy, the already-acquired local lock is released before the error
    propagates, so a failed acquisition never leaves a partial lock held.
    """
    local_handle = _FlockHandle(local_ref_lock_path(common_dir, local_ref))
    local_handle.acquire()
    remote_handle: _FlockHandle | None = None
    try:
        if remote_target is not None:
            identity, ref = remote_target
            remote_handle = _FlockHandle(
                remote_target_lock_path(common_dir, identity, ref)
            )
            remote_handle.acquire()
        yield CandidateLocks(local=local_handle, remote=remote_handle)
    finally:
        if remote_handle is not None:
            remote_handle.release()
        local_handle.release()


# ---------------------------------------------------------------------------
# Durable checkpoint
# ---------------------------------------------------------------------------


def checkpoint_path(common_dir: Path, invocation_id: str) -> Path:
    return (
        common_dir
        / ROOT_NAMESPACE
        / CHECKPOINT_SUBDIR
        / f"{_sanitize_component(invocation_id)}.json"
    )


def write_checkpoint_atomic(path: Path, document: dict[str, Any]) -> None:
    """Validate and atomically persist a checkpoint document.

    Writes to a sibling temporary file and `os.replace`s it into place so a
    reader never observes a partially written checkpoint, matching the
    design's "write checkpoints atomically." Uses `validate.canonical_json`
    for deterministic serialization and rejects an invalid document before
    touching disk — the durable checkpoint can never disagree with its own
    schema and cross-field contract.
    """
    errors = validate.validate_checkpoint(document)
    if errors:
        raise InvalidCheckpointError("; ".join(errors))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".tmp-checkpoint-", suffix=".json"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(validate.canonical_json(document))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise


def read_checkpoint(path: Path) -> dict[str, Any]:
    """Load and validate a checkpoint document. Raises `InvalidCheckpointError`
    rather than returning a document that would fail its own schema."""
    try:
        document = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise InvalidCheckpointError(f"{path}: {exc}") from exc
    if not isinstance(document, dict):
        raise InvalidCheckpointError(f"{path}: top-level JSON value must be an object")
    errors = validate.validate_checkpoint(document)
    if errors:
        raise InvalidCheckpointError("; ".join(errors))
    return document


def reconcile_checkpoint_for_resume(
    *,
    invocation: dict[str, Any],
    checkpoint: dict[str, Any],
    live_head: str,
    live_base_sha: str,
    live_worktree_status: dict[str, list[str]],
    lock_busy: bool,
) -> None:
    """Enforce every design-required resume precondition or raise.

    Checks, in order: no active lock holder; the complete cross-document
    identity set via `validate.validate_checkpoint_against_invocation` (same
    invocation ID, repository, branch, original budget, publication policy,
    initial head, and initial comparison base — this is also where "the same
    original budget and authority" is verified, reusing #96's validator
    rather than duplicating it); a clean candidate; and that the live head and
    comparison base are exactly the checkpoint's current values. Raises one of
    this module's `LocalExecutionError` subclasses and never mutates
    anything; the caller decides how to report `blocked/checkpoint_mismatch`
    or `blocked/candidate_busy`.
    """
    if lock_busy:
        raise CandidateBusyError("candidate lock is already held; cannot resume")

    mismatch_errors = validate.validate_checkpoint_against_invocation(
        invocation, checkpoint
    )
    if mismatch_errors:
        raise CheckpointMismatchError("; ".join(mismatch_errors))

    if not is_clean(live_worktree_status):
        raise DirtyWorktreeError("worktree must be clean to resume a checkpoint")

    if checkpoint.get("current_head") != live_head:
        raise CheckpointMismatchError(
            f"checkpoint current_head {checkpoint.get('current_head')!r} does not "
            f"match live head {live_head!r}"
        )

    checkpoint_base_sha = checkpoint.get("comparison_base", {}).get("sha")
    if checkpoint_base_sha != live_base_sha:
        raise CheckpointMismatchError(
            f"checkpoint comparison_base {checkpoint_base_sha!r} does not match "
            f"live base {live_base_sha!r}"
        )


# ---------------------------------------------------------------------------
# Transactional remediation attempts
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class AttemptHandle:
    path: Path
    branch: str
    base_sha: str


def default_attempts_root(common_dir: Path) -> Path:
    return common_dir / ROOT_NAMESPACE / ATTEMPTS_SUBDIR


def attempt_branch_name(invocation_id: str, sequence: int) -> str:
    return f"{ATTEMPT_BRANCH_PREFIX}{_sanitize_component(invocation_id)}/{sequence}"


def attempt_namespace_ref_prefix(invocation_id: str) -> str:
    """Return the full-ref prefix covering every attempt branch this
    invocation could create — `refs/heads/review-fix-loop/attempt/<id>/`.

    Used by `reviewer_orchestration.detect_worktree_mutation`'s
    `attempt_namespace_prefix` to classify a ref change inside this
    invocation's own attempt namespace as Tier 1 (candidate-bound), while a
    change inside a *different* invocation's attempt namespace — which does
    not share this prefix — stays Tier 2.
    """
    return f"refs/heads/{ATTEMPT_BRANCH_PREFIX}{_sanitize_component(invocation_id)}/"


def create_attempt(
    *,
    repo: Path,
    attempts_root: Path,
    base_sha: str,
    invocation_id: str,
    sequence: int,
) -> AttemptHandle:
    """Create an isolated attempt worktree and a dedicated branch from the
    exact canonical head.

    `git worktree add -b <branch> <path> <base_sha>` creates a brand-new
    working directory bound to a brand-new branch, both entirely outside the
    canonical worktree's path and branch. Nothing about the canonical
    candidate is read or touched by this call, satisfying "attempts occur
    outside the canonical worktree and leave it unchanged until promotion."
    """
    branch = attempt_branch_name(invocation_id, sequence)
    if branch_exists(repo, branch):
        raise LocalExecutionError(f"attempt branch already exists: {branch}")
    attempt_path = attempts_root / _sanitize_component(invocation_id) / str(sequence)
    if attempt_path.exists():
        raise LocalExecutionError(
            f"attempt worktree path already exists: {attempt_path}"
        )
    attempt_path.parent.mkdir(parents=True, exist_ok=True)
    git("worktree", "add", "-b", branch, str(attempt_path), base_sha, cwd=repo)
    return AttemptHandle(path=attempt_path, branch=branch, base_sha=base_sha)


def commit_attempt(handle: AttemptHandle, message: str) -> str:
    """Stage every change in the attempt worktree and create exactly one
    commit whose parent is the attempt's recorded `base_sha`.

    Raises `LocalExecutionError` if the resulting commit's parent does not
    match — this should be unreachable given `create_attempt`'s own
    bookkeeping, but the check keeps the transactional guarantee explicit
    rather than assumed.
    """
    git("add", "-A", cwd=handle.path)
    with _message_file(message) as msg_path:
        git("commit", "-F", msg_path, cwd=handle.path)
    new_head = current_head(handle.path)
    parent = git("rev-parse", f"{new_head}^", cwd=handle.path).stdout.strip()
    if parent != handle.base_sha:
        raise LocalExecutionError(
            f"attempt commit parent {parent!r} does not match recorded base "
            f"{handle.base_sha!r}"
        )
    return new_head


def promote_attempt(
    *,
    canonical_worktree: Path,
    canonical_branch: str,
    attempt_sha: str,
    expected_old_head: str,
) -> str:
    """Verified fast-forward-only promotion of `attempt_sha` onto the
    canonical worktree.

    Implements the design's "Transactional remediation attempts" promotion
    steps: verify the canonical worktree is on `canonical_branch` and
    globally clean; verify its live HEAD equals `expected_old_head`; verify
    the attempt commit's parent equals `expected_old_head` (otherwise the
    base drifted since the attempt started, and this raises `StaleBaseError`
    without touching canonical state — "dirty or advanced canonical state
    fails closed and preserves the candidate"); perform one
    `git merge --ff-only` through the canonical worktree so branch, HEAD,
    index, and files advance together; and verify the resulting HEAD, tree,
    and cleanliness before returning. Any failure leaves the canonical
    candidate exactly at its prior head — this function never resets,
    stashes, or force-updates anything.
    """
    on_branch = current_branch(canonical_worktree)
    if on_branch != canonical_branch:
        raise CandidateIntegrityFailureError(
            f"canonical worktree is on {on_branch!r}, expected {canonical_branch!r}"
        )

    status = worktree_status(canonical_worktree)
    if not is_clean(status):
        raise DirtyWorktreeError("canonical worktree must be clean before promotion")

    live_head = current_head(canonical_worktree)
    if live_head != expected_old_head:
        raise StaleBaseError(
            f"canonical head {live_head!r} no longer matches expected old head "
            f"{expected_old_head!r}"
        )

    attempt_parent = git(
        "rev-parse", f"{attempt_sha}^", cwd=canonical_worktree
    ).stdout.strip()
    if attempt_parent != expected_old_head:
        raise StaleBaseError(
            f"attempt {attempt_sha!r} parent {attempt_parent!r} does not match "
            f"expected old head {expected_old_head!r}"
        )

    git("merge", "--ff-only", attempt_sha, cwd=canonical_worktree)

    new_head = current_head(canonical_worktree)
    if new_head != attempt_sha:
        raise CandidateIntegrityFailureError(
            f"canonical head {new_head!r} does not equal promoted commit "
            f"{attempt_sha!r} after merge --ff-only"
        )
    resulting_tree = git(
        "rev-parse", f"{new_head}^{{tree}}", cwd=canonical_worktree
    ).stdout.strip()
    attempt_tree = git(
        "rev-parse", f"{attempt_sha}^{{tree}}", cwd=canonical_worktree
    ).stdout.strip()
    if resulting_tree != attempt_tree:
        raise CandidateIntegrityFailureError(
            "canonical tree does not equal the promoted commit's tree"
        )
    if not is_clean(worktree_status(canonical_worktree)):
        raise CandidateIntegrityFailureError(
            "canonical worktree is not clean immediately after promotion"
        )
    return new_head


def discard_attempt(
    *,
    common_dir: Path,
    handle: AttemptHandle,
    attempt_sha: str | None,
    reason: str,
) -> dict[str, str]:
    """Preserve a failed or stale-based attempt's patch and diagnostics.

    Returns a `{attempt_ref, reason}`-shaped record matching
    `checkpoint.preserved_failed_attempts`, plus the on-disk `patch_path` for
    operator inspection. Deliberately does not remove the attempt worktree or
    branch: recovery, and an eventual explicit `cleanup_attempt`, remain the
    only ways to remove them, so a failed attempt's commits (or in-progress
    edits) are never silently lost — "preserve recoverable commits ... when
    promotion cannot complete."
    """
    artifacts_dir = (
        common_dir
        / ROOT_NAMESPACE
        / PRESERVED_ATTEMPTS_SUBDIR
        / _sanitize_component(handle.branch)
    )
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    patch_path = artifacts_dir / "attempt.patch"
    if attempt_sha:
        diff = git("diff", handle.base_sha, attempt_sha, cwd=handle.path).stdout
    else:
        diff = git("diff", cwd=handle.path).stdout
    patch_path.write_text(diff)
    (artifacts_dir / "reason.txt").write_text(reason.rstrip() + "\n")
    return {
        "attempt_ref": handle.branch,
        "patch_path": str(patch_path),
        "reason": reason,
    }


def cleanup_attempt(*, repo: Path, handle: AttemptHandle, force: bool = False) -> None:
    """Remove an attempt's worktree and branch.

    Refuses to act on anything whose branch is not inside the
    `review-fix-loop/attempt/` namespace this module itself creates in
    `create_attempt` — the one hard safety invariant issue #97 requires:
    "cleanup never deletes user-owned work or reference branches." A forged
    or corrupted handle can therefore never cause this function to remove a
    user's branch or worktree.
    """
    if not handle.branch.startswith(ATTEMPT_BRANCH_PREFIX):
        raise UnsafeCleanupError(
            f"refusing to remove branch outside the attempt namespace: "
            f"{handle.branch!r}"
        )
    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(handle.path))
    git(*args, cwd=repo)
    git("branch", "-D", handle.branch, cwd=repo)


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class RecoveredAttempt:
    branch: str
    base_sha: str
    attempt_sha: str | None
    already_promoted: bool
    worktree_path: Path | None


def _list_attempt_branches(repo: Path, prefix: str) -> list[str]:
    result = git(
        "for-each-ref",
        "--format=%(refname:short)",
        f"refs/heads/{prefix}",
        cwd=repo,
    )
    return [line for line in result.stdout.splitlines() if line]


def _find_worktree_path_for_branch(repo: Path, branch: str) -> Path | None:
    output = git("worktree", "list", "--porcelain", cwd=repo).stdout
    current_path: str | None = None
    for line in output.splitlines():
        if line.startswith("worktree "):
            current_path = line[len("worktree ") :]
        elif line == f"branch refs/heads/{branch}" and current_path is not None:
            return Path(current_path)
    return None


def recover_interrupted_attempts(
    *,
    repo: Path,
    invocation_id: str,
    checkpoint: dict[str, Any],
) -> list[RecoveredAttempt]:
    """Reconcile attempt branches left behind by an interrupted invocation.

    Compares every existing `review-fix-loop/attempt/<invocation_id>/*`
    branch against the checkpoint's own `cycle_attempts` and `head_history`.
    A branch whose tip already appears as a `committed` attempt's
    `resulting_head` is already reflected in checkpoint history and is
    skipped. A branch whose tip is itself a recorded head (no commit was made
    before interruption) or whose tip's sole new commit has a parent
    appearing in `head_history` is a uniquely identifiable leftover from an
    interrupted cycle and is returned for the caller to decide whether to
    retry promotion or discard.

    Anything else — a branch whose parent is not in `head_history`, or more
    than one branch claiming the same starting head — cannot be uniquely
    reconciled and raises `CandidateIntegrityFailureError` rather than being
    silently resolved or deleted, per the design's "Accept only a uniquely
    identifiable expected commit. Ambiguity returns
    blocked/candidate_integrity_failure."
    """
    prefix = f"{ATTEMPT_BRANCH_PREFIX}{_sanitize_component(invocation_id)}/"
    branches = _list_attempt_branches(repo, prefix)
    head_history = list(checkpoint.get("head_history", []))
    head_history_set = set(head_history)
    committed_heads = {
        attempt.get("resulting_head")
        for attempt in checkpoint.get("cycle_attempts", [])
        if attempt.get("outcome") == "committed"
    }
    current = checkpoint.get("current_head")

    recovered: list[RecoveredAttempt] = []
    claimed_bases: dict[str, str] = {}
    for branch in branches:
        tip = git("rev-parse", branch, cwd=repo).stdout.strip()
        if tip in committed_heads:
            continue

        worktree_path = _find_worktree_path_for_branch(repo, branch)

        if tip in head_history_set:
            base_sha = tip
            attempt_sha: str | None = None
        else:
            parent_result = git("rev-parse", f"{tip}^", cwd=repo, check=False)
            parent = (
                parent_result.stdout.strip() if parent_result.returncode == 0 else None
            )
            if parent is None or parent not in head_history_set:
                raise CandidateIntegrityFailureError(
                    f"attempt branch {branch!r} tip {tip!r} does not derive from "
                    "a recorded head; cannot uniquely reconcile"
                )
            base_sha = parent
            attempt_sha = tip

        if base_sha in claimed_bases and claimed_bases[base_sha] != branch:
            raise CandidateIntegrityFailureError(
                f"more than one attempt branch claims to start from head "
                f"{base_sha!r}: {claimed_bases[base_sha]!r} and {branch!r}"
            )
        claimed_bases[base_sha] = branch

        recovered.append(
            RecoveredAttempt(
                branch=branch,
                base_sha=base_sha,
                attempt_sha=attempt_sha,
                already_promoted=(attempt_sha is not None and attempt_sha == current),
                worktree_path=worktree_path,
            )
        )
    return recovered
