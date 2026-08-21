# GitHub ticket and PR adapter

Use GitHub independently as an issue tracker, a PR host, or both. Apply only the
sections owned by its role for this ticket.

## Ownership boundary

- When GitHub owns ticket state, use the issue preflight, scope, relationship,
  duplicate-work, closing-reference, and transition rules below.
- Whenever GitHub hosts the PR, use PR preflight, review, check, merge, and
  branch rules.
- When Linear owns the ticket and GitHub hosts the PR, route parent, blocker,
  status, and close decisions through the Linear adapter. Do not inspect or
  mutate a same-numbered GitHub issue as a substitute.

## Issue preflight and scope

When GitHub owns ticket state:

- read the live title, body, state, issue type, labels, and scope-affecting
  comments;
- read native `parent`, `subIssues`, `blockedBy`, and `blocking` relationships
  through GraphQL or an equivalent structured tool;
- use native issue type and sub-issues to apply the epic scope guard;
- verify every required closed-blocker outcome in its authoritative source; and
- search open and merged PRs plus plausible feature branches for an existing or
  superseding implementation.

Do not infer ownership, epic status, or dependency state from title, number,
Markdown task lists, or prose when native relationships exist. A label may
support but cannot override contradictory structured state.

For a ticket that belongs to an epic, read the parent outcome and only the
sibling contracts or prerequisite results needed for correctness and independent
shipping. Never select another child or mutate the graph from this skill.

When duplicate branches or PRs exist, compare actual patches or resulting trees
and retain one canonical implementation path. For an open canonical path owned
by another worker, return `blocked` with its identity unless ownership is
explicitly transferred; never claim its candidate as this run's `ready_pr` or
`ready_prs`. A merged PR and `CLOSED` issue prove delivery/administrative state,
not acceptance. Return `merged` without new implementation only when the
criterion-specific ledger passes for the current candidate/deployment and the
tracker transition is correct. Return `blocked` rather than creating a competing
PR when canonical ownership is unresolved.

## PR-host preflight and contract

- Resolve the repository from the request or checkout and confirm
  authentication.
- Confirm the remote base, current checkout, branch, and worktree topology.
- Inspect open and merged PRs that reference the owning tracker ticket.
- Use one tracker ticket per candidate, and publish that candidate exactly once.
  The publication takes one of three shapes: one ordinary PR, one ordered carved
  stack, or the several PRs a repository-owned `publish-candidate` may split an
  ordinary publication into.
- When GitHub owns ticket state and every required acceptance item can pass
  before merge, use the repository's closing syntax, normally `Fixes #<issue>`.
- When any required item needs merged code, deployment, authentication, or
  another post-merge environment, use `Refs #<issue>`, `Supports #<issue>`, or
  the repository's established non-closing equivalent. Close manually only after
  the current acceptance ledger passes and close authority exists.
- If closing automation transitions the issue before required acceptance passes,
  treat it as incomplete. Reopen it when authorized; otherwise report missing
  reopen authority as a blocker.
- For a carved stack, closing syntax is permitted only on the final changeset PR
  and only under the same pre-merge-acceptance rule. Every intermediate PR uses
  a non-closing reference.
- When another tracker owns state, use its required reference and avoid GitHub
  closing syntax unless a real GitHub issue is also intentionally in scope.
- Describe the branch as a whole, preserve material non-goals, and report actual
  validation plus pre-merge and post-merge acceptance-ledger state.
- Confirm the PR base and head match the ticket worktree.

Use file-based commit and PR messages when shell interpolation could alter
Markdown.

## Handoff and caller-owned closeout

For the ordinary path, resolve repository-owned `publish-candidate` by stable
name at the publication boundary. When it resolves, transfer publication to it
with the fields [the publish-candidate handoff](publish-candidate-handoff.md)
requires; when it does not, push the branch and open the one PR here as before.
Then capture the exact PR head and base, effective candidate, worktree state,
validation, initial review, required remote-gate policy, connector contract,
completion policy, and authority required by
[the babysit-pr handoff](babysit-pr-handoff.md), and delegate each published PR
to repository-owned `babysit-pr`.

For the carved path, capture the immutable source candidate, guardrail and
operator-decision evidence, completion policy, tracker semantics, and authority
required by [the carve-changesets handoff](carve-changesets-handoff.md), then
delegate the entire stack lifecycle to repository-owned `carve-changesets`.

Do not infer a gate's absence from an empty read. Pass the documented policy and
all known current evidence so the babysitter can establish current-candidate
state. Do not also poll, mutate, reply, resolve, or merge from this caller after
ownership transfer.

After every PR of the publication reports merged — a babysitter `merged` per
published PR, or a carve `all_merged` for a stack — independently verify that PR
or stack state and complete candidate representation on the base, then run every
required post-merge acceptance item with separately granted authority. A subset
merged is merged delivery of a fraction and is not this step. Transition the
GitHub issue only after the ledger passes. When the ticket is an epic child,
reread affected native relationships only after acceptance and the transition
pass. If local worktree ownership prevents switching to the base, use a
read-only remote verification path and perform local cleanup separately. Never
close a parent issue from this skill.
