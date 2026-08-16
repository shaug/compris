# Eval Candidate Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an eval summary's `candidate` block name repository state a later
reader can still retrieve, by recording per-path subtree hashes, guarding their
reachability, backfilling the summaries that can still be derived, and merging
eval-carrying pull requests in a way that keeps the measured content on `main`.

**Architecture:** `candidate_identity()` gains `trees`, a map from repository
path to that path's subtree hash — `skills/<skill>` always, plus `triggering`
for a triggering-suite run. A new guard under `scripts/tests/` holds every
recorded entry to reachability from `HEAD`, modeled on the changelog citation
guard #236 added. A one-shot derivation backfills the 23 summaries still naming
a reachable commit. `AGENTS.md` states the corrected durability claim and the
merge-method rule that makes it true.

**Tech Stack:** Python 3 standard library only (`json`, `subprocess`,
`unittest`, `pathlib`). No new dependencies. `just format`, `just lint`,
`just test` are the gates.

## Global Constraints

- Required before every commit: `just format`, `just lint`, `just test`.
- Commit messages use Conventional Commits, written to a temp file and passed
  with `git commit -F`, never inline `-m`. Bodies are Markdown with `## Summary`
  and `## Why`.
- Markdown links are inline reference links with definitions collected at the
  end of the file under
  `<!-- inline reference link definitions. please keep alphabetized -->`.
- Test modules under `scripts/tests/` that import a sibling helper establish
  their own `sys.path` entry from `__file__`. The new guard imports no sibling,
  so it needs no shim.
- Summaries are written with
  `json.dumps(summary, indent=2, sort_keys=True) + "\n"`. All 82 existing files
  round-trip byte-identically under that call; the backfill must preserve this
  so its diff is pure addition.
- Do not use destructive git commands. Do not rewrite reference branches.
- The design this implements is
  [`docs/superpowers/specs/2026-08-16-eval-candidate-identity-design.md`][spec].

______________________________________________________________________

## File Structure

| File                                             | Responsibility                                                                                                    |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| `scripts/record_eval_run.py`                     | Add `subtree_paths()`; extend `candidate_identity()` to take `skill`/`suite` and record `trees`                   |
| `scripts/tests/test_record_eval_run.py`          | Replace the test asserting the disproved claim; add `trees` coverage; assert `AGENTS.md` states the merge policy  |
| `scripts/tests/test_eval_candidate_citations.py` | New. Hold every recorded subtree to reachability from `HEAD`                                                      |
| `skills/*/evals/results/*.json`                  | Data. 23 files gain `candidate.trees`                                                                             |
| `AGENTS.md`                                      | Correct the durability claim; state the merge policy, the backfill, and the grandfathering                        |
| `skills/babysit-pr/SKILL.md`                     | Editorial: line 398's example says "squash method" where line 357 already says "repository-approved merge method" |
| `CHANGELOG.md`                                   | One entry per commit, newest first, under today's heading                                                         |

______________________________________________________________________

### Task 1: Record the subtree identity that survives a rebase

**Files:**

- Modify: `scripts/record_eval_run.py:389-425` (after `RESULTS_PATH_MARKER`,
  through `candidate_identity`)
- Modify: `scripts/record_eval_run.py:513` (the `build_summary` call site)
- Test: `scripts/tests/test_record_eval_run.py:459-511` (replace
  `test_candidate_tree_survives_rebase_and_squash`)
- Test: `scripts/tests/test_record_eval_run.py:597-620` (two call sites that
  pass no arguments)

**Interfaces:**

- Consumes: `record_eval_run.FORWARD_SUITE` (`"forward"`),
  `record_eval_run.TRIGGERING_SUITE` (`"triggering"`),
  `record_eval_run.REPOSITORY_ROOT`, both already defined.

- Produces:

  - `subtree_paths(skill: str, suite: str) -> list[str]` — the repository paths
    whose content decides what a run of that suite read.
  - `candidate_identity(skill: str, suite: str) -> dict` — signature change,
    from no arguments. Returns the existing keys plus `trees: dict[str, str]`,
    mapping each path from `subtree_paths` to its subtree hash.
  - Task 2's backfill reproduces `subtree_paths`' path selection against
    recorded summaries. Task 3's guard reads `candidate["trees"]`.

- [ ] **Step 1: Replace the test that encodes the disproved claim**

The existing `test_candidate_tree_survives_rebase_and_squash` passes only
because it simulates a rebase as "same tree, new parent", which is the one thing
a real rebase never is. Delete it — the whole method and its four-line `# AC:`
comment above it — and put this in its place, keeping the surrounding class:

