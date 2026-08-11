#!/usr/bin/env python3
"""Run a skill's evaluations and record the summary as committed evidence.

This is the tool side of the eval-evidence norm in `AGENTS.md`: a change to a
skill's normative prose ships with a recorded before/after model-behavior run
where a real-model executor exists, and with a recorded deterministic run plus
the named gap where one does not.

Each run writes one JSON summary to `skills/<skill>/evals/results/`, carrying
the recorded date, the tier and exact executor command, the candidate the run
evaluated, per-case pass/fail, and the diff against that skill's previous
recorded run of the same tier. Summaries are evidence, not a CI gate. Record
from a committed, clean tree so `candidate.sha` names a commit a later reader
can actually resolve.

Usage:
    python3 scripts/record_eval_run.py implement-ticket --stage baseline
    python3 scripts/record_eval_run.py implement-ticket --stage before
    python3 scripts/record_eval_run.py carve-changesets  # deterministic + gap

A run ends in one of three recorded statuses, and the command exits non-zero
for the two that are not `completed`:

- `completed` — the evaluations ran and reported no failure.
- `failed` — they ran and reported failures, which are recorded with them.
- `attempted` — they could not run at all, so no evidence was collected. This
  is the environment-without-model-access case, and it never covers a run that
  happened and went red.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPOSITORY_ROOT / "skills"

SUMMARY_SCHEMA = "eval-run-summary/1"
STAGES = ("baseline", "before", "after")
REAL_MODEL = "real-model"
DETERMINISTIC = "deterministic"

# The real-model subject is pinned rather than left to whatever `claude -p`
# defaults to in a given environment on a given day: a before/after diff taken
# across a model update must compare two runs of the same model, not two
# different subjects wearing the same tier name. Changing the pin is a
# one-line edit plus a re-baseline, not a schema change.
RECORDED_MODEL = "claude-opus-5"

_RUN_FORWARD = "skills/implement-ticket/scripts/evals/run_forward.py"
_CLAUDE_EXECUTOR = "skills/implement-ticket/scripts/evals/claude_executor.py"

# Every eval a skill owns, as data. `real_model` exercises an actual model;
# `deterministic` replays the same corpus through a simulation. Both write one
# JSON file per case when handed `--output-dir` and print an aggregate summary,
# which is where per-case pass/fail and the diff come from. A skill absent from
# this table has no corpus to record, and the recorder says so rather than
# substituting its unit tests: those cannot observe SKILL.md prose at all, so a
# summary built from them would carry no cases, no totals, and no diff — the
# three fields the norm asks a reader to trust.
#
# implement-epic's forward cases live in implement-ticket's corpus and are
# selected with `--target-skill`; its results are still recorded under its own
# skill directory.
EVAL_TARGETS = {
    "implement-ticket": {
        "real_model": [
            _RUN_FORWARD,
            "--executor",
            f"{{python}} {_CLAUDE_EXECUTOR} --model {RECORDED_MODEL}",
        ],
        "deterministic": [_RUN_FORWARD],
    },
    "implement-epic": {
        "real_model": [
            _RUN_FORWARD,
            "--executor",
            f"{{python}} {_CLAUDE_EXECUTOR} --model {RECORDED_MODEL}",
            "--target-skill",
            "implement-epic",
        ],
        "deterministic": [_RUN_FORWARD, "--target-skill", "implement-epic"],
    },
    "carve-changesets": {
        "deterministic": ["skills/carve-changesets/scripts/evals/runner.py"],
    },
    "ready-ticket": {
        "real_model": [
            "skills/ready-ticket/scripts/evals/run_forward.py",
            "--executor",
            f"{{python}} skills/ready-ticket/scripts/evals/claude_executor.py "
            f"--model {RECORDED_MODEL}",
        ],
        "deterministic": ["skills/ready-ticket/scripts/evals/run_forward.py"],
    },
    "review-fix-loop": {
        "deterministic": ["skills/review-fix-loop/scripts/evals/runner.py"],
    },
}

_TRIGGERING_RUNNER = "triggering/runner.py"
_DESCRIPTION_EXECUTOR = "triggering/executors/description_executor.py"

# The triggering corpus is one corpus covering every skill, so each skill's
# entry is the same runner filtered to that skill's cases. Its real-model tier
# is the description executor; the headless executor is selected explicitly,
# because whether headless output reports skill invocation is unverified.
TRIGGERING_TARGETS = {
    skill: {
        "real_model": [
            _TRIGGERING_RUNNER,
            "--skill",
            skill,
            "--executor",
            f"{{python}} {_DESCRIPTION_EXECUTOR} --model {RECORDED_MODEL}",
        ],
        "deterministic": [_TRIGGERING_RUNNER, "--skill", skill],
    }
    for skill in (
        "babysit-pr",
        "carve-changesets",
        "implement-epic",
        "implement-ticket",
        "ready-ticket",
        "review-code-change",
        "review-code-simplicity",
        "review-correctness",
        "review-fix-loop",
        "review-solution-simplicity",
    )
}

FORWARD_SUITE = "forward"
TRIGGERING_SUITE = "triggering"
SUITES = {FORWARD_SUITE: EVAL_TARGETS, TRIGGERING_SUITE: TRIGGERING_TARGETS}

# The gap recorded whenever a run's own tier means no model read the prose. It
# is a property of the run, not of the registry: a deterministic run of a skill
# that has a real-model executor still collected no model-behavior evidence, and
# a summary that stayed silent about that would read as though it had.
NO_MODEL_READ_GAP = (
    "recorded tier is deterministic, so no model read the prose and the "
    "model-behavior evidence is absent"
)
NO_REAL_MODEL_EXECUTOR = (
    " No real-model executor is registered for this skill, so this tier is the "
    "only one available here."
)


class RecordingError(Exception):
    """A precondition failed before or during a recordable run."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def resolve_command(
    skill: str,
    tier: str | None,
    override: str | None,
    per_case: bool,
    suite: str = FORWARD_SUITE,
) -> tuple[list[str], str, str | None, bool]:
    """Return (command, tier, gap, reports_per_case) for one recorded run."""
    if not (SKILLS_DIR / skill).is_dir():
        available = sorted(path.name for path in SKILLS_DIR.iterdir() if path.is_dir())
        raise RecordingError(
            f"unknown skill {skill!r}; expected one of: {', '.join(available)}"
        )

    target = SUITES[suite].get(skill, {})
    has_real_model = "real_model" in target

    def gap_for(resolved_tier: str) -> str | None:
        if resolved_tier == REAL_MODEL:
            return None
        return NO_MODEL_READ_GAP + ("" if has_real_model else NO_REAL_MODEL_EXECUTOR)

    if override is not None:
        resolved_tier = tier or (REAL_MODEL if has_real_model else DETERMINISTIC)
        return shlex.split(override), resolved_tier, gap_for(resolved_tier), per_case

    if not target:
        raise RecordingError(
            f"{skill} has no registered {suite} evaluations to record; supply "
            f"--command with the run to record, or state the gap in the pull request"
        )

    key = "real_model" if (tier or REAL_MODEL) == REAL_MODEL else "deterministic"
    if key not in target:
        if tier:
            raise RecordingError(
                f"{skill} has no {tier} evaluations; "
                f"registered tiers are {', '.join(sorted(target))}"
            )
        key = next(iter(sorted(target)))

    resolved_tier = REAL_MODEL if key == "real_model" else DETERMINISTIC
    command = [sys.executable] + [
        part.format(python=shlex.quote(sys.executable)) for part in target[key]
    ]
    return command, resolved_tier, gap_for(resolved_tier), True


