# PR lifecycle and successor-source recovery handoffs

This reference defines how `carve-changesets` composes with the repository-owned
`babysit-pr` skill for a published PR's lifecycle, and the successor-source
recovery procedure that follows a returned handback. The normative changeset
state, authority, and safety rules remain in [SPEC.md](SPEC.md). Each
changeset's own local review and fix loop is delegated to `review-fix-loop`
instead — see [the review-fix-loop handoff](review-fix-loop-handoff.md) for that
composition, including the per-changeset review packet fields it feeds into
`review-fix-loop`'s `reviewer` port. The delegated skills' live contracts remain
authoritative for their internal behavior.

## Ownership boundaries

`carve-changesets` owns changeset boundaries, materialization, chain ordering,
metadata, whole-chain equivalence, and downstream propagation. It constructs
each changeset's `review-fix-loop` invocation and the published PR-lifecycle
handoff, and verifies returned identities before promoting chain state.

`review-code-change` remains read-only underneath `review-fix-loop`: it reviews
one exact changeset candidate and returns an evidence-bound verdict; it does not
edit a changeset, choose a new boundary, mutate the plan, or push a branch.
`review-fix-loop` owns applying an accepted fix and rebuilding invalidated
validation and review evidence within one changeset's local review loop;
`carve-changesets` never reproduces that mechanic itself.

Once ownership of a published PR is delegated, `babysit-pr` exclusively owns
that PR's current-head CI, failed-check diagnosis and eligible retries,
published feedback, ticket-scoped candidate fixes, post-fix repository review,
base drift, mergeability, and optional merge. `carve-changesets` must not run a
competing watcher, retry checks, disposition review threads, or mutate the
delegated candidate.

The reverse boundary is equally strict: `babysit-pr` does not rebase, renumber,
retarget, or successor-restamp the remaining stacked changesets and does not
perform downstream propagation. After a verified merge result or explicit
recovery handback returns, those chain mechanics belong to `carve-changesets`
again.

## Per-changeset review packet

[The review-fix-loop handoff](review-fix-loop-handoff.md)'s `reviewer` port
constructs a fresh `review-code-change` packet for changeset *i* from raw,
current evidence for every review pass that invocation runs. Never add the
implementation transcript, expected findings, prior conclusions, or fixture
answers.

| Packet section    | Changeset evidence                                                                                                                                                                                                                                                                                                               |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `repository`      | Exact repository identity and the stacked base branch: the chain's base branch for changeset 1, otherwise changeset *i - 1*'s branch.                                                                                                                                                                                            |
| `candidate`       | Exact changeset head SHA, exact stacked-base SHA as `comparison_base_sha`, and the complete unified diff from that stacked base to the changeset head.                                                                                                                                                                           |
| `change_contract` | Goal derived from the changeset slug and description, with `pr_notes` preserving scaffolding, flags, and intentional incompleteness. Acceptance criteria state the observable outcome at this position; non-goals name work reserved for later changesets; preserved behaviors include the applicable invariants from `SPEC.md`. |
| `sources`         | Applicable repository instructions, `SPEC.md`, named architecture or design documents, and representative nearby patterns for the files changed by this changeset.                                                                                                                                                               |
| `validation`      | At least one focused and one full entry with exact commands and results. Focused evidence covers the chain prefix through changeset *i*; full evidence records the approved repository or whole-chain validation applicable at this boundary. Required unavailable checks are recorded as unavailable, never silently omitted.   |
| `worktree`        | Tracked, staged, unstaged, untracked, and ignored state when needed to prove candidate integrity.                                                                                                                                                                                                                                |

The packet must satisfy the bundled review-suite contract and schema. In
particular, the diff is complete and candidate-bound, acceptance criteria are
non-empty, and every required validation command has an exact result or an
explicit unavailable reason.

Review is required before claiming `chain_ready` or `prs_open`, and the
`review-fix-loop` result must be `converged` for every exact changeset candidate
represented by that terminal state. It is also required before a published
candidate is handed to `babysit-pr` when no current `converged` result exists.
Any changeset head change invalidates its packet, validation, and verdict;
rebuild all three through a fresh `review-fix-loop` invocation before
continuing.

For base-only drift, retain review evidence only when the review-suite contract
allows it: the effective diff and resulting tree are unchanged, no conflict or
relevant overlap exists, repository policy permits retention, and the proof is
recorded. Otherwise rebuild the affected packet and review.

Review may run earlier after a changeset has been materialized, but an early
result does not establish a later terminal state unless its candidate identity
still matches. `plan_ready`, dry-run planning, and status-only operations have
no materialized candidate to review and do not require or invent a packet.

## PR lifecycle handoff

Delegate only an open PR whose exact head and predecessor base match the
rehydrated chain. Immediately before handoff, capture and verify:

- repository, PR number and URL, head repository, branch, head SHA, base branch,
  and base SHA;
- changeset index, slug, source identity, required metadata, complete diff,
  resulting tree, and commit history;
- tracked, staged, unstaged, untracked, and ignored worktree state;
- focused and full validation evidence and the current clean per-changeset
  review result;
- the ticket-level publication observation received from `implement-ticket`:
  `predicted_shape` with unchanged identity and authoritative source or explicit
  missing values, and the exact named `fired_trigger` or `null`; the
  pre-publication handoff never guesses a terminal outcome;
- required CI, human, connector, comment, formal-review, reaction, and thread
  gates, including documented absence;
