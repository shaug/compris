# Review-fix-loop handoff and result mapping

Use repository-owned `review-fix-loop` as the sole canonical owner of one
changeset's review, finding disposition, fix authorship orchestration,
re-review, and convergence detection. Read its live skill,
[`references/CONTRACT.md`](../../review-fix-loop/references/CONTRACT.md), and
[`references/local-commit.md`](../../review-fix-loop/references/local-commit.md)
before delegation. If its delivered contract differs materially from this
boundary, stop and reconcile ownership rather than copying loop mechanics back
into `carve-changesets`.

This reference applies to every changeset's local review before publication —
during "Materialize and prove equivalence" and again while rebuilding review
evidence during successor-source recovery — always under
`publication.policy: local_commit` — `review-fix-loop` never pushes on this
skill's behalf. `babysit-pr`'s post-publication remediation loop is a separate,
already-migrated consumer (delegated to `review-fix-loop` under `update_pr` per
issue #104); this handoff does not apply to it, and `carve-changesets` never
constructs that invocation itself. See [the suite handoffs](suite-handoffs.md)
for the PR lifecycle and recovery handback this reference does not cover.

## One invocation per changeset, in chain order

A chain of *N* changesets is *N* independent `review-fix-loop` invocations, not
one — `review-fix-loop` has no notion of a changeset stack, and this skill does
not make it aware of one. Each invocation is bound to exactly one changeset
branch and is locked, checkpointed, and resolved to a terminal result on its own
before the next is constructed.

Construct and resolve them in chain order: changeset *i*'s comparison base is
changeset *i - 1*'s finalized branch (or the chain base for changeset 1), so
changeset *i*'s invocation is not constructed until changeset *i - 1*'s review
has returned `converged`. Reviewing out of order would bind a packet to a
stacked base that has not finished changing.

## Responsibility boundary

`carve-changesets` retains decomposition analysis, plan authoring, chain branch
creation and ordering, native commit-trailer stamping and PR prose, each
changeset's change-contract authored content (goal and acceptance criteria
derived from the changeset's slug and description, non-goals naming work
reserved for later changesets, preserved behaviors from `SPEC.md`'s applicable
invariants, and `allowed_remediation_scope` bounded to that changeset's own
extraction selectors), the validation commands it approves, invocation
construction, host-port implementation (see below), terminal-result validation,
whole-chain equivalence, downstream propagation, publication-path selection, the
handoff to `babysit-pr`, and successor-source recovery mechanics.

After delegation, `review-fix-loop` owns the local candidate lock for that one
changeset, reviewer isolation and integrity enforcement, raw
`review-code-change` packet construction and binding, finding selection and
ordering, fix-cycle budget accounting, validated commit and fast-forward
promotion of every accepted fix, evidence invalidation after each new head,
convergence detection, and its own durable checkpoint and terminal result. Do
not reproduce those mechanics in this skill.

## Pre-mutation dependency gate