```python
    # AC: the recorded identity still resolves to the evaluated content after
    # a real rebase onto a moved `main` — one that changes files outside the
    # skill, as every rebase in this repository does. `sha` cannot survive
    # that, and neither can the whole-repository `tree`; the skill's subtree
    # must, because unrelated files moving cannot disturb it.
    def test_candidate_identity_survives_a_rebase_onto_a_moved_base(self) -> None:
        repo = self.root / "git-repo"
        skill = repo / "skills" / "demo"
        skill.mkdir(parents=True)

        def git(*args: str) -> str:
            completed = subprocess.run(
                ["git", *args],
                cwd=repo,
                text=True,
                capture_output=True,
                check=True,
            )
            return completed.stdout.strip()

        git("init", "-q")
        git("config", "user.email", "a@example.com")
        git("config", "user.name", "a")
        (repo / "AGENTS.md").write_text("base\n", encoding="utf-8")
        (skill / "SKILL.md").write_text("prose v1\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", "first")

        with mock.patch.object(record_eval_run, "REPOSITORY_ROOT", repo):
            before = record_eval_run.candidate_identity(
                "demo", record_eval_run.FORWARD_SUITE
            )

        # The rebase: `main` moved by changing a file outside the skill, and
        # the branch's work is replayed on top. The skill's content is
        # untouched; the repository's tree is not.
        (repo / "AGENTS.md").write_text("moved\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", "unrelated change on main")

        with mock.patch.object(record_eval_run, "REPOSITORY_ROOT", repo):
            after = record_eval_run.candidate_identity(
                "demo", record_eval_run.FORWARD_SUITE
            )

        self.assertNotEqual(after["sha"], before["sha"])
        self.assertNotEqual(after["tree"], before["tree"])
        self.assertEqual(after["trees"], before["trees"])
        self.assertEqual(sorted(before["trees"]), ["skills/demo"])

    # AC: a squash-merge that keeps the measured content keeps the recorded
    # identity with it. This is the half of the deleted test that was worth
    # keeping — it is what makes a run recorded at the shipping head
    # resolvable on `main` afterward, and it is the only durability the
    # merge-method rule in `AGENTS.md` cannot supply on its own.
    def test_candidate_identity_survives_a_squash_that_keeps_the_content(
        self,
    ) -> None:
        repo = self.root / "squash-repo"
        skill = repo / "skills" / "demo"
        skill.mkdir(parents=True)

        def git(*args: str) -> str:
            completed = subprocess.run(
                ["git", *args],
                cwd=repo,
                text=True,
                capture_output=True,
                check=True,
            )
            return completed.stdout.strip()

        git("init", "-q")
        git("config", "user.email", "a@example.com")
        git("config", "user.name", "a")
        (repo / "AGENTS.md").write_text("base\n", encoding="utf-8")
        (skill / "SKILL.md").write_text("prose v1\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", "first")

        with mock.patch.object(record_eval_run, "REPOSITORY_ROOT", repo):
            before = record_eval_run.candidate_identity(
                "demo", record_eval_run.FORWARD_SUITE
            )

        # The squash: one brand new commit carrying the other files the pull
        # request touched, with no ancestry to the recorded commit at all.
        (repo / "AGENTS.md").write_text("squashed\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", "other files in the same pull request")
        squashed = git("commit-tree", git("rev-parse", "HEAD^{tree}"), "-m", "squash")
        git("reset", "--hard", squashed)

        with mock.patch.object(record_eval_run, "REPOSITORY_ROOT", repo):
            after = record_eval_run.candidate_identity(
                "demo", record_eval_run.FORWARD_SUITE
            )

        self.assertNotEqual(after["sha"], before["sha"])
        self.assertNotEqual(after["tree"], before["tree"])
        self.assertEqual(after["trees"], before["trees"])

    # AC: a triggering run's executors live in `triggering/`, outside every
    # skill, so a summary naming only the skill would under-describe the
    # instrument that produced it.
    def test_triggering_run_also_names_the_triggering_executors(self) -> None:
        repo = self.root / "triggering-repo"
        (repo / "skills" / "demo").mkdir(parents=True)
        (repo / "triggering").mkdir(parents=True)

        def git(*args: str) -> str:
            completed = subprocess.run(
                ["git", *args],
                cwd=repo,
                text=True,
                capture_output=True,
                check=True,
            )
            return completed.stdout.strip()

        git("init", "-q")
        git("config", "user.email", "a@example.com")
        git("config", "user.name", "a")
        (repo / "skills" / "demo" / "SKILL.md").write_text("p\n", encoding="utf-8")
        (repo / "triggering" / "runner.py").write_text("r\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "-m", "first")

        with mock.patch.object(record_eval_run, "REPOSITORY_ROOT", repo):
            identity = record_eval_run.candidate_identity(
                "demo", record_eval_run.TRIGGERING_SUITE
            )

        self.assertEqual(
            sorted(identity["trees"]), ["skills/demo", "triggering"]
        )
```

- [ ] **Step 2: Update the two call sites that pass no arguments**

`candidate_identity` is called with no arguments in two other tests. Both are
about worktree cleanliness and do not care which skill ran, so pass the same
values the new tests use. In
`test_a_previous_summary_does_not_make_the_next_run_look_dirty` and
`test_real_dirt_still_makes_a_run_unclean`, change each

