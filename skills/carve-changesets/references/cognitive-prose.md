# Cognitive prose

Prose compris emits is written for the human accountable to the codebase, not
for the agent that will parse it: **clear, understandable, and unambiguous —
never merely efficient.**

This is the contract for that prose. [Cognitive debt] is the problem it answers.

## The standard

Agent idiom is token-efficient and human-hostile. It optimizes for the wrong
reader.

A reviewer meets a change through its description before they meet its diff. If
that description is dense, hedged, or organized around what was done rather than
why, the reviewer starts behind. A correctly sized change nobody can parse has
not transferred the theory of the program to anyone — it has only made the
failure smaller.

So the test for prose is the test for shape, one layer up: after reading it, can
a reviewer construct an accurate mental model of the change?

## Scope

This contract governs **pull request bodies** and **ticket bodies**.

It does not govern `SKILL.md` prose, which is written for an agent reader and
answers to the repository's skill-authoring standard instead. It does not govern
code comments. It does not govern commit bodies.

## The opening move

Open with one or two sentences establishing **why this change is necessary**,
and **how it solves the problem** where that fits in the same breath.

This is not a summary of the change. It is orientation. A reader who stops after
those two sentences should still know what problem exists and roughly what was
done about it.

Write it last, after the body. You cannot compress an argument you have not made
yet.

## The reader's question order

A body answers the reader's questions in the order they ask them.

1. **What was wrong.** The problem, concretely, before any solution.
2. **What this does about it.**
3. **Why this and not the obvious alternative** — when a real alternative was
   weighed. Omit the section when none was.
4. **How it was verified.** What was actually run, and what it showed.

Never organize a body around the repository's file layout. A walk through
changed files is the writer's convenience; the reader came for the argument.

## The prohibitions

Each is sourced to a pull request where it was observed.

| Do not                                 | Because                                                                                          | Observed in                                                                                                                                                                   |
| -------------------------------------- | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Restate the diff.                      | Content recoverable from `git diff --stat` spends the reader's attention without informing them. | [#20], five bullets each opening on an imperative verb — Extract, Establish, Keep, Preserve, Add                                                                              |
| Stack modifiers where a verb would do. | Adjectives accumulate to signal importance and carry none.                                       | [#20], "the reusable, runtime-neutral workflow … through safe review and delivery gates"                                                                                      |
| Write a feature list as a sentence.    | Nobody holds five nouns joined by commas. They can hold one claim.                               | [#20], "cross-system GitHub and Linear ownership, explicit authority boundaries, current-candidate review gates, safe base-drift handling, and post-merge dependency refresh" |
| Open on what was added.                | Opening on the addition leaves the reason unstated, and the reason is what a reader needs first. | [#20] and [#60], both opening on "Adds"/"Add"                                                                                                                                 |

**The rationalization table is deliberately unwritten.** The repository's
authoring standard admits only rows sourced to the agent's own wording, and the
pull requests above carry observed output rather than the reasoning that
produced it. Inventing those rows is what that rule exists to forbid. Until
baseline transcripts supply them, this contract's voice half is weaker than its
final form, and that is stated here rather than left for a reader to find out.

## Scale

Length is calibration, not a gate.

A few hundred words usually carries a few hundred changed lines. Falling outside
that is not a defect. It is where the question stops being rhetorical and has to
be asked deliberately.

This section guards one specific over-correction. "Cognitive prose" read
carelessly means "explain everything," and it does not mean that. A body that
grows into a tutorial has traded one unreadable artifact for another. Say what
the reader needs, then stop.

## The exemplar pair

Same repository, same author, three weeks apart.

[#20] is the failure. It opens on "Adds `implement-ticket` as the reusable,
runtime-neutral workflow for implementing exactly one standalone ticket or named
epic child through safe review and delivery gates" — four stacked modifiers, and
no statement of what was wrong before it. Its summary restates the diff in five
bullets.

[#209] is the standard. It opens on the defect: "Every module under
`scripts/tests/` took its sibling `helpers.py` on the `sys.path` entry
`unittest discover` happens to supply." Then a `## Why` arguing from the ticket,
naming the commit the bug predates. Then an explicit "why the shim rather than
standardizing on discovery," with a survey table showing which suites already
solve it that way. Then reviewer notes proving the new guard was verified
capable of failing.

Read [#209] before writing. It makes every move this contract asks for, on a
change small enough to hold in one sitting.

<!-- inline reference link definitions. please keep alphabetized -->

[#20]: https://github.com/shaug/compris/pull/20
[#209]: https://github.com/shaug/compris/pull/209
[#60]: https://github.com/shaug/compris/pull/60
[cognitive debt]: https://github.com/shaug/compris/blob/main/docs/cognitive-debt.md
