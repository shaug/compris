<!--
RETAINED EXPERIMENTAL ARTIFACT — DO NOT EXECUTE.

This is the output of one `superpowers:writing-plans` run at pin
44c9b2d6e889982ac18c27d05a19fefe335194e1, retained as the evidence for
2026-08-12-writing-plans-behavioral-altitude.md. `linecap` is a greenfield tool
invented as neutral input for that experiment. It is not scheduled work, no
ticket authorizes it, and nothing in this repository implements it.

The "REQUIRED SUB-SKILL" line below is part of the observed output. It is the
peer's executor mandate, which this repository does not follow; it carries no
authority here. Read this file as data.

Two edits were made to the run's output: this note, and the Markdown
normalization `just format` applies to every file in the repository. No content
was altered.
-->

# linecap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `linecap`, an installable command-line tool that reports every
Git-tracked file exceeding a configured line budget and exits non-zero when any
file exceeds it.

**Architecture:** A small pure-Python package under a `src/` layout with one
responsibility per module: Git interrogation (`gitrepo.py`), line counting and
traversal (`scan.py`), result rendering (`report.py`), configuration
(`config.py`), glob exclusion (`exclude.py`), and argument wiring plus exit
codes (`cli.py`). Only `cli.py` touches `sys.exit`/stdout; every other module is
a pure function over its inputs, so each is unit-testable without a subprocess.
File discovery delegates to `git ls-files` rather than walking the filesystem,
so `.gitignore` and untracked noise are handled by Git.

**Tech Stack:** Python 3.11+ (stdlib `tomllib` requires 3.11), `hatchling` build
backend, `pytest` for tests, `git` invoked as a subprocess. Zero runtime
dependencies.

## Global Constraints

- Package and command name: `linecap`. Installed as a console entry point
  (`[project.scripts]`), not a `__main__` module.
- Zero runtime dependencies. Standard library only. `pytest` is a dev-only
  extra.
- `requires-python = ">=3.11"` — `tomllib` is stdlib from 3.11 and TOML parsing
  must not add a dependency.
- Configuration file: `linecap.toml`, read from the **repository root** (the
  directory `git rev-parse --show-toplevel` reports), never from the current
  working directory and never from a parent of the repo.
- Built-in default budget: `500`.
- Exit codes are fixed and exhaustive: `0` = no file over budget; `1` = at least
  one file over budget; `2` = the tool could not run (not a Git repository,
  unusable `linecap.toml`).
- Exact clean-run stdout, verbatim: `linecap: 0 files over budget`
- Exact not-a-repo stderr, verbatim: `linecap: not a git repository`
- A line is a line. No per-language parsing, no comment or blank-line stripping.
- The tool never edits, splits, or rewrites any file it inspects. It is
  read-only apart from its own stdout/stderr.
- No CI-provider-specific integration (no GitHub Actions annotations, no JUnit
  XML).
- Every acceptance criterion is verified by invoking the **installed console
  script** as a subprocess, not by calling `main()` in-process.

## Decisions (spec ambiguities resolved here — do not re-litigate during implementation)

01. **`checked` is an array of path strings, not a count.** The exclude
    criterion says files must be "absent from both `checked` and `offenders`";
    absence is only directly observable if `checked` is a collection. Sorted
    ascending by path for determinism.
02. **The offender listing prints exactly one line per offender and nothing else
    on stdout.** The clean run's `linecap: 0 files over budget` line is a
    distinct case; no summary header is printed when offenders exist, because
    the criterion says "one line per offending file".
03. **Offender line format:** `{path}: {lines} lines (budget {budget})` —
    carries path, line count, and budget, as required.
04. **Ordering:** offenders sort by descending line count, then ascending path
    to break ties deterministically.
05. **Line count definition:** number of `\n` bytes, plus one if the file is
    non-empty and does not end in `\n`. An empty file is 0 lines. Files are read
    as bytes so undecodable content cannot crash the run.
06. **Over budget means strictly greater than the budget.** A file with exactly
    `budget` lines is not an offender.
07. **`--version` prints `linecap {version}`** via argparse's `version` action.
    The criterion requires the package version be printed; the program name
    prefix is conventional and does not violate it.
08. **A malformed or wrongly typed `linecap.toml` exits 2** with
    `linecap: linecap.toml: {detail}` on stderr. The spec does not cover this
    case, but the tool must do *something* deterministic; reusing exit 2 (cannot
    run) is the minimal choice.
09. **Tracked-but-missing paths are skipped silently.** `git ls-files` reports
    deleted-but-staged files and submodule directories; neither is a readable
    file, and neither belongs in `checked`.
10. **Glob semantics for `exclude`:** `**` matches any characters including `/`;
    a single `*` matches any characters except `/`; `?` matches one non-`/`
    character. Patterns match the full repo-relative POSIX path. This is why the
    plan hand-rolls a translator instead of using `fnmatch` (whose `*` crosses
    `/`) or `PurePath.match` (whose `**` is not recursive before Python 3.13).

## File Structure

**Created by this plan:**

