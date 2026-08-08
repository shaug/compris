---
name: carve-changesets
description: 'Use when a large but coherent review-ready branch must be recomposed into an ordered chain of independently reviewable changesets — asked to split, carve, decompose, stack, publish, or propagate a branch too large for one pull request. The requested boundary may stop at a proposal, at a local chain, at open GitHub pull requests, or at a fully merged and propagated chain. Scope is recomposing an existing branch with its final behavior preserved: it never re-implements the work, delegates per-changeset review and PR lifecycle to the repository-owned skills, and requires explicit authority for every remote mutation. Returns one terminal state: plan_ready, chain_ready, prs_open, all_merged, or blocked.'
---

# Carve Changesets

Turn one existing review-ready source branch into a plain-git, plain-GitHub
changeset chain. Preserve every immutable source identity, keep each
intermediate result safe and reviewable, and prove that the fully merged chain
is equivalent to the active intended result. When an accepted post-publication
fix changes an unmerged suffix after a prefix has merged, recover that suffix
onto a distinct immutable successor source without rewriting the prefix.

This skill owns decomposition, truth promotion, chain mechanics, whole-chain
equivalence, and downstream propagation. It delegates each changeset's review
and fix loop to `review-fix-loop` and a published PR's lifecycle to `babysit-pr`
without copying either skill's workflow.

## Load the references

- Always read [the normative contract](references/SPEC.md) before planning or
  mutating a chain.
- Read [the plan schema](references/plan-schema.md) before creating or editing
  `.carve-changesets/plan.json`.
- Read [the CLI reference](references/cli.md) before invoking a subcommand or
  selecting flags.
- Always read
  [the review-fix-loop handoff](references/review-fix-loop-handoff.md) before
  reviewing a changeset. It requires validating every `review-fix-loop` terminal
  result against its own bundled contract and schemas before consuming it.
- Read [the suite handoffs](references/suite-handoffs.md) before publishing PRs,
  delegating a PR lifecycle, or recovering a successor suffix.
- Always read [the compaction ledger](references/ledger.md) before the first
  changeset action of a session and again before resuming, so a session resumed
  after a compaction recovers prior changeset outcomes from the ledger and live
  state rather than from recollection.

Use `scripts/cli.py` as the single command surface. Resolve script and reference
paths from this skill's root, not from a repository-relative installation
assumption.

## Require compatible capabilities

Require a runtime that can:

- resolve exact git refs, inspect ancestry and trees, and create isolated local
  branches or worktrees without mutating the source branch;
- run Python 3 and separately approved repository validation commands;
- reach GitHub over the network and use an authenticated `gh` session whenever
  publication, live PR state, review, merge, or propagation is in scope;
- load repository-owned `review-fix-loop` for required per-changeset review and
  fix; its own dependency gate covers `review-code-change` and its lenses, so
  this skill does not separately require it;
- load repository-owned `babysit-pr` and retain task ownership while waiting
  whenever a published PR lifecycle is delegated; and
- read current checks, reviews, comments, reactions, and resolved-thread state
  before a readiness or merge claim.

Return `blocked` before the affected mutation when a required capability is
missing. Do not download a substitute workflow, bypass review, publish a PR that
has no lifecycle owner, or treat partial GitHub data as clean.

## Resolve the operating contract

Before mutation, discover or receive and verify:

- repository identity, current checkout, worktree state, and applicable
  repository instructions;
- exact root source, any successor-source lineage, and base branches and SHAs,
  their merge bases, source freshness, and the complete active candidate diff;
- the immutable source outcome and the behavior, schema, constraints, public
  interfaces, migrations, and rollout properties the final chain must preserve;
- explicitly approved argv arrays for tests and any required database, build,
  integration, or manual validation commands;
- cognitive-load guardrails, acceptable intermediate states, decomposition
  order, feature-flag policy, and database-migration requirements from the
  normative contract;
- the requested terminal boundary: proposal only, local chain, published PRs, or
  fully merged chain; and
- authority for local decomposition, validation execution, publication,
  candidate repair, review communication, merge, propagation, and cleanup.

Review communication runs on
[the consumption disciplines](references/review-suite/consumption-disciplines.md):
verify each finding against the codebase before implementing it, clarify every
unclear finding before implementing any, never perform agreement in a reply, and
implement blocking before simple before complex, validating each on its own.

Treat discovered validation commands as proposals until the user explicitly
approves their argv boundaries. Execute argv directly without implicit shell
parsing; use `["sh", "-lc", "..."]` only for intentionally approved shell
semantics. Every source in the lineage is immutable throughout the workflow.
Stop if the active source is behind the base unless the contract's explicit
override and confirmation are both present.

### Authority levels

- **Decompose-only** permits the ephemeral plan, local changeset branches and
  commits, required trailers, and separately approved validation. It forbids
  every remote write.
