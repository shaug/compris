# Standalone `local_commit` workflow

This document implements
[`design/review-fix-loop.md`](../../../design/review-fix-loop.md)'s "Workflow"
section (steps 1 "Resolve" through 9 "Return"), "Convergence and stop
conditions", "Terminal result contract", and the `local_commit` parts of
"Publication policy" — for the executing agent that follows
[`SKILL.md`](../SKILL.md). It does not redefine any contract, locking,
checkpoint, or reviewer-orchestration behavior already owned by
[`references/CONTRACT.md`](CONTRACT.md) and
[`references/reviewer-orchestration.md`](reviewer-orchestration.md); it composes
them into the one entry point issue #99 delivers:
[`scripts/local_commit.py`](../scripts/local_commit.py)'s
`run_local_commit(...)`.

`update_pr` (issue #100) and remote publication of any kind are out of scope
here; every path in this module ends without a remote write, per this
invocation's `publication.policy: local_commit`.

## What this module composes, and what it does not reimplement

`run_local_commit` sequences calls into the three already-merged children of
epic #95:

- `validate.py` (#96) validates the invocation up front and every checkpoint and
  terminal result this module produces, so a caller never receives a document
  that would fail its own contract.
- `local_execution.py` (#97) owns the candidate lock, isolated attempt
  worktrees, durable checkpoint persistence, verified fast-forward-only
  promotion, and interrupted-attempt recovery. This module never reimplements
  Git locking, promotion, or recovery logic — it calls the existing functions.
- `reviewer_orchestration.py` (#98) owns fixed lens resolution, raw-result
  evaluation and candidate binding, mutation detection, reviewer identity, and
  deterministic finding ordering. This module never reimplements
  `evaluate_review_result`, `detect_worktree_mutation`, or `select_next_finding`
  — it calls them once per review pass.

What issue #99 itself owns, and what did not exist before this module:

- the loop's control flow across the design's nine workflow steps;
- fix-cycle budget enforcement (reserving a cycle before the first mutation of
  an attempt, whether it commits, fails, or is interrupted);
- the "Decide" step's disposition/scope/operator-input branching;
- the automatic non-convergence stops that are safely detectable from
  candidate-visible evidence alone (`expanding_findings`, `oscillation`,
  `repeated_failed_attempt`, `cycle_budget_exhausted`); and
- assembling and validating the checkpoint and terminal-result documents this
  invocation produces.

## Host boundary: the three ports

A dependency-free module cannot itself spawn a review subagent, write a fix's
actual content, or decide whether a finding is genuinely tractable and in scope.
`run_local_commit` accepts these as small callables ("ports") so the executing
agent supplies exactly the judgment the design assigns to it, nothing more:

- `reviewer(*, packet, briefing, head_sha, comparison_base_sha, independence, sequence) -> ReviewPass`
  — run one complete `review-code-change` pass. In Claude Code, this means
  spawning a fresh subagent restricted to
  `Read, Grep, Glob, Bash, Agent, Task, Skill` per
  [`references/reviewer-orchestration.md`](reviewer-orchestration.md) and
  returning its raw aggregate result. `run_local_commit` still performs the
  tiered before/after mutation snapshot, `evaluate_review_result` binding, and
  `write_isolation` recording around this call — the port only needs to return
  the raw result, plus any tool-trace mutation evidence the runtime observed
  (`ReviewPass.mutation_attempts`) and whether it performed tool-trace
  inspection at all for this pass (`ReviewPass.tool_trace_available`, recorded
  as the review record's `integrity_evidence`).
- `decide(*, finding, change_contract, attempt_number) -> FixDecision` — verify
  the selected finding's evidence against the candidate, confirm it is within
  `change_contract.allowed_remediation_scope`, and return `accepted`,
  `rejected`, or `deferred` with a rationale. Set `expands_scope=True` when a
  correct fix would exceed the allowed scope, or `operator_input_required=True`
  when the finding itself needs a human decision before any fix is attempted.
- `apply_fix(*, finding, attempt_path, change_contract, attempt_number) -> str`
  — write the smallest coherent remediation directly into the isolated attempt
  worktree at `attempt_path` and return a commit message. Called only after
  `decide` returns `accepted` with neither `expands_scope` nor
  `operator_input_required` set, and only when budget remains.
- `run_validation(*, name, command, scope, cwd) -> ValidationOutcome` (optional;
  defaults to a real `subprocess` runner) — run one recorded validation command.
  Never interpolate untrusted text into `command`; it must already be one of the
  invocation's own recorded commands.
- `classify_validation_failure(*, outcome, invocation) -> dict | None`
  (optional; defaults to always returning `None`) — called only when validation
  fails for a head no fix cycle just produced. Returning `None` means the
  failure has no tractable correction, per the design; returning a
  finding-shaped dict routes it through the same decide/fix pipeline as an
  ordinary review finding, consuming a fix cycle like one.

Every other action — acquiring the candidate lock, running
`git diff`/`git show`, building the raw review packet, creating and promoting
attempts, writing checkpoints — happens for real against the repository at
`repo`. There is no mocked Git state anywhere in this module or its tests,
matching `local_execution.py`'s own testing convention.

## The loop, step by step

1. **Resolve.** Validate the invocation against `validate.validate_invocation`
   and reject anything but `publication.policy: local_commit`. Acquire the local
   candidate lock (`local_execution.acquire_candidate_locks`); a busy lock
   returns `blocked/candidate_busy` without touching the repository. Reconcile a
   supplied `resume_checkpoint` through
   `local_execution.reconcile_checkpoint_for_resume`, then recover any
   interrupted attempt left behind by a prior crashed run through
   `local_execution.recover_interrupted_attempts` — each uniquely identifiable
   leftover is discarded (preserved for inspection) and recorded as one
   `interrupted` cycle attempt, consuming budget exactly as the design requires
   ("the reserved cycle is spent regardless of outcome").
2. **Establish evidence.** Capture the live head and comparison base and verify
   them against the invocation's recorded candidate identity (a mismatch is
   `blocked/candidate_integrity_failure`). Run the invocation's recorded focused
   and full validation against the current head. An `unavailable` scope is
   `blocked/validation_unavailable`. A `failed` scope is classified via
   `classify_validation_failure`: untractable is
   `changes_remaining/current_candidate_validation_failure` (no cycle consumed);
   tractable routes the returned finding through Decide/Fix like any other
   finding.
3. **Review.** Resolve the review-execution mode
   (`reviewer_orchestration.resolve_review_execution_mode`); an unsupported
   `fresh_subagent` host with no explicit override is
   `blocked/missing_capability`. Build the raw packet, snapshot the worktree
   before and after the reviewer port runs, and feed both snapshots plus the raw
   result into `reviewer_orchestration.build_review_record`. Any detected
   mutation attempt is `blocked/reviewer_integrity_failure` immediately — this
   cycle is never "fixed up" by continuing to iterate on it. A `clean` verdict
   ends the loop as `converged`. A `blocked` verdict from the review pass itself
   is `blocked/missing_capability`.
4. **Decide.** `reviewer_orchestration.select_next_finding` picks the next
   gating finding in the fixed severity/lens/id order. `None` (only deferred
   findings remain) is `blocked/operator_input_required`. Otherwise the `decide`
   port runs once per finding; its disposition is recorded on the owning review
   pass immediately, so a declined finding's rationale is visible in the
   terminal result's `review_records` even though it was never fixed.
   `rejected`/`deferred` is `blocked/operator_input_required`; `expands_scope`
   is `blocked/scope_decision_required`; a generic `operator_input_required`
   flag is `blocked/operator_input_required`.
5. **Fix.** If budget remains, reserve one cycle, create an isolated attempt
   from the exact current head (`local_execution.create_attempt`), and call
   `apply_fix`. If budget is already exhausted, stop as
   `changes_remaining/cycle_budget_exhausted` before creating an attempt — the
   same accepted finding remains visible as unresolved.
6. **Validate and commit.** Run the recorded validation inside the attempt
   worktree. On success, commit and promote through the verified
   fast-forward-only path (`local_execution.commit_attempt` +
   `local_execution.promote_attempt`); the canonical worktree, checkpoint, and
   in-memory state all advance together. On failure, discard the attempt
   (preserved for inspection) and retry the same accepted finding from the same
   head — no fresh review is needed since nothing changed. Two consecutive
   failures from the same head stop early as
   `changes_remaining/repeated_failed_attempt`, preserving remaining budget.
7. **Invalidate and repeat.** A successful promotion always triggers a fresh
   review at the new head before anything else. Two additional automatic,
   evidence-based stops fire here, both preserving budget: a fix that leaves
   every prior gating finding present and adds new ones is
   `changes_remaining/expanding_findings`; a finding set that returns to exactly
   a set seen two reviews ago after having actually changed in between is
   `changes_remaining/oscillation`. A finding that simply survives unchanged,
   cycle after cycle, is deliberately **not** an automatic early stop — the
   design tolerates that until the budget itself is exhausted (see
   `references/examples/local-commit-terminal-changes-remaining.json`, which
   consumes all three cycles on one recurring finding rather than stopping
   early). A `decide` port sophisticated enough to notice unproductive
   repetition may still request `operator_input_required` itself; the engine
   does not second-guess that judgment call on its behalf.
8. **Publish.** Never, under `local_commit`. Every terminal result reports
   `publication: {policy: "local_commit", status: "not_applicable", non_converged_exposure: false}`
   and lists every created commit in `unpushed_commits` — the expected,
   non-error shape of a converged (or non-converged) `local_commit` result.
   `operator_action` always names how the operator publishes those commits
   through their own workflow.
9. **Return.** Every return path writes a durable checkpoint
   (`local_execution.write_checkpoint_atomic`) before releasing the candidate
   lock, then assembles and validates (`validate.validate_terminal_result`)
   exactly one terminal-result document. `run_local_commit` never returns a
   document that would fail its own schema; an internal inconsistency raises
   `LocalCommitError` instead of silently shipping bad evidence.

## Terminal states this module actually returns

- `converged` — the final head's review is `clean`, required validation passed,
  and `write_isolation` was `enforced` throughout.
- `changes_remaining` — `cycle_budget_exhausted`,
  `current_candidate_validation_failure`, `repeated_failed_attempt`,
  `expanding_findings`, or `oscillation`.
- `blocked` — `candidate_busy`, `candidate_integrity_failure`,
  `checkpoint_mismatch`, `missing_capability`, `reviewer_integrity_failure`,
  `validation_unavailable`, `operator_input_required`, or
  `scope_decision_required`.

`repeated_finding` (a finding surviving one fix without a stronger pattern) is
deliberately not one of this module's own automatic stop reasons — see step 7
above. `base_drift`, `remote_advanced`, and `publication_failed` never apply to
`local_commit`, since this module never reads a remote or a shared base outside
its own repository, and never touches `update_pr`'s publication path.

## Recovery

`resume_checkpoint` reconciles a prior invocation's durable checkpoint against
live Git state before doing anything else. A lock still held by another process,
or any cross-document identity mismatch, returns `blocked/candidate_busy` or
`blocked/checkpoint_mismatch` without mutation. On a clean reconciliation, any
attempt branch left behind by an interrupted run is recovered, discarded, and
recorded as one `interrupted` cycle attempt — visible in both the checkpoint and
the terminal result's `preserved_failed_attempts` — before the loop resumes
forward exactly as a fresh invocation would.

## Tests

[`scripts/tests/test_local_commit.py`](../scripts/tests/test_local_commit.py)
drives `run_local_commit` against real temporary Git repositories (no mocked Git
state) with small deterministic reviewer/decide/apply_fix fakes, covering:
immediate convergence with no fix cycle; one and multiple successful fix cycles;
budget exhaustion on a recurring finding; a validation failure that is
`unavailable`, untractable, and tractable (fixed through the synthetic-finding
path); a declined finding and a scope-expanding fix, both surfaced as operator
input; a fix that introduces a new finding (`expanding_findings`); an
oscillating finding set; two consecutive failed attempts
(`repeated_failed_attempt`); an interrupted attempt recovered and resumed to
convergence; an already-held candidate lock (`candidate_busy`); an attempted
reviewer mutation (`reviewer_integrity_failure`); a host without fresh-subagent
support and no override (`missing_capability`); and rejection of an invalid
invocation or an `update_pr` invocation at the API boundary.