```python
            identity = record_eval_run.candidate_identity()
```

to

```python
            identity = record_eval_run.candidate_identity(
                "demo", record_eval_run.FORWARD_SUITE
            )
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python3 -m unittest scripts.tests.test_record_eval_run -v`

Expected: FAIL. All three new tests —
`test_candidate_identity_survives_a_rebase_onto_a_moved_base`,
`test_candidate_identity_survives_a_squash_that_keeps_the_content`, and
`test_triggering_run_also_names_the_triggering_executors` — raise
`TypeError: candidate_identity() takes 0 positional arguments but 2 were given`.

This failure is the point of the task: the rebase it models is the one the old
test avoided, and the old test's passing is what let the false claim into
`AGENTS.md`.

- [ ] **Step 4: Add `subtree_paths` and extend `candidate_identity`**

In `scripts/record_eval_run.py`, insert `subtree_paths` immediately after the
`RESULTS_PATH_MARKER` assignment and before `candidate_identity`:

```python
def subtree_paths(skill: str, suite: str) -> list[str]:
    """Name the paths whose content decides what a run of this suite read.

    The skill directory holds both the prose under measurement and, at
    `scripts/evals/`, the executor that produced the evidence — which is the
    pair a re-record at the shipping head exists to keep together. A
    triggering run's executors live in `triggering/` instead, outside every
    skill, so naming only the skill would under-describe the instrument.
    """

    paths = [f"skills/{skill}"]
    if suite == TRIGGERING_SUITE:
        paths.append("triggering")
    return paths
```

Then replace `candidate_identity`'s signature, docstring, and return statement.
The `git` helper and the `status` block above it are unchanged:

```python
def candidate_identity(skill: str, suite: str) -> dict:
    """Bind the run to the content that produced it.

    `trees` is the durable half. `sha` and `tree` are both branch-local: a
    rebase onto a moved `main` rewrites the commit and changes the
    whole-repository tree through files outside the skill entirely, so neither
    survives one. A subtree the change never touched is undisturbed by
    unrelated files moving, which is why it is `trees` a later reader should
    expect to resolve.

    `worktree_clean` is left unknown rather than asserted when git cannot be
    read: an empty `git status` and a failed `git status` are the same string,
    and defaulting to `True` would let a summary claim the strongest available
    provenance on the strength of a command that never ran.
    """
```

and the return:

```python
    trees = {}
    for path in subtree_paths(skill, suite):
        resolved = git("rev-parse", f"HEAD:{path}")
        if resolved is not None:
            trees[path] = resolved
    return {
        "sha": git("rev-parse", "HEAD"),
        "tree": git("rev-parse", "HEAD^{tree}"),
        "trees": trees,
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "worktree_clean": None if relevant is None else not relevant,
    }
```

A path that does not resolve is omitted rather than recorded as `None`, for the
same reason `worktree_clean` is left unknown: a key whose value is `null` reads
in the guard like a citation to check, and there is nothing there to check.

- [ ] **Step 5: Pass `skill` and `suite` at the call site**

In `build_summary`, at `scripts/record_eval_run.py:513`, change

```python
        "candidate": candidate_identity(),
```

to

```python
        "candidate": candidate_identity(skill, suite),
```

Both names are already parameters of `build_summary`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m unittest scripts.tests.test_record_eval_run -v` Expected: PASS,
all tests.

- [ ] **Step 7: Run the full gate**

```bash
just format && just lint && just test
```

Expected: all pass.

- [ ] **Step 8: Add the changelog entry**

Under a `## 2026-08-16 — ...` heading at the top of `CHANGELOG.md` (the heading
already exists from the design commit; add this entry above the existing one,
newest first), with no SHA — it has not landed:

```markdown
- feat(evals): record the subtree identity that survives a rebase —
  `candidate.tree` was `git rev-parse HEAD^{tree}`, the whole repository's, so
  a rebase onto a moved `main` changed it through files outside the skill and
  the recorded identity resolved to nothing. `candidate.trees` now maps each
  path whose content decided what the run read — `skills/<skill>` always, and
  `triggering` as well for a triggering-suite run, whose executors live outside
  every skill — to that path's subtree hash. The test that had asserted the old
  claim passed only by simulating a rebase as a new parent over an identical
  tree, which is the one thing a real rebase never is; it now models a base
  that moved, and fails against the old behavior.
```

- [ ] **Step 9: Commit**

```bash
cat >/tmp/commit-msg.md <<'EOF'
feat(evals): record the subtree identity that survives a rebase

## Summary

- Add `subtree_paths()` and record `candidate.trees`, a map from repository
  path to that path's subtree hash
- Take `skill` and `suite` in `candidate_identity()`, so a triggering run also
  names `triggering/`
- Replace the test that asserted the disproved durability claim with one that
  models a real rebase onto a moved base

## Why

`candidate.tree` names the whole repository, so a rebase onto a moved `main`
changes it through files outside the skill entirely. The test that was supposed
to hold the claim honest simulated a rebase as a new parent over an identical
tree — the one shape a real rebase never has — so it passed while the claim it
guarded was false. The replacement moves a file outside the skill, and fails
against the old behavior.
EOF
git add scripts/record_eval_run.py scripts/tests/test_record_eval_run.py CHANGELOG.md
git commit -F /tmp/commit-msg.md
```