- completion policy, retry and review-cycle budgets, and the separately granted
  mutation, push, retry, reply, resolution, and merge authorities; and
- exclusive mutation ownership plus the changeset scope and non-goals that
  constrain any PR fix.

Candidate identity and authority must match the live `babysit-pr` contract.
Reject stale, conflicting, forked, superseded, or ambiguously owned PR state
instead of delegating it.

At each handoff, derive `implementation_outcome` at the PR-lifecycle boundary
from the live publication state. A verified complete carved topology with an
available one-PR prediction is `falsified`; an incomplete publication with an
available prediction is `unavailable`; and a missing prediction is `missing`.
Pass that current outcome with the stable ticket-level prediction and trigger,
and require each returned `lifecycle_observation` to bind both its item and head
identity to that PR's exact current PR head. If publication completeness changes
while the PR head stays fixed, record a new same-head observation; recovery uses
the latest matching entry rather than the stale outcome.

Accept the observation only when it echoes `predicted_shape`,
`implementation_outcome`, and `fired_trigger`, reports reviewability and
operator effort separately as `observed`, `uncertain`, or `missing`, and is
explicitly non-gating through `non_gating: true`. Missing, contradictory, or
stale-head telemetry blocks lifecycle result mapping; it never changes the
independently verified delivery state or any existing gate.

| Active `carve-changesets` authority | `babysit-pr` policy | Passed authority                                                                                                                                          |
| ----------------------------------- | ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Decompose-only                      | No handoff          | Remote publication is forbidden.                                                                                                                          |
| Publish                             | `ready_to_merge`    | Existing changeset candidate mutation and push authority may be passed through. Merge is withheld; reply and thread-resolution authority remain separate. |
| Merge-and-propagate                 | `merge_when_ready`  | Explicit merge authority is passed through without expansion. Reply and thread-resolution authority remain separate.                                      |

Ordinary pending CI or review time is not a reason for `carve-changesets` to
reclaim ownership. A head-changing fix made before any prefix merge remains
inside `babysit-pr`: rerun affected and full validation, obtain a fresh
repository-owned review, push the new candidate, and rebuild invalidated remote
gates before returning a terminal result.

## Successor-source recovery handback

When a ticket-scoped fix changes a suffix candidate after an earlier changeset
has merged, `babysit-pr` must not merge a candidate that fails the chain's
root-source equivalence and must not attempt chain mechanics itself. It returns
exclusive ownership to `carve-changesets` with the exact PR, old stamped head,
corrected head and tree, accepted ticket scope, current gates, and the merged
prefix identity. This is a recovery handback, not a terminal success.

`carve-changesets` may proceed only when the merged prefix remains valid and is
represented on current base. It must create or receive a distinct immutable
successor source containing all accepted fixes, then:

1. rehydrate the root chain and exact open suffix from live git and GitHub;
2. prove continuous source lineage and exclusive same-repository branch and PR
   ownership;
3. preview and exact-lease update only the unmerged suffix with v2 commit and PR
   metadata while preserving stable indexes, slugs, branches, and PRs;
4. prove current base plus the recovered suffix equals the successor source;
5. invalidate every candidate-bound validation, review, CI, connector, feedback,
   and mergeability result for each changed head;
6. delegate a fresh `review-fix-loop` invocation for each recovered changeset,
   per [the review-fix-loop handoff](review-fix-loop-handoff.md), and obtain a
   `converged` result bound to the exact recovered head; and
7. hand the corrected exact PR back to `babysit-pr` under the original bounded
   authority.

If the accepted fix invalidates the merged prefix, or lineage, ownership, exact
leases, source immutability, or successor equivalence cannot be proved, return
`blocked`. Recovery never rewrites or restamps the merged prefix.

## Terminal-result mapping

Reread live GitHub and git state before accepting a returned terminal result.
The repository, PR, branch, head, base, completion policy, authority, gate
evidence, and exact-current-head `lifecycle_observation` must match the handoff.
A stale or conflicting result maps to `blocked`; do not translate it into
progress.

| `babysit-pr` result | `carve-changesets` handling                                                                                                                                                                                                                                                                                                                                                      |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ready_to_merge`    | Accept only for the exact open, mergeable candidate after every applicable non-merge gate passes. With publish authority, this contributes to `prs_open`; merge remains withheld.                                                                                                                                                                                                |
| `merged`            | Independently verify the exact PR merged and its result is represented on the live base. Rehydrate the chain, propagate the downstream branches and PR bases under merge-and-propagate authority, then hand the next exact PR to `babysit-pr`. Claim `all_merged` only after the final PR, propagation, equivalence, validation, and cleanup requirements in `SPEC.md` all pass. |
| recovery handback   | Verify the corrected exact candidate and merged prefix, reclaim exclusive ownership, and run the successor-source recovery procedure above. Rebuild all invalidated evidence before re-delegating.                                                                                                                                                                               |
| `closed`            | Return `blocked` with `PR closed without merge` unless a canonical replacement is independently verified; preserve partial artifacts.                                                                                                                                                                                                                                            |
| `blocked`           | Return `blocked` with the concrete reason, exact candidate reached, preserved artifacts, and one action required to resume.                                                                                                                                                                                                                                                      |

When propagation changes a downstream head or effective candidate, prior review,
validation, CI, and feedback evidence is invalid. Rebuild the per-changeset
review through a fresh `review-fix-loop` invocation before the next lifecycle
handoff. When only the stacked base identity changes, apply the review-suite
base-drift rules rather than assuming evidence survives.
