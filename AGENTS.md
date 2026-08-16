# Agent Guidelines

This repo is a monorepo of agent skills under `skills/`.

## Working Model

- Treat each skill folder as the unit of change.
- Keep changes local to the relevant skill unless the task is clearly
  cross-cutting.
- Prefer direct, runnable scripts under each skill’s `scripts/` directory.

## Required Checks

Before every commit and push, run:

```bash
just format
just lint
just test
```

`just lint` includes `skills-ref validate` and will auto-install it into `.venv`
if missing (network required).

## Eval Evidence for Skill-Prose Changes

A change to a skill's normative prose — its `SKILL.md` or any `references/` file
that governs behavior — ships with recorded model-behavior evidence. Editorial
changes that alter no obligation do not.

- **Where a real-model executor exists**, run the skill's evals with it before
  and after the change and commit both summaries. `implement-ticket` is the
  skill this covers today; `implement-epic` is covered through the same corpus.
- **Where one does not**, record the skill's deterministic corpus replay —
  `carve-changesets` and `review-fix-loop` have one. Any deterministic run
  carries gap text stating that no model read the prose, whether or not a
  real-model executor exists for that skill: the gap describes what the run
  collected, not what the registry offers.
- **Where `just eval-record <skill>` has no corpus registered for that target**,
  it says so instead of recording something — that gap describes what the
  recorder can drive, not whether a corpus exists at all. The review-lens skills
  are the current example: `review-suite/evals/` ships seven corpora (one under
  `corpus/`, six under `strata/`) that load `review-code-change`,
  `review-code-simplicity`, or `review-solution-simplicity` as `target_skill` —
  `review-correctness`'s prose reaches the reviewer as a
  `target_skill_dependency` of the `review-code-change`-targeted corpora rather
  than as a directly named target — but the runner exposes `--artifact-dir`,
  `--attempts-out`, and `--report-out` rather than the `--output-dir` the
  recorder appends, and its exit codes report evaluation integrity rather than
  case outcomes, so `just eval-record` can't drive any of them until that
  interface is adapted. State the gap in the pull request, naming the corpus
  that already exists when one does rather than reporting it as absent. Do not
  substitute the skill's unit tests: they cannot observe `SKILL.md` prose, so a
  summary built from them would carry no cases, no totals, and no diff.

Record a run with:

```bash
just eval-record implement-ticket --stage before
```

Summaries land in `skills/<skill>/evals/results/` as one JSON file per run,
carrying the recorded date, the tier and exact executor command, the candidate
SHA, per-case pass/fail, each case's own observation, and the diff against that
skill's previous recorded run. They are committed evidence, not a CI gate; no
check blocks on them.

A run also names its **suite**. `forward` asks whether a skill's prose governs
behavior once the skill is loaded; `triggering` asks the prior question, whether
it is the one that loads at all — `just eval-record <skill> --suite triggering`,
with `triggering/` owning that corpus. A non-forward suite is part of the
summary's filename, and a diff is scoped to the same tier **and** the same
suite, because comparing across either reports a change of question as
behavioral movement.

Per-case observations are recorded rather than reduced to pass/fail, because a
tier may report more than an outcome — the triggering corpus's description tier
reports how many of its repetitions agreed. Variance is the metric there, and a
case degrading from unanimous to a bare majority still records `pass`.

Record from a committed, clean tree, so the summary's `candidate.sha` names a
commit a later reader can resolve, and commit the summaries on top. A run
recorded from a dirty tree — or from a commit later amended away — names a tree
nobody else can retrieve, which is the one thing the record exists to supply.

Each summary also carries `candidate.tree`, the committed content's
`git rev-parse HEAD^{tree}`, and — for a real-model run — `model`, the exact
`--model` the recorded command passed. `sha` names the commit, which rebase
rewrites and squash-merge discards outright; `tree` names the content, which is
identical under both, so it is `tree`, not `sha`, that a reader should expect to
still resolve once a change has landed on `main`. `model` exists because a
before/after pair taken across a model update compares two different subjects
wearing the same tier name; a diff is drawn only when the compared runs' tier,
suite, and model all match. A deterministic run records no model — there is none
to name. Summaries recorded before this field existed carry no `model` at all
and are branch-local and unattributed: no model can be recovered for them after
the fact, and they are not backfilled.

Summaries already written under `evals/results/` are the one exemption, and it
is narrow by construction. Recording several skills in sequence writes a summary
per skill, so without the exemption only the first run of a batch could report a
clean tree and every later one would carry false dirt. Sibling evidence cannot
change what an eval read. Any other uncommitted change still makes a run
unclean.

Each run records one of three statuses. `completed` and `failed` both mean the
evaluations ran, and a `failed` run commits its failures. `attempted` means they
could not run at all — the real-model tier needs the `claude` CLI with model
access, and where the environment lacks it the recorder still writes the attempt
with the observed limitation and exits non-zero. Commit that record and say in
the PR that the model-behavior evidence is deferred to the first capable run.
Recording the attempt is required; skipping it silently is not an option the
norm offers.

[`docs/skill-authoring.md`](docs/skill-authoring.md) owns why this evidence has
to be worth what it is, under "The eval-backed change norm". Note that the norm
asks whether a skill's *prose* still governs an agent's behavior, while the same
document's testing doctrine asks whether a change's *code* does what its ticket
said. Neither satisfies the other.