______________________________________________________________________

### Task 2: Backfill the 23 summaries that can still be derived

**Files:**

- Modify (data): 23 files under `skills/*/evals/results/*.json`
- No script is added to the repository. The derivation is a one-shot migration
  with nothing left to run afterward; its exact text lives in this plan so a
  reviewer can reproduce it.

**Interfaces:**

- Consumes: `candidate.sha` from each summary; the path selection Task 1 encoded
  in `subtree_paths`.

- Produces: `candidate.trees` in 23 files. Task 3's guard checks them, and its
  vacuity test depends on this task having run — which is why the backfill comes
  first: the guard would otherwise have to be committed red.

- [ ] **Step 1: Run the derivation**

Save this as `/tmp/backfill_eval_trees.py` and run it from the repository root
with `python3 /tmp/backfill_eval_trees.py`:

```python
"""Derive `candidate.trees` for every summary still naming a reachable commit.

This is a computation over what each file already carries, not an addition to
it: `git rev-parse <recorded sha>:<path>` could not have come out differently
had the field existed when the summary was written. That is what separates it
from backfilling a landing commit, which would assert something decided after
the run by a merge that had not happened yet.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if not (ROOT / "AGENTS.md").is_file():
    ROOT = Path.cwd()

FORWARD_SUITE = "forward"
TRIGGERING_SUITE = "triggering"


def git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(ROOT), *arguments), capture_output=True, text=True
    )


reachable = set(git("rev-list", "HEAD").stdout.split())
written = 0

for summary in sorted(ROOT.glob("skills/*/evals/results/*.json")):
    recorded = json.loads(summary.read_text(encoding="utf-8"))
    candidate = recorded.get("candidate") or {}
    sha = candidate.get("sha")
    if candidate.get("trees") or sha not in reachable:
        continue

    suite = recorded.get("suite")
    if suite is None:
        # A summary predating the `suite` field is a forward run — unless its
        # name says otherwise, in which case guessing would silently record
        # the wrong path set, so stop instead.
        named = [s for s in (TRIGGERING_SUITE,) if s in summary.name]
        if named:
            sys.exit(f"{summary}: no recorded suite, but its name says {named}")
        suite = FORWARD_SUITE

    skill = summary.parents[2].name
    paths = [f"skills/{skill}"]
    if suite == TRIGGERING_SUITE:
        paths.append(TRIGGERING_SUITE)

    trees = {}
    for path in paths:
        resolved = git("rev-parse", f"{sha}:{path}")
        if resolved.returncode:
            sys.exit(f"{summary}: {path} does not exist at {sha}")
        trees[path] = resolved.stdout.strip()

    candidate["trees"] = trees
    summary.write_text(
        json.dumps(recorded, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    written += 1

print(f"backfilled {written} summaries")
```

Expected output: `backfilled 23 summaries`.

If it prints any other count, stop and report it rather than continuing — the
set was verified at 23 against this tree, and a different number means the tree
moved or the selection logic diverged from the design.

- [ ] **Step 2: Verify the diff is pure addition**

```bash
git diff --stat -- 'skills/*/evals/results/*.json'
git diff -- 'skills/*/evals/results/*.json' | grep -c '^-[^-]'
```

Expected: 23 files changed, and the second command prints `0` — every existing
line is untouched, because all 82 summaries already round-trip byte-identically
under `json.dumps(..., indent=2, sort_keys=True)`.

- [ ] **Step 3: Verify one derivation by hand**

Pick any changed file and confirm the recorded hash is what its own `sha`
yields, so the reviewer is not taking the script's word for it:

```bash
python3 - <<'EOF'
import glob, json, subprocess
for path in sorted(glob.glob("skills/*/evals/results/*.json"))[:200]:
    candidate = (json.loads(open(path).read()).get("candidate") or {})
    for repo_path, digest in (candidate.get("trees") or {}).items():
        expected = subprocess.run(
            ["git", "rev-parse", f"{candidate['sha']}:{repo_path}"],
            capture_output=True, text=True,
        ).stdout.strip()
        assert expected == digest, (path, repo_path, expected, digest)
print("every recorded subtree matches its own recorded sha")
EOF
```

Expected: `every recorded subtree matches its own recorded sha`.

- [ ] **Step 4: Confirm every derived entry is reachable**

Task 3's guard does not exist yet, so check the property it will enforce
directly. This is what makes the guard land green rather than red:

