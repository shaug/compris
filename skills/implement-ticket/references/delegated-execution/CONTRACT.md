# Delegated execution contract

This optional contract lets an external coordinator invoke `implement-ticket`
while retaining authority over consequential external mutations. It is generic:
the coordinator is opaque to Compris, and no Atelier concept appears in the
protocol.

The capability identifier is `compris.implement-ticket/delegated-execution/v2`.

## Contract ownership

- `capability.json` is the discovery manifest and is validated by
  `capability.schema.json`.
- `invocation.schema.json` owns the invocation shape.
- `checkpoint-request.schema.json` and `checkpoint-response.schema.json` own the
  synchronous fencing exchange.
- `result.schema.json` owns the terminal result shape.
- `validate.py` validates schemas and cross-field semantics without third-party
  dependencies.
- This document owns process semantics that JSON Schema cannot express.

All objects reject unknown fields. An unsupported version, malformed object,
failed validator, failed checkpoint command, or ambiguous response blocks
execution.

## Invocation

The caller validates and supplies one invocation object before any mutation. It
binds the run to:

- one ticket and tracker;
- one repository, exact base ref, and exact base SHA;
- one caller-owned work identifier and revision;
- opaque caller-owned approval evidence;
- intent, scope, non-goals, constraints, and done definition;
- a structured acceptance contract with one stable criterion identity, required
  flag, evidence category, stage, candidate/deployment identity basis, and
  applicable environment/URL requirement per item;
- the caller-observed starting deployment's candidate SHA, deployed SHA,
  environment, and URL, or explicit null when none applies;
- required validation and review expectations;
- a finite authority ceiling;
- one desired delivery outcome;
- the terminal states the caller can consume;
- an argv-style checkpoint command;
- the caller's last consumed checkpoint sequence; and
- an opaque continuation token.

Capability tier is deliberately not a field here. A coordinator composing this
invocation still chooses one, so the recommendation applies as prose: take the
cheapest tier adequate for the work, inherit the session's tier for judgment
work, and escalate one tier on repeated failure rather than retrying
identically. An omitted selection silently inherits the session's tier, so state
it when it matters. Prefer fewer, better-briefed invocations to many thin ones.
This adds no field, gates nothing, and never changes a terminal state — a
coordinator that ignores it remains contract-conformant.

Required validation expectations include the change-demonstrating-test evidence
slot that `implement-ticket` requires of every run. The delegate records which
form applies — `evidence_behavioral_test`, `evidence_regression_test`,
`evidence_refactor_preservation`, or `evidence_docs_config_exemption` — and the
observations that satisfy it: behavioral tests encoding the ticket's acceptance
criteria against the product's public surface, failing at the base SHA and
passing at the head SHA for feature work; a regression test red at base and
green at head for a bug fix; the existing behavioral suite green at both SHAs
with no behavioral-test changes for a behavior-preserving refactor; or the
recorded exemption for a docs-or-config-only change. Those tests assert surface
behavior and never implementation internals, so a test that would churn under a
behavior-preserving refactor does not satisfy the slot.

Encode the slot inside the existing observation shape. Two bundled-validator
rules constrain it, and a violation of either blocks execution: no
`$.validation` entry may carry a `candidate_sha` other than the candidate head
SHA or `null`, and no two entries may share a byte-identical `name`. The
base-failing observation therefore cannot be bound to the base SHA; name that
SHA instead.

Two encodings satisfy both rules without any schema change, and a delegate may
use either:

- one entry whose `name` carries the identifier and both observations, bound to
  the candidate head SHA; or
- two entries with distinct names, where the base-failing entry leaves
  `candidate_sha` as `null` and the head-passing entry is bound to the head SHA.

When the caller also lists the slot identifier among its required validation
commands, that entry is additionally bound by the delivery-terminal rule: its
`name` must equal the caller's command string exactly and its `candidate_sha`
must be the head SHA, so a composed name is rejected there. Carry the
base-failing observation in a second, differently named entry in that case.

This obligation is prose riding in the existing validation evidence; it adds no
invocation or result field. It is peer-independent and supersedes the absolutes
of any peer methodology skill loaded in the delegate's context — including a
universal red–green law, which the two named exemptions override; a process law
requiring the test first, since the slot requires the base-failing and
head-passing observations and evidence produced after the implementation
satisfies it; and a per-unit test checklist, which the surface-behavior
requirement overrides. A peer instruction to consult a human maps to the typed
`blocked` result rather than stalling the delegation.

The checkpoint command is an array of executable and argument strings. Agent
Scripts sends one JSON checkpoint request on standard input and requires exactly
one JSON checkpoint response on standard output. It does not invoke a shell,
interpret extra output, persist credentials, or inspect the continuation token.
The first request sequence is exactly one greater than the invocation's
`last_sequence`, so a new delegate can continue an existing caller-owned claim.

