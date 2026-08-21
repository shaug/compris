# Publish-candidate handoff and result mapping

Use repository-owned `publish-candidate` as the sole owner of the ordinary
path's publication whenever the repository provides that role. Read its live
skill, references, and result contract before delegation. If its delivered
contract differs materially from this boundary, stop and reconcile ownership
rather than copying publication mechanics into `implement-ticket`.

This role is optional, and its absence is the ordinary case rather than a
failure. Where no `publish-candidate` resolves, this reference does not apply
and [step 6](../SKILL.md#6-publish-and-delegate-the-selected-path) publishes
inline exactly as it always has, with nothing else about the step changed.

The reference also applies only to the ordinary single-PR publication path. The
carved path is unchanged: `carve-changesets` already owns its own publication
and its own per-changeset `babysit-pr` delegations, so never route a carved
candidate through `publish-candidate`. Use
[the carve-changesets handoff](carve-changesets-handoff.md) there instead.

## Responsibility boundary

`implement-ticket` retains ticket resolution and readiness, epic routing,
exclusive implementation state, the implementation and its validation, the
initial `review-fix-loop` delegation, the acceptance evidence ledger, the
publication size gate, completion-policy and authority mapping, the tracker
reference and closing-syntax decision, the `babysit-pr` handoff for every
published PR, terminal-result validation, post-merge mainline and tracker
verification, dependency refresh, cleanup, and final reporting.

After handoff, `publish-candidate` owns everything between a converged local
candidate and one or more open pull requests: base-ref selection, branch push,
PR creation, PR title and body authorship, whatever pre-flight repository
requirements publication carries, publication-time repository gates, and whether
this candidate publishes as one PR or as several. It returns responsibility at
the open PR. It does not review the candidate, own any PR's post-publication
lifecycle, transition the tracker, merge, delete a branch, or deploy.

Do not reproduce those mechanics in this skill, and do not encode any particular
repository's publication rules here. A mandatory base branch that is not the
default branch, a required PR title format, a required author-written narrative
section, a pre-flight routing or ownership manifest entry, a gate that runs only
at publication time, and a mandatory split of one change class into its own PR
are each the delegate's to know. This skill knows only that a delegate may
require them, and that one of them may require a human.

## Resolution at the publication boundary, not a pre-mutation gate

`review-fix-loop` and `babysit-pr` are verified before a branch exists, because
every successful run needs both and a candidate no owner will monitor must never
be created. `publish-candidate` is the opposite case and is deliberately absent
from that gate. Resolve it at the publication boundary in
[step 6](../SKILL.md#6-publish-and-delegate-the-selected-path), after the
candidate has converged, and only on the ordinary path.

An unresolved `publish-candidate` never blocks and never reports a missing
capability. It selects inline publication — push the candidate branch, open one
focused PR — and changes nothing else. Resolving it before mutation would invert
that: a repository that defines no publication role is the common case, and a
pre-mutation dependency gate would turn the common case into a stop.

Resolve it by stable repository-owned name only. Never download an
implementation at runtime, substitute a third-party publisher, or infer the role
from a repository file that merely describes publication rules in prose. A
repository whose rules live in prose rather than in a resolvable skill has no
delegate here: publish inline and leave those rules to the repository's own
gates.

## Exclusive mutation ownership

Publication is a mutation, so the ordinary rule holds unchanged. The same
exclusive implementation context may invoke `publish-candidate` directly. If
another worker or equivalent context runs it, transfer ownership explicitly and
prove the caller has stopped mutating, then do not resume mutation until that
worker returns or ownership is explicitly reclaimed and live state is
reverified.

The candidate is immutable from handoff until the delegate returns. A delegate
may create branches and push them; it may not amend, rebase, or otherwise
rewrite the converged candidate's own commits, because the initial review, the
change-demonstrating-test evidence, and every pre-merge acceptance entry are
bound to that exact head. A returned head other than the handed-off head
invalidates all of it — see [Terminal result mapping](#terminal-result-mapping).

## Verified handoff

Immediately before delegation, capture and verify:

- ticket identity, owning tracker, observable goal, acceptance criteria,
  required verification items, non-goals, and preserved behavior;
- repository, PR host, current remote base, repository instructions, and named
  architecture, design, contract, migration, and rollout documents;
- the candidate branch, exact head SHA, base branch, exact base SHA, complete
  effective diff, resulting tree, and commit history;
- tracked, staged, unstaged, untracked, and ignored worktree state;
- the change scope: what this candidate changes and what it deliberately does
  not, in enough detail for the delegate to decide whether its own rules require
  more than one PR;
- focused and full validation commands and their exact outcomes;
- the criterion-specific acceptance ledger, with every required pre-merge entry
  passing for the handed-off head and every post-merge entry identified as
  caller-owned;
- `review_converged`: this candidate has already converged under
  `review-fix-loop`, named with that terminal result's exact reviewed head and
  base. The delegate must not re-review it. State this rather than leave it
  implied — a repository publication skill typically runs its own review gates,
  and an unstated assertion gets one converged candidate reviewed twice;
- `tracker_transition: retained_by_caller`: the delegate must not transition the
  tracker. `implement-ticket` retains the acceptance ledger and the transition.
  State this for the same reason — a repository publication skill typically
  detects the tracker reference and updates the item itself;
- the tracker reference and closing-syntax decision this run selected at the
  acceptance stage, expressed as a rule the delegate applies rather than a PR
  identity the caller names. Whether the candidate publishes as one PR or
  several is the delegate's own decision, so at handoff time the caller cannot
  know which PR would carry the reference — only the rule that resolves it:
  exactly one published PR carries the closing syntax and it is the last to
  merge, every other PR carries the non-closing reference, or no PR carries
  closing syntax at all when the completion policy forbids an automatic
  transition. This mirrors
  [the carved path's rule](carve-changesets-handoff.md#policy-and-tracker-mapping),
  which designates the final changeset PR the same way and for the same reason;
  and
- every granted and withheld authority: push, PR creation, and PR update are
  granted; review, merge, branch deletion, tracker mutation, deployment,
  destructive operations, and human-authored communication stay withheld; and
- `publication_shape`: `one_pr_or_several` ordinarily, or `single_pr_only` when
  this run cannot accept a split. The delegate decides the shape within what
  this assertion allows, and a delegate that exceeds it is a contract violation.
  State it explicitly rather than leaving the ordinary case implied, because the
  only caller that must restrict it — a run under
  [the delegated-execution contract](delegated-execution/CONTRACT.md#terminal-result),
  whose `ready_prs` names a stack and cannot represent a split — otherwise has
  no way to say so, and a delegate that split anyway would open every PR before
  the caller discovered it could not report them.

Supply the ticket-wide outcome, important non-goals, actual validation, and
acceptance-ledger state as evidence the delegate may use. The delegate owns the
PR body. Never author it on the delegate's behalf, and never author, paraphrase,
or infer any part of it the delegate reports only the ticket's author may
supply.

The delegate must reject stale or conflicting repository, candidate, head, base,
branch, worktree, scope, or ownership identity. Use this documented shape
without adding a larger mandatory schema unless tests demonstrate a need.

## Policy and authority mapping

- `ready PR only` grants push, PR creation, and PR update. Merge stays withheld.
- `merge after gates` grants the same publication authority and no more. Merge
  is not the delegate's: `implement-ticket` still hands every published PR to
  `babysit-pr` with `merge_when_ready`.
- `merge plus manual transition` maps identically. The separately authorized
  manual tracker transition stays with `implement-ticket` after merge
  verification.

Publication authority is not review, merge, tracker, deployment, or
communication authority, and no completion policy implies any of those for this
delegate. A publication-time repository gate the delegate runs is a check, not a
grant: passing it does not authorize a mutation this run withheld. Pass
authority through without expansion and preserve stricter repository rules.

`publish-candidate` never invokes `babysit-pr`. Every PR it returns gets exactly
one `babysit-pr` handoff, constructed by `implement-ticket` through
[the babysit-pr handoff](babysit-pr-handoff.md). One publication event, and
exactly one lifecycle owner per PR.

## Terminal result mapping

The delegate returns the PR identity or identities, the head SHA, the base ref,
and one status. Reread live host state and validate the returned repository, PR,
head, base, and branch evidence against it before mapping, exactly as
[the babysit-pr handoff](babysit-pr-handoff.md#terminal-result-mapping) already
requires. A returned identity that does not exist, does not match, or carries a
head other than the handed-off candidate head fails closed.

- `published` with exactly one PR is the ordinary single-PR shape. Hand that PR
  to `babysit-pr` and map its result exactly as
  [the babysit-pr handoff](babysit-pr-handoff.md#terminal-result-mapping)
  specifies: `ready_pr` under `ready PR only`, `merged` under either merge
  policy.
- `published` with more than one PR maps to `ready_prs` under `ready PR only`,
  and to `merged` under either merge policy only once every PR it opened is
  merged and represented on the base. This is the one semantic widening the role
  introduces, and it is deliberate: a delegate may legitimately split one
  candidate into several PRs, because a repository may require a
  schema-migration or dependency change to land and deploy ahead of the code
  depending on it. Verify every returned PR is open and correctly based, that
  the closing-syntax rule resolved to exactly one PR and no other, and that each
  PR has exactly one `babysit-pr` owner. The invariant is one publication event
  and one lifecycle owner per PR, not one PR per ticket — and one merged PR of a
  split is merged delivery of a fraction, never the ticket's `merged`.
- `needs_author_input` maps to `blocked`. Publication requires content only a
  human can supply — most often a narrative section the repository requires its
  author to write. Surface exactly what the delegate named as missing, preserve
  the converged candidate and its evidence as a resumable handoff, and stop.
  Never author, paraphrase, or infer the missing content, and never retry
  publication with a placeholder. Report it as a publication gap awaiting the
  author, not as an implementation failure: the implementation converged and the
  ledger says so, and an unattended run halts here rather than inventing the
  sentence a human owes. A `needs_author_input` may carry PR identities: a
  delegate splitting one candidate can publish the first PR and then find the
  second needs author-owned content. Report every PR it did open, hand each one
  a `babysit-pr` owner, and name the publication as partial — a published PR is
  live whatever stopped the run after it, and reporting the stop as "nothing
  published" would strand it unmonitored.
- `blocked` maps to `blocked` with the delegate's concrete reason, the current
  candidate, whatever it published before stopping, and one next action. A
  partial publication is preserved and reported by identity, never silently
  completed inline.

`ready_prs` is shared with the carved path, and the sharing is in the terminal
name only. Ordered predecessor-base topology and whole-chain equivalence are
`carve-changesets`'s obligations, discharged through
[its handoff](carve-changesets-handoff.md#terminal-result-mapping). Require them
of a delegated split only where the delegate itself claims a chain; several PRs
sharing one base are a legitimate split, not a broken stack.

One caller cannot accept a split at all. The optional
[delegated-execution contract](delegated-execution/CONTRACT.md#terminal-result)
defines `ready_prs` as a stack specifically: its `publication.kind` has no name
for a split, and its validator requires every later PR to base on the previous
PR's head. Such a run sends `publication_shape: single_pr_only` in the verified
handoff above, which is what actually reaches the delegate — saying "withhold
split authority" with no field to carry it would convert the dead end rather
than close it, leaving a splitting delegate to open every PR before the caller
discovered it could report none of them. A delegate that splits despite the
assertion is a contract violation: return `blocked`, preserve and report every
published PR identity, and hand each one a `babysit-pr` owner anyway, because
PRs that exist are PRs someone must watch. Outside delegated execution the
assertion is `one_pr_or_several` and a split maps as described above.

A status this contract does not define, a `published` result carrying no PR
identity, or a head this run never handed over is a contract violation: return
`blocked` and reconcile it rather than guessing which mapping was meant. Never
fall back to inline publication after the delegate has run — that risks
publishing one candidate twice, and one candidate publishes once.

Resume from live host state. Reread this candidate's open PRs on the host before
re-invoking the delegate, so an interrupted run does not publish the same
candidate a second time.

## Forward evaluation integrity

Exercise this composition with raw live-shaped ticket, repository-instruction,
candidate, diff, validation, and delegate-result artifacts, including the
delegate-absent case, which must reproduce inline publication unchanged. Exclude
implementation transcripts, intended publication decisions, expected outputs,
and prior conclusions. Treat contaminated evidence as invalid and rerun the
evaluation with a fresh isolated worker context.