```bash
python3 - <<'EOF'
import glob, json, subprocess
def subtrees(path):
    commits = subprocess.run(["git", "rev-list", "HEAD"], capture_output=True, text=True).stdout.split()
    listed = subprocess.run(
        ["git", "cat-file", "--batch-check=%(objectname) %(objecttype)"],
        input="".join(f"{c}:{path}\n" for c in commits), capture_output=True, text=True,
    ).stdout
    return {line.split()[0] for line in listed.splitlines() if line.endswith("tree")}
cache, cited, dangling = {}, 0, []
for summary in sorted(glob.glob("skills/*/evals/results/*.json")):
    trees = (json.loads(open(summary).read()).get("candidate") or {}).get("trees") or {}
    for path, digest in trees.items():
        cited += 1
        if digest not in cache.setdefault(path, subtrees(path)):
            dangling.append((summary, path, digest))
print(f"{cited} entries cited, {len(dangling)} unreachable")
assert not dangling, dangling
EOF
```

Expected: `24 entries cited, 0 unreachable` — 23 summaries, one of which is a
triggering run carrying two paths.

- [ ] **Step 5: Run the full gate**

```bash
just format && just lint && just test
```

Expected: all pass, with `just test` now fully green.

- [ ] **Step 6: Add the changelog entry**

```markdown
- fix(evals): derive the durable identity of every summary that still names a
  reachable commit — 23 of the 82 summaries gain `candidate.trees` computed
  from the commit each already carries, and the other 59 keep none. The
  derivation asserts nothing the recorder did not hold:
  `git rev-parse <recorded sha>:<path>` could not have come out differently had
  the field existed when the summary was written, which is what separates it
  from backfilling a landing commit — a fact decided after the run by a merge
  that had not happened yet. One of the 23 is a triggering-suite run and needs
  both its skill path and `triggering`. The 59 measured content that no longer
  exists in any clone but its author's; unlike the changelog's citations, there
  is nothing left to recover.
```

- [ ] **Step 7: Commit**

```bash
cat >/tmp/commit-msg.md <<'EOF'
fix(evals): derive the durable identity of every recoverable summary

## Summary

- Backfill `candidate.trees` into the 23 summaries whose recorded `sha` is
  still reachable from `HEAD`
- Leave the other 59 without the field, recorded as unresolvable rather than
  pretended into evidence

## Why

The derivation is a computation over what each file already carries, not an
addition to it. `git rev-parse <recorded sha>:<path>` is reproducible by any
reader from the file alone and could not have come out differently had the
field existed when the summary was written — which is what separates it from a
backfilled landing commit, decided after the run by a merge that had not
happened yet.

All 23 derive and every derived entry is reachable, so the new guard goes green
on real evidence rather than on an empty set. The remaining 59 measured content
that exists in no clone but their author's.
EOF
git add 'skills/*/evals/results/*.json' CHANGELOG.md
git commit -F /tmp/commit-msg.md
```

______________________________________________________________________

### Task 3: Guard every recorded subtree against reachability

**Files:**

- Create: `scripts/tests/test_eval_candidate_citations.py`
- Reference (do not modify): `scripts/tests/test_changelog_citations.py`, the
  sibling this is modeled on

**Interfaces:**

- Consumes: `candidate["trees"]`, as newly written by Task 1 and backfilled into
  the 23 recoverable summaries by Task 2.

- Produces: a test module `just test` picks up through
  `python3 -m unittest discover -s scripts/tests -p 'test_*.py'` (the
  `test-plugins` recipe). Nothing imports it.

- [ ] **Step 1: Write the guard**

Create `scripts/tests/test_eval_candidate_citations.py`:

```python
"""Every subtree an eval summary cites has to still name reachable content.

A summary's `candidate.trees` is the only machine-checkable link from a
recorded measurement to the content it measured, and its failure mode is
silent: a subtree hash that resolves to nothing reads exactly like one that
resolves, so nobody discovers the rot until they try to follow it.

The check is reachability from `HEAD`, and under subtree identity it is
well-defined at every point in a change's life. A summary recorded on an open
branch names a subtree of that branch's own history, rebase included, because
a rebase that leaves the skill alone leaves its subtree alone. So this module
needs no unlanded-branch exemption, unlike its changelog sibling.

It turns red in two cases, and both are real. A pull request carrying eval
evidence was squash-merged, which keeps one tree per pull request and discards
the intermediate states eval evidence measures by construction — `AGENTS.md`
requires such a pull request to merge as a merge commit for exactly this
reason. Or a rebase resolved conflicts inside the skill directory, in which
case the recorded run measured content that never shipped and the answer is to
re-record.
"""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SUMMARIES = sorted(REPOSITORY_ROOT.glob("skills/*/evals/results/*.json"))


def _git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(REPOSITORY_ROOT), *arguments),
        capture_output=True,
        text=True,
    )


def _citations() -> list[tuple[str, str, str]]:
    """Return (summary path, repository path, subtree hash) for every citation.

    A summary carrying no `trees` is not a failure. Those predate the field
    and could not have their identity derived from a commit that still
    resolves; `AGENTS.md` records them as branch-local and unresolvable.
    """

    found = []
    for summary in SUMMARIES:
        recorded = json.loads(summary.read_text(encoding="utf-8"))
        trees = (recorded.get("candidate") or {}).get("trees") or {}
        for path, digest in sorted(trees.items()):
            found.append(
                (str(summary.relative_to(REPOSITORY_ROOT)), path, digest)
            )
    return found


def _reachable_subtrees(path: str) -> set[str]:
    """Every hash `path` has had across the commits reachable from `HEAD`."""

    commits = _git("rev-list", "HEAD").stdout.split()
    request = "".join(f"{commit}:{path}\n" for commit in commits)
    listed = subprocess.run(
        (
            "git",
            "-C",
            str(REPOSITORY_ROOT),
            "cat-file",
            "--batch-check=%(objectname) %(objecttype)",
        ),
        input=request,
        capture_output=True,
        text=True,
    ).stdout
    return {
        line.split()[0] for line in listed.splitlines() if line.endswith("tree")
    }


class EvalCandidateCitationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.citations = _citations()

    def test_some_summary_cites_a_subtree(self) -> None:
        # Without this, deleting the field from every summary — or writing it
        # under a key this module does not read — would turn the reachability
        # check green by emptying it, which is the failure this module exists
        # to prevent rather than reproduce.
        self.assertTrue(
            self.citations,
            "no summary under skills/*/evals/results/ carries "
            "candidate.trees, so the reachability check below is vacuous",
        )

    def test_every_cited_subtree_is_reachable_from_head(self) -> None:
        if _git("rev-parse", "--git-dir").returncode != 0:
            self.skipTest("not a git repository, so no history to check against")
        if _git("rev-parse", "--is-shallow-repository").stdout.strip() == "true":
            self.fail(
                "history is shallow, so an unreachable subtree cannot be told "
                "apart from an unfetched one; run `git fetch --unshallow`"
            )

        reachable: dict[str, set[str]] = {}
        dangling = []
        for summary, path, digest in self.citations:
            if path not in reachable:
                reachable[path] = _reachable_subtrees(path)
            if digest not in reachable[path]:
                dangling.append((summary, path, digest))

        self.assertEqual(
            dangling,
            [],
            "eval summaries cite subtrees that are not reachable from HEAD:\n"
            + "\n".join(
                f"  {summary}\n    {path} @ {digest}"
                for summary, path, digest in dangling
            )
            + "\n\nA recorded subtree stays resolvable only while the commit "
            "carrying it does\n(see AGENTS.md). A pull request touching "
            "skills/*/evals/results/ merges as a\nmerge commit rather than a "
            "squash for this reason. If one was squashed, the\nmeasured "
            "content is gone and the remedy is to re-record against a state "
            "that\nstill exists, saying in the summary that the original is "
            "unrecoverable.",
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it and verify it passes on real evidence**

Run: `python3 -m unittest scripts.tests.test_eval_candidate_citations -v`

Expected: PASS, both tests. `test_some_summary_cites_a_subtree` is satisfied by
the 23 summaries Task 2 backfilled, and every one of their 24 entries is
reachable.

A pass here proves nothing on its own — a check that cannot fail passes too.
Step 3 is what earns it.

- [ ] **Step 3: Verify the reachability check is capable of failing**

Prove the guard can go red before trusting it, and prove both of its tests can.
First, mutate one backfilled summary to carry a subtree that names nothing:

```bash
python3 - <<'EOF'
import json
from pathlib import Path
p = Path("skills/ready-ticket/evals/results/2026-08-15T173118Z-0003-before.json")
d = json.loads(p.read_text())
d["candidate"]["trees"] = {"skills/ready-ticket": "0" * 40}
p.write_text(json.dumps(d, indent=2, sort_keys=True) + "\n")
EOF
python3 -m unittest scripts.tests.test_eval_candidate_citations -v
```

Expected: `test_every_cited_subtree_is_reachable_from_head` FAILS, naming that
file, that path, and `0000...`.

Restore it:

```bash
git checkout -- skills/ready-ticket/evals/results/2026-08-15T173118Z-0003-before.json
```

Then prove the vacuity test can fail too, by stripping every `trees` entry into
a scratch copy of the tree rather than the real one:

```bash
python3 - <<'EOF'
import importlib.util, unittest
from pathlib import Path
spec = importlib.util.spec_from_file_location(
    "guard", "scripts/tests/test_eval_candidate_citations.py"
)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
guard.SUMMARIES = []          # the state before Task 2 backfilled anything
case = guard.EvalCandidateCitationTests("test_some_summary_cites_a_subtree")
guard.EvalCandidateCitationTests.setUpClass()
print(unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([case])))
EOF
```

Expected: FAIL with "no summary under skills/\*/evals/results/ carries
candidate.trees". That is the state the repository was in before Task 2, and it
is what the test exists to catch if the field is ever removed or renamed.

- [ ] **Step 4: Run the full gate**

```bash
just format && just lint && just test
```

Expected: all pass. Confirm the working tree is clean before committing — Step 3
mutated a summary and restored it:

```bash
git status --porcelain
```

Expected: only `scripts/tests/test_eval_candidate_citations.py` and
`CHANGELOG.md` appear.

- [ ] **Step 5: Add the changelog entry**

```markdown
- test(evals): hold every recorded subtree to reachability from `HEAD` —
  `scripts/tests/test_eval_candidate_citations.py` fails when a summary's
  `candidate.trees` names content no commit reachable from `HEAD` carries,
  which is the same silent rot `scripts/tests/test_changelog_citations.py`
  catches for the changelog: a hash resolving to nothing reads exactly like one
  that resolves. Unlike its sibling it needs no unlanded-branch exemption,
  because a subtree recorded on an open branch stays reachable from that
  branch's own history across a rebase. A summary carrying no `trees` passes —
  those predate the field and are recorded as unresolvable rather than
  pretended into evidence.