Verify `review-fix-loop` by stable repository-owned name before materializing
any changeset, per
[the skill's own capability requirements](../SKILL.md#require-compatible-capabilities).
`review-fix-loop`'s own dependency gate covers `review-code-change` and its
three lenses; do not additionally require or substitute a direct
`review-code-change` binding here. Missing `review-fix-loop` returns `blocked`
before mutation; do not download an external implementation at runtime, restore
a private inlined review loop, or accept an unreviewed candidate as ready.

## Constructing the invocation

Immediately before delegating changeset *i*, capture its exact committed head,
its stacked comparison base (changeset *i - 1*'s branch, or the chain base for
changeset 1), the complete diff from that base to the head, and
tracked/staged/unstaged/untracked/ignored worktree state. The worktree must be
globally clean and every intended change committed — `review-fix-loop`'s own
invocation schema rejects anything else.

Map that evidence onto one `review-fix-loop` invocation:

- `repository`: `identity` and `git_common_directory` only — `review-fix-loop`'s
  invocation-level `repository` has no field for a base branch. The stacked base
  (changeset *i - 1*'s branch, or the chain base for changeset 1) is carried by
  `candidate.comparison_base` below, and separately by the `reviewer` port's own
  `review-code-change` packet, whose own `repository.base_branch` field is
  exactly
  [the suite handoffs' per-changeset review packet](suite-handoffs.md#per-changeset-review-packet)
  table's `repository` row — a different schema than this invocation's.
- `candidate`: changeset *i*'s exact branch, head SHA, the stacked base as
  `comparison_base` (`{ref, sha}`), the complete unified diff from that base to
  the head, and the worktree state above, with `all_changes_committed: true`. No
  PR exists yet at this point in the workflow, so record
  `source_unavailable_reason` rather than a `source_binding` — this delegation
  never needs publication authority.
- `change_contract`: `goal` and `acceptance_criteria` derived from the
  changeset's slug, description, and plan `pr_notes` (scaffolding, flags, and
  intentional incompleteness); `non_goals` naming work reserved for later
  changesets; `preserved_behaviors` naming the applicable invariants from
  `SPEC.md`; `sources` naming applicable repository instructions, `SPEC.md`,
  named architecture or design documents, and representative nearby patterns for
  the files this changeset touches. Set `allowed_remediation_scope` to this
  changeset's own extraction selectors and boundary — a fix cycle may not spill
  into a sibling changeset's territory. This mirrors
  [the suite handoffs' per-changeset review packet](suite-handoffs.md#per-changeset-review-packet)
  table's `change_contract` and `sources` rows, which describe the same content
  for the `reviewer` port's own `review-code-change` packet.
- `review_execution.mode`: `fresh_subagent` by default, matching this skill's
  existing fresh read-only review requirement. Use `in_agent_override` only
  through an explicit current-user or caller-authorized override recorded before
  delegation; there is no automatic fallback.
- `fix_cycle_budget.max_fix_cycles`: `3`, matching the repository's existing
  three-cycle norm used elsewhere in this suite. This is a distinct budget from
  `review-code-change`'s own three-cycle lens-sequence retry budget; neither
  touches the other.
- `validation`: at least one focused and one full `{name, command, scope}` entry
  — commands only, matching `review-fix-loop`'s own invocation schema;
  `review-fix-loop` itself runs them and produces the results. Focused evidence
  covers the chain prefix through changeset *i*; full evidence names the
  approved repository or whole-chain validation applicable at this boundary.
  This is distinct from the `reviewer` port's own `review-code-change` packet,
  whose `validation` row does carry exact commands and results, per
  [the suite handoffs' per-changeset review packet](suite-handoffs.md#per-changeset-review-packet)
  table.
- `publication.policy`: always `local_commit`. Never supply
  `publication.pull_request` or `remote_iteration_grants` here — no PR exists
  yet, and this skill withholds every changeset's first remote push until
  [phase 3, Publish](../SKILL.md#3-publish).

Author the change contract's goal, acceptance criteria, non-goals, and preserved
behaviors as neutral evidence, never as a pre-judged verdict —
`review-fix-loop`'s `reviewer` port passes them straight into its own
`review-code-change` packet, so steering language here steers that review
exactly as it would have before delegation.

## Host ports remain caller-owned

`review-fix-loop`'s engine is dependency-free: it cannot itself spawn a review
subagent, write a fix's content, or judge whether a finding is genuinely
tractable and in scope. Supply its `reviewer`, `decide`, `apply_fix`, and
validation ports yourself, exactly as
[`local-commit.md`](../../review-fix-loop/references/local-commit.md)'s "Host
boundary: the three ports" section describes:

- **`reviewer`**: spawn a fresh read-only context restricted to
  `Read, Grep, Glob, Bash, Agent, Task, Skill` that invokes repository-owned
  `review-code-change` with raw candidate evidence only — excluding the plan,
  the implementation transcript, prior conclusions, and suspected findings. Each
  changeset's reviewer receives evidence and contracts, never conclusions. If
  the invocation being written steers the answer — "do not flag", "this is
  fine", a pre-judged severity, or the verdict expected back — stop and rewrite
  it. The pressure is specific to a chain: an earlier changeset reviewed clean,
  so it is tempting to tell the next reviewer the design is already settled. A
  steered reviewer returns confirmation, not review, and a chain compounds one
  such result across every changeset that follows.

  Give each changeset review a capability tier adequate for judgment: it
  inherits the session's tier by default rather than the cheapest one, and a
  review that missed a defect a later changeset surfaces escalates one tier
  instead of rerunning identically. Prefer one well-briefed review per changeset
  to several thin ones — a chain multiplies the cost of a rerun by its remaining
  length.

- **`decide`**: apply
  [the consumption disciplines](review-suite/consumption-disciplines.md) to
  every finding `review-fix-loop` selects — verify it against the codebase
  before implementing it, clarify every unclear finding before implementing any,
  never perform agreement, and accept only a finding that is material and within
  `change_contract.allowed_remediation_scope`. A finding whose correct fix would
  exceed that changeset's own boundary — spilling into a sibling changeset's
  territory — is not this changeset's to absorb: return `expands_scope` and let
  `review-fix-loop` stop as `blocked/scope_decision_required`, surfacing it for
  this skill to disposition (typically a plan revision) rather than silently
  widening the changeset.

- **`apply_fix`**: implement the smallest coherent accepted remediation, within
  this changeset's own boundary. When this port is about to consume the
  invocation's final remaining cycle, replace the incumbent implementer rather
  than continuing it: dispatch a fresh context one capability tier above the
  incumbent's, or a fresh context at the same tier when no higher tier is
  available in the session, briefed with the surviving finding and a summary of
  what prior attempts tried and why they failed, not the full transcript. This
  is a caller-supplied policy layered onto the port — `review-fix-loop`'s own
  engine has no escalation mechanic and needs none for this to work. When a fix
  fails repeatedly and `superpowers:systematic-debugging` is available in the
  session skill listing, load it as the escalated implementer's recommended
  diagnosis method; when the peer is not in the listing, the escalated
  implementer diagnoses from logs and evidence without comment.

- **validation ports**: run this changeset's separately approved focused and
  full validation commands and classify a candidate-attributable failure as
  tractable remediation input exactly as
  [phase 2](../SKILL.md#2-materialize-and-prove-equivalence) already requires.

## Resuming an interrupted invocation

`review-fix-loop` resumes from live repository and checkpoint state without
requiring an uninterrupted transcript. Before constructing a new invocation for
changeset *i*, check for an existing durable checkpoint under
`<git-common-directory>/review-fix-loop/checkpoints/` — keyed by Git common
directory and candidate identity, so each changeset's checkpoint is independent
of its siblings' and survives independently of any one worktree's lifetime:

- If one exists for this exact repository, changeset branch, and candidate
  identity, reconcile and resume it rather than starting a fresh invocation,
  keeping its original `invocation_id` and fix-cycle budget. A reconciliation
  failure (an active lock holder, a dirty candidate, or a live head/base that
  cannot be reconciled with the checkpoint) is `blocked/checkpoint_mismatch` or
  `blocked/candidate_busy` — preserve the checkpoint and candidate for
  inspection rather than discarding it.
- If none exists — including when a changeset's materialization happened in an
  earlier, unrelated session — construct a fresh invocation from live repository
  state alone, bound to that changeset's exact current head and stacked
  comparison base. A resumed chain may find some changesets already `converged`
  (nothing to do but verify) and others with no checkpoint at all (start fresh);
  handle each independently in chain order.

## Terminal result mapping

Validate the returned terminal result against `review-fix-loop`'s own schema and
reread live Git state before mapping:

- `converged` ends this changeset's review. The final head and stacked base are
  clean, required validation passed, and `write_isolation` was `enforced`
  throughout. Continue to changeset *i + 1*'s invocation, or to `chain_ready`
  when *i* was the last changeset. Do not invoke an additional invented review
  cycle once a schema-valid `converged` result is already bound to the current
  head and base.
- `changes_remaining` maps to `blocked`. Preserve every already-`converged`
  changeset's evidence and this changeset's local candidate — every commit
  `review-fix-loop` made remains locally committed and is reported in
  `unpushed_commits`. Report the exact `reason` (`cycle_budget_exhausted`,
  `oscillation`, `expanding_findings`, `repeated_failed_attempt`, or
  `current_candidate_validation_failure` — `repeated_finding` is in
  `review-fix-loop`'s general schema but is deliberately never one of
  `local_commit`'s own automatic stop reasons, per its own
  [`local-commit.md`](../../review-fix-loop/references/local-commit.md)),
  `unresolved_or_deferred_findings`, and `operator_action` as the blocking
  evidence and next action.
- `blocked` maps to `blocked` with the exact reason, current changeset
  candidate, and `operator_action`. `missing_capability` and
  `reviewer_integrity_failure` fold into this skill's existing "treat as a
  failed local gate" rule for a missing dependency or reviewer mutation.
  `scope_decision_required` and `operator_input_required` fold into this skill's
  existing stop condition for a proposed changeset that cannot remain cohesive
  or independently understandable — a finding that cannot be resolved inside one
  changeset's boundary is evidence the plan itself needs revision.
  `remote_advanced` and `publication_failed` never apply under `local_commit`
  and indicate a contract violation if returned.

Never translate a stale, malformed, or invocation-mismatched terminal result
into `converged`. Read `review_records` and `unresolved_or_deferred_findings`
directly from the terminal result for the per-cycle finding history; do not
reconstruct a separate resolved/unresolved/superseded ledger on top of it —
`review-fix-loop` already binds every review pass and disposition to the exact
head that produced it.

## Forward evaluation integrity

Exercise this composition with raw live-shaped candidate, change-contract, and
validation artifacts. Exclude the plan, implementation transcripts, intended
fixes, expected outputs, suspected findings, and prior conclusions. Treat
contaminated evidence as invalid and rerun the evaluation with a fresh isolated
reviewer or worker context.