## Skill Conventions

- [`docs/skill-authoring.md`](docs/skill-authoring.md) is the authoring standard
  for every new skill and for any edit that changes an existing skill's
  normative behavior. Follow it for descriptions, body form, pressure and
  micro-testing, the contractual layer, peer precedence, and context economy.
  Its testing doctrine reaches further than skill authoring: it governs test
  evidence for any change to this repository's code.

- Skill root contains `SKILL.md` and optional `scripts/`, `references/`, and
  `assets/`.

- Tests live under `scripts/tests/` and should use `unittest`.

- A test module that imports a sibling helper establishes its own `sys.path`
  entry from `__file__`, rather than relying on the one discovery happens to
  supply:

  ```python
  TESTS_DIR = Path(__file__).resolve().parent
  if str(TESTS_DIR) not in sys.path:
      sys.path.insert(0, str(TESTS_DIR))

  from helpers import compact  # noqa: E402
  ```

  Without it the module imports only under `unittest discover`, and the
  module-path form ticket bodies name as required verification —
  `python3 -m unittest scripts.tests.test_skill_authoring_doc` — errors with
  `ModuleNotFoundError` before any assertion runs, so a later reader cannot
  reproduce the recorded evidence. `scripts/tests/test_suite_invocation.py`
  holds the root suite to this; `skills/carve-changesets/scripts/tests/` and
  `skills/review-fix-loop/scripts/tests/` do not yet carry the shim and are
  discovery-only.

- Record intermediate record-keeping data under a skill-local dot directory (for
  example, `.skill-state/` or `.<skill-name>/`) and keep it out of git history
  via a skill-local `.gitignore`.

## Safety

- Do not use destructive git commands (e.g., `git reset --hard`) unless
  explicitly requested.
- Avoid rewriting or mutating user-specified reference branches as part of skill
  workflows.

## Git Workflow

- Use Conventional Commits for commit messages (e.g., `feat: ...`, `fix: ...`,
  `chore: ...`).

- Changelog: maintain `CHANGELOG.md` in a daily format.

- Changelog: create or update a section for today near the top:
  `## YYYY-MM-DD — <day summary>`.

- Changelog: summarize the day in that heading.

- Changelog: order entries with newest days first and newest commits first
  within a day.

- Changelog: a backfilled SHA names the commit that carried the entry onto
  `main` — the squash-merge commit for a squash-merged pull request, and the
  authoring commit only where it survives, as under a merge-commit pull request
  or a direct push to `main`. `main` is almost entirely squash-merged, and a
  squash discards every authoring commit the pull request held, so backfilling
  an authoring SHA leaves a citation that resolves to nothing while still
  reading like one that resolves.

- Changelog: backfill an entry only once it has landed on `main`. An entry added
  on the current branch cannot know which commit will carry it there, so it
  stays SHA-less until it does. Before adding a new entry, backfill every entry
  below it that has landed and still lacks a SHA — which is more than one
  whenever the previous pull request contributed several.

- Changelog: several entries citing one SHA is expected, not a mistake. A
  squash-merge commit carries every entry its pull request contributed, so each
  of those entries names it.

- Changelog: recover an entry's landing commit with
  `git log main --format='%H %s' -S'<the entry's first line>' -- CHANGELOG.md`,
  whose last line is the commit that introduced the entry.

- Changelog: omit the SHA for the new entry being added in the current commit.

- Changelog: format backfilled entries as `<commit title> (<full SHA>)`.

- Changelog: format new entries as `<commit title>`.

- Changelog: `scripts/tests/test_changelog_citations.py` holds the file to this:
  every SHA it cites in parentheses must name a commit reachable from `HEAD`. A
  backticked SHA outside parentheses is not a citation — the changelog uses that
  form to pin a peer repository's commit, which names history that cannot
  resolve here.

- Release process: [`docs/release-process.md`](docs/release-process.md)
  documents how a tagged release is prepared and cut, including the four version
  surfaces `scripts/validate_plugins.py` keeps in sync and operator-only tagging
  authority. `RELEASE-NOTES.md` is the narrative release history — distinct from
  `CHANGELOG.md`'s daily journal above.

- Avoid shell interpolation in commit and PR messages. Always write the full
  message to a temporary file and use file-based flags instead of inline `-m`
  strings.

  ```bash
  cat >/tmp/commit-msg.md <<'EOF'
  chore: initialize compris monorepo

  ## Summary
  - Add monorepo structure and CI

  ## Why
  - Establish consistent quality gates
  EOF
  git commit -F /tmp/commit-msg.md
  ```

  ```bash
  gh pr create --title "$TITLE" --body-file /tmp/pr-body.md
  ```

- If a ticket subject or title includes backticks, escape them as \`\`\` before
  placing the text into shell commands or temp files.

- Write commit bodies in Markdown. Summarize what changed and why it was added.
  Example of a good commit body:

  ```md
  ## Summary
  - Split eval path resolution to use `__file__`-relative paths
  - Fold `skills-ref validate` into `just lint`

  ## Why
  - Make scripts location-independent in the monorepo
  - Ensure skill validation always runs as part of lint
  ```

  Example of a bad commit body:

  ```md
  fixed stuff
  cleanups
  ```

- Push directly to `main` for small, self-contained changes.

- Use branches only for larger tasks that require multiple steps.

- When submitting a PR, rebase onto `main` first.
