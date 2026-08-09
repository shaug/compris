# Cognitive-driven development

This is the design document for compris taking sole ownership of cognitive
shaping — the doctrine that decides whether a unit of work is comprehensible —
together with the vocabulary that carries it and the skill that enforces it.

Nothing described here is built. This document records the direction, the
decisions behind it, the evidence they rest on, and the one experiment still
owed. A presentation copy is published at
<https://claude.ai/code/artifact/71ba7b43-e1fc-432f-b094-a72ce38852f1>.

## The practice

Work is normally broken apart by feature area, team ownership, or sprint
capacity. Cognitive-driven development breaks it apart by what a reviewer can
understand in one sitting, and treats that as the binding constraint rather than
a nicety observed when there is time.

Two consequences follow, and both are load-bearing.

The tracker hierarchy stops being an organizational choice and becomes a
**derived artifact of the implementation breakdown** — which is why the
breakdown has to happen before the tickets exist, and why nobody can know
whether something is one ticket or twelve until it has been broken down.

And the skill that performs it becomes the highest-leverage and highest-risk in
the suite: everything downstream inherits its decomposition, and no amount of
good implementation repairs a bad one.

## Why this exists

compris is ticket-driven, and that is what separates it from a methodology
library. Capturing a design, reviewing it, breaking it into an implementation
plan, and building it are all necessary — but they have to happen *in public*,
at whatever scope the organization draws. A plan file is local, ephemeral,
single-agent, and dies with the context that produced it.

So the test is simple: **if an implementation plan spans more than one pull
request, it has exceeded its grasp** and should have been represented by
something more permanent. Durable identity, real dependency edges, visibility to
the org, survival across handoffs and context loss. That is a tracker, not a
markdown file.

## The boundary: for when the brainstorming is done

`README.md` currently says compris is *for when the planning is done, and the
work begins*. That is wrong, and it has already misled a reader into inverting
this design once. compris plans constantly — it builds an implementation plan,
shapes it into tickets, and revises it when reality disagrees. Planning is not
the thing it starts after.

Brainstorming is. It names an activity with a definite output, so the boundary
can be checked rather than interpreted.

> Brainstorming is done when the requirements and acceptance criteria are
> captured, the goals and non-goals are known, and the stakeholders and
> deadlines are identified — each at the scale the work warrants. For a one-line
> bugfix, the sentence is the design.

Everything after that is compris: turn it into a ticket-based implementation
plan, and drive it to completion, adjusting the plan against conditions on the
ground.

The entry point does not care how much of that there is. A bugfix described in
one sentence and a design document representing months of work are both legal
inputs — the difference surfaces in the breakdown, not at the door.

The boundary is hard in both directions. Left of it, a human decides what the
work is. Right of it, compris decides how it is cut, delivers it, and re-cuts
when the ground moves. That re-cutting loop is core behavior, not error
recovery.

## The invariant

Every leaf ticket is scoped to what is predicted to be one cognitively shaped
changeset, realized as one pull request.

The prediction is the invariant, not the identity. `implement-ticket` ships
`ready_prs` — one ticket, an authorized carved stack, several pull requests —
and that path stays. A carved stack is the *recorded falsification* of a shaping
prediction, not a violation of the rule. Developers are bad at estimating; the
answer is measurement, not accuracy.

The standard comes from atelier and travels intact, because inventing a second
wording is how two codifications start drifting:

> Line counts may inform judgment but are not universal correctness gates. The
> test is whether a reviewer can construct an accurate mental model of the
> change and evaluate it independently.
>
> — atelier, `docs/atelier-skill-design.md:480`

Note what that rules out. This is not a threshold check. Line count is an input
to judgment and nothing more — atelier dropped its predecessor's fixed
implementation and *some* of its numeric heuristics, subordinating line count to
the mental-model test, and states outright that lines of code are not a success
measure. Any implementation that reduces this to a number has failed to port it.

### The breakdown rules, ported whole