| Path                       | Responsibility                                                               |
| -------------------------- | ---------------------------------------------------------------------------- |
| `pyproject.toml`           | Package metadata, `linecap` console script, build backend, pytest config     |
| `.gitignore`               | Keep build and virtualenv artifacts out of history                           |
| `src/linecap/__init__.py`  | Package docstring and `__version__` — the single source of the version       |
| `src/linecap/gitrepo.py`   | Locate the repository root and list tracked files; raise `NotAGitRepository` |
| `src/linecap/scan.py`      | Count lines in a file; walk tracked files into a `Report`                    |
| `src/linecap/report.py`    | `Offender` / `Report` data types and the two output formatters               |
| `src/linecap/config.py`    | Defaults, `linecap.toml` loading and validation                              |
| `src/linecap/exclude.py`   | Glob-pattern to regex translation and matching                               |
| `src/linecap/cli.py`       | Argument parsing, module wiring, exit codes, stdout/stderr                   |
| `tests/conftest.py`        | Fixtures: locate the installed script, run it, build throwaway Git repos     |
| `tests/test_acceptance.py` | One test per spec acceptance criterion, against the installed command        |
| `tests/test_gitrepo.py`    | Unit tests for repo discovery and tracked-file listing                       |
| `tests/test_scan.py`       | Unit tests for line-count edge cases                                         |
| `tests/test_config.py`     | Unit tests for config defaults and validation errors                         |
| `tests/test_exclude.py`    | Unit tests for glob translation semantics                                    |

`report.py` holds both the data types and the formatters because they change
together: adding a field to `Report` always means changing both formatters.
`exclude.py` is separate from `config.py` because reading TOML and matching
globs are different responsibilities with different failure modes.

**Task ordering rationale:** JSON output (Task 4) lands before the config tasks
because the budget criterion is "observable through the budget reported in
**both** output formats" and the exclude criterion is stated in terms of the
JSON keys. Building config first would leave those criteria unverifiable until
later.

______________________________________________________________________

## Task 1: Project skeleton, packaging, and `--version`

**Delivers:** Acceptance criterion 7 (`linecap --version` prints the package
version, exits 0). An installed console script exists from here on, which every
later task's tests depend on.

**Files:**

- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/linecap/__init__.py`
- Create: `src/linecap/cli.py`
- Create: `tests/conftest.py`
- Test: `tests/test_acceptance.py`

**Interfaces:**

- Consumes: nothing (first task).

- Produces:

  - `linecap.__version__: str` — the version string, single-sourced here and
    read by the build backend.
  - `linecap.cli.build_parser() -> argparse.ArgumentParser`
  - `linecap.cli.main(argv: list[str] | None = None) -> int` — returns the
    process exit code; the generated console script wraps it in `sys.exit(...)`.
  - Test fixtures `linecap_bin`, `run_linecap`, `git_repo`, `add_file` (defined
    in `tests/conftest.py`, described below).

- [ ] **Step 1: Initialize the repository and directory layout**

```bash
git init
mkdir -p src/linecap tests
```

- [ ] **Step 2: Write `.gitignore`**

Create `.gitignore`:

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
build/
dist/
*.egg-info/
```

- [ ] **Step 3: Write `pyproject.toml`**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "linecap"
description = "Report repository files that exceed a configured line budget."
requires-python = ">=3.11"
dynamic = ["version"]
dependencies = []

[project.scripts]
linecap = "linecap.cli:main"

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.hatch.version]
path = "src/linecap/__init__.py"

