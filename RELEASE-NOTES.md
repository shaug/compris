---
summary: Narrative history of tagged releases, distinct from the daily commit journal in CHANGELOG.md.
---

# Release Notes

Each entry here describes one **tagged release** in narrative form: what changed
for someone installing or upgrading the plugin, why it changed, and the evidence
backing the claim. This is not the daily development journal — see
`CHANGELOG.md` for that. An entry lands here only when a release is actually
cut; a merged PR alone does not earn one, except for the dry-run entry below,
recorded to document the tooling itself before any tag exists.

## Format

Each entry is a level-2 heading naming the version and date
(`## 0.1.1 — 2026-08-08`), followed by three parts:

- **What changed** — a short narrative summary in plain language, not a
  commit-log dump.
- **Why** — the motivating problem or goal.
- **Evidence** — citations for the claim: linked issues/PRs, the eval-evidence
  summaries `AGENTS.md`'s norm requires for skill-prose changes (per #135), and
  any recorded validation output.

Entries are ordered newest first. See `docs/release-process.md` for how a
release is prepared and who holds tagging authority.

## 0.1.1 — dry run, 2026-08-08

**What changed:** Added `scripts/bump_version.py`, extended
`scripts/validate_plugins.py`'s existing plugin-version drift check to cover all
four version surfaces (`.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json`, `.agents/plugins/marketplace.json`,
`.codex-plugin/plugin.json`), and documented the release process in
`docs/release-process.md`. This entry itself is that tooling's first exercise.

**Why:** #138 — distribution maturity needs a documented, drift-checked release
path before the first tagged release, as part of #121's outer-loop positioning
work.

**Evidence:** `python3 scripts/bump_version.py --bump patch` run on this
ticket's branch, bumping every enumerated surface from `0.1.0` to `0.1.1` in one
pass (see the diff in this entry's own PR); `just lint` and `just test` both
green at the resulting head, including the new
`scripts/tests/test_bump_version.py` and the extended
`scripts/tests/test_validate_plugins.py`. This is a recorded **dry run**: the
bump and validation ran end-to-end and no git tag was cut. Cutting the first
real tagged release remains a separate, explicit operator action — see
`docs/release-process.md`.
