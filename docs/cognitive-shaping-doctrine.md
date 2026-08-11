# Cognitive shaping doctrine

This is compris's doctrine of cognitive shaping: work is broken apart by what a
reviewer can understand, and that is the binding constraint rather than a nicety
observed when there is time.

[cognitive-driven-development.md] records the program behind this and the
decisions that shaped it. This document is the statement itself.

## The standard

A unit of work is correctly shaped when a reviewer can construct an accurate
mental model of the change and evaluate it independently.

Line counts inform that judgment. They never decide it.

## Scale

A changeset is sized to be read in one sitting, and most that meet the standard
run to a few hundred changed lines. Both figures are calibration, not a gate:
they say where the standard usually lands, not where it is enforced.

Three things move the number without moving the standard.

- Deletion costs less than addition, once the reason for the removal and the
  behavior replacing it are clear.
- Mechanical change — a systematic rename, a codemod, a formatting pass — runs
  much larger, because the reviewer verifies one transformation instead of
  reading every line.
- Recorded machine-generated evidence is excluded outright. Committed eval
  results, generated fixtures, and lockfiles are part of the change and part of
  nothing anyone reads. A change carrying 177 reviewable lines and 4,538 lines
  of recorded eval results is a 177-line change.

Falling outside the range is not itself a defect. It is where the standard's
question stops being rhetorical and has to be asked deliberately.

## The breakdown rules

- Keep an initiative executable as one ticket when it is already reviewable.
- Avoid one-child decomposition without a real reason.
- Separate unrelated concern domains.
- Prefer additive foundations before disruptive transitions.
- Separate mechanical restructuring from behavioral change when that helps
  review.
- Keep validation with the behavior it proves.
- Identify re-split triggers before implementation.
- Create follow-up work when implementation or review reveals new scope.

One ticket is a legal outcome. The first two rules outrank the impulse to
decompose: a breakdown that splits because splitting is what a breakdown does
buys review overhead and nothing else.

Creating follow-up work is the one rule that applies downstream. It is
discharged when implementation or review reveals the new scope, not when the
breakdown is authored.

## Vocabulary

| Logical    | Realized     |
| ---------- | ------------ |
| initiative | epic         |
| changeset  | pull request |

A leaf ticket is a child of an epic, scoped to one changeset. Doctrine,
contracts, and handoffs speak in the logical nouns; descriptions and tracker
items use the realized ones, because that is what people type.

## Enforcement

Shape is always judged. Whether an oversized verdict gates anything is the
consuming project's decision — judging is read-only, and acting on the verdict
is policy.

The invariant is a prediction: every leaf ticket is scoped to what is predicted
to be one changeset, realized as one pull request. An authorized carved stack is
that prediction recorded as falsified. Developers are bad at estimating; the
answer is measurement, not accuracy.

## Consumers

This doctrine governs shape judgment in:

- `carve-changesets`, for changeset boundaries;
- `review-solution-simplicity`, for whole-solution complexity; and
- `implement-ticket`, at the publication size gate.

<!-- inline reference link definitions. please keep alphabetized -->

[cognitive-driven-development.md]: cognitive-driven-development.md
