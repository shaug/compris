"""Test helpers for carve-changesets identity and rehydration."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def run(cwd: Path, *args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        list(args),
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"Command failed ({result.returncode}): {' '.join(args)}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.stdout.strip()


def commit(cwd: Path, message: str) -> str:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as message_file:
        message_file.write(message)
        message_file.flush()
        run(cwd, "git", "commit", "-F", message_file.name)
    return run(cwd, "git", "rev-parse", "HEAD")


def init_repo(root: Path) -> tuple[Path, Path, str]:
    bare = root / "remote.git"
    repo = root / "builder"
    run(root, "git", "init", "--bare", "-b", "main", str(bare))
    run(root, "git", "init", "-b", "main", str(repo))
    run(repo, "git", "config", "user.name", "Carve Tests")
    run(repo, "git", "config", "user.email", "carve@example.test")
    (repo / "base.txt").write_text("base\n")
    run(repo, "git", "add", "base.txt")
    commit(repo, "initial")
    run(repo, "git", "remote", "add", "origin", str(bare))
    run(repo, "git", "push", "-u", "origin", "main")

    run(repo, "git", "checkout", "-b", "feature/report")
    (repo / "source.txt").write_text("complete source\n")
    run(repo, "git", "add", "source.txt")
    source_sha = commit(repo, "source result")
    run(repo, "git", "push", "-u", "origin", "feature/report")
    return repo, bare, source_sha