The generic terminal states remain `ready_pr`, `ready_prs`, `merged`, `blocked`,
and `requires_epic`. A caller may narrow this set. `implement-ticket` must not
select an outcome the invocation excludes. If its only correct outcome is
excluded, it returns `blocked` without performing the excluded action.

## Consequential mutation checkpoint

Immediately before every consequential external mutation, `implement-ticket`
sends a `pre_external_mutation` request. The finite action vocabulary is:

- `repository.candidate.create`
- `repository.candidate.push`
- `pull_request.create`
- `pull_request.update`
- `review.reply`
- `review.resolve`
- `ticket.update`
- `tracker.auto_close.authorize`
- `ticket.dependencies.update`
- `ticket.followup.create`
- `changeset.carve`
- `pull_request.merge`
- `repository.branch.delete`
- `deployment.execute`
- `production.mutate`
- `destructive.execute`

The request includes the invocation identity, current continuation token,
strictly increasing sequence, action, exact current ticket observation, exact
candidate when one exists, and a concise proposed-effect description.

Candidate push, pull-request, review, carving, merge, and candidate-branch
deletion checkpoints require the exact candidate. A push checkpoint describes
the proposed remote URL, full ref, base SHA, and head SHA before publication.

The coordinator must reread its authoritative state and return `allow` or
`deny`. `allow` must name the same invocation and request sequence and return a
new opaque continuation token. `deny` echoes the request's continuation token;
it does not advance durable sequence or token state. Identity mismatch, sequence
mismatch, token mismatch, malformed output, command failure, or unavailable
coordinator blocks the mutation.

An `allow` decision authorizes only that one proposed mutation. It does not
cache authority for a later action.

The bundled validator is stateless. The checkpoint command must atomically
compare the expected sequence and current continuation token with its durable
state before returning `allow`, then persist the returned sequence and token.
For an allowed request it must also persist the invocation ID, phase, action,
proposed effect, exact candidate identity, and acknowledgement before returning.
These records are an append-only authorization ledger; they let the caller
compare the terminal `authority_used` report with every consumed allowance.
Replaying a consumed request must fail. The validator's
`validate_checkpoint_progress` helper checks the sequence and token transition,
but the caller owns atomic persistence and the authorization ledger.

## Candidate publication acknowledgement

Immediately after every successful remote candidate publication or advancement,
`implement-ticket` sends a `candidate_published` checkpoint before any later
mutation or terminal result.

The request contains the verified remote URL, full remote ref, base SHA, and
published head SHA. The coordinator returns `allow` only after it has durably
acknowledged that exact candidate. Its response must repeat the acknowledged
head SHA. A missing or different SHA blocks continuation.

This post-publication acknowledgement closes the unavoidable interval between a
Git push and the coordinator's durable record. The pushed candidate remains a
recoverable project artifact even when acknowledgement fails. A blocked result
may report that verified published candidate whether acknowledgement succeeded
or failed. It becomes shared coordinator state only after the caller records it
in a later verified transition.

## Deployment observation acknowledgement

A starting deployment is only an invocation-time baseline; it is not evidence
for a different candidate. After merge and after any authorized deployment, the
delegate sends a `deployment_observed` checkpoint containing the exact candidate
and proposed deployed SHA, environment, and URL. The coordinator rereads the
current deployment from its authoritative source and returns `allow` with
`observed_deployment` only when every field matches and the deployment
represents the exact candidate. A denial or mismatch blocks acceptance.

The caller persists that observation in the checkpoint ledger and passes it to
`validate_result_checkpoint_state` for combined terminal and durable-ledger-tail
validation. That helper forwards the live observation to
`validate_result_for_invocation`; the live observation overrides the starting
snapshot. Without a caller-verified live observation, only a starting deployment
already bound to the exact candidate may satisfy a deployment-based criterion.
Passing post-merge evidence also requires merged PR state; an open candidate
cannot carry post-merge acceptance.

## Terminal result

The terminal result is always validated before return. It records:

- terminal state and exact identities;
- whether implementation state is `none`, `local`, or `published`;
- a remotely reachable candidate and publication topology when one exists;
- whether the handoff is transferable;
- checkpoint sequence and final continuation token;
- validation and review observations;
- a criterion-specific acceptance ledger with required flag, evidence category,
  pre/post-merge stage, candidate/deployed SHA, environment/URL, source, and
  `pass`/`fail`/`missing` status;
- the caller-verified final tracker state, transition mode, and observation
  time;
- authority actually used;
- unresolved obligations; and
- one next action or blocking reason.

`ready_pr`, `ready_prs`, and `merged` require published, transferable candidate
state and at least one acceptance record. `ready_pr` requires exactly one PR;
`ready_prs` requires a stack. `requires_epic` requires no implementation state
and may have an empty ledger.

