# Cleanup and terminal result

Verify remote, mainline, tracker, and local state before deleting anything or
returning a terminal handoff.

## Safe per-candidate cleanup

01. Confirm the ordinary PR or every carved-stack PR is merged remotely.
02. Fetch and prune the remote.
03. Confirm the ordinary branch or complete stack result is represented on the
    verified base. Use ancestry first and patch equivalence after squash or
    rebase when needed.
04. Map the exact ticket worktree, source and published branches, upstreams, PR
    heads, and base branch. Never rely on the current directory or a branch-name
    guess.
05. Inspect tracked, staged, unstaged, untracked, and ignored state in that
    exact worktree. Classify ignored and untracked paths as reproducible output
    or non-reproducible/user-created data. Preserve credentials, `.env` files,
    local databases, and all non-reproducible artifacts.
06. Confirm each local published branch has no commits absent from its pushed PR
    branch. When a remote branch is gone, compare it with the recorded PR head.
07. If a pushed branch exists, confirm it did not advance beyond the recorded PR
    head and that the recorded result is represented on the base.
08. Remove only a clean disposable worktree, scoped to
    [provenance-scoped cleanup](worktree-isolation.md#provenance-scoped-cleanup):
    the exact worktree this run created, at its recorded path. Never force
    removal and never sweep a convention directory by naming pattern.
09. Delete only verified merged local feature branches, then their remote
    branches when policy and authority permit.
10. Prune worktree metadata and verify the intended path and branches are gone.

Stop cleanup and report exact dirty paths, ignored paths, unique commits, or
branch drift when any precondition fails. Preserve unrelated worktrees,
branches, ignored files, untracked files, and user edits.

## Mainline and ticket verification

After merge, verify:

- the remote base advanced or otherwise contains the complete ordinary or
  stacked result;
- the implemented behavior and tests exist on the base;
- every required post-merge acceptance entry passes for the exact deployed or
  candidate SHA, environment, evidence category, and source;
- the owning tracker transitioned only after acceptance passed;
- for an epic child, affected native dependency relationships were reread after
  acceptance and transition, and newly unblocked work was reported without
  selection or mutation;
- no required check or review state invalidated the claimed result; and
- every performed cleanup action passed its preconditions.

A merged candidate with missing required post-merge evidence is delivered but
not accepted: keep or reopen the ticket, return `blocked`, preserve the merged
publication identity, and name the next verification or authority needed.

Do not close a parent epic, verify whole-epic acceptance, or implement newly
unblocked work. Report newly ready work only as context.

## Result fields

Return a concise documented handoff. Do not require a machine-readable schema
unless the caller supplies the versioned delegated-execution contract. In that
mode, validate the structured result against both its schema and invocation
before return. Otherwise include every applicable field:

- `terminal_state`: `ready_pr`, `ready_prs`, `merged`, `blocked`, or
  `requires_epic`;
- ticket identity, tracker, repository, PR host, and base identity;
- branch, worktree, candidate head, publication path, and PR or ordered stack
  identity when created;
- delivery state separately from tracker/acceptance state;
- the readiness gate's re-check of the ticket's stated assumptions: which still
  hold, and which could not be checked from the tree — `none` when the ticket
  states no assumption;
- completion policy and the authority actually used;
- the criterion-specific acceptance ledger: criterion, required flag, evidence
  category, pre/post-merge stage, candidate/deployed SHA, environment/URL,
  source, and `pass`/`fail`/`missing` status;
- focused and full validation commands, outcomes, and limitations;
- the initial `review-fix-loop` terminal state (`converged`,
  `changes_remaining`, or `blocked`), its `review_records` and
  `unresolved_or_deferred_findings`, and the reviewed candidate identity;
- when a fix cycle ran: `review-fix-loop`'s consumed/remaining cycle accounting,
  each cycle's `finding_dispositions`, any `scope_decision_required` block
  surfaced for caller disposition, and whether the final cycle's `apply_fix`
  port was escalated to a fresh implementer and at what capability tier;
- `babysit-pr` policy, terminal state, returned candidate identity, authority
  used, mutation ownership, and independently verified live-state match, one
  entry per published PR;
- when a repository-owned `publish-candidate` owned publication: its returned
  status, every PR identity it returned with that PR's head SHA and base ref,
  which single PR carries the closing or non-closing tracker reference, the
  independently verified live-state match, and — for `needs_author_input` —
  exactly what the delegate named as author-owned and unsupplied. When no
  `publish-candidate` resolved, record that publication was inline;
- for a stack, `carve-changesets` source identity, guardrail and operator
  decision, authority, terminal state, ordered PR topology, equivalence,
  propagation, closing-syntax placement, and verified live-state match;
- applicable CI, human, connector, comment, formal-review, and thread state;
- merge, mainline, ticket transition, and cleanup state;
- deferred findings and intentionally unperformed work; and
- one concrete next action or blocking reason.

For example:

```text
terminal_state: ready_pr
ticket: LIN-482 (Linear)           repository: example/project (GitHub PRs)
pr: #91 open, mergeable            base: main @ 7be0…44c2
branch: scott/lin-482-rate-limits  worktree: ../wt-lin-482
head: 4f2c…9a1d
completion_policy: ready PR only   authority_used: implement + push + PR create
acceptance: API regression test (required, pre-merge, automated-test) pass;
  head 4f2c…9a1d; source `just test`; no post-merge items
validation: `just test` pass @ head; `just check` full gate pass @ head
initial_review: review-fix-loop converged @ head 4f2c…9a1d vs base 7be0…44c2
  (1/3 fix cycles consumed)
babysit_pr: ready_to_merge @ head, verified against live GitHub state;
  CI 6/6 pass, human review approved, 0 unresolved threads
merge: withheld (not authorized)   tracker: LIN-482 still In Progress
cleanup: none performed (PR open)  deferred: one defer-severity naming finding
next_action: caller may merge; integration will transition LIN-482 only because
  all acceptance is pre-merge
```

For `ready_pr`, require a verified `babysit-pr: ready_to_merge` result for the
still-current open and mergeable PR and passing required pre-merge acceptance
entries. Every applicable non-merge gate must pass; the only withheld action is
merge. Post-merge entries may remain pending only with non-closing tracker
syntax. Do not list ordinary pending CI or review as a remaining gate.

For `ready_prs`, require passing required pre-merge acceptance entries; every PR
open, correctly based, mergeable, and at its applicable non-merge gate; correct
closing/non-closing syntax; exactly one lifecycle owner per PR; and each PR's
exact base ref, base SHA, head ref, and head SHA. Which further evidence is
required depends on which delegate published, not on the terminal name:

- A carved stack requires a verified `carve-changesets: prs_open` result for the
  still-current ordered stack, verified whole-chain equivalence, and a chain
  topology the reported refs prove: the first PR starts at the candidate base,
  each later PR starts at the prior PR head, and the final PR head equals the
  candidate. The only withheld actions are merge and propagation.
- A delegated ordinary publication requires a verified
  `publish-candidate: published` result naming every PR it opened, each one
  independently reverified against live host state. Do not require chain
  topology or whole-chain equivalence of it: those are the carved path's
  obligations, and a delegate may legitimately open several PRs sharing one base
  because the repository requires one class of change to land ahead of another.
  The only withheld action is merge.

A `publish-candidate: needs_author_input` result is `blocked` with nothing
published. Preserve the converged candidate and its evidence as a resumable
handoff, report exactly the author-owned content the delegate named as missing,
and never substitute authored, paraphrased, or inferred text for it. Report it
as a publication gap awaiting the author, not as a failed implementation.

For `merged`, require a verified `babysit-pr: merged` or
`carve-changesets: all_merged` result plus independent mainline, complete
criterion-specific acceptance evidence, tracker transition, dependency refresh,
and cleanup checks. A merged delivery with pending acceptance remains `blocked`,
even if automation closed the tracker. A `closed` babysitter result becomes
`blocked` with `PR closed without merge` and preserves local artifacts unless
another canonical completion is proven.

For `requires_epic`, require all of:

- no branch, worktree, ticket, or PR mutation occurred;
- `target_skill` is `implement-epic`;
- the resolved tracker, repository, ticket, native type, and sub-issue evidence;
- stable marker `implement-ticket:requires-epic:<tracker>:<ticket-id>`; and
- an explicit missing-skill limitation when `implement-epic` is unavailable.

If the incoming handoff already contains the same marker, return `blocked` with
`routing cycle detected` rather than another `requires_epic` result.

For delegated execution, a blocked result distinguishes `none`, `local`, and
`published` implementation state. Published state includes the verified remote
URL, full ref, exact head, and publication topology and is transferable. Local
state is explicitly non-transferable and includes the reason publication could
not safely occur. Never substitute a workspace path or local-only SHA for a
durable handoff.
