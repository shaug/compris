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
- **Where the skill has no corpus at all**, `just eval-record` says so instead
  of recording something. State that gap in the pull request. Do not substitute
  the skill's unit tests: they cannot observe `SKILL.md` prose, so a summary
  built from them would carry no cases, no totals, and no diff.

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

- Changelog: before adding a new entry, backfill the full SHA onto the previous
  entry (which may be on an earlier day).

- Changelog: omit the SHA for the new entry being added in the current commit.

- Changelog: format backfilled entries as `<commit title> (<full SHA>)`.

- Changelog: format new entries as `<commit title>`.

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