- Keep an initiative executable as one ticket when it is already reviewable.
- Avoid one-child decomposition without a real reason.
- Separate unrelated concern domains.
- Prefer additive foundations before disruptive transitions.
- Separate mechanical restructuring from behavioral change when that helps
  review.
- Keep validation with the behavior it proves.
- Identify re-split triggers before implementation.
- Create follow-up work when implementation or review reveals new scope.

The first two matter most for tone: one ticket is a legal outcome. Ceremonial
decomposition is a failure, not diligence.

## Ending shared custody

atelier used to own the breakdown. It is moving toward multi-agent process
management and model selection and routing, and it is mid-rebuild. Leaving the
doctrine in the project that no longer applies it guarantees the drift this
program exists to stop. A doctrine with two homes has no home.

The name already fits the job. *compris* is French for *understood* — what the
suite claims at the moment work changes hands. The shaping test asks whether a
reviewer can build an accurate mental model. That is understanding,
operationalized.

**Port at a pinned commit.** atelier's text is still moving. compris already
solved this for superpowers: the named-peer registry pins `obra/superpowers` at
`44c9b2d6` because an unpinned reference describes a moving target. Record
atelier's doctrine the same way, or the first thing the new owner inherits is
the drift it was created to end.

### Vocabulary comes too, but only our half of it

atelier's layer diagram already split the nouns, and it put ours on our side.
The mailbox layer holds "assignments, messages, claims, receipts"; the compris
layer holds "implementation, review, changeset carving, PR lifecycle."

So **changeset comes home** — it was always ours, it is already the noun in
`carve-changesets`, and it is the noun in the doctrine's own title. **Initiative
comes too**, but mapped rather than substituted. An initiative is the *logical*
grouping the breakdown derives; an **epic** is its tracker realization, and
compris keeps its own richer semantics there — `implement-epic:340` gives the
parent its own acceptance ledger and holds parent closeout to explicit
authority, which atelier's lighter "non-authoritative grouping" would have
overwritten.

**Assignment, claim, receipt and worker stay with atelier.** They are the
process-management layer it is moving into, and importing them would duplicate
concepts compris already has — an assignment is a claimable unit of approved
work, which is not the same thing as the shaped unit of code a reviewer reads.
atelier's own wording keeps them distinct: an initiative that "fits one project
and one reviewable changeset may consist of a single assignment." One maps to
the other; neither replaces it. Receipt resolves the same way, since it and
compris's evidence-binding are one idea under two names.

That leaves two logical-to-realized mappings, with the leaf ticket binding them:

| Logical (internal currency) | Realized (what users say) |
| --------------------------- | ------------------------- |
| initiative                  | epic                      |
| changeset                   | pull request              |

A **leaf ticket** is a child of an epic and is scoped to one changeset. The
logical nouns are how contracts, handoffs and doctrine talk; the realized ones
are what descriptions claim, because that is what people type.

Keeping `ticket` as the leaf noun is what makes this safe. Descriptions are the
routing surface and description-based routing is winner-takes-attention: people
say "implement this GitHub issue," and a description answering only to "execute
this assignment" would quietly stop matching them. Because the leaf keeps the
word users already say, only `initiative` and `changeset` are new internal
currency — and `changeset` is already in a skill name, so it is not new at all.

## The shaping skill

Three skills judge shape independently today and none cites the others:
`carve-changesets` decides changeset boundaries, `review-solution-simplicity`
judges whole-solution complexity, and `plan-implementation` will decide the
decomposition. That is the same two-codifications problem, already inside one
repo.

The fourth is the precedent rather than the problem. `implement-ticket` does
*not* carry its own heuristic — at `SKILL.md:632-635` it loads
`carve-changesets` by stable name and reads its live guardrails, and is
explicitly forbidden to "copy their thresholds or substitute local heuristics."
`docs/skill-authoring.md:198` records that as the repository's worked example of
the pattern. So one caller already delegates shape judgment to an external
authority; extracting the shaper generalizes something that works rather than
inventing something new.

