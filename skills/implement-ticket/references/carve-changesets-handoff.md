# Carve-changesets handoff and result mapping

Use repository-owned `carve-changesets` as the sole owner of decomposing and
publishing an oversized ticket candidate. This path is selected only after the
complete candidate is validated, committed, worktree-clean, and the initial
[review-fix-loop delegation](review-fix-loop-handoff.md) has returned
`converged`.

Read the live `carve-changesets` skill, its
[normative contract](../../carve-changesets/references/SPEC.md), and its
[suite handoffs](../../carve-changesets/references/suite-handoffs.md) before
classifying candidate size or transferring ownership. Those sources remain
authoritative for guardrails, decomposition, equivalence, per-changeset review,
publication, lifecycle delegation, propagation, and terminal evidence. Do not
copy their thresholds or mechanics into `implement-ticket`.

## Responsibility boundary

`implement-ticket` retains ticket resolution and readiness, candidate
implementation, complete validation, the initial whole-candidate review, the
publication size gate, the split-ticket versus split-branch recommendation,
operator-decision enforcement, authority mapping, tracker semantics, terminal
result validation, mainline and ticket-transition verification, cleanup, and
reporting.

After handoff, `carve-changesets` exclusively owns changeset planning,
materialization, chain identity, per-changeset validation and review,
equivalence, publication, each `babysit-pr` delegation, sequential merge and
downstream propagation, and its own authorized cleanup. `implement-ticket` must
not directly invoke `babysit-pr`, run a competing watcher, mutate a stack
branch, disposition stack feedback, or reproduce propagation mechanics.

The reverse boundary is equally strict. `carve-changesets` does not change the
ticket contract, split tracker work, transition the ticket, verify an epic,
close a parent, or perform caller-owned mainline and tracker closeout.

## Publication decision and authority gate

Evaluate the exact clean candidate against the live
[changeset shape and decomposition order](../../carve-changesets/references/SPEC.md#changeset-shape-and-decomposition-order)
rules. Record the effective diff, semantic shape, mechanical exceptions,
cohesive intent, and independent-reviewability evidence. Never reduce this
decision to a duplicated numeric threshold.

When the candidate is oversized, recommend tracker-level ticket decomposition if
its parts are independently valuable and trackable. Recommend branch carving
only when the ticket remains one coherent deliverable and the diff is simply too
large for one reviewable PR. The operator decides. An unresolved decision or a
ticket-split choice returns `blocked` before publication; this workflow does not
create or edit the replacement tickets.

The explicit `decompose oversized candidates into stacked changesets` grant is
required before handoff and is off by default. Ready-PR, merge, ticket-edit, or
generic completion authority never implies it. Without the grant, preserve the
clean source candidate and return `blocked` with the guardrail evidence; do not
publish a monolithic PR or begin a local chain.

## Verified handoff

Immediately before transfer, capture and verify:

- ticket identity, owning tracker, complete observable goal, acceptance
  criteria, non-goals, and preserved behavior;
- repository instructions and named architecture, design, contract, migration,
  and rollout documents;
- source repository, immutable source branch and SHA, base branch and SHA, merge
  base, complete effective diff, resulting tree, and commit history;
- tracked, staged, unstaged, untracked, and ignored worktree state;
- focused and full validation commands and exact outcomes;
- a `converged` initial `review-fix-loop` result bound to the exact source and
  base, plus reviewer-integrity evidence;
- guardrail evidence, the operator's branch-carving decision, and the explicit
  decomposition grant;
- requested terminal boundary, completion policy, retry and review-cycle
  budgets, and every granted or withheld mutation, publish, reply, resolution,
  merge, propagation, and cleanup authority;
- tracker reference and closing behavior, including the expected transition only
  after the full stack merges; and
- exclusive mutation ownership of the immutable source candidate and every stack
  branch created from it.

Reject a stale, dirty, behind-base, conflicting, incomplete, review-stale, or
ambiguously owned candidate. The source branch becomes immutable at handoff.

## Policy and tracker mapping

- `ready PR only` maps to `carve-changesets` publish authority and the
  `prs_open` boundary. Merge and propagation remain withheld.
- `merge after gates` maps to merge-and-propagate authority and the `all_merged`
  boundary.
- `merge plus manual transition` also maps to `all_merged`; the separately
  authorized manual tracker transition stays with `implement-ticket` after
  mainline verification.

One ticket owns one candidate. That candidate publishes as either one ordinary
PR or one ordered carved stack. Put the tracker's closing syntax only on the
final changeset PR, or on none when the completion policy forbids automatic
transition. Intermediate PRs use non-closing references, remain behaviorally
safe at their chain positions, and never transition the ticket. Verify the
ticket transition only after a current, independently verified `all_merged`
result.

## Terminal-result mapping

Reread live git, GitHub, and tracker state before accepting a returned result.
The ticket, repository, source, base, stack topology, PR identities, authority,
validation, review, equivalence, gate, and cleanup evidence must match the
handoff.

- `prs_open` maps to `ready_prs` only when every changeset PR is open and
  correctly based, every applicable current-candidate non-merge gate passes,
  final-only closing syntax is verified, whole-chain equivalence holds, merge is
  withheld, and ownership is consistent.
- `all_merged` maps to `merged` only after `implement-ticket` independently
  verifies every sequential merge and propagation step, complete representation
  and required validation on the base, the expected ticket transition, and
  authorized cleanup.
- `blocked` maps to `blocked` with the exact phase, source, base, stack, PR,
  candidate, preserved artifacts, last trustworthy evidence, and one action
  needed to resume.
- `plan_ready` or `chain_ready` cannot satisfy an `implement-ticket` publication
  policy and map to `blocked` unless the caller explicitly changes the requested
  boundary.

A material redesign raised on changeset N that invalidates an earlier merged
changeset is a genuine `blocked` result. Preserve the partial stack and report
the required product or architecture decision; never rewrite merged history or
hide the inconsistency in a later changeset.

Resume from the live `carve-changesets` source, branches, PRs, and mainline
state. Do not duplicate prior publication, watcher, review, merge, or
propagation actions from cached handoff evidence.