def model_for(command: list[str], tier: str) -> str | None:
    """The model a real-model run's own command explicitly selects, if any.

    Read from the resolved command rather than a separate parameter, so a
    registered target and a `--command` override are named the same way: both
    are trusted only insofar as the command they actually run carries an
    explicit `--model`, never an environment default. A deterministic run
    records no model — there is no model to name.

    A registered target's `--model` normally lives inside its `--executor`
    argument, one compound string rather than a separate command-list token
    (`--executor "python3 claude_executor.py --model claude-opus-5"`), so each
    token is re-split before the flag is searched for.
    """
    if tier != REAL_MODEL:
        return None
    flat: list[str] = []
    for token in command:
        flat.extend(shlex.split(token) if " " in token else [token])
    for index, token in enumerate(flat):
        if token == "--model" and index + 1 < len(flat):
            return flat[index + 1]
    return None


def run_command(
    command: list[str], reports_per_case: bool
) -> tuple[subprocess.CompletedProcess[str], dict[str, str], dict[str, dict | None]]:
    """Execute the eval command from the repository root.

    Returns the process, the pass/fail map the diff is computed over, and each
    case's own observation. The third is kept because a harness may report more
    than pass/fail — the description tier reports how many of its repetitions
    agreed — and discarding it would leave a case degrading from 5/5 to 3/5
    recorded as an unchanged `pass`.
    """
    if not reports_per_case:
        completed = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        return completed, {}, {}

    with tempfile.TemporaryDirectory() as directory:
        completed = subprocess.run(
            [*command, "--output-dir", directory],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        evidence = {}
        for path in sorted(Path(directory).glob("*.json")):
            try:
                evidence[path.stem] = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                evidence[path.stem] = None
    return completed, {case_id: "pass" for case_id in evidence}, evidence


def parse_summary(stdout: str) -> dict | None:
    """Read the harness's aggregate JSON summary from its stdout."""
    start = stdout.find("{")
    end = stdout.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        summary = json.loads(stdout[start : end + 1])
    except json.JSONDecodeError:
        return None
    return summary if isinstance(summary, dict) else None


def failing_case_ids(failures: list[str]) -> list[str]:
    return sorted({failure.split(":", 1)[0].strip() for failure in failures})


def tail(text: str, limit: int = 2000) -> str:
    text = text.strip()
    return text if len(text) <= limit else "…" + text[-limit:]


def results_dir(skill: str) -> Path:
    return SKILLS_DIR / skill / "evals" / "results"


def previous_run(
    directory: Path, tier: str, cases: dict[str, str], suite: str, model: str | None
) -> dict | None:
    """The most recent run this one can honestly be compared against.

    Both sides must have produced case outcomes at the same tier. A cross-tier
    diff reports the tier change as behavioral movement; a diff involving a run
    that recorded no cases reports "nothing regressed" when nothing was
    compared. Both are silent, and both land in the field the norm asks a
    reader to trust over the totals — including on the sanctioned fallback
    path, where an aborted run has no cases of its own to compare.
    """
    if not cases or not directory.is_dir():
        return None
    for path in reversed(sorted(directory.glob("*.json"))):
        try:
            recorded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(recorded, dict):
            continue
        if recorded.get("schema") != SUMMARY_SCHEMA:
            continue
        if recorded.get("tier") != tier or not recorded.get("cases"):
            continue
        # A triggering run and a forward-eval run measure different things, so
        # a diff across them would report the change of question as behavioral
        # movement.
        if recorded.get("suite", FORWARD_SUITE) != suite:
            continue
        # A before/after pair taken across a model update is two different
        # subjects, not one subject over time. A summary recorded before this
        # field existed has no model at all and is equally unusable as a
        # model-pinned comparison.
        if recorded.get("model") != model:
            continue
        recorded["_filename"] = path.name
        return recorded
    return None


def diff_against(
    previous: dict | None, cases: dict[str, str]
) -> tuple[str | None, dict]:
    """Compare per-case outcomes with the skill's previous recorded run."""
    if previous is None:
        return None, {
            "newly_failing": [],
            "newly_passing": [],
            "still_failing": sorted(
                case for case, status in cases.items() if status == "fail"
            ),
            "unchanged": 0,
        }

    prior = previous.get("cases") or {}
    newly_failing = sorted(
        case
        for case, status in cases.items()
        if status == "fail" and prior.get(case) == "pass"
    )
    newly_passing = sorted(
        case
        for case, status in cases.items()
        if status == "pass" and prior.get(case) == "fail"
    )
    still_failing = sorted(
        case
        for case, status in cases.items()
        if status == "fail" and prior.get(case) == "fail"
    )
    unchanged = sum(1 for case, status in cases.items() if prior.get(case) == status)
    return previous.get("_filename"), {
        "newly_failing": newly_failing,
        "newly_passing": newly_passing,
        "still_failing": still_failing,
        "unchanged": unchanged,
    }


# Recorded summaries are themselves files in the tree, so a run that records
# several skills in sequence would see its own earlier summaries as dirt and
# report every run after the first as unclean. Sibling evidence cannot change
# what an eval read, so cleanliness is computed over everything else — and the
# exemption is narrow and named rather than a general tolerance for a dirty
# tree.
RESULTS_PATH_MARKER = "/evals/results/"


def candidate_identity() -> dict:
    """Bind the run to the tree that produced it.

    `worktree_clean` is left unknown rather than asserted when git cannot be
    read: an empty `git status` and a failed `git status` are the same string,
    and defaulting to `True` would let a summary claim the strongest available
    provenance on the strength of a command that never ran.
    """

    def git(*args: str) -> str | None:
        completed = subprocess.run(
            ["git", *args],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        return None if completed.returncode else completed.stdout.strip()

    status = git("status", "--porcelain")
    if status is None:
        relevant = None
    else:
        relevant = [
            line
            for line in status.splitlines()
            if RESULTS_PATH_MARKER not in line.replace("\\", "/")
        ]
    return {
        "sha": git("rev-parse", "HEAD"),
        "tree": git("rev-parse", "HEAD^{tree}"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "worktree_clean": None if relevant is None else not relevant,
    }


def build_summary(
    *,
    skill: str,
    stage: str,
    tier: str,
    gap: str | None,
    note: str | None,
    suite: str,
    model: str | None,
    command: list[str],
    completed: subprocess.CompletedProcess[str],
    cases: dict[str, str],
    case_evidence: dict[str, dict | None],
    expects_summary: bool,
    recorded_at: datetime,
    previous: dict | None,
) -> dict:
    harness = parse_summary(completed.stdout)
    failures = list(harness.get("failures") or []) if harness else []
    for case_id in failing_case_ids(failures):
        if case_id in cases:
            cases[case_id] = "fail"

    # A harness that reports an aggregate summary has run whatever it exited
    # with. Its absence means something different in each direction: where a
    # summary was expected the harness aborted and produced no evidence, while
    # a plain command that never emits one is fully described by its exit code.
    # Collapsing the two would file a genuine eval regression as a run that
    # could not happen, which is the reading reserved for a missing executor.
    if harness:
        ran = True
    elif expects_summary:
        ran = completed.returncode == 0
    else:
        ran = True

    limitation = None
    if not ran:
        limitation = (
            f"eval command exited {completed.returncode} without an aggregate "
            f"summary; model-behavior evidence not collected"
        )

    totals = None
    if harness and {"total", "passed", "failed"} <= set(harness):
        totals = {
            "total": harness["total"],
            "passed": harness["passed"],
            "failed": harness["failed"],
        }
    elif cases:
        totals = {
            "total": len(cases),
            "passed": sum(1 for status in cases.values() if status == "pass"),
            "failed": sum(1 for status in cases.values() if status == "fail"),
        }

    if not ran:
        status = "attempted"
    elif completed.returncode or (totals and totals["failed"]):
        status = "failed"
    else:
        status = "completed"

    if status == "failed" and not failures:
        failures = [f"eval command exited {completed.returncode}"]

    compared_to, diff = diff_against(previous, cases)

    return {
        "schema": SUMMARY_SCHEMA,
        "skill": skill,
        "stage": stage,
        "suite": suite,
        "recorded_at": recorded_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tier": tier,
        "model": model,
        # Deliberately keyed off the forward suite whatever suite is being
        # recorded: the field's recorded meaning is "this skill has a
        # real-model forward executor", and making it suite-relative made
        # every triggering summary assert that for skills with none.
        "forward_evals": "real_model" in EVAL_TARGETS.get(skill, {}),
        "gap": gap,
        "note": note,
        "command": command,
        "candidate": candidate_identity(),
        "status": status,
        "exit_code": completed.returncode,
        "limitation": limitation,
        "totals": totals,
        "cases": cases,
        "case_evidence": case_evidence,
        "failures": failures,
        "compared_to": compared_to,
        "diff": diff,
        "output_tail": tail(completed.stdout or completed.stderr),
    }


def summary_filename(
    directory: Path,
    recorded_at: datetime,
    stage: str,
    label: str | None,
    suite: str = FORWARD_SUITE,
) -> str:
    """Name summaries so a plain lexicographic sort is chronological.

    Two runs recorded in the same second would otherwise sort by stage name,
    which silently reverses a before/after pair and inverts its recorded diff.
    """
    stamp = recorded_at.strftime("%Y-%m-%dT%H%M%SZ")
    existing = len(list(directory.glob("*.json"))) if directory.is_dir() else 0
    parts = [stamp, f"{existing + 1:04d}", stage]
    if suite != FORWARD_SUITE:
        parts.append(suite)
    if label:
        parts.append(label)
    return "-".join(parts) + ".json"


def plan(
    *,
    skill: str,
    tier: str | None,
    override: str | None,
    per_case: bool,
    suite: str = FORWARD_SUITE,
) -> dict:
    """Resolve what a run would execute, without executing or recording it."""
    command, resolved_tier, gap, _ = resolve_command(
        skill, tier, override, per_case, suite
    )
    return {
        "skill": skill,
        "suite": suite,
        "tier": resolved_tier,
        "model": model_for(command, resolved_tier),
        "gap": gap,
        "command": command,
    }


def record(
    *,
    skill: str,
    stage: str,
    tier: str | None,
    label: str | None,
    note: str | None,
    override: str | None,
    per_case: bool,
    suite: str = FORWARD_SUITE,
) -> tuple[dict, Path]:
    command, resolved_tier, gap, reports_per_case = resolve_command(
        skill, tier, override, per_case, suite
    )
    model = model_for(command, resolved_tier)
    completed, cases, case_evidence = run_command(command, reports_per_case)
    recorded_at = utc_now()
    directory = results_dir(skill)
    summary = build_summary(
        skill=skill,
        stage=stage,
        tier=resolved_tier,
        gap=gap,
        note=note,
        suite=suite,
        model=model,
        command=command,
        completed=completed,
        cases=cases,
        case_evidence=case_evidence,
        expects_summary=reports_per_case,
        recorded_at=recorded_at,
        previous=previous_run(directory, resolved_tier, cases, suite, model),
    )

    path = directory / summary_filename(directory, recorded_at, stage, label, suite)
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", "utf-8")
    return summary, path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill", help="Skill directory name under skills/")
    parser.add_argument("--stage", choices=STAGES, default="baseline")
    parser.add_argument("--label", help="Optional suffix for the summary filename")
    parser.add_argument("--tier", choices=(REAL_MODEL, DETERMINISTIC))
    parser.add_argument(
        "--suite",
        choices=tuple(SUITES),
        default=FORWARD_SUITE,
        help="Which corpus to run: the skill's forward evals or the triggering corpus",
    )
    parser.add_argument("--note", help="Free-text note stored with the summary")
    parser.add_argument(
        "--command",
        help="Override the registered eval command; recorded verbatim",
    )
    parser.add_argument(
        "--per-case-output-dir",
        action="store_true",
        help=(
            "The overridden command accepts --output-dir and writes one JSON "
            "file per case; registered forward-eval targets set this already"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the command a run would execute; execute and record nothing",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.dry_run:
            print(
                json.dumps(
                    plan(
                        skill=args.skill,
                        tier=args.tier,
                        override=args.command,
                        per_case=args.per_case_output_dir,
                        suite=args.suite,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        summary, path = record(
            skill=args.skill,
            stage=args.stage,
            tier=args.tier,
            label=args.label,
            note=args.note,
            override=args.command,
            per_case=args.per_case_output_dir,
            suite=args.suite,
        )
    except RecordingError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    print(f"recorded {path.relative_to(REPOSITORY_ROOT)}", file=sys.stderr)
    print(json.dumps(summary, indent=2, sort_keys=True))

    return 0 if summary["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
