# Decomposition plan schema

The proposal phase stores one ephemeral JSON plan at
`.carve-changesets/plan.json`. Keep `.carve-changesets/` ignored and out of git.
The plan is authoritative only for changesets that have not been materialized;
live commit trailers, native PR topology, and mainline replace it in later
phases.

Successor sources and suffix recovery are deliberately absent from this schema.
They can exist only after materialization and publication, so their authority is
the exact live source refs, v3 commit trailers, native PR topology, remote
heads, and current mainline. Historical v1/v2 PR blocks are read-only adoption
evidence. A plan edit cannot create lineage, restamp a suffix, replace a
published candidate, or override a merged prefix.

## Minimal example

```json
{
  "feature_title": "Cloud host migration",
  "base_branch": "main",
  "source_branch": "feature/cloud-host-migration",
  "test_argv": ["just", "test"],
  "changesets": [
    {
      "slug": "rename-config-types",
      "description": "Rename config types without behavior changes.",
      "mode": "paths",
      "include_paths": ["src/config/**", "src/types/**"],
      "exclude_paths": [],
      "allow_partial_files": false,
      "commit_message": "refactor: rename config types",
      "pr_notes": ["No behavior changes."]
    },
    {
      "slug": "add-dual-write-path",
      "description": "Add the flag-guarded dual-write path.",
      "mode": "hunks",
      "include_paths": ["src/migration/**"],
      "exclude_paths": [],
      "allow_partial_files": true,
      "hunk_selectors": [
        {
          "file": "src/migration/write.ts",
          "contains": ["enableDualWrite"],
          "occurrence": 1
        }
      ],
      "commit_message": "feat: add dual-write path behind flag",
      "pr_notes": [
        "Introduces temporary flag enableDualWrite.",
        "A later changeset removes the accommodation."
      ]
    }
  ]
}
```

## Top-level fields

- `feature_title` (required string): shared title stem for the changeset PRs.
- `base_branch` (required string): mainline branch that precedes changeset 1.
- `source_branch` (required string): immutable review-ready branch to recompose.
- `test_argv` (optional string array): separately approved validation argv.
  Arguments are executed directly without implicit shell parsing. Use
  `["sh", "-lc", "<approved shell command>"]` only when shell semantics are
  intentional; see the
  [concrete shell migrations](cli.md#explicit-shell-migrations). An empty array
  records that no command has been approved yet.
- `changesets` (required non-empty array): ordered proposed changesets.

## Changeset fields

- `slug` (required string): stable concise intent identifier carried into the
  native commit trailers and human-readable PR prose.
- `description` (required string): independently reviewable goal and scope.
- `mode` (optional string): `paths` by default, `patch`, or `hunks`.
- `include_paths` (string array): glob patterns included by `paths`, or a coarse
  filter for `hunks`; required and non-empty for `paths`.
- `exclude_paths` (optional string array): glob patterns removed from the
  selected paths.
- `allow_partial_files` (optional boolean): whether a changeset may select only
  some textual hunks from a file; defaults to true.
- `patch_file` (required string for `patch`): a non-empty patch path, normally
  under `.carve-changesets/patches/`.
- `hunk_selectors` (required non-empty object array for `hunks`): explicit
  textual hunk selectors described below.
- `commit_message` (optional string): changeset commit subject/body before the
  required native metadata trailers are added.
- `pr_notes` (optional string array): scaffolding, flags, intentional
  incompleteness, and later changeset ownership shown in the PR body.

## Hunk selector fields

- `file` (required string): repository-relative old or new path; prefer the new
  path after a rename.
- `range` (optional string): exact unified-diff hunk header.
- `contains` (optional string array): every string must appear in the hunk body.
- `excludes` (optional string array): none of the strings may appear.
- `occurrence` (optional positive integer): select one match when the other
  filters match more than one hunk.
- `all` (optional boolean): select every textual hunk in the file.

Selectors must resolve unambiguously. Binary changes use `patch`, not `hunks`.
Pure renames should use `paths` or `patch` so rename intent is preserved.

## Authoring rules

- Keep one cohesive intent per changeset and prefer additive foundations before
  consumers, cutovers, or removals.
- Treat repository-discovered command text as a proposal only. Never copy it
  into `test_argv` or infer argument boundaries without separate approval.
- Legacy `test_command` strings are invalid. Replace them with an explicit argv
  array; the validator never applies shell-style splitting.
- Make changesets append-only once validated; do not reorder or renumber an
  existing materialized position.
- Document temporary flags and incomplete states in `pr_notes`, including the
  later changeset that removes them.
- Use `validate --strict` before materialization. Placeholder warnings, missing
  files, unmatched selectors, ambiguous hunks, or unappliable patches must be
  resolved rather than ignored.
- After materialization, do not use plan edits to change the meaning or identity
  of an existing changeset. Create a new candidate commit and renew evidence.
- After publication, use the live successor-source recovery protocol when an
  accepted correction requires a new intended result. Do not add successor
  fields to the plan or use it as a recovery cache.