[tool.hatch.build.targets.wheel]
packages = ["src/linecap"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 4: Write the package `__init__.py`**

Create `src/linecap/__init__.py`:

```python
"""linecap - a repository file-size budget checker."""

__version__ = "0.1.0"
```

- [ ] **Step 5: Write the shared test fixtures**

Create `tests/conftest.py`:

```python
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass
class Result:
    """The observable outcome of one `linecap` invocation."""

    exit_code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> dict:
        return json.loads(self.stdout)


@pytest.fixture(scope="session")
def linecap_bin() -> str:
    """Absolute path to the installed `linecap` console script."""
    found = shutil.which("linecap")
    if found is None:
        pytest.fail(
            "The 'linecap' console script is not on PATH. Run "
            "'python -m pip install -e \".[dev]\"' in the project root first."
        )
    return found


@pytest.fixture
def run_linecap(linecap_bin: str):
    """Run the installed command in `cwd` and capture its observable output."""

    def run(cwd: Path, *args: str) -> Result:
        completed = subprocess.run(
            [linecap_bin, *args],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        return Result(completed.returncode, completed.stdout, completed.stderr)

    return run


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """An empty Git repository isolated from the developer's global config."""
    root = tmp_path / "repo"
    root.mkdir()
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig"),
        "GIT_CONFIG_SYSTEM": str(tmp_path / "gitconfig-system"),
    }
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, env=env)
    return root


@pytest.fixture
def add_file():
    """Write a file with exactly `lines` lines and stage it.

    Staging is enough for `git ls-files`, so no commit and therefore no
    user.name/user.email configuration is needed.
    """

    def add(root: Path, relative: str, lines: int) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(f"line {n}\n" for n in range(lines)), encoding="utf-8")
        subprocess.run(["git", "add", "--", relative], cwd=root, check=True)
        return path

    return add


@pytest.fixture
def write_config():
    """Write and stage a linecap.toml at the repository root."""

    def write(root: Path, body: str) -> Path:
        path = root / "linecap.toml"
        path.write_text(body, encoding="utf-8")
        subprocess.run(["git", "add", "--", "linecap.toml"], cwd=root, check=True)
        return path

    return write
```

- [ ] **Step 6: Write the failing acceptance test**

Create `tests/test_acceptance.py`:

```python
from __future__ import annotations

from pathlib import Path

from linecap import __version__


def test_version_flag_prints_package_version(run_linecap, tmp_path: Path) -> None:
    result = run_linecap(tmp_path, "--version")

    assert result.exit_code == 0
    assert __version__ in result.stdout
```

- [ ] **Step 7: Install the package and run the test to verify it fails**

```bash
python -m pip install -e ".[dev]"
python -m pytest tests/test_acceptance.py -v
```

Expected: FAIL — installation itself fails, or collection fails with
`ModuleNotFoundError: No module named 'linecap.cli'`, because `cli.py` does not
exist yet.

- [ ] **Step 8: Write the minimal implementation**

Create `src/linecap/cli.py`:

```python
"""Command-line entry point for linecap."""

from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version


def _version_string() -> str:
    """The installed distribution's version, falling back to the source value."""
    try:
        return package_version("linecap")
    except PackageNotFoundError:  # running from a source tree, not installed
        from . import __version__

        return __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="linecap",
        description="Report tracked files that exceed the repository line budget.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"linecap {_version_string()}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0
```

- [ ] **Step 9: Reinstall and run the test to verify it passes**

```bash
python -m pip install -e ".[dev]"
python -m pytest tests/test_acceptance.py -v
```

Expected: PASS (1 passed).

- [ ] **Step 10: Commit**

```bash
git add .gitignore pyproject.toml src/linecap/__init__.py src/linecap/cli.py tests/conftest.py tests/test_acceptance.py
git commit -m "feat: scaffold linecap package with --version"
```

______________________________________________________________________

## Task 2: Git repository discovery and the not-a-repository exit

**Delivers:** Acceptance criterion 6 (outside a Git repository: exit 2,
`linecap: not a git repository` on stderr, nothing on stdout).

**Files:**

- Create: `src/linecap/gitrepo.py`
- Modify: `src/linecap/cli.py`
- Test: `tests/test_gitrepo.py`
- Test: `tests/test_acceptance.py` (append)

**Interfaces:**

- Consumes: `linecap.cli.main(argv) -> int`, `linecap.cli.build_parser()` from
  Task 1.

- Produces:

  - `linecap.gitrepo.NotAGitRepository` — exception raised when `start` is not
    inside a Git working tree, or `git` is not runnable.
  - `linecap.gitrepo.repo_root(start: Path) -> Path` — absolute path of the
    working-tree root.
  - `linecap.gitrepo.tracked_files(root: Path) -> list[Path]` — repo-relative
    `Path` objects, in `git ls-files` order.

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_gitrepo.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from linecap.gitrepo import NotAGitRepository, repo_root, tracked_files


def test_repo_root_finds_the_working_tree_root(git_repo: Path, add_file) -> None:
    add_file(git_repo, "src/deep/nested.py", 1)

    assert repo_root(git_repo / "src" / "deep").resolve() == git_repo.resolve()


def test_repo_root_raises_outside_a_repository(tmp_path: Path) -> None:
    outside = tmp_path / "not_a_repo"
    outside.mkdir()

    with pytest.raises(NotAGitRepository):
        repo_root(outside)


def test_tracked_files_lists_staged_paths_relative_to_root(git_repo: Path, add_file) -> None:
    add_file(git_repo, "a.py", 1)
    add_file(git_repo, "pkg/b.py", 1)
    (git_repo / "untracked.py").write_text("x\n", encoding="utf-8")

    listed = sorted(path.as_posix() for path in tracked_files(git_repo))

    assert listed == ["a.py", "pkg/b.py"]
```

- [ ] **Step 2: Write the failing acceptance test**

Append to `tests/test_acceptance.py`:

```python
def test_outside_a_git_repository_exits_2(run_linecap, tmp_path: Path) -> None:
    outside = tmp_path / "not_a_repo"
    outside.mkdir()

    result = run_linecap(outside)

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.strip() == "linecap: not a git repository"
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
python -m pytest tests/test_gitrepo.py tests/test_acceptance.py -v
```

Expected: FAIL — `tests/test_gitrepo.py` errors on collection with
`ModuleNotFoundError: No module named 'linecap.gitrepo'`, and
`test_outside_a_git_repository_exits_2` fails with `assert 0 == 2`.

- [ ] **Step 4: Write the Git module**

Create `src/linecap/gitrepo.py`:

```python
"""Interrogate Git for the repository root and its tracked files."""

from __future__ import annotations

import subprocess
from pathlib import Path


class NotAGitRepository(Exception):
    """Raised when the given directory is not inside a Git working tree."""


def _git(args: list[str], cwd: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            encoding="utf-8",
            errors="surrogateescape",
            check=False,
        )
    except (FileNotFoundError, NotADirectoryError) as exc:
        # `git` is not installed, or `cwd` does not exist.
        raise NotAGitRepository(str(exc)) from exc
    if completed.returncode != 0:
        raise NotAGitRepository(completed.stderr.strip())
    return completed.stdout


def repo_root(start: Path) -> Path:
    """Absolute path of the working tree containing `start`."""
    return Path(_git(["rev-parse", "--show-toplevel"], cwd=start).strip())


def tracked_files(root: Path) -> list[Path]:
    """Every tracked path, relative to `root`, in `git ls-files` order."""
    output = _git(["ls-files", "-z"], cwd=root)
    return [Path(name) for name in output.split("\0") if name]
```

- [ ] **Step 5: Wire the exit-2 path into the CLI**

Replace the contents of `src/linecap/cli.py` with:

```python
"""Command-line entry point for linecap."""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path

from .gitrepo import NotAGitRepository, repo_root


def _version_string() -> str:
    """The installed distribution's version, falling back to the source value."""
    try:
        return package_version("linecap")
    except PackageNotFoundError:  # running from a source tree, not installed
        from . import __version__

        return __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="linecap",
        description="Report tracked files that exceed the repository line budget.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"linecap {_version_string()}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    try:
        repo_root(Path.cwd())
    except NotAGitRepository:
        print("linecap: not a git repository", file=sys.stderr)
        return 2
    return 0
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python -m pytest -v
```

Expected: PASS (5 passed).

- [ ] **Step 7: Commit**

```bash
git add src/linecap/gitrepo.py src/linecap/cli.py tests/test_gitrepo.py tests/test_acceptance.py
git commit -m "feat: detect the git repository root and exit 2 outside one"
```

______________________________________________________________________

## Task 3: Line counting, scanning, and human-readable output

**Delivers:** Acceptance criteria 1 and 2 (clean repo prints
`linecap: 0 files over budget` and exits 0; two oversized files exit 1 and print
one line each, descending by line count) against the built-in default budget of
500\.

**Files:**

- Create: `src/linecap/report.py`
- Create: `src/linecap/scan.py`
- Modify: `src/linecap/cli.py`
- Test: `tests/test_scan.py`
- Test: `tests/test_acceptance.py` (append)

**Interfaces:**

- Consumes: `linecap.gitrepo.tracked_files(root) -> list[Path]` and
  `linecap.gitrepo.repo_root(start) -> Path` from Task 2.

- Produces:

  - `linecap.report.Offender` — frozen dataclass with fields `path: str`
    (repo-relative POSIX) and `lines: int`.
  - `linecap.report.Report` — frozen dataclass with fields `budget: int`,
    `checked: list[str]`, `offenders: list[Offender]`.
  - `linecap.report.format_human(report: Report) -> str` — returns the full
    stdout text including its trailing newline.
  - `linecap.scan.count_lines(path: Path) -> int`
  - `linecap.scan.scan(root: Path, budget: int) -> Report` — **Task 6 widens
    this signature** to
    `scan(root: Path, budget: int, exclude: Sequence[str] = ()) -> Report`.

- [ ] **Step 1: Write the failing unit tests for line counting**

Create `tests/test_scan.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from linecap.scan import count_lines


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"", 0),
        (b"one\n", 1),
        (b"one", 1),
        (b"one\ntwo\n", 2),
        (b"one\ntwo", 2),
        (b"\n\n\n", 3),
    ],
)
def test_count_lines(tmp_path: Path, content: bytes, expected: int) -> None:
    target = tmp_path / "sample.txt"
    target.write_bytes(content)

    assert count_lines(target) == expected


