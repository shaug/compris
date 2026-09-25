"""Shared helpers for carve-changesets scripts."""

from __future__ import annotations

import datetime as _dt
import json
import re
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

DEFAULT_PLAN_PATH = Path(".carve-changesets/plan.json")


class CommandError(RuntimeError):
    """Raised when a subprocess or git command fails."""


TEST_COMMAND_HINTS: Tuple[str, ...] = (
    "just test",
    "make test",
    "pytest",
    "python -m pytest",
    "npm test",
    "pnpm test",
    "yarn test",
    "bun test",
    "go test",
    "cargo test",
    "tox",
    "nox",
)


def run(
    cmd: Sequence[str], *, capture: bool = True, check: bool = True
) -> subprocess.CompletedProcess:
    """Run a command and return the completed process."""
    try:
        result = subprocess.run(
            list(cmd),
            text=True,
            capture_output=capture,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CommandError(f"Command not found: {cmd[0]}") from exc

    if check and result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        detail = stderr or stdout or f"exit code {result.returncode}"
        raise CommandError(f"Command failed: {' '.join(cmd)}\n{detail}")
    return result


def git(
    *args: str, capture: bool = True, check: bool = True
) -> subprocess.CompletedProcess:
    """Run a git command."""
    return run(("git",) + args, capture=capture, check=check)


def ensure_git_repo() -> None:
    git("rev-parse", "--is-inside-work-tree")


def repo_root() -> Path:
    return Path(git("rev-parse", "--show-toplevel").stdout.strip())


def ensure_clean_tree() -> None:
    status = git(
        "status",
        "--porcelain",
        "--",
        ".",
        ":(exclude).carve-changesets",
    ).stdout.strip()
    if status:
        raise CommandError(
            "Working tree is not clean. Commit, stash, or discard changes first."
        )


def is_path_ignored(path: Path | str) -> bool:
    raw = path.as_posix() if isinstance(path, Path) else str(path)
    candidates = {raw, raw.rstrip("/")}
    for candidate in sorted(candidates):
        if not candidate:
            continue
        result = git(
            "check-ignore",
            "-q",
            "--",
            candidate,
            capture=False,
            check=False,
        )
        if result.returncode == 0:
            return True
    return False


def branch_exists(name: str) -> bool:
    result = git("rev-parse", "--verify", name, capture=True, check=False)
    return result.returncode == 0


def current_branch() -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def merge_base(base: str, source: str) -> str:
    return git("merge-base", base, source).stdout.strip()


def compute_freshness(base: str, source: str) -> Dict[str, object]:
    base_head = git("rev-parse", base).stdout.strip()
    source_head = git("rev-parse", source).stdout.strip()
    mb = merge_base(base, source)
    return {
        "base_head": base_head,
        "source_head": source_head,
        "merge_base": mb,
        "source_behind_base": mb != base_head,
    }


def diff_name_status(base: str, source: str) -> str:
    return git("diff", "--name-status", f"{base}..{source}").stdout.strip()


def diff_stat(base: str, source: str) -> str:
    return git("diff", "--stat", f"{base}..{source}").stdout.strip()


def unique_temp_branch(prefix: str) -> str:
    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{ts}"


def delete_branch(name: str) -> None:
    git("branch", "-D", name, check=False)


@contextmanager
def message_file(message: str):
    """Yield a temporary file containing a commit or GitHub message."""

    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix="carve-message-"
    ) as handle:
        handle.write(message.rstrip() + "\n")
        handle.flush()
        yield handle.name


def commit_with_message(message: str) -> None:
    """Commit staged changes using the repository-required file interface."""

    with message_file(message) as path:
        git("commit", "-F", path)


def ensure_branches_exist(branches: Iterable[str]) -> None:
    missing = [b for b in branches if not branch_exists(b)]
    if missing:
        raise CommandError("Missing branch(es):\n" + "\n".join(missing))


def branch_name_for(source_branch: str, index: int) -> str:
    return f"{source_branch}-{index}"


def base_for_changeset(base_branch: str, source_branch: str, index: int) -> str:
    if index <= 1:
        return base_branch
    return branch_name_for(source_branch, index - 1)


def squashed_branch_name(source_branch: str) -> str:
    return f"{source_branch}-squashed"


