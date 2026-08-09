---
summary: How a compris release is prepared and cut, and who holds tagging authority.
---

# Release process

This repository ships as an installable plugin (Claude Code and Codex
packaging). A release is cutting a git tag and GitHub release from a commit on
`main` whose version surfaces are in sync. This document is the process; the
tooling it describes lives in `scripts/bump_version.py` and
`scripts/validate_plugins.py`.

## Version surfaces

Four files carry the plugin's version. `scripts/validate_plugins.py` (wired into
`just lint`) rejects any drift among them:

| Surface                            | Where the version lives |
| ---------------------------------- | ----------------------- |
| `.claude-plugin/plugin.json`       | top-level `version`     |
| `.codex-plugin/plugin.json`        | top-level `version`     |
| `.claude-plugin/marketplace.json`  | `plugins[0].version`    |
| `.agents/plugins/marketplace.json` | `plugins[0].version`    |

## Preparing a release (bump script)

`scripts/bump_version.py` is the only tool that should change any of the four
surfaces. It reads the current version from the two plugin manifests, computes
the target, and writes all four in one pass — restoring any surfaces it already
wrote if a later write fails, so a partial bump never lands.

```bash
python3 scripts/bump_version.py --bump patch   # 0.1.0 -> 0.1.1
python3 scripts/bump_version.py --bump minor   # 0.1.0 -> 0.2.0
python3 scripts/bump_version.py --bump major   # 0.1.0 -> 1.0.0
python3 scripts/bump_version.py --to 0.3.0     # explicit target
python3 scripts/bump_version.py --bump patch --dry-run   # preview only
```

Run it on a branch, then `just lint` and `just test` to confirm the four
surfaces agree and nothing else broke. Commit the result as an ordinary PR like
any other change — preparing a bump carries no special authority.

## Narrative release notes

`RELEASE-NOTES.md` is the narrative history of tagged releases: what changed,
why, and the evidence behind the claim (see the format documented at the top of
that file). It is distinct from `CHANGELOG.md`, the daily development journal
`AGENTS.md`'s Git Workflow section already governs. Add a `RELEASE-NOTES.md`
entry for every tagged release, not for every merged PR.

## Cutting the release (operator-only)

Preparing a release — bumping versions, updating `RELEASE-NOTES.md`, merging
that PR to `main` — is ordinary PR completion authority. **Cutting the git tag
and GitHub release is not.** That step is reserved for the operator:

1. Confirm `main` is at the commit intended for release and that
   `just lint`/`just test` are green there.
2. Tag it (`git tag vX.Y.Z` matching the synced version) and push the tag.
3. Cut the GitHub release from that tag, with notes drawn from the corresponding
   `RELEASE-NOTES.md` entry.

No automation in this repository creates a tag or a GitHub release on the
operator's behalf. A PR that prepares a release must never assume tagging
authority merely because its own acceptance criteria are otherwise satisfied.

## The first real release

This tooling was built ahead of the first tagged release. Cutting the first tag
is still a separate, explicit operator action — this document does not itself
authorize it, and no ticket that merely adds tooling, notes, or a dry run should
be read as having done so.