A document gets cited; a skill gets called. Extracting the judgment is what
makes the doctrine enforceable rather than aspirational, and compris has the
exact precedent — `review-code-change` does not implement its three lenses, it
invokes them and reconciles typed verdicts.

| Facet               | Contract                                                                                                                                                                                                                                                  |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Input**           | A candidate in any of its forms — source material, design document, ticket, implementation plan, branch, pull request — plus repository context. Heterogeneous evidence is expected.                                                                      |
| **Output**          | Typed. The verdict; the seam-aligned breakdown whenever the verdict is *exceeds*; a rationale per seam; and the re-split triggers the doctrine requires.                                                                                                  |
| **Terminal states** | Exactly three: `fits`, `exceeds`, `blocked`. `blocked` is the honest fallback, claimed when the evidence needed to judge shape cannot be recovered. A `fits` verdict still emits a one-element breakdown, so the mechanical checks always have an object. |
| **Stance**          | Read-only. It never creates a ticket, carves a branch, or mutates the candidate. Callers act on the proposal.                                                                                                                                             |
| **Callers**         | `plan-implementation` (source material to tickets), `carve-changesets` (branch to stacked changesets), `implement-ticket` (verdict at the publication size gate).                                                                                         |

### Verdict and breakdown are one skill, not two

Splitting them is tempting, since the size gate only wants the verdict. Resist
it. You cannot credibly return *too big* without naming the seams — the
seam-aligned breakdown **is** the evidence for the verdict. A skill that says
too big with no proposed decomposition is asserting, not judging. Callers ignore
the part they do not need.

### Two things this quietly fixes

It dissolves a question that looked hard: what should `plan-implementation`
return for work that is one coherent subsystem but too large for a single PR?
There is no terminal-state puzzle once the skill calls the shaper and receives a
two-ticket breakdown. Oversized-coherent is not an outcome, it is an input to
decomposition.

And it closes the feedback loop. The shaper predicts where a re-split would
become necessary; when one fires downstream, that is a falsified prediction
recorded against a specific named trigger. You learn *which* seam judgment was
wrong, not merely that one was. `carve-changesets` stops being a repair
mechanism that implies guilt and becomes the instrument that measures the
prediction.

## The program

Ordered so that each step is independently valuable and every later step cites
an earlier one. The first two are pure documentation.

1. **The doctrine document.** Human-shaped changesets, ported at a pinned
   atelier commit, owned by compris. Genuinely zero behavior change: a new
   document that nothing yet cites.

2. **Wire the doctrine in.** Add citations from the skills that judge shape, and
   retire `carve-changesets/references/SPEC.md`'s own cognitive-load guardrails
   and decomposition-order sections in favor of one — otherwise the doctrine
   becomes a *fifth* codification rather than replacing the existing ones. This
   step edits normative skill prose, so it carries the `just eval-record`
   before/after obligation; step 1 does not.

3. **Revise the governing documents.** `docs/skill-authoring.md`: the
   trigger-namespace list claims implementation-planning language; the
   `writing-plans` registry entry moves from House territory to referenced peer;
   the `ready-ticket` collision-audit row is renamed and a `plan-implementation`
   × `writing-plans` row is added. `README.md`: the new tagline, the line at
   `:15` about peers owning the thinking-it-through phase, and composition rule
   1\.

4. **The object model document.** Initiative, leaf ticket, changeset, dependency
   — and the mapping onto GitHub and Linear stated once. Still zero behavior
   change. Deliberately narrow: it does *not* import assignment, claim, receipt
   or worker, which stay in atelier's process layer. Receipt in particular would
   duplicate compris's evidence-binding, which is the same idea and already ours
   — and is where the prediction-feedback loop gets its home for free.

5. **The shaping skill.** The contract above. One executable home for the
   judgment, with its own eval corpus, rather than shape judgments buried in
   four skills' separate corpora where none is really testing the doctrine.