def test_count_lines_handles_undecodable_bytes(tmp_path: Path) -> None:
    target = tmp_path / "binary.bin"
    target.write_bytes(b"\xff\xfe\n\x00\x01\n")

    assert count_lines(target) == 2
```

- [ ] **Step 2: Write the failing acceptance tests**

Append to `tests/test_acceptance.py`:

```python
def test_clean_repository_reports_zero_and_exits_0(run_linecap, git_repo: Path, add_file) -> None:
    add_file(git_repo, "src/small.py", 10)
    add_file(git_repo, "src/also_small.py", 499)

    result = run_linecap(git_repo)

    assert result.exit_code == 0
    assert result.stdout == "linecap: 0 files over budget\n"


def test_two_offenders_exit_1_and_list_descending(run_linecap, git_repo: Path, add_file) -> None:
    add_file(git_repo, "src/big.py", 600)
    add_file(git_repo, "src/bigger.py", 900)
    add_file(git_repo, "src/small.py", 10)

    result = run_linecap(git_repo)

    assert result.exit_code == 1
    assert result.stdout.splitlines() == [
        "src/bigger.py: 900 lines (budget 500)",
        "src/big.py: 600 lines (budget 500)",
    ]
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
python -m pytest tests/test_scan.py tests/test_acceptance.py -v
```

Expected: FAIL — `tests/test_scan.py` errors on collection with
`ModuleNotFoundError: No module named 'linecap.scan'`; both new acceptance tests
fail because stdout is empty.

- [ ] **Step 4: Write the report module**

Create `src/linecap/report.py`:

```python
"""Result types and output formatters for linecap."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Offender:
    """One tracked file whose line count exceeds the budget."""

    path: str
    lines: int


@dataclass(frozen=True)
class Report:
    """The outcome of one scan."""

    budget: int
    checked: list[str]
    offenders: list[Offender]


def format_human(report: Report) -> str:
    """Render a report as human-readable text, trailing newline included."""
    if not report.offenders:
        return "linecap: 0 files over budget\n"
    return "".join(
        f"{offender.path}: {offender.lines} lines (budget {report.budget})\n"
        for offender in report.offenders
    )
```

- [ ] **Step 5: Write the scan module**

Create `src/linecap/scan.py`:

```python
"""Count lines in tracked files and collect the ones over budget."""

from __future__ import annotations

from pathlib import Path

from .gitrepo import tracked_files
from .report import Offender, Report


def count_lines(path: Path) -> int:
    """Number of lines in `path`.

    Read as bytes so undecodable content cannot raise. A final line without a
    trailing newline still counts; an empty file is zero lines.
    """
    data = path.read_bytes()
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def scan(root: Path, budget: int) -> Report:
    """Check every tracked file under `root` against `budget`."""
    checked: list[str] = []
    offenders: list[Offender] = []
    for relative in tracked_files(root):
        absolute = root / relative
        if not absolute.is_file():
            # Staged-but-deleted paths and submodule directories.
            continue
        posix = relative.as_posix()
        lines = count_lines(absolute)
        checked.append(posix)
        if lines > budget:
            offenders.append(Offender(path=posix, lines=lines))
    checked.sort()
    offenders.sort(key=lambda offender: (-offender.lines, offender.path))
    return Report(budget=budget, checked=checked, offenders=offenders)
```

- [ ] **Step 6: Wire scanning and human output into the CLI**

In `src/linecap/cli.py`, add these imports below the existing
`from .gitrepo import ...` line:

```python
from .report import format_human
from .scan import scan
```

Then replace the body of `main` with:

```python
def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    try:
        root = repo_root(Path.cwd())
    except NotAGitRepository:
        print("linecap: not a git repository", file=sys.stderr)
        return 2
    report = scan(root, budget=500)
    sys.stdout.write(format_human(report))
    return 1 if report.offenders else 0
```

- [ ] **Step 7: Run the tests to verify they pass**

```bash
python -m pytest -v
```

Expected: PASS (14 passed).

- [ ] **Step 8: Commit**

```bash
git add src/linecap/report.py src/linecap/scan.py src/linecap/cli.py tests/test_scan.py tests/test_acceptance.py
git commit -m "feat: report tracked files over the default line budget"
```

______________________________________________________________________

## Task 4: JSON output format

**Delivers:** Acceptance criterion 3 (`--format json` emits one JSON object with
`budget`, `checked`, and `offenders`; `offenders` entries carry `path` and
`lines`; exit-code rule unchanged).

**Files:**

- Modify: `src/linecap/report.py`
- Modify: `src/linecap/cli.py`
- Test: `tests/test_acceptance.py` (append)

**Interfaces:**

- Consumes: `linecap.report.Report`, `linecap.report.Offender`,
  `linecap.report.format_human(report) -> str`,
  `linecap.scan.scan(root, budget) -> Report` from Task 3.

- Produces:

  - `linecap.report.format_json(report: Report) -> str` — a single-line JSON
    object plus a trailing newline.
  - CLI option `--format {human,json}`, defaulting to `human`.

- [ ] **Step 1: Write the failing acceptance tests**

Append to `tests/test_acceptance.py`:

```python
def test_json_format_on_a_clean_repository(run_linecap, git_repo: Path, add_file) -> None:
    add_file(git_repo, "src/small.py", 10)

    result = run_linecap(git_repo, "--format", "json")

    assert result.exit_code == 0
    assert result.json == {
        "budget": 500,
        "checked": ["src/small.py"],
        "offenders": [],
    }


def test_json_format_lists_offenders_and_exits_1(run_linecap, git_repo: Path, add_file) -> None:
    add_file(git_repo, "src/big.py", 600)
    add_file(git_repo, "src/bigger.py", 900)
    add_file(git_repo, "src/small.py", 10)

    result = run_linecap(git_repo, "--format", "json")

    assert result.exit_code == 1
    assert result.json == {
        "budget": 500,
        "checked": ["src/big.py", "src/bigger.py", "src/small.py"],
        "offenders": [
            {"path": "src/bigger.py", "lines": 900},
            {"path": "src/big.py", "lines": 600},
        ],
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/test_acceptance.py -v
```

Expected: FAIL — both new tests exit 2 with argparse's
`error: unrecognized arguments: --format json` on stderr, and `result.json`
raises `json.decoder.JSONDecodeError` on empty stdout.

- [ ] **Step 3: Add the JSON formatter**

In `src/linecap/report.py`, add `import json` under
`from __future__ import annotations` (before
`from dataclasses import dataclass`), then append:

```python
def format_json(report: Report) -> str:
    """Render a report as one JSON object, trailing newline included."""
    payload = {
        "budget": report.budget,
        "checked": list(report.checked),
        "offenders": [
            {"path": offender.path, "lines": offender.lines}
            for offender in report.offenders
        ],
    }
    return json.dumps(payload) + "\n"
```

- [ ] **Step 4: Add the `--format` option and select the formatter**

In `src/linecap/cli.py`, change the report import to:

```python
from .report import format_human, format_json
```

Add this argument inside `build_parser()`, before the `--version` argument:

```python
    parser.add_argument(
        "--format",
        choices=("human", "json"),
        default="human",
        help="Output format (default: human).",
    )
```

Then replace the body of `main` with:

```python
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = repo_root(Path.cwd())
    except NotAGitRepository:
        print("linecap: not a git repository", file=sys.stderr)
        return 2
    report = scan(root, budget=500)
    rendered = format_json(report) if args.format == "json" else format_human(report)
    sys.stdout.write(rendered)
    return 1 if report.offenders else 0
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest -v
```

Expected: PASS (16 passed).

- [ ] **Step 6: Commit**

```bash
git add src/linecap/report.py src/linecap/cli.py tests/test_acceptance.py
git commit -m "feat: add --format json output"
```

______________________________________________________________________

## Task 5: `linecap.toml` budget override

**Delivers:** Acceptance criterion 4 (`budget = 300` in `linecap.toml` overrides
the built-in default of 500, observable in both output formats).

**Files:**

- Create: `src/linecap/config.py`
- Modify: `src/linecap/cli.py`
- Test: `tests/test_config.py`
- Test: `tests/test_acceptance.py` (append)

**Interfaces:**

- Consumes: `linecap.gitrepo.repo_root(start) -> Path` from Task 2;
  `linecap.scan.scan(root, budget) -> Report` from Task 3.

- Produces:

  - `linecap.config.DEFAULT_BUDGET: int` — `500`.
  - `linecap.config.CONFIG_FILENAME: str` — `"linecap.toml"`.
  - `linecap.config.InvalidConfig` — exception for an unreadable or wrongly
    typed config.
  - `linecap.config.Config` — frozen dataclass with field
    `budget: int = DEFAULT_BUDGET`. **Task 6 adds** the field
    `exclude: tuple[str, ...] = ()`.
  - `linecap.config.load_config(root: Path) -> Config`.

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_config.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from linecap.config import DEFAULT_BUDGET, Config, InvalidConfig, load_config


def test_default_budget_is_500() -> None:
    assert DEFAULT_BUDGET == 500


def test_missing_config_yields_defaults(tmp_path: Path) -> None:
    assert load_config(tmp_path) == Config(budget=500)


def test_budget_is_read_from_the_config(tmp_path: Path) -> None:
    (tmp_path / "linecap.toml").write_text("budget = 300\n", encoding="utf-8")

    assert load_config(tmp_path).budget == 300


def test_config_without_budget_keeps_the_default(tmp_path: Path) -> None:
    (tmp_path / "linecap.toml").write_text("# nothing here\n", encoding="utf-8")

    assert load_config(tmp_path).budget == 500


@pytest.mark.parametrize(
    "body",
    ["budget = = 3\n", 'budget = "300"\n', "budget = true\n", "budget = -1\n"],
)
def test_unusable_config_raises(tmp_path: Path, body: str) -> None:
    (tmp_path / "linecap.toml").write_text(body, encoding="utf-8")

    with pytest.raises(InvalidConfig):
        load_config(tmp_path)
```

- [ ] **Step 2: Write the failing acceptance test**

Append to `tests/test_acceptance.py`:

```python
def test_config_budget_overrides_the_default(
    run_linecap, git_repo: Path, add_file, write_config
) -> None:
    add_file(git_repo, "src/mid.py", 400)
    write_config(git_repo, "budget = 300\n")

    human = run_linecap(git_repo)
    assert human.exit_code == 1
    assert human.stdout.splitlines() == ["src/mid.py: 400 lines (budget 300)"]

    as_json = run_linecap(git_repo, "--format", "json")
    assert as_json.exit_code == 1
    assert as_json.json["budget"] == 300
    assert as_json.json["offenders"] == [{"path": "src/mid.py", "lines": 400}]
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
python -m pytest tests/test_config.py tests/test_acceptance.py -v
```

Expected: FAIL — `tests/test_config.py` errors on collection with
`ModuleNotFoundError: No module named 'linecap.config'`; the acceptance test
fails with `assert 0 == 1` because a 400-line file is still under the
un-overridden budget of 500.

- [ ] **Step 4: Write the config module**

Create `src/linecap/config.py`:

```python
"""Load and validate the repository's linecap.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILENAME = "linecap.toml"
DEFAULT_BUDGET = 500