@contextmanager
def checkout_restore(target: Optional[str] = None):
    """Checkout target (if provided) and restore the exact original checkout."""
    original_branch = current_branch()
    original_detached = original_branch == "HEAD"
    original = (
        git("rev-parse", "HEAD").stdout.strip()
        if original_detached
        else original_branch
    )
    try:
        if target and target != original:
            git("checkout", target)
        yield original
    finally:
        if original_detached:
            current_sha = git("rev-parse", "HEAD").stdout.strip()
            if current_branch() != "HEAD" or current_sha != original:
                git("checkout", "--detach", original)
        elif current_branch() != original:
            git("checkout", original)


def load_plan(path: Path) -> Dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise CommandError(f"Plan file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CommandError(f"Invalid JSON in plan file {path}: {exc}") from exc


def validate_plan(plan: Dict) -> Tuple[bool, List[str]]:
    errors: List[str] = []

    def require_string(key: str) -> None:
        if (
            key not in plan
            or not isinstance(plan.get(key), str)
            or not str(plan[key]).strip()
        ):
            errors.append(f"Missing or invalid string field: {key}")

    require_string("feature_title")
    require_string("base_branch")
    require_string("source_branch")

    if "test_command" in plan:
        errors.append(
            "Legacy plan.test_command is not supported; replace it with "
            'test_argv, for example ["just", "test"] or '
            '["sh", "-lc", "<approved shell command>"].'
        )

    test_argv = plan.get("test_argv", [])
    from command_argv import validate_optional_argv

    try:
        validate_optional_argv(test_argv, label="plan.test_argv")
    except CommandError as exc:
        errors.append(str(exc))

    changesets = plan.get("changesets")
    if not isinstance(changesets, list) or not changesets:
        errors.append("Plan must include a non-empty 'changesets' array.")
        return False, errors

    for idx, cs in enumerate(changesets, start=1):
        if not isinstance(cs, dict):
            errors.append(f"Changeset {idx} must be an object.")
            continue

        for key in ("slug", "description"):
            if key not in cs:
                errors.append(f"Changeset {idx} missing required field: {key}")

        if "slug" in cs and (not isinstance(cs["slug"], str) or not cs["slug"].strip()):
            errors.append(f"Changeset {idx} has invalid slug.")
        if "description" in cs and (
            not isinstance(cs["description"], str) or not cs["description"].strip()
        ):
            errors.append(f"Changeset {idx} has invalid description.")

        mode = str(cs.get("mode", "paths")).strip() or "paths"
        if mode not in ("paths", "patch", "hunks"):
            errors.append(
                f"Changeset {idx} has invalid mode '{mode}'. Use 'paths', 'patch', or 'hunks'."
            )

        include = cs.get("include_paths", [])
        if include and (
            not isinstance(include, list)
            or not all(isinstance(p, str) for p in include)
        ):
            errors.append(
                f"Changeset {idx} include_paths must be a string array when provided."
            )
        if mode == "paths":
            if not isinstance(include, list) or not include:
                errors.append(
                    f"Changeset {idx} include_paths must be a non-empty string array for mode=paths."
                )

        if mode == "patch":
            patch_file = cs.get("patch_file")
            if not isinstance(patch_file, str) or not patch_file.strip():
                errors.append(
                    f"Changeset {idx} patch_file must be a non-empty string for mode=patch."
                )

        if mode == "hunks":
            selectors = cs.get("hunk_selectors")
            if (
                not isinstance(selectors, list)
                or not selectors
                or not all(isinstance(s, dict) for s in selectors)
            ):
                errors.append(
                    f"Changeset {idx} hunk_selectors must be a non-empty array for mode=hunks."
                )

        exclude = cs.get("exclude_paths", [])
        if exclude and (
            not isinstance(exclude, list)
            or not all(isinstance(p, str) for p in exclude)
        ):
            errors.append(
                f"Changeset {idx} exclude_paths must be a string array when provided."
            )

        allow_partial = cs.get("allow_partial_files")
        if allow_partial is not None and not isinstance(allow_partial, bool):
            errors.append(
                f"Changeset {idx} allow_partial_files must be a boolean when provided."
            )

        pr_notes = cs.get("pr_notes", [])
        if pr_notes and (
            not isinstance(pr_notes, list)
            or not all(isinstance(p, str) for p in pr_notes)
        ):
            errors.append(
                f"Changeset {idx} pr_notes must be a string array when provided."
            )

    return (not errors), errors


def default_changeset(index: int) -> Dict:
    return {
        "mode": "paths",
        "slug": f"changeset-{index}",
        "description": f"Describe the intent for changeset {index}.",
        "include_paths": ["src/**"],
        "exclude_paths": [],
        "allow_partial_files": True,
        "commit_message": f"changeset: placeholder {index}",
        "pr_notes": ["Replace with PR notes for this changeset."],
    }


def init_plan(
    *,
    plan_path: Path,
    base: str,
    source: str,
    title: str,
    changesets: int,
    test_argv: object,
    force: bool,
) -> None:
    from command_argv import validate_optional_argv

    approved_test_argv = validate_optional_argv(test_argv, label="test argv")
    plan_path.parent.mkdir(parents=True, exist_ok=True)

    if plan_path.exists() and not force:
        raise CommandError(
            f"Plan already exists: {plan_path}. Use --force to overwrite."
        )

    plan = {
        "feature_title": title,
        "base_branch": base,
        "source_branch": source,
        "test_argv": approved_test_argv,
        "changesets": [default_changeset(i) for i in range(1, changesets + 1)],
    }

    plan_path.write_text(json.dumps(plan, indent=2) + "\n")


def _is_test_command(cmd: str) -> bool:
    lower = cmd.lower()
    if any(hint in lower for hint in TEST_COMMAND_HINTS):
        return True
    # Catch generic patterns like "just test-foo" or "make test-all".
    return bool(re.search(r"\b(test|pytest)\b", lower))


def _extract_code_blocks(text: str) -> List[str]:
    # Keep this permissive; we are mining for likely commands, not parsing Markdown.
    pattern = re.compile(r"```[a-zA-Z0-9_-]*\n(.*?)```", re.DOTALL)
    return [m.group(1) for m in pattern.finditer(text)]


def _commands_from_block(block: str) -> List[str]:
    commands: List[str] = []
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*:", line):
            continue
        if re.match(r"^\"[A-Za-z0-9_-]+\":", line):
            continue
        if re.match(r"^'[A-Za-z0-9_-]+':", line):
            continue
        # Treat each non-empty line as a potential command.
        commands.append(line)
    return commands


def parse_agents_test_commands(path: Path) -> List[str]:
    try:
        text = path.read_text()
    except FileNotFoundError:
        return []

    candidates: List[str] = []
    seen: Set[str] = set()
    for block in _extract_code_blocks(text):
        for cmd in _commands_from_block(block):
            if not _is_test_command(cmd):
                continue
            if cmd not in seen:
                seen.add(cmd)
                candidates.append(cmd)
    return candidates


def _add_suggestion(cmd: str, suggestions: List[str], seen: Set[str]) -> None:
    clean = cmd.strip()
    if not clean or clean in seen:
        return
    seen.add(clean)
    suggestions.append(clean)


def _suggest_from_justfile(root: Path, suggestions: List[str], seen: Set[str]) -> None:
    for name in ("justfile", "Justfile"):
        path = root / name
        if not path.exists():
            continue
        text = path.read_text()
        if re.search(r"(?m)^test\s*:", text):
            _add_suggestion("just test", suggestions, seen)


def _suggest_from_makefile(root: Path, suggestions: List[str], seen: Set[str]) -> None:
    for name in ("Makefile", "makefile"):
        path = root / name
        if not path.exists():
            continue
        text = path.read_text()
        if re.search(r"(?m)^test\s*:", text):
            _add_suggestion("make test", suggestions, seen)


def _suggest_from_package_json(
    root: Path, suggestions: List[str], seen: Set[str]
) -> None:
    path = root / "package.json"
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return

    scripts = data.get("scripts") if isinstance(data, dict) else None
    test_script = scripts.get("test") if isinstance(scripts, dict) else None
    if not isinstance(test_script, str) or not test_script.strip():
        return

    if (root / "pnpm-lock.yaml").exists():
        tool_cmd = "pnpm test"
    elif (root / "yarn.lock").exists():
        tool_cmd = "yarn test"
    elif (root / "bun.lockb").exists():
        tool_cmd = "bun test"
    else:
        tool_cmd = "npm test"

    _add_suggestion(tool_cmd, suggestions, seen)
    # The project's declared test script is authoritative even if it does not
    # contain the word "test" (for example, "vitest run").
    _add_suggestion(test_script, suggestions, seen)


def _suggest_from_python_project(
    root: Path, suggestions: List[str], seen: Set[str]
) -> None:
    pyproject = root / "pyproject.toml"
    setup_cfg = root / "setup.cfg"
    tests_dir = root / "tests"

    pyproject_text = pyproject.read_text() if pyproject.exists() else ""
    setup_cfg_text = setup_cfg.read_text() if setup_cfg.exists() else ""

    if "[tool.pytest" in pyproject_text or "pytest" in pyproject_text:
        _add_suggestion("python -m pytest", suggestions, seen)
        return
    if "[tool:pytest]" in setup_cfg_text or "pytest" in setup_cfg_text:
        _add_suggestion("python -m pytest", suggestions, seen)
        return

    if tests_dir.exists() and any(p.suffix == ".py" for p in tests_dir.rglob("*.py")):
        _add_suggestion("python -m pytest", suggestions, seen)


def _suggest_from_other_roots(
    root: Path, suggestions: List[str], seen: Set[str]
) -> None:
    if (root / "tox.ini").exists():
        _add_suggestion("tox", suggestions, seen)
    if (root / "noxfile.py").exists():
        _add_suggestion("nox", suggestions, seen)
    if (root / "go.mod").exists():
        _add_suggestion("go test ./...", suggestions, seen)
    if (root / "Cargo.toml").exists():
        _add_suggestion("cargo test", suggestions, seen)


def _suggest_from_workflows(root: Path, suggestions: List[str], seen: Set[str]) -> None:
    workflows_dir = root / ".github" / "workflows"
    if not workflows_dir.exists():
        return

    workflow_paths = sorted(
        [
            *workflows_dir.glob("*.yml"),
            *workflows_dir.glob("*.yaml"),
        ]
    )
    run_line = re.compile(r"^\s*run:\s*(.*)$")

    for path in workflow_paths:
        lines = path.read_text().splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            m = run_line.match(line)
            if not m:
                i += 1
                continue

            rest = m.group(1).strip()
            if rest and rest not in ("|", ">"):
                if _is_test_command(rest):
                    _add_suggestion(rest, suggestions, seen)
                i += 1
                continue

            # Handle multi-line run blocks.
            base_indent = len(line) - len(line.lstrip(" "))
            i += 1
            while i < len(lines):
                block_line = lines[i]
                indent = len(block_line) - len(block_line.lstrip(" "))
                if indent <= base_indent:
                    break
                cmd = block_line.strip()
                if cmd and _is_test_command(cmd):
                    _add_suggestion(cmd, suggestions, seen)
                i += 1


def suggest_test_commands(root: Path, *, prior: Sequence[str] = ()) -> List[str]:
    suggestions: List[str] = []
    seen: Set[str] = set()

    for cmd in prior:
        _add_suggestion(cmd, suggestions, seen)

    _suggest_from_justfile(root, suggestions, seen)
    _suggest_from_makefile(root, suggestions, seen)
    _suggest_from_package_json(root, suggestions, seen)
    _suggest_from_python_project(root, suggestions, seen)
    _suggest_from_other_roots(root, suggestions, seen)
    _suggest_from_workflows(root, suggestions, seen)

    return suggestions


def discover_test_command(preferred: str = "") -> Dict[str, object]:
    """Discover a repo-specific test command and return diagnostics.

    The return object always includes:
    - command: Optional[str]
    - source: str
    - reason: str
    - candidates: List[str]
    - suggestions: List[str]
    """
    if preferred.strip():
        return {
            "command": preferred.strip(),
            "source": "cli",
            "reason": "provided",
            "candidates": [],
            "suggestions": [],
        }

    root = repo_root()
    agents_path = root / "AGENTS.md"
    agents_candidates = parse_agents_test_commands(agents_path)

    if agents_candidates and len(agents_candidates) == 1:
        return {
            "command": agents_candidates[0],
            "source": "agents",
            "reason": "agents-single",
            "candidates": agents_candidates,
            "suggestions": agents_candidates,
        }

    if not agents_path.exists():
        reason = "agents-missing"
    elif not agents_candidates:
        reason = "agents-no-test-command"
    else:
        reason = "agents-ambiguous"

    suggestions = suggest_test_commands(root, prior=agents_candidates)
    return {
        "command": None,
        "source": "none",
        "reason": reason,
        "candidates": agents_candidates,
        "suggestions": suggestions,
    }