6. **`plan-implementation`** (was `ready-ticket`). Source material to an
   initiative plus tickets: shaped by step 1, expressed via step 2, discovered
   through the `writing-plans` breakdown, judged by step 3. Input ranges from a
   stacktrace to a full design document; output ranges from one ticket to a
   multi-tier dependency graph.

7. **Migrate the downstream skills.** `implement-ticket`, `implement-epic` and
   `babysit-pr` move to the object model internally. Trigger surfaces unchanged.

8. **atelier cites compris.** atelier drops its section and points here.

**On renaming.** Rename only where the name misleads about behavior.
`ready-ticket` did — it promised one ticket and will produce a graph — so it
becomes `plan-implementation`. `implement-ticket` does not mislead; it really
does take one ticket, and `implement-epic` keeps a noun users say out loud. A
big-bang rename buys nothing and costs routing.

## Decisions on record

### `plan-implementation` consumes an approved design; it does not produce one

It stops approximating brainstorming's questioning. Elicitation narrows to the
tracker-shaped residue a design cannot answer — surface-observable criteria,
verification commands, pre- and post-merge classification.

*Note this reverses a recorded decision.* Epic #118 established that "a ready
ticket satisfies brainstorming's design-approval gate (elicitation happened at
authoring time)."

### The composition rules stand; the boundary is hard

The *ordering* rule survives — brainstorming applies pre-ticket, never
mid-pipeline. But README composition rule 1 is not merely re-justified: its
title and mechanism sentence assert a ready ticket satisfies the gate *because
`ready-ticket` ran elicitation and obtained approval of the body*. Once
elicitation narrows to the tracker-shaped residue, that sentence is false. The
rule is rewritten to say the gate is satisfied by brainstorming having run.

And the boundary fails closed. When a compris step finds itself wanting
something brainstorming should have settled, that is a compris failure case:
exit with *needs more information*, naming what is missing. Never gather it. A
distinct typed result — `requires_brainstorming`, parallel to
`implement-ticket`'s `requires_epic` — makes it machine-routable and keeps the
planner from drifting back into being a design prompt.

### A design document is required for every ticket, scaled to the work

No threshold to adjudicate and no second door for bug reports. Trivial work gets
a trivial design.

*Verified.* brainstorming already owns the scaling problem: "Every project goes
through this process. A todo list, a single-function utility, a config change —
all of them. The design can be short (a few sentences for truly simple
projects), but you MUST present it and get approval."

### compris owns the implementation breakdown, using writing-plans to do it

The breakdown is how the ticket structure is *discovered* — nobody can know
whether something is one ticket or twelve until it has been broken down. That
moves `writing-plans` in the registry from House territory to a genuine
referenced peer: compris owns the implementation-breakdown phase and points at
the peer by name as the recommended method for it.

**The breakdown is house-owned and complete without a peer.**
`docs/skill-authoring.md:598` is unambiguous — a skill "may never depend on" a
peer — and `:619` forbids conditioning a quality outcome on peer availability.
So compris writes its own breakdown procedure: file map, task boundaries,
sequencing, enough to judge shape. `writing-plans` supplies a deeper and
better-tested method when it is present. Outcome house-owned, method delegated,
exactly as the convention requires.

*The cost is real and accepted.* A house procedure that mostly duplicates the
peer's has to be written and maintained, and the two paths can produce different
shapes for the same input — which the shaping corpus then has to grade on both
paths rather than one.

### Ticket authority is endpoint-scoped, not per-item

Granting the skill ticket management grants it the whole graph. In for a penny,
in for a pound.

*Note this reverses two recorded decisions.* `docs/skill-authoring.md:366` makes
authority "granular, separately granted, and never inferred… Each defaults to
off," and `ready-ticket:82-84` states that authoring authority "never implies
authority to… create additional tracker items." Endpoint-scoped authority
supersedes both for this skill, and the reversal is recorded here rather than
left for a reader to find.