class InvalidConfig(Exception):
    """Raised when linecap.toml exists but cannot be used."""


@dataclass(frozen=True)
class Config:
    """Effective settings for one run."""

    budget: int = DEFAULT_BUDGET


def load_config(root: Path) -> Config:
    """Read `root/linecap.toml`, falling back to built-in defaults."""
    path = root / CONFIG_FILENAME
    if not path.is_file():
        return Config()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise InvalidConfig(f"{CONFIG_FILENAME}: {exc}") from exc

    budget = raw.get("budget", DEFAULT_BUDGET)
    # bool is a subclass of int, so reject it explicitly.
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
        raise InvalidConfig(f"{CONFIG_FILENAME}: budget must be a non-negative integer")

    return Config(budget=budget)
```

- [ ] **Step 5: Wire config loading into the CLI**

In `src/linecap/cli.py`, add this import above the `from .gitrepo import ...`
line:

```python
from .config import InvalidConfig, load_config
```

Then replace the body of `main` with:

```python
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = repo_root(Path.cwd())
    except NotAGitRepository:
        print("linecap: not a git repository", file=sys.stderr)
        return 2
    try:
        config = load_config(root)
    except InvalidConfig as exc:
        print(f"linecap: {exc}", file=sys.stderr)
        return 2
    report = scan(root, budget=config.budget)
    rendered = format_json(report) if args.format == "json" else format_human(report)
    sys.stdout.write(rendered)
    return 1 if report.offenders else 0
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python -m pytest -v
```

Expected: PASS (25 passed).

- [ ] **Step 7: Commit**

```bash
git add src/linecap/config.py src/linecap/cli.py tests/test_config.py tests/test_acceptance.py
git commit -m "feat: read the line budget from linecap.toml"
```

______________________________________________________________________

## Task 6: `exclude` glob patterns

**Delivers:** Acceptance criterion 5 (`exclude = ["vendor/**"]` removes files
under `vendor/` from both `checked` and `offenders`).

**Files:**

- Create: `src/linecap/exclude.py`
- Modify: `src/linecap/config.py`
- Modify: `src/linecap/scan.py`
- Modify: `src/linecap/cli.py`
- Test: `tests/test_exclude.py`
- Test: `tests/test_config.py` (append)
- Test: `tests/test_acceptance.py` (append)

**Interfaces:**

- Consumes: `linecap.config.Config` and
  `linecap.config.load_config(root) -> Config` from Task 5;
  `linecap.scan.scan(root, budget) -> Report` from Task 3.

- Produces:

  - `linecap.exclude.matches_any(path: str, patterns: Sequence[str]) -> bool` —
    `path` is a repo-relative POSIX string.
  - `linecap.config.Config.exclude: tuple[str, ...]` — new field, defaulting to
    `()`.
  - `linecap.scan.scan(root: Path, budget: int, exclude: Sequence[str] = ()) -> Report`
    — widened signature; the two-argument calls from Task 3 remain valid.

- [ ] **Step 1: Write the failing unit tests for glob matching**

Create `tests/test_exclude.py`:

```python
from __future__ import annotations

