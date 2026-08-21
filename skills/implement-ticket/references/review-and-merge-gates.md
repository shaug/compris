# Initial review and delegation gates

Apply these gates to the complete initial ticket candidate. Repository
instructions may add stricter requirements but must not silently weaken them.
After review, select exactly one publication path. Delegate an ordinary PR's
continuing lifecycle to repository-owned `babysit-pr`, or delegate an oversized
candidate's entire stacked lifecycle to repository-owned `carve-changesets`. On
the ordinary path, publication itself goes to repository-owned
`publish-candidate` whenever that optional role resolves at the publication
boundary, and is performed inline whenever it does not. Do not duplicate any
delegate's mechanics here.

## Delegate the initial review and fix loop

Require repository-owned `review-fix-loop` before the publication size gate.
Fail closed when it is missing or unreadable. Do not substitute another skill, a
generic self-review, an inlined ad hoc fix loop, or an unreviewed path.

Read [the review-fix-loop handoff](review-fix-loop-handoff.md) for exactly how
to construct the invocation, supply its `reviewer`/`decide`/`apply_fix`/
validation ports, and map its terminal result. Do not duplicate that mechanic
here: `review-fix-loop` owns raw `review-code-change` packet construction and
binding, schema and head/base validation of the resulting aggregate, and
per-cycle finding history. A schema-valid `converged` result already bound to
the current head and base needs no additional invented review-fix-loop
invocation.

Require every intended ticket change to be committed and the implementation
worktree to be clean before invoking `review-fix-loop` — its own invocation
schema requires the same. If unrelated user artifacts prevent a clean state,
classify and preserve them and prove they are irrelevant to the candidate.

Reviewers receive evidence and contracts, never conclusions. Author the
invocation's change contract — the live ticket's goal, every acceptance
criterion and required verification item classified as pre-merge or post-merge,
the criterion-specific acceptance ledger, every named architecture, design,
contract, migration, and rollout document, repository instructions, and
representative nearby code and tests — as neutral evidence, never as a
pre-judged verdict. If what is being authored steers the answer — "do not flag",
"this is fine", a pre-judged severity, or the verdict expected back — stop and
rewrite it. It steers the `reviewer` port's own `review-code-change` packet
exactly as it would have steered a directly authored one; a steered reviewer
returns confirmation, not review, and confirmation is indistinguishable from a
clean result at the point it is consumed.

Give the `reviewer` port a capability tier adequate for judgment: reviewing is
judgment work, so it inherits the session's tier by default rather than the
cheapest one, and a review that missed a defect the fix loop later surfaces
escalates one tier instead of rerunning identically. Prefer one well-briefed
review-fix-loop invocation to several thin ones; each fresh review pass costs a
full three-lens sequence.

Consume `review-fix-loop`'s validated terminal result without restating or
overriding its lens order, severity, deduplication, or
correctness-versus-simplicity rules — those remain `review-code-change`'s own,
unchanged by delegation. Apply only material findings the `decide` port accepted
within `change_contract.allowed_remediation_scope`. Preserve deferred findings
without expanding the PR. Reply with evidence when a finding no longer applies.

A `converged` terminal result ends the initial loop. A `changes_remaining` or
`blocked` result maps to `blocked` with the unresolved evidence — see
[the handoff's terminal-result mapping](review-fix-loop-handoff.md#terminal-result-mapping)
for the exact reasons and the caller-owned escalation-on-final-cycle policy that
apply before this point is reached.

## Publication and delegation gate

Before invoking any publication or lifecycle delegate:

- verify the initial `review-fix-loop` result is `converged` for the exact live
  head and applicable base;
- verify every required pre-merge acceptance entry passes and choose closing or
  non-closing tracker syntax from whether post-merge entries exist;
- evaluate the exact candidate against the live `carve-changesets` guardrails
  without duplicating their thresholds;
- verify the selected publication identity — one PR, every PR of a delegated
  split, or the ordered stack — together with the effective diff, resulting
  tree, validation, worktree, ticket reference, and authority, are internally
  consistent;
- assemble every field required by the applicable
  [babysit-pr](babysit-pr-handoff.md),
  [carve-changesets](carve-changesets-handoff.md), or
  [publish-candidate](publish-candidate-handoff.md) handoff contract;
- on the ordinary path, resolve repository-owned `publish-candidate` by stable
  name — treating its absence as inline publication rather than a failed gate;
- map the completion policy without broadening merge, deployment, verification,
  or tracker-transition authority; and
- establish one exclusive mutating owner.

Treat a missing dependency, malformed result, `blocked` verdict, reviewer
mutation, stale identity, or unavailable required evidence as a failed gate. Do
not claim `ready_pr` or `ready_prs` merely because a PR or stack exists or the
initial `review-fix-loop` result is `converged`.

## Caller-side completion verification

After the selected delegate returns, reread live GitHub state and apply the
applicable [babysit-pr](babysit-pr-handoff.md),
[carve-changesets](carve-changesets-handoff.md), or
[publish-candidate](publish-candidate-handoff.md) result mapping. A `ready_pr`
requires a validated current `ready_to_merge` result plus passing required
pre-merge acceptance evidence. A `ready_prs` requires the same evidence plus a
validated current `prs_open` result from `carve-changesets` for a stack, or a
validated current `published` result from `publish-candidate` naming every PR of
a delegated split. A `merged` result requires independent remote merge or
`all_merged`, mainline, complete current acceptance evidence, tracker
transition, dependency refresh, and cleanup verification by `implement-ticket`.

If the live head, base, PR state, ownership, acceptance ledger, or gate evidence
differs from the result, reconcile the live candidate or fail closed. Never
carry stale evidence through a head/deployment change or accept a closed issue,
merged PR, or closed-unmerged PR as acceptance proof.

## Findings that must not expand the ticket

Keep these out unless the live ticket requires them:

- speculative pre-release backfills;
- support for nonexistent legacy data;
- broad refactors unrelated to correctness;
- defensive abstraction without demonstrated duplication;
- product polish or future hardening; and
- changes owned by a sibling or parent epic.
