<!--
RETAINED EXPERIMENTAL ARTIFACT — NOT SCHEDULED WORK.

This is the spec handed to `superpowers:writing-plans` for the experiment
recorded in 2026-08-12-writing-plans-behavioral-altitude.md. `linecap` is a
greenfield tool invented as neutral input: its acceptance criteria are stated
purely as observable command behavior, which is the property the experiment
tests. No ticket authorizes it and nothing in this repository implements it.
-->

# Spec: `linecap` — a repository file-size budget checker

## Outcome

A repository can run one command that reports every tracked file exceeding a
configured line budget and fails when any file exceeds it.

## Scope

- A `linecap` command-line tool, installed as a console entry point.
- A `linecap.toml` configuration file read from the repository root.
- A `--format` option selecting human-readable or JSON output.

## Non-goals

- Editing, splitting, or rewriting oversized files.
- Integration with any specific continuous-integration provider.
- Per-language parsing. A line is a line.

## Acceptance criteria

- [ ] Running `linecap` in a repository where no tracked file exceeds the budget
  prints `linecap: 0 files over budget` and exits 0.
- [ ] Running `linecap` in a repository where two tracked files exceed the
  budget exits 1 and prints one line per offending file, each naming the file's
  path, its line count, and the budget, ordered by descending line count.
- [ ] Running `linecap --format json` emits a single JSON object on stdout with
  the keys `budget`, `checked`, and `offenders`, where `offenders` is an array
  of objects each carrying `path` and `lines`. The exit-code rule is unchanged
  from the human-readable format.
- [ ] A `linecap.toml` containing `budget = 300` overrides the built-in default
  of 500, observable through the budget reported in both output formats.
- [ ] A `linecap.toml` containing `exclude = ["vendor/**"]` causes files under
  `vendor/` to be absent from both `checked` and `offenders`.
- [ ] Running `linecap` outside a Git repository exits 2, prints
  `linecap: not a git repository` on stderr, and prints nothing on stdout.
- [ ] Running `linecap --version` prints the package version and exits 0.

## Required verification

- The acceptance criteria above, each exercised against the installed
  command-line tool.