*What remains is an approval gate, not a disclosure.* `ready-ticket:220-223`
already requires explicit approval of the body before `ticket_ready`; scaling
that to the graph — shape, leaves, dependency edges — is continuity, not a new
gate. **Approval may be given at invocation**, and when it is the presentation
becomes a disclosure: the run reports the graph and proceeds. That is also what
makes autonomous operation possible at all, since an autonomous run has nobody
to ask.

### Prediction is best-effort, and instrumented

Developers are bad at estimating; the answer is measurement, not accuracy.
Paying for the full plan now is acceptable provided the approach's usefulness
can be reflected on later and adjusted.

*Cheapest version.* The ticket records its predicted shape; `implement-ticket`
and `babysit-pr` already observe the actual outcome. atelier's evaluation
criteria — whether changes remain cognitively reviewable, and how much operator
effort acceptance costs — are a better forward-eval target than grading prose
compliance.

### Three eval surfaces, not one stretched corpus

The **forward corpus** keeps asking whether the prose governs once loaded,
extended with peer-present cases and new vocabulary terms. The **shaping
corpus** belongs to the shaping skill and asks a question nothing here asks
today — was the breakdown good — graded by judge panel against the eight
doctrine rules. **Re-split telemetry** is the real measure: every shipped leaf
records whether its prediction held.

*Why the shaping corpus lives on the shaping skill.* One corpus then tests the
doctrine for all three call sites — the extraction argument carried through to
verification. Two non-goals: the eval does not observe artifact lifecycle, since
"reason from artifacts alone" is the right constraint and unit tests plus one
manual run cover the filesystem more cheaply; and diff continuity is not claimed
across the vocabulary change — record a fresh baseline and say so.

### The shaping rubric grades seams, not partitions

**Sort all eight rules by kind first, and account for every one.** Three are
mechanically checkable and need no judge: one-child decomposition (count
children; if one, require a stated reason), re-split triggers (a presence
check), and the fits-as-one-ticket case (a `fits` verdict must emit exactly one
element). Four need judgment: concern separation, ordering of additive
foundations before disruptive transitions, mechanical-versus-behavioral
separation, and validation placement. The eighth — create follow-up work when
implementation or review reveals new scope — **is not gradeable at plan time at
all**: it describes a downstream event, so it belongs to the re-split telemetry
surface rather than to this corpus. The mental-model test is not one of the
eight; it is the standard the four judgment rules serve, and is judged alongside
them.

**Grade seams, not partitions.** Two good decompositions of the same work
typically agree on *where the seams are* and disagree on *how they group*. Score
those separately: did each proposed cut land on a boundary the reference also
recognized, and was the grouping defensible? A decomposition that cuts at real
seams but bundles differently is fine; one that cuts through the middle of a
concern is wrong regardless of how many pieces it made. Partition equality gets
this backwards, and seam-level scoring maps onto the skill's own output
vocabulary.

**Build each case around a specific trap.** The eight rules imply eight ways to
be wrong — an input that tempts ceremonial one-child decomposition, one that
invites mixing a rename with a behavior change, one where validation naturally
drifts from the behavior it proves. A corpus that only rewards good answers
measures very little; one where every case has a known bait measures whether the
doctrine governs.

**Anchor on merged history.** Shipped work whose shape held is a labeled
positive; work that had to be carved is a labeled negative, already annotated by
the fact that it was carved. Reconstruct the input, ask the shaper what it would
have proposed, compare. Free labeled data, and it grounds the standard in the
team's real review culture rather than a synthetic one — the retrospective twin
of the re-split telemetry.

**Diverse judges, not redundant ones.** A concern-coherence judge, an ordering
judge, and a mental-model judge, matching the review-suite pattern. Three
identical judges mostly measure sampling temperature.

**No numeric score.** The doctrine retired numeric heuristics; a rubric emitting
7.2 out of 10 reintroduces what atelier removed. Per-rule pass/fail with
recorded observations matches what `AGENTS.md` already asks for.

### `ready-ticket` becomes `plan-implementation`

It names the activity rather than the artifact, so it no longer promises one
ticket while producing a graph — and it is verb-first, like every other skill in
the suite.