- **Publish** additionally permits pushing exact changeset branches, opening or
  updating their correctly based PRs, and delegating each PR to `babysit-pr`
  with `ready_to_merge`. Merge and force-push authority remain withheld.
- **Merge-and-propagate** additionally permits `merge_when_ready`, sequential
  changeset merges after all gates pass, and exact-lease downstream propagation.
  It never permits force-pushing the base, source, merged upstream, or an
  unowned branch.

Suffix recovery is a separate acknowledgement within merge-and-propagate
authority. It permits `recover-suffix` to restamp and exact-lease update only an
owned, unmerged suffix onto a verified successor source. It does not permit
changing the root source, a merged position, a stable index, or another owner's
branch.

Pass authority to delegated skills without expansion. Reply and thread
resolution authority remain separate from branch mutation and merge authority.

## Execute the phase workflow

At the start of a session that will act on a source branch, record one
session-identity line in [the compaction ledger](references/ledger.md), then
read it. On resume or after a context compaction, trust that ledger plus freshly
read live git/GitHub state over recollection of prior phase-workflow progress;
never skip `review-fix-loop`, republication, or a merge step for a changeset the
ledger does not show as completed and live-verified.

### 1. Propose

Run `preflight` against the exact source and base with the approved test argv.
Use `init-plan` to create `.carve-changesets/plan.json`, then replace every
placeholder with cohesive boundaries, ordering, intent, extraction selectors,
validation, and intentional incompleteness. Use `hunk-preview` when textual hunk
selection needs inspection, and require `validate --strict` before promotion.

At this phase the plan is the only writable truth. Do not create changeset refs
or perform remote operations. Return `plan_ready` when proposal is the requested
boundary.

### 2. Materialize and prove equivalence

Use `create-chain` to create append-only `<source>-N` branches and stamped
commits. Run `validate-chain` with approved validation, `compare` for the
reconstructed tree, and the applicable `squash-check` or `db-compare` evidence.
Use `status --local-only` to inspect live local truth without GitHub.

