# Cognitive shaping doctrine

This is compris's canonical statement of cognitive shaping: the standard that
decides whether a unit of work is comprehensible, the rules that break work
apart against it, the vocabulary that carries them, and what enforcement is and
is not.

It is doctrine, not design. [cognitive-driven-development.md] records the
program this doctrine was extracted for, the decisions behind it, and the
alternatives still open. Read that for why; read this for what holds.

## Ownership

compris is the sole owner of this doctrine. Any other statement of the same
standard — in a consuming skill's own contract or anywhere else — is a copy,
never a competing authority.

A doctrine with two homes has no home. Once the same standard is stated in two
places, the two drift, and a reader who finds both has no way to tell which one
governs.

Retiring the remaining copies is separately tracked and is not performed here.
Naming that state is part of the ownership claim rather than a caveat on it: a
reader who finds two texts needs to know which one is authoritative while the
other is still standing.

## The standard

> Line counts may inform judgment but are not universal correctness gates. The
> test is whether a reviewer can construct an accurate mental model of the
> change and evaluate it independently.

That wording is fixed. Restating it in fresh words in each place it is needed is
how one standard becomes several, which is the drift this document exists to
end.

Note what the standard rules out. It is not a threshold check. Line count is an
input to judgment and nothing more. Earlier statements of this standard carried
numeric heuristics alongside it; they were dropped deliberately, to subordinate
line count to the mental-model test rather than let a number stand in for it.
Any implementation that reduces this standard to a threshold has failed to carry
it, however defensible the threshold is.

### Recorded machine-generated evidence is excluded from shape judgment

Committed eval results, generated fixtures, lockfiles, and comparable
machine-produced artifacts are part of the change and are excluded from the
shape judgment, because no reviewer builds a mental model of them.

*Prevents:* a judgment made on raw churn rejects a small change because the
eval-evidence norm in [AGENTS.md] required that change's evidence to be
committed. Pull request #179 is the observed case: 4,715 lines of churn, of
which 4,538 lines are recorded eval results, leaving a reviewable change of 177
lines. Judging the 4,715 measures the wrong thing.

## The breakdown rules

Eight rules. Each is load-bearing, and a breakdown is judged against all of
them.

- Keep an initiative executable as one ticket when it is already reviewable.
- Avoid one-child decomposition without a real reason.
- Separate unrelated concern domains.
- Prefer additive foundations before disruptive transitions.
- Separate mechanical restructuring from behavioral change when that helps
  review.
- Keep validation with the behavior it proves.
- Identify re-split triggers before implementation.
- Create follow-up work when implementation or review reveals new scope.

The first two carry the tone. One ticket is a legal outcome, and ceremonial
decomposition is a failure rather than diligence: a breakdown that splits
because splitting is what a breakdown does buys review overhead and nothing
else.

The eighth is the only one that does not apply when the breakdown is authored.
It describes a downstream event, so it is discharged when implementation or
review actually reveals the new scope.

## Vocabulary

The doctrine's nouns are logical; the tracker's are realized. Both are needed,
and conflating them is what makes contracts and descriptions disagree about the
same object.

| Logical (internal currency) | Realized (what users say) |
| --------------------------- | ------------------------- |
| initiative                  | epic                      |
| changeset                   | pull request              |

A leaf ticket is a child of an epic and is scoped to one changeset. The logical
nouns are how this doctrine, contracts, and handoffs talk; the realized nouns
are what descriptions claim, because that is what people type.

Keeping `ticket` as the leaf noun is what makes the split safe.
Description-based routing is winner-takes-attention: people say "implement this
GitHub issue", and a description answering only to a logical noun would quietly
stop matching them.

Process-management nouns — `assignment`, `claim`, `receipt`, `worker` — are
deliberately outside this vocabulary. A claimable unit of approved work is not
the shaped unit of code a reviewer reads; one maps onto the other, and neither
replaces it.

## Enforcement is policy-controlled

Judgment and enforcement are separate, and only judgment is universal. The
shaper always judges, and the consuming project decides whether an exceeds
verdict gates anything.

compris is itself such a project today: it declines shape gating, which is why
its own merged history contains changes this standard would not call reviewable,
and why `carve-changesets` has never carved anything here. The mechanism has not
failed; it has not been asked.

*Prevents:* a doctrine that gates by construction cannot be adopted
incrementally, so a project wanting ticket authoring and delivery automation
without shape gating has to fork it or ignore it. Separating judgment from
enforcement is what lets the standard be stated once and applied at whatever
strength each project chose.

### A carved stack is a recorded falsification, not a violation

The invariant is a prediction: every leaf ticket is scoped to what is predicted
to be one changeset, realized as one pull request. When implementation proves
that prediction wrong, an authorized carved stack is the recorded falsification
of it. Developers are bad at estimating; the answer is measurement, not
accuracy.

## Consumers

Named so a reader can tell authority from copy. Binding each consumer to this
document is separately tracked and is not performed here.

- `carve-changesets` decides changeset boundaries and still carries its own
  generic codification.
- `review-solution-simplicity` judges whole-solution complexity.
- `implement-ticket` classifies a candidate at its publication size gate, and
  already reads a named authority rather than carrying a heuristic of its own.

<!-- inline reference link definitions. please keep alphabetized -->

[agents.md]: ../AGENTS.md
[cognitive-driven-development.md]: cognitive-driven-development.md