*It forces a doctrine revision.* The trigger-namespace rule forbids compris
descriptions from claiming planning language, because that is what peer skills
trigger on. That rule assumed planning lived upstream; this program moves it
in-house. The namespace list has to say compris now claims
implementation-planning language deliberately, and the collision audit needs a
`plan-implementation` × `writing-plans` row recording the overlap as structural
and cooperative.

## Verified evidence

Established against `obra/superpowers` at pin `44c9b2d6` and the compris tree.
Three assumptions were falsified in the process; all are reflected above.

| Finding                                                                                                   | Consequence                                                                                                                                                                                                             | Source                             |
| --------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| `writing-plans` never reads a spec from disk — no path parameter, no file read                            | The design can be handed over inline; no document has to exist for the handoff                                                                                                                                          | `SKILL.md:23,71,140`               |
| It supplies no pull-request sizing verdict; the PR concept appears nowhere in it                          | Sizing is house-owned outright. Its only whole-plan check duplicates a trigger we already have                                                                                                                          | `skills/writing-plans/`            |
| Its plan review is an inline checklist; the typed subagent reviewer it replaced is now referenced nowhere | The peer ships no typed, evidence-bound review, so the house reviewer is required rather than optional                                                                                                                  | `plan-document-reviewer-prompt.md` |
| Committed peer plans run 143–1649 lines, placeholders forbidden, complete code required                   | A material context expenditure — accepted, pending instrumentation                                                                                                                                                      | 13 committed plans                 |
| `brainstorming` writes *and commits* its design document to git                                           | It stays a borrow, never invoked. Borrow a peer that mutates the user's repo; invoke one whose output is disposable                                                                                                     | `SKILL.md:107,110`                 |
| Its step-7 Spec Self-Review is `ready-ticket`'s four scans, same order                                    | The skill already ports the peer further than the registry declares                                                                                                                                                     | `SKILL.md:112–118`                 |
| Planning language is a **negative** case owned by `review-code-change`, expecting no compris skill        | The expectation inverts, but the case cannot simply be flipped: doing so destroys that skill's negative coverage. Add a positive `plan-implementation` case and re-scope the negative                                   | `triggering/expectations.json:130` |
| Skill-invokes-skill is established practice across five compris skills                                    | Dispatch is not novel. `implement-ticket`'s anti-invoke rule covers three pairings plus a self-re-entry bar, and `implement-epic` adds a layering rule — a read-only shaper closes no cycle, because it invokes nothing | `implement-ticket:301-303`         |

## Recorded experiments

Not open questions. Nobody owes an answer here; someone owes a run.

### Can `writing-plans` be steered to behavioral altitude?

Depth is not the worry — sample code, schemas and protocol design are welcome,
because the rough shape of an implementation is what makes a sizing estimate
credible. The worry is altitude. The peer produces unit-level TDD bound to
internals, while compris requires acceptance criteria observable at the public
surface.

**The run.** Install superpowers at pin `44c9b2d6`, hand `writing-plans` a spec
written as surface-observable acceptance criteria, and inspect what returns.

**Success criterion.** Its Interfaces block does not name internal function
signatures, and its test steps assert against observable behavior rather than
against functions. One session; blocks neither step 1 nor step 2.

**The hypothesis, if it holds.** The peer's own coverage check — "skim each
requirement in the spec, can you point to a task that implements it?" — maps
behavior onto implementation tasks for us. The plan's unit detail sharpens
sizing and dies with the scratch artifact; the ticket keeps the
surface-observable contract.

**The fork if it fails**, deliberately not pre-decided:

- _Take it as-is_ — use the output only for sizing and derive the behavioral
  criteria independently. Cheapest; nothing binds plan coverage to ticket
  criteria.
- _Post-process_ — compris lifts internal-altitude tests to the surface as a
  house step. Preserves the binding; a translation step can lose or invent.
- _Structure only_ — take the file map, task boundaries and sequencing; compris
  owns everything test-shaped. Cleanest boundary, least peer value.