Before constructing changeset *i*'s invocation, check
[the compaction ledger's recovery rule](references/ledger.md#recovery-rule) for
a completed, live-verified `review_fix_loop` entry for that changeset, scoping
the lookup to `action: review_fix_loop`
(`already_recorded_complete(..., action="review_fix_loop")`) so a later
`publish` or `merge` entry for the same changeset can never mask an earlier
`converged` result. Skip straight to *i + 1* when one exists; otherwise proceed
as below. This is a dedup guard only — a ledger entry that fails live
verification, or that records anything other than `converged`, changes nothing
about this step.

Delegate each exact changeset candidate's review and fix loop to
repository-owned `review-fix-loop` under `publication.policy: local_commit`,
following [the review-fix-loop handoff](references/review-fix-loop-handoff.md).
Review changesets in chain order: changeset *i*'s invocation is not constructed
until changeset *i - 1*'s is `converged`, since *i*'s comparison base is *i -
1*'s finalized branch. This skill still owns and constructs the `reviewer`,
`decide`, `apply_fix`, and validation ports the handoff describes; delegation
transfers judgment about findings and fix authorship for the remediation
interval, not exclusive ownership of the branch. Treat any `review-fix-loop`
dependency failure, invocation or terminal-result validation failure, or
`blocked` result as a failed local gate exactly as a missing dependency or a
`blocked` verdict was always treated. Record one ledger entry per changeset
(`action: review_fix_loop`) as soon as its own `review-fix-loop` result is
known, whether `converged` or a failed gate — an interrupted session must find
exactly where it stopped, not just where it succeeded. Return `chain_ready` only
after every local candidate has a `converged` `review-fix-loop` result bound to
its exact head and stacked base, and the full chain satisfies the contract.

### 3. Publish

Require publish authority before any remote mutation. `push-chain` and
`pr-create` are dry-run by default; use their execution flag only after
reverifying the exact remote, branches, heads, predecessor bases, metadata, and
exclusive ownership. Use `status` to reconstruct published truth from live git
and GitHub rather than a local cache.

Delegate each exact PR to `babysit-pr` using the policy and evidence in the
suite handoff reference. While delegated, do not run a competing CI, feedback,
review, or mutation loop. Record one ledger entry per changeset
(`action: publish`) once its `babysit-pr` result is known, translating that
result into this skill's own vocabulary rather than babysit-pr's: record
`terminal_result: prs_open` for a `ready_to_merge` babysit-pr result (this phase
always requests `ready_to_merge`, never `merge_when_ready`), or
`terminal_result: blocked` for `blocked`/`closed`. Return `prs_open` only when
every applicable non-merge gate at the requested boundary passes and merge is
withheld.

### 4. Merge and propagate

Require merge-and-propagate authority. When `babysit-pr` returns `merged`,
independently verify the exact merged candidate on the live base, rehydrate the
chain, use `propagate` to rewrite only the downstream suffix with exact leases,
then hand the next exact PR back to `babysit-pr`. Record one ledger entry per
changeset (`action: merge`, `terminal_result: merged`, the merge SHA as
`head_sha`) immediately after this independent verification — never before it,
since the ledger must never claim a merge the live base does not yet show.

When `babysit-pr` instead returns a ticket-scoped head-changing fix after an
earlier prefix has merged, reclaim ownership only through the recovery handback
in the suite reference. Create or receive a distinct immutable successor source
containing the accepted result. Preview, then run `recover-suffix` with the
explicit recovery acknowledgement. The command must verify the merged prefix on
current base, preserve stable positions and PRs, restamp only the exact owned
suffix with ordered lineage, and prove current base plus that suffix equals the
successor source. Rebuild all candidate-bound validation, review, CI, and
feedback evidence before returning the corrected exact PR to `babysit-pr`.

Use `merge-propagate` only when the resolved workflow explicitly assigns the
direct merge to this CLI and no delegated owner controls that PR. Both execution
paths are dry-run by default and require the merge-and-propagate acknowledgement
before mutation. Resume interrupted work from live git and GitHub state, not
from the plan or a cache.

Return `all_merged` only after every PR, propagation step, final equivalence
check against the active source, required validation, and authorized cleanup has
been verified.

Do not skip a propagation's own equivalence proof because an earlier one passed.
Recognize the excuse and answer it with the rule that already applies:

| Rationalization                          | Why it still applies                                                                                                                                                                                                                                                                                |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "The equivalence check passed last time" | Each propagation step rewrites a different downstream suffix against a different current base, so live chain validation must re-derive from current git objects that the reconstructed base-plus-suffix tree equals the active source after this step — a prior pass proves nothing about this one. |

## Preserve safety and truth

- Keep `.carve-changesets/` ignored and out of commits and PRs — its
  per-source-branch ledger workspace additionally self-excludes via its own
  `.gitignore`, per
  [the compaction ledger](references/ledger.md#workspace-layout).
- Keep `db-compare` raw outputs ephemeral by default. Retain exact raw output
  only at an explicitly selected, reported, permission-restricted destination;
  bound terminal diagnostics without transforming comparison inputs.
- Resolve every mutation target to an exact repository, ref, SHA, PR, and
  worktree immediately before acting.
- Keep remote mutation dry-run by default and use explicit refspecs and exact
  leases where the contract permits force-push.
- Preserve the exact root and successor-source identities and reconstruct their
  ordered lineage from commit trailers and PR metadata.
- Never use a plan edit, cached head, or ledger entry to override materialized,
  published, or merged truth; the ledger is a dedup guard, verified against live
  state, never a source of truth in its own right.
- Never reset away, overwrite, or delete user work, credentials, environment
  files, databases, or non-reproducible artifacts.
- Rebuild candidate-bound validation, review, CI, and feedback evidence after a
  head change; retain evidence across base-only drift only with the documented
  proof.

## Stop conditions

Return `blocked` without widening scope when:

- source, base, repository, candidate, chain, PR, or ownership identity is
  ambiguous, stale, conflicting, or changes unexpectedly;
- the source is dirty, incomplete, mutable, or behind the base without the
  explicit two-part override;
- a proposed changeset cannot remain cohesive, independently understandable,
  safely intermediate, or mergeable in sequence;
- required validation, review, equivalence, migration, or GitHub evidence is
  missing or fails;
- stronger live truth conflicts with the plan or other weaker records;
- safe progress would require rewriting the source, base, merged upstream, or an
  unowned branch;
- recovery lineage is missing, conflicting, repeated, discontinuous, mutable, or
  cannot be proved from live refs and PR metadata;
- required authority, capability, infrastructure, or exclusive ownership is
  absent; or
- a material product, data, architecture, migration, or rollout decision is
  unresolved.

Ordinary CI wait time, difficult decomposition, or an independently ready later
changeset is not a blocker.

## Return one terminal handoff

Return exactly one terminal state with evidence bound to the root source, active
source, complete lineage, base, chain, and PR candidates:

- `plan_ready`: exact source/base identity, complete validated plan and proposed
  validation, with no materialized branch or remote mutation.
- `chain_ready`: exact local branch heads, trailers, ancestry, per-changeset
  validation and clean review, whole-chain equivalence, and no new publication.
- `prs_open`: all `chain_ready` evidence plus exact remote heads, correctly
  based open PRs, current metadata, applicable non-merge gates, and merge
  withheld.
- `all_merged`: every exact PR verified merged on the base, propagation and
  final equivalence with the active immutable source verified, required
  validation passing, and cleanup complete or precisely limited.
- `blocked`: one concrete blocker, exact phase and identities reached, preserved
  partial artifacts and last trustworthy evidence, and one action or decision
  needed to resume.

An open PR, green check, local diff, stale review, or plan alone is never enough
to claim a later terminal state.