```

- [ ] **Step 6: Commit**

```bash
cat >/tmp/commit-msg.md <<'EOF'
test(evals): hold every recorded subtree to reachability from HEAD

## Summary

- Add `scripts/tests/test_eval_candidate_citations.py`, failing when a
  summary's `candidate.trees` names content unreachable from `HEAD`
- Guard against vacuity: the module fails if no summary cites a subtree at all

## Why

A subtree hash that resolves to nothing reads exactly like one that resolves,
which is how 59 of this repository's 82 summaries came to name commits nobody
can retrieve without anyone noticing. The check needs no unlanded-branch
exemption, unlike the changelog's: a subtree recorded on an open branch is
reachable from that branch's own history across a rebase, so it is well-defined
at every point in a change's life.
EOF
git add scripts/tests/test_eval_candidate_citations.py CHANGELOG.md
git commit -F /tmp/commit-msg.md
```

______________________________________________________________________

### Task 4: State the merge policy and correct the durability claim

**Files:**

- Modify: `AGENTS.md:86-97` (the `candidate.tree` paragraph)
- Modify: `AGENTS.md:95-97` (the grandfathering sentence about `model`)
- Modify: `skills/babysit-pr/SKILL.md:398`
- Test: `scripts/tests/test_record_eval_run.py`, class `NormIsStatedTests`

**Interfaces:**

- Consumes: nothing from earlier tasks at runtime. The prose describes the
  behavior Tasks 1–3 built.

- Produces: no callable surface.

- [ ] **Step 1: Write the failing test**

In `scripts/tests/test_record_eval_run.py`, add to `NormIsStatedTests`, after
`test_agents_md_states_the_norm_and_the_results_convention`:

```python
    def test_agents_md_states_the_merge_method_the_evidence_depends_on(
        self,
    ) -> None:
        """AC: the rule that keeps a recorded subtree resolvable is written
        where a contributor and a merging agent both read it.

        A recorded subtree resolves only while a commit carrying it stays
        reachable, so the merge method is load-bearing rather than stylistic
        and its failure is unrepairable. Prose that omits it leaves the guard
        firing on `main` with nothing to point the citation at.
        """

        agents = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")

        self.assertIn("candidate.trees", agents)
        self.assertIn("merge commit", agents)
        self.assertIn("skills/*/evals/results/", agents)
```

- [ ] **Step 2: Run it to verify it fails**

Run:
`python3 -m unittest scripts.tests.test_record_eval_run.NormIsStatedTests -v`

Expected: FAIL on `assertIn("candidate.trees", agents)` — `AGENTS.md` still
describes only `candidate.tree`.

- [ ] **Step 3: Replace the durability paragraph in `AGENTS.md`**

Replace the paragraph beginning "Each summary also carries `candidate.tree`" and
ending "...they are not backfilled." with:

```markdown
Each summary also carries `candidate.trees` — a map from repository path to
that path's subtree hash, holding `skills/<skill>` for every run and
`triggering` as well for a triggering-suite run, whose executors live outside
every skill — `candidate.tree`, the whole repository's
`git rev-parse HEAD^{tree}`, and, for a real-model run, `model`, the exact
`--model` the recorded command passed.

`sha` and `tree` are both branch-local. A rebase onto a moved `main` rewrites
the commit and changes the repository tree through files outside the skill
entirely, so neither survives one, and a squash-merge then discards both
outright. It is `trees` a reader should expect to still resolve, because
unrelated files moving cannot disturb a subtree the change never touched.

A subtree resolves only while a commit carrying it stays reachable, so a pull
request that adds or changes any file under `skills/*/evals/results/` merges as
a merge commit rather than a squash. A squash keeps one tree per pull request,
and the states eval evidence measures are intermediate by construction: a
before-stage run measures a new corpus against the old prose, and a superseded
after-stage run measures prose a later commit changed. Squashing such a pull
request destroys the measured content in every clone but the author's, and no
later repair recovers it — the only remedy is to re-record against a state that
still exists and to say in the summary that the original is unrecoverable.
`scripts/tests/test_eval_candidate_citations.py` is what turns red when this
goes wrong, and `carve-changesets` already defaults its merge method to `merge`.