`ready_prs` meaning a stack is narrower here than in the skill's own terminal
vocabulary, and deliberately so at `v2`. `implement-ticket` also reaches
`ready_prs` when a repository-owned `publish-candidate` splits an ordinary
publication into several PRs sharing one base — a shape `publication.kind`
cannot name and this contract's chain rules below reject, since they require
every later PR to base on the previous PR's head. A run under this contract
therefore must not publish a split: pass no
`decompose oversized candidates into stacked changesets` equivalent for
publication, and treat a delegate that splits anyway as a contract violation
that returns `blocked` with its published PR identities preserved, rather than a
`ready_prs` this validator would reject after every PR already exists.
Representing a split needs a new `publication.kind` and its own validation
branch, which is a versioned change to this contract and not something a caller
may assume at `v2`.

Except for `requires_epic`, the terminal ledger must cover the invocation's
acceptance contract one-to-one: it may neither omit a criterion nor invent one,
and its required flag, category, stage, identity basis, exact required source,
and applicable environment/URL must match the caller-owned requirement. A
passing record's source must equal the authored source; a delegate summary or
other nonempty substitute does not satisfy it. Passing evidence must match the
required identity basis: candidate-bound evidence names the exact candidate;
deployment-bound evidence names the exact caller-observed deployment SHA,
environment, and URL whose candidate SHA matches the result candidate. Delivery
terminals must report every required pre-merge entry as passing at the exact
candidate, every required validation command as passed, satisfy requested
independent review, and report zero unresolved material feedback when requested.
Every passing post-merge record requires merged PR state. `merged` additionally
requires every required post-merge entry to pass with its declared candidate or
caller-verified deployment identity. A merged publication with pending
acceptance returns `blocked` while preserving its transferable candidate.

`merged` is also a tracker-completion claim. The result's `tracker_transition`
is delegate-supplied evidence, not an authoritative observation. The caller must
reread the owning tracker and pass a final observation bound to provider, ticket
ID, state, transition mode, and observation time into
`validate_result_for_invocation` or `validate_result_checkpoint_state`; the
helper requires an exact match. It also requires the caller's consumed-authority
ledger to match `authority_used` exactly. A manual transition requires
`ticket.update`; an automatic transition requires the distinct
`tracker.auto_close.authorize` grant for closing syntax and a subsequent live
closed-state observation. Automatic closing authority does not imply manual
`ticket.update` authority. A merged publication with an open, stale, delegate-
only, mismatched, or unauthorized tracker transition returns `blocked` while
preserving delivery.

Published implementation must report the candidate push in `authority_used`. A
result containing a pull request must also report the corresponding pull-request
create or update action. Validation and review observation names are unique;
duplicate observations cannot override one another by array order. An ordered
`ready_prs` stack contains distinct pull request identities, URLs, and heads,
and its final pull request head equals the reported candidate head. Each PR
records its exact base ref, base SHA, head ref, and head SHA. The first base ref
and SHA equal the invocation base; every later base ref and SHA equal the
previous PR head ref and SHA.

A blocked run with published implementation must return its transferable
candidate. It may have zero pull requests when execution blocked after the push
but before PR creation, including when candidate acknowledgement failed. A
blocked run with only local implementation returns no candidate, sets
`transferable` to false, and explains why no durable handoff exists. It must
never describe a local-only SHA as transferable.

The caller must validate every terminal result against the durable checkpoint
ledger tail, not merely the invocation's starting position. The bundled
`validate_result_checkpoint_state` helper requires the terminal sequence and
continuation token to equal that caller-supplied tail. For `merged`, it also
requires the caller-observed final tracker record and consumed-authority ledger.
The CLI accepts those JSON values through `--observed-tracker` and
`--consumed-authority`. A stale terminal checkpoint blocks handoff.

A material ticket-observation change always causes the caller to deny the
current invocation. Eligibility may be reevaluated only before starting a fresh
invocation with a newly observed ticket contract. The current invocation's
terminal result therefore continues to identify its original ticket observation
truthfully.

## Compatibility and failure

Standalone invocations remain unchanged and may return the documented human
handoff. Delegated execution applies only when the caller supplies a valid v2
invocation. Version 2 adds the required acceptance-evidence ledger to terminal
results; v1 manifests, invocations, checkpoints, and results are rejected rather
than silently interpreted under the stronger closeout contract.

There is no daemon, callback server, or background lease. The checkpoint command
is synchronous and caller-owned. If the caller disappears, execution fails
closed at the next checkpoint and preserves any already-published candidate.

The coordinator identity is cooperative attribution, not authentication.
Operating-system permissions, repository access, and provider controls remain
the enforcement boundaries.