import pytest

from linecap.exclude import matches_any


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        ("vendor/lib.py", "vendor/**", True),
        ("vendor/deep/nested/lib.py", "vendor/**", True),
        ("vendor", "vendor/**", False),
        ("vendorish/lib.py", "vendor/**", False),
        ("src/vendor/lib.py", "vendor/**", False),
        ("src/generated.py", "src/*.py", True),
        ("src/deep/generated.py", "src/*.py", False),
        ("a.py", "?.py", True),
        ("ab.py", "?.py", False),
        ("src/a.py", "**/*.py", True),
        ("notes.txt", "**/*.py", False),
    ],
)
def test_matches_any_single_pattern(path: str, pattern: str, expected: bool) -> None:
    assert matches_any(path, [pattern]) is expected


def test_matches_any_is_false_without_patterns() -> None:
    assert matches_any("vendor/lib.py", []) is False


def test_matches_any_is_true_when_one_pattern_matches() -> None:
    assert matches_any("vendor/lib.py", ["build/**", "vendor/**"]) is True
```

- [ ] **Step 2: Write the failing config unit tests**

Append to `tests/test_config.py`:

```python
def test_exclude_defaults_to_empty(tmp_path: Path) -> None:
    assert load_config(tmp_path).exclude == ()


def test_exclude_is_read_from_the_config(tmp_path: Path) -> None:
    (tmp_path / "linecap.toml").write_text('exclude = ["vendor/**"]\n', encoding="utf-8")

    assert load_config(tmp_path).exclude == ("vendor/**",)