`model` exists because a before/after pair taken across a model update compares
two different subjects wearing the same tier name; a diff is drawn only when the
compared runs' tier, suite, and model all match. A deterministic run records no
model — there is none to name. Summaries recorded before these fields existed
carry `trees` only where it could be derived from a commit they still name, and
carry no `model` at all: no model can be recovered for them after the fact, and
they are not backfilled. The derivation that is backfilled,
`git rev-parse <recorded sha>:<path>`, is a computation over what the file
already carries and could not have come out differently had the field existed
when it was written. A landing commit is not backfilled for the opposite
reason: which commit carries a summary onto `main` is decided after the run by a
merge that has not happened yet, so writing it in would add a claim nothing in
the file supports.
```

- [ ] **Step 4: Correct the `babysit-pr` example**

At `skills/babysit-pr/SKILL.md:398`, change

```text
next_action: caller may merge via repository-approved squash method
```

to

```text
next_action: caller may merge via the repository-approved merge method
```

This is editorial and carries no eval-evidence obligation: line 357 already
obliges the caller to use "the repository-approved merge method", so the example
is being brought into line with the rule rather than changing one.

- [ ] **Step 5: Run the test to verify it passes**

Run:
`python3 -m unittest scripts.tests.test_record_eval_run.NormIsStatedTests -v`
Expected: PASS.

- [ ] **Step 6: Run the full gate**

```bash
just format && just lint && just test
```

Expected: all pass. `just lint` runs `skills-ref validate`, which must stay
green across the `babysit-pr` edit.

- [ ] **Step 7: Add the changelog entry**

```markdown
- docs: state the merge method the eval evidence depends on, and correct what
  `AGENTS.md` claims survives — the file told a reader to trust `candidate.tree`
  over `candidate.sha` on the grounds that content is identical under rebase and
  squash where a commit is not. It is not: `tree` is the whole repository's, so
  a rebase onto a moved `main` changes it through files outside the skill. Both
  are now stated as branch-local, `candidate.trees` is named as the durable
  half, and the rule that makes it durable is written down — a pull request
  touching `skills/*/evals/results/` merges as a merge commit, because a squash
  keeps one tree per pull request while the states eval evidence measures are
  intermediate by construction. `babysit-pr`'s example output block is brought
  into line with the obligation its own prose already carried.
```

- [ ] **Step 8: Commit**

```bash
cat >/tmp/commit-msg.md <<'EOF'
docs: state the merge method the eval evidence depends on

## Summary

- Correct `AGENTS.md`: `sha` and `tree` are both branch-local, and
  `candidate.trees` is the half a reader should expect to resolve
- State the merge-commit rule for pull requests touching
  `skills/*/evals/results/`, and why its failure is unrepairable
- Record why the subtree derivation is backfilled where a landing commit is not
- Bring `babysit-pr`'s example output into line with the obligation at
  `SKILL.md:357`

## Why

The claim that `tree` outlives `sha` was false in the rebase case, and it was
the claim a contributor was told to rely on. Correcting it without stating the
merge method would leave the corrected claim just as false, because a subtree
resolves only while a commit carrying it stays reachable — and a squash-merge
of a pull request carrying eval evidence destroys the measured content in every
clone but the author's.

The `babysit-pr` edit is editorial: line 357 already obliges the caller to use
the repository-approved merge method, so the example at line 398 is being
brought into line with a rule rather than given a new one. No obligation
changes, so the eval-backed change norm does not apply.
EOF
git add AGENTS.md skills/babysit-pr/SKILL.md scripts/tests/test_record_eval_run.py CHANGELOG.md
git commit -F /tmp/commit-msg.md
```

______________________________________________________________________

## Merging this work

This pull request adds files under `skills/*/evals/results/` — Task 2 modifies
23 of them — so by the rule it installs, **it merges as a merge commit, not a
squash**. Merging it with a squash would be the first violation of its own
policy, and would discard the intermediate states its commits carry.

The eval-backed change norm does not apply to this work: `AGENTS.md` is
repository prose rather than a skill's, and the one skill edit is editorial. Say
so in the pull request body rather than leaving a reviewer to derive it.

Two things to state plainly in the pull request body:

- 59 summaries remain unresolvable and cannot be repaired. Unlike #236's
  citations, the history they should have named is on no branch — the pull
  request repairs what is derivable and says the rest is gone.
- Both of the guard's tests were verified capable of failing, per Task 3 Step 3,
  rather than assumed to work because they are green.

<!-- inline reference link definitions. please keep alphabetized -->

[spec]: ../specs/2026-08-16-eval-candidate-identity-design.md