@pytest.mark.parametrize("body", ['exclude = "vendor/**"\n', "exclude = [1, 2]\n"])
def test_unusable_exclude_raises(tmp_path: Path, body: str) -> None:
    (tmp_path / "linecap.toml").write_text(body, encoding="utf-8")

    with pytest.raises(InvalidConfig):
        load_config(tmp_path)
```

- [ ] **Step 3: Write the failing acceptance test**

Append to `tests/test_acceptance.py`:

```python
def test_excluded_paths_are_absent_from_checked_and_offenders(
    run_linecap, git_repo: Path, add_file, write_config
) -> None:
    add_file(git_repo, "vendor/huge.py", 900)
    add_file(git_repo, "vendor/deep/also_huge.py", 800)
    add_file(git_repo, "src/small.py", 10)
    write_config(git_repo, 'exclude = ["vendor/**"]\n')

    result = run_linecap(git_repo, "--format", "json")

    assert result.exit_code == 0
    assert result.json["offenders"] == []
    assert result.json["checked"] == ["linecap.toml", "src/small.py"]
    assert not any(path.startswith("vendor/") for path in result.json["checked"])
```

- [ ] **Step 4: Run the tests to verify they fail**

```bash
python -m pytest tests/test_exclude.py tests/test_config.py tests/test_acceptance.py -v
```

Expected: FAIL — `tests/test_exclude.py` errors on collection with
`ModuleNotFoundError: No module named 'linecap.exclude'`; the config tests fail
with `AttributeError: 'Config' object has no attribute 'exclude'`; the
acceptance test fails with `assert 1 == 0` because the vendor files are still
counted.

- [ ] **Step 5: Write the exclude module**

Create `src/linecap/exclude.py`:

```python
"""Match repo-relative paths against gitignore-flavoured glob patterns.

`fnmatch` lets a single `*` cross directory separators and `PurePath.match`
does not treat `**` as recursive before Python 3.13, so neither gives the
semantics `exclude = ["vendor/**"]` needs. Translating by hand does.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Sequence


@lru_cache(maxsize=None)
def _compiled(pattern: str) -> re.Pattern[str]:
    """Translate one glob pattern into an anchored regular expression.

    `**` matches any characters including `/`; `*` matches any characters
    except `/`; `?` matches exactly one non-`/` character.
    """
    parts: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if pattern.startswith("**", index):
                parts.append(".*")
                index += 2
            else:
                parts.append("[^/]*")
                index += 1
            continue
        if char == "?":
            parts.append("[^/]")
        else:
            parts.append(re.escape(char))
        index += 1
    return re.compile("".join(parts) + r"\Z")


def matches_any(path: str, patterns: Sequence[str]) -> bool:
    """True when `path` matches at least one pattern."""
    return any(_compiled(pattern).match(path) is not None for pattern in patterns)
```

- [ ] **Step 6: Add `exclude` to the config**

In `src/linecap/config.py`, add the field to `Config`:

```python
@dataclass(frozen=True)
class Config:
    """Effective settings for one run."""

    budget: int = DEFAULT_BUDGET
    exclude: tuple[str, ...] = ()
```

Then, in `load_config`, insert this block after the budget validation and change
the return statement:

```python
    exclude = raw.get("exclude", [])
    if not isinstance(exclude, list) or not all(
        isinstance(pattern, str) for pattern in exclude
    ):
        raise InvalidConfig(f"{CONFIG_FILENAME}: exclude must be a list of strings")

    return Config(budget=budget, exclude=tuple(exclude))
```

- [ ] **Step 7: Apply exclusion during the scan**

In `src/linecap/scan.py`, change the imports to:

```python
from pathlib import Path
from typing import Sequence

from .exclude import matches_any
from .gitrepo import tracked_files
from .report import Offender, Report
```

Then replace `scan` with:

```python
def scan(root: Path, budget: int, exclude: Sequence[str] = ()) -> Report:
    """Check every tracked, non-excluded file under `root` against `budget`."""
    checked: list[str] = []
    offenders: list[Offender] = []
    for relative in tracked_files(root):
        posix = relative.as_posix()
        if matches_any(posix, exclude):
            continue
        absolute = root / relative
        if not absolute.is_file():
            # Staged-but-deleted paths and submodule directories.
            continue
        lines = count_lines(absolute)
        checked.append(posix)
        if lines > budget:
            offenders.append(Offender(path=posix, lines=lines))
    checked.sort()
    offenders.sort(key=lambda offender: (-offender.lines, offender.path))
    return Report(budget=budget, checked=checked, offenders=offenders)
```

- [ ] **Step 8: Pass the patterns through the CLI**

In `src/linecap/cli.py`, change the `scan` call inside `main` to:

```python
    report = scan(root, budget=config.budget, exclude=config.exclude)
```

- [ ] **Step 9: Run the full suite to verify everything passes**

```bash
python -m pytest -v
```

Expected: PASS (43 passed).

- [ ] **Step 10: Commit**

```bash
git add src/linecap/exclude.py src/linecap/config.py src/linecap/scan.py src/linecap/cli.py tests/test_exclude.py tests/test_config.py tests/test_acceptance.py
git commit -m "feat: honour exclude globs from linecap.toml"
```

______________________________________________________________________

## Final Verification

Every acceptance criterion must be exercised against the installed command-line
tool, as the spec's "Required verification" section demands.

- [ ] **Step 1: Reinstall from a clean state and run the whole suite**

```bash
python -m pip install -e ".[dev]" --force-reinstall --no-deps
python -m pytest -v
```

Expected: PASS, all tests green.

- [ ] **Step 2: Confirm each acceptance criterion has a named test**

Check that `tests/test_acceptance.py` contains all eight tests below, one per
criterion (criterion 4 is covered by one test asserting both formats):

| Spec criterion                                             | Test                                                                                     |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Clean repo prints `linecap: 0 files over budget`, exits 0  | `test_clean_repository_reports_zero_and_exits_0`                                         |
| Two offenders, exit 1, one line each, descending           | `test_two_offenders_exit_1_and_list_descending`                                          |
| `--format json` object with `budget`/`checked`/`offenders` | `test_json_format_on_a_clean_repository`, `test_json_format_lists_offenders_and_exits_1` |
| `budget = 300` overrides the default in both formats       | `test_config_budget_overrides_the_default`                                               |
| `exclude = ["vendor/**"]` removes paths from both keys     | `test_excluded_paths_are_absent_from_checked_and_offenders`                              |
| Outside a repo: exit 2, stderr message, empty stdout       | `test_outside_a_git_repository_exits_2`                                                  |
| `--version` prints the package version, exits 0            | `test_version_flag_prints_package_version`                                               |

- [ ] **Step 3: Smoke-test the tool against its own repository by hand**

```bash
linecap; echo "exit=$?"
linecap --format json; echo "exit=$?"
linecap --version; echo "exit=$?"
```

Expected: `linecap: 0 files over budget` with `exit=0`; a JSON object listing
this project's own source files in `checked` with an empty `offenders` and
`exit=0`; `linecap 0.1.0` with `exit=0`.

- [ ] **Step 4: Commit anything outstanding**

```bash
git status --short
```

Expected: clean tree. If not, review and commit the remainder.
