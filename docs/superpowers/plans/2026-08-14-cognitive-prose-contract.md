# Cognitive Prose Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `docs/cognitive-prose.md` as the canonical contract for prose
compris emits, distributed into three consuming skills and held against drift by
a test, without changing any skill's behavior.

**Architecture:** Canonical doctrine text lives in `docs/`, beside
`cognitive-debt.md` and `cognitive-shaping-doctrine.md`. `just sync-contracts`
copies it verbatim into `skills/<skill>/references/cognitive-prose.md` for the
three skills that will later consume it, and a root-suite test fails when a copy
drifts, a required section disappears, or a prohibition is added without a
source. No `SKILL.md` references the bundled file when this lands — teaching
skills to load it is a separate piece of work.

**Tech Stack:** Markdown, `just` recipes (bash), Python 3 `unittest`.

## Global Constraints

- Canonical text lives at `docs/cognitive-prose.md`. Bundled copies live at
  `skills/<skill>/references/cognitive-prose.md` — directly under `references/`,
  not in a subdirectory.
- The three bundling skills are exactly `implement-ticket`, `carve-changesets`,
  and `ready-ticket`.
- **Every link in `docs/cognitive-prose.md` must be an absolute `https://`
  URL.** A relative link dangles once the file is copied into a skill's
  `references/`, which is why
  `review-suite/scripts/tests/test_bundled_contracts.py:147` exists. This
  constraint is non-negotiable and a test enforces it.
- Markdown links are inline reference links with no alias, definitions
  alphabetized at the end of the file under the comment
  `<!-- inline reference link definitions. please keep alphabetized -->`.
- New test modules under `scripts/tests/` carry the `__file__`-relative
  `sys.path` shim; `scripts/tests/test_suite_invocation.py` enforces it.
- `just format`, `just lint`, and `just test` must all pass before every commit.
- Conventional Commits. Commit messages are written to a temp file and passed
  with `git commit -F`, never inline `-m`.
- `CHANGELOG.md` gets an entry per commit, newest first within the day. Before
  adding a new entry, backfill the full SHA onto the previous entry.
- No skill's `SKILL.md` is edited by this plan. If a task appears to require it,
  stop — that is a later piece.

______________________________________________________________________

## File Structure

| File                                                    | Responsibility                                                                              |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `docs/cognitive-prose.md`                               | Create. The canonical contract — seven sections, sourced prohibitions, absolute links only. |
| `scripts/tests/test_cognitive_prose_doc.py`             | Create. Content invariants (Task 1), then drift invariants (Task 2).                        |
| `justfile`                                              | Modify. One new `sync-contracts` block distributing the contract to three skills.           |
| `docs/cognitive-debt.md`                                | Modify. Its three commitments become four, naming prose.                                    |
| `skills/implement-ticket/references/cognitive-prose.md` | Create by `just sync-contracts`. Never hand-edited.                                         |
| `skills/carve-changesets/references/cognitive-prose.md` | Create by `just sync-contracts`. Never hand-edited.                                         |
| `skills/ready-ticket/references/cognitive-prose.md`     | Create by `just sync-contracts`. Never hand-edited.                                         |
| `CHANGELOG.md`                                          | Modify. One entry per task commit.                                                          |

Two tasks. Task 1 produces the document and the invariants that hold its
content. Task 2 produces the distribution and the invariants that hold the
copies. A reviewer can accept the contract and reject the distribution
mechanism, or the reverse, which is where the boundary is drawn.

______________________________________________________________________

## Task 1: The canonical contract

**Files:**

- Create: `docs/cognitive-prose.md`
- Create: `scripts/tests/test_cognitive_prose_doc.py`
- Modify: `docs/cognitive-debt.md:84` (the "Three commitments" sentence and
  list)
- Modify: `CHANGELOG.md`

**Interfaces:**

- Consumes: nothing from earlier tasks.

- Produces: `docs/cognitive-prose.md` with exactly these seven second-level
  headings, in this order — `## The standard`, `## Scope`,
  `## The opening move`, `## The reader's question order`,
  `## The prohibitions`, `## Scale`, `## The exemplar pair`. Task 2 asserts on
  the same file path and does not re-assert its content.

- [ ] **Step 1: Write the failing test**

Create `scripts/tests/test_cognitive_prose_doc.py`:

```python
"""Content invariants for the canonical cognitive prose contract.

`docs/cognitive-prose.md` states how prose compris emits is written. These
tests hold the claims a later editor could quietly drop: the seven sections a
reader is promised, the sourcing rule that separates an observed prohibition
from an invented one, and the recorded gap where the rationalization table
would go.

Repository-wide rather than skill-scoped, so these live here alongside
`test_cognitive_shaping_doctrine.py` and
`test_cognitive_driven_development_doc.py`.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from helpers import compact  # noqa: E402

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CANONICAL = REPOSITORY_ROOT / "docs" / "cognitive-prose.md"

REQUIRED_SECTIONS = (
    "## The standard",
    "## Scope",
    "## The opening move",
    "## The reader's question order",
    "## The prohibitions",
    "## Scale",
    "## The exemplar pair",
)


def _section(heading: str) -> str:
    """Return the body of one second-level section, heading excluded."""
    text = CANONICAL.read_text()
    start = text.index(heading) + len(heading)
    remainder = text[start:]
    end = remainder.find("\n## ")
    return remainder if end == -1 else remainder[:end]


def _table_rows(section: str) -> list[list[str]]:
    """Return the data rows of the first Markdown table in `section`."""
    lines = [line for line in section.splitlines() if line.strip().startswith("|")]
    rows = [
        line for line in lines if not re.fullmatch(r"\s*\|[\s|:-]*\|\s*", line)
    ]
    return [[cell.strip() for cell in row.strip().strip("|").split("|")] for row in rows[1:]]


class CognitiveProseContractTests(unittest.TestCase):
    def test_the_contract_states_the_standard(self) -> None:
        standard = compact(_section("## The standard"))
        text = compact(CANONICAL.read_text())
        self.assertIn(
            "written for the human accountable to the codebase",
            text,
        )
        self.assertIn("never merely efficient", text)
        self.assertIn("token-efficient and human-hostile", standard)

    def test_the_contract_carries_every_required_section(self) -> None:
        text = CANONICAL.read_text()
        for heading in REQUIRED_SECTIONS:
            with self.subTest(section=heading):
                self.assertIn(f"\n{heading}\n", text)

    def test_the_required_sections_appear_in_the_promised_order(self) -> None:
        text = CANONICAL.read_text()
        positions = [text.index(f"\n{heading}\n") for heading in REQUIRED_SECTIONS]
        self.assertEqual(positions, sorted(positions))

    def test_the_contract_carries_no_section_beyond_the_promised_seven(self) -> None:
        # A new section is a change to what the document promises a reader, so
        # it belongs in REQUIRED_SECTIONS rather than arriving silently.
        found = re.findall(r"^## .+$", CANONICAL.read_text(), flags=re.MULTILINE)
        self.assertEqual(found, [heading for heading in REQUIRED_SECTIONS])

    def test_every_prohibition_names_a_source(self) -> None:
        # docs/skill-authoring.md admits only sourced entries. An invented
        # prohibition carries none of the format's evidentiary weight, so the
        # table is only trustworthy if every row cites where it was observed.
        rows = _table_rows(_section("## The prohibitions"))
        self.assertGreaterEqual(len(rows), 4)
        for row in rows:
            with self.subTest(prohibition=row[0]):
                self.assertRegex(row[-1], r"\[#\d+\]")

    def test_the_contract_records_the_rationalization_table_as_unwritten(self) -> None:
        # The voice half is deliberately incomplete. Saying so is what keeps a
        # reader from treating the prohibitions as fully armed.
        prohibitions = compact(_section("## The prohibitions"))
        self.assertIn("rationalization table is deliberately unwritten", prohibitions)

    def test_every_link_is_absolute(self) -> None:
        # A bundled copy sits in skills/<skill>/references/ with none of this
        # repository's layout beside it, so a relative link dangles there.
        text = CANONICAL.read_text()
        targets = re.findall(r"^\[[^\]]+\]:\s*(\S+)", text, flags=re.MULTILINE)
        self.assertGreaterEqual(len(targets), 4)
        for target in targets:
            with self.subTest(target=target):
                self.assertTrue(target.startswith("https://"))
        self.assertEqual(re.findall(r"\]\((?!https://)([^)]+)\)", text), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest scripts.tests.test_cognitive_prose_doc -v`

Expected: FAIL. Every test errors with
`FileNotFoundError: … docs/cognitive-prose.md` because the document does not
exist yet.

- [ ] **Step 3: Write the contract**

Create `docs/cognitive-prose.md` with exactly this content:

```markdown
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

| Do not | Because | Observed in |
| --- | --- | --- |
| Restate the diff. | Content recoverable from `git diff --stat` spends the reader's attention without informing them. | [#20], five bullets each opening on an imperative verb — Extract, Establish, Keep, Preserve, Add |
| Stack modifiers where a verb would do. | Adjectives accumulate to signal importance and carry none. | [#20], "the reusable, runtime-neutral workflow … through safe review and delivery gates" |
| Write a feature list as a sentence. | Nobody holds five nouns joined by commas. They can hold one claim. | [#20], "cross-system GitHub and Linear ownership, explicit authority boundaries, current-candidate review gates, safe base-drift handling, and post-merge dependency refresh" |
| Open on what was added. | Opening on the addition leaves the reason unstated, and the reason is what a reader needs first. | [#20] and [#60], both opening on "Adds"/"Add" |

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
epic child through safe review and delivery gates" — two stacked adjectives
ahead of the noun, the rest of the qualification trailing in prepositional
phrases, and no statement of what was wrong before it. Its summary restates the
diff in five bullets.

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
```

**Expect `just format` to reflow this file in Step 8**, and do not treat the
reflow as a content change. `fmt-md` runs `mdformat --wrap 80`, which renumbers
the ordered list under `## The reader's question order` to four `1.` entries and
pads the prohibitions table's columns to equal width. Both were verified not to
break the parsing in Step 1: the section, table, and link assertions all pass
against the formatted file. Write the content as given above and let `format`
normalize it.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest scripts.tests.test_cognitive_prose_doc -v`

Expected: PASS, 7 tests.

If `test_the_contract_carries_no_section_beyond_the_promised_seven` fails, the
document has a heading the test does not know about — either remove the heading
or add it to `REQUIRED_SECTIONS` deliberately. Do not weaken the test to accept
an unlisted section.

- [ ] **Step 5: Name prose as the fourth commitment in the problem statement**

In `docs/cognitive-debt.md`, replace this line:

```markdown
Three commitments follow, and each is already load-bearing in the suite.
```

with:

```markdown
Four commitments follow, and each is already load-bearing in the suite.
```

Then add this fourth bullet immediately after the **Why, not just what** bullet,
before the `compris` is French for _understood_ paragraph:

```markdown
- **Prose.** A theory nobody can read was not transferred. The artifacts compris
  emits are written for the human accountable to the codebase rather than the
  agent that will parse it, which is a separate discipline from shaping the work
  and is stated in [cognitive-prose.md].
```

Then add this reference link definition to the alphabetized block at the end of
the file, between `[cognitive-driven-development.md]` and
`[cognitive-shaping-doctrine.md]`:

```markdown
[cognitive-prose.md]: cognitive-prose.md
```

A relative link is correct here. `cognitive-debt.md` is never bundled into a
skill, so it has no dangling-link constraint.

- [ ] **Step 6: Verify the problem statement still passes its own tests**

Run: `python3 -m unittest scripts.tests.test_cognitive_prose_doc -v`

Expected: PASS, 7 tests — unchanged, confirming the `cognitive-debt.md` edit did
not disturb the contract.

Run: `just test`

Expected: PASS, exit 0. No existing test asserts on `cognitive-debt.md`'s
commitment count, so nothing should turn red. If something does, read the
failure before changing it — it means a document invariant existed that this
plan did not know about.

- [ ] **Step 7: Add the changelog entry**

In `CHANGELOG.md`, under the `## 2026-08-14` heading, add this entry **above**
the existing `docs: name cognitive debt …` entry, and backfill that entry's full
SHA first per the repository convention. Get the SHA with `git rev-parse HEAD`
before committing anything in this task.

```markdown
- docs: publish the canonical cognitive prose contract — compris shaped what a
  reviewer reads and said nothing about how it was written. The entire
  pull-request-body obligation was a four-item content checklist at
  `skills/implement-ticket/SKILL.md:669`, and `carve-changesets` inherited none
  at all, so an agent could satisfy the suite in full while emitting prose no
  reviewer could use. `docs/cognitive-prose.md` states the standard — prose is
  written for the human accountable to the codebase, never merely efficient —
  and splits its rules by failure shape per `docs/skill-authoring.md`: the
  reader's question order is a positive contract, because a prohibition cannot
  fix a shape problem, and the voice rules are prohibitions, each sourced to the
  pull request where it was observed. #20 supplies three of the four and #60 the
  last; #209 is the worked exemplar. The rationalization table ships unwritten
  and says so, because the sourced material carries observed output rather than
  the agent's own rationalizations, and inventing those rows is what
  `skill-authoring.md:132` forbids. `cognitive-debt.md` gains prose as a fourth
  commitment beside shape, publicity, and why-not-just-what. Nothing consumes
  the contract yet — no `SKILL.md` is edited, so no skill's behavior changes and
  the eval-evidence norm does not apply.
```

- [ ] **Step 8: Run the full required checks**

Run: `just format && just lint && just test`

Expected: all three pass, exit 0.

- [ ] **Step 9: Commit**

```bash
cat >/tmp/commit-cognitive-prose-1.md <<'EOF'
docs: publish the canonical cognitive prose contract

## Summary

- Add `docs/cognitive-prose.md`: the standard, its scope, the required opening
  move, the reader's question order, four sourced prohibitions, a scale rule,
  and the worked exemplar pair
- Add `scripts/tests/test_cognitive_prose_doc.py` holding the seven promised
  sections, the sourcing rule, and the absolute-link constraint
- Name prose as a fourth commitment in `docs/cognitive-debt.md`

## Why

compris shaped what a reviewer reads and said nothing about how it was written.
The entire pull-request-body obligation was a four-item content checklist at
`skills/implement-ticket/SKILL.md:669`; `carve-changesets` inherited none at
all. An agent could satisfy that in full and still emit prose no reviewer could
use, which defeats the shaping it sits on top of.

## Why prohibitions and a positive contract, not one or the other

`docs/skill-authoring.md` matches the textual form to the failure. Structure is
wrong-shaped output, and a prohibition cannot fix a shape problem, so the
reader's question order is written as a positive contract. Voice is a discipline
violation, so it takes prohibitions — each sourced to the pull request where it
was observed, per `skill-authoring.md:132`.

The rationalization table ships unwritten, and the document says so about
itself. #20 and #60 carry observed output rather than the reasoning that
produced it, and inventing those rows is exactly what that rule forbids.

## Reviewer notes

- **No skill prose changed**, so the eval-evidence norm does not apply. Nothing
  loads the contract yet; distribution is the next commit and consumption is
  later work.
- **Every link is absolute**, enforced by a test. The file gets bundled into
  skills' `references/` in the next commit, where a relative link would dangle.

## Validation

`just format`, `just lint`, and `just test` all pass.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
git add docs/cognitive-prose.md scripts/tests/test_cognitive_prose_doc.py docs/cognitive-debt.md CHANGELOG.md
git commit -F /tmp/commit-cognitive-prose-1.md
```

______________________________________________________________________

## Task 2: Distribution and drift

**Files:**

- Modify: `justfile:14-42` (the `sync-contracts` recipe — append a new block
  after the existing `ledger/core.py` block)
- Modify: `scripts/tests/test_cognitive_prose_doc.py` (append a second test
  class)
- Create by recipe: `skills/implement-ticket/references/cognitive-prose.md`
- Create by recipe: `skills/carve-changesets/references/cognitive-prose.md`
- Create by recipe: `skills/ready-ticket/references/cognitive-prose.md`
- Modify: `CHANGELOG.md`

**Interfaces:**

- Consumes: `docs/cognitive-prose.md` from Task 1, and the module-level
  `REPOSITORY_ROOT` and `CANONICAL` constants already defined in
  `scripts/tests/test_cognitive_prose_doc.py`.

- Produces: three bundled copies at
  `skills/<skill>/references/cognitive-prose.md`, byte-identical to the
  canonical file. Later pieces load them by that path.

- [ ] **Step 1: Write the failing test**

Append to `scripts/tests/test_cognitive_prose_doc.py`, after the existing
`CognitiveProseContractTests` class and before the `if __name__ == "__main__":`
block.

Also add this constant beside the existing module-level constants, under
`CANONICAL`:

```python
BUNDLING_SKILLS = ("implement-ticket", "carve-changesets", "ready-ticket")
```

Then the new class:

```python
class BundledProseContractTests(unittest.TestCase):
    """`just sync-contracts` copies the contract into each consuming skill so
    each stays self-contained when installed outside this repository. These
    fail when a copy drifts from the canonical file."""

    def test_every_consuming_skill_bundles_an_identical_copy(self) -> None:
        for skill in BUNDLING_SKILLS:
            bundled = (
                REPOSITORY_ROOT
                / "skills"
                / skill
                / "references"
                / "cognitive-prose.md"
            )
            with self.subTest(skill=skill):
                self.assertTrue(
                    bundled.exists(),
                    f"{bundled} is missing; run `just sync-contracts`",
                )
                self.assertEqual(
                    CANONICAL.read_bytes(),
                    bundled.read_bytes(),
                    f"{bundled} drifted from {CANONICAL}; "
                    "run `just sync-contracts`",
                )

    def test_no_bundled_copy_carries_a_link_it_cannot_resolve(self) -> None:
        # The canonical file is already all-absolute by test_every_link_is_absolute.
        # This asserts the property survives bundling, where nothing from this
        # repository's layout sits beside the copy.
        for skill in BUNDLING_SKILLS:
            bundle = REPOSITORY_ROOT / "skills" / skill / "references"
            text = (bundle / "cognitive-prose.md").read_text()
            for target in re.findall(r"\]\(([^)#][^)]*)\)", text):
                if target.startswith("https://"):
                    continue
                with self.subTest(skill=skill, target=target):
                    self.assertTrue(
                        (bundle / target).exists(),
                        f"{skill} bundles a link to {target}, which it does not ship",
                    )

    def test_no_unlisted_skill_bundles_the_contract(self) -> None:
        # A stray copy in a skill the recipe does not sync would drift silently
        # the first time the canonical text changed.
        found = {
            path.parents[1].name
            for path in (REPOSITORY_ROOT / "skills").glob(
                "*/references/cognitive-prose.md"
            )
        }
        self.assertEqual(found, set(BUNDLING_SKILLS))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest scripts.tests.test_cognitive_prose_doc -v`

Expected: the 7 tests from Task 1 PASS.
`test_every_consuming_skill_bundles_an_identical_copy` FAILS with
`skills/implement-ticket/references/cognitive-prose.md is missing; run just sync-contracts`.
`test_no_unlisted_skill_bundles_the_contract` FAILS comparing `set()` against
the three names. `test_no_bundled_copy_carries_a_link_it_cannot_resolve` errors
with `FileNotFoundError`.

- [ ] **Step 3: Add the sync block**

In `justfile`, inside the `sync-contracts` recipe, append this block after the
existing `ledger/core.py` block that ends the recipe:

```make
  @for skill in implement-ticket carve-changesets ready-ticket; do \
    dest="{{skills_dir}}/$skill/references"; \
    mkdir -p "$dest"; \
    cp docs/cognitive-prose.md "$dest/cognitive-prose.md"; \
    echo "Synced $dest/cognitive-prose.md"; \
  done
```

Then update the recipe's doc comment above `sync-contracts:` so it no longer
claims to refresh only review-suite copies. Replace:

```make
# Refresh the review-suite contract copies bundled into each review skill and
# each caller that consumes a review-code-change result, so every skill stays
# self-contained when installed outside this repository.
```

with:

```make
# Refresh the canonical text bundled into each consuming skill, so every skill
# stays self-contained when installed outside this repository: the review-suite
# contract copies for each review skill and each caller that consumes a
# review-code-change result, and the cognitive prose contract for each skill
# that emits reader-facing prose.
```

- [ ] **Step 4: Run the sync**

Run: `just sync-contracts`

Expected: the existing "Synced …" lines, followed by three new ones:

```text
Synced skills/implement-ticket/references/cognitive-prose.md
Synced skills/carve-changesets/references/cognitive-prose.md
Synced skills/ready-ticket/references/cognitive-prose.md
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest scripts.tests.test_cognitive_prose_doc -v`

Expected: PASS, 10 tests.

- [ ] **Step 6: Verify the drift test can actually fail**

A drift check that cannot go red is worse than none. Prove it:

```bash
printf '\ndrift\n' >> skills/ready-ticket/references/cognitive-prose.md
python3 -m unittest scripts.tests.test_cognitive_prose_doc -v
```

Expected: FAIL, naming `skills/ready-ticket/references/cognitive-prose.md`
drifted.

Restore and confirm green:

```bash
just sync-contracts
python3 -m unittest scripts.tests.test_cognitive_prose_doc -v
```

Expected: PASS, 10 tests. Record this before/after in the pull request body — it
is the change-demonstrating evidence for this task.

- [ ] **Step 7: Confirm no skill loads the contract yet**

Run: `grep -rn "cognitive-prose" skills/*/SKILL.md`

Expected: no output. If any `SKILL.md` matches, something outside this plan's
scope has been edited — revert it. Teaching skills to load the contract is a
later piece.

- [ ] **Step 8: Add the changelog entry**

Backfill Task 1's full SHA onto its changelog entry first
(`git rev-parse HEAD`), then add this entry above it:

```markdown
- build: distribute the cognitive prose contract to its consuming skills — the
  contract landed with no way to reach a skill. `just sync-contracts` now copies
  `docs/cognitive-prose.md` into `references/` for `implement-ticket`,
  `carve-changesets`, and `ready-ticket`, and a drift test fails when a copy
  diverges or when an unlisted skill carries one. The copies are deliberately
  unreferenced: no `SKILL.md` loads them, so this commit changes no behavior and
  leaves the consuming edits to be reviewed on their own. This branch expected
  to be the first exercise of the doctrine-distribution mechanism Spec B of the
  shaping program needs; #221 landed the same mechanism concurrently for the
  shaping doctrine, so the two arrived at one answer independently — including
  the same absolute-link constraint — rather than one piloting it for the
  other.
  The drift check was verified capable of failing: appending a line to the
  `ready-ticket` copy turns it red naming that file, and `just sync-contracts`
  restores green.
```

- [ ] **Step 9: Run the full required checks**

Run: `just format && just lint && just test`

Expected: all three pass, exit 0. `just lint` runs `skills-ref validate`, which
inspects every skill folder — the three new `references/` files must not break
it. If validation objects to an unreferenced reference file, stop and report it
rather than deleting the file; that would be a real finding about the bundling
approach.

- [ ] **Step 10: Commit**

```bash
cat >/tmp/commit-cognitive-prose-2.md <<'EOF'
build: distribute the cognitive prose contract to its consuming skills

## Summary

- Add a `just sync-contracts` block copying `docs/cognitive-prose.md` into
  `references/` for `implement-ticket`, `carve-changesets`, and `ready-ticket`
- Add drift, dangling-link, and unlisted-copy tests over the three bundles
- Correct the `sync-contracts` doc comment, which claimed the recipe refreshed
  only review-suite copies

## Why

The contract landed in the previous commit with no way to reach a skill. A skill
installed outside this repository carries only what is bundled into it, so
canonical text in `docs/` governs nothing until it is copied and drift-checked —
the same mechanism `review-suite/` has used for its contract all along.

## Why the copies are unreferenced

No `SKILL.md` loads them, deliberately. Distribution lands separately from
consumption so a reviewer can accept the mechanism without also accepting a
change to how any skill writes. The consuming edits are later work and will be
reviewed on their own.

This branch expected to be the first exercise of the doctrine-distribution
mechanism Spec B of the shaping program needs. #221 landed the same mechanism
concurrently for the shaping doctrine, so the two programs converged on one
answer independently rather than one piloting it for the other.

## Reviewer notes

- **The drift check was verified capable of failing.** Appending a line to the
  `ready-ticket` copy turns it red naming that file; `just sync-contracts`
  restores green.
- **No skill prose changed.** `grep -rn "cognitive-prose" skills/*/SKILL.md`
  returns nothing, so the eval-evidence norm still does not apply.

## Validation

`just format`, `just lint`, and `just test` all pass.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
git add justfile scripts/tests/test_cognitive_prose_doc.py skills/implement-ticket/references/cognitive-prose.md skills/carve-changesets/references/cognitive-prose.md skills/ready-ticket/references/cognitive-prose.md CHANGELOG.md
git commit -F /tmp/commit-cognitive-prose-2.md
```

______________________________________________________________________

## Final verification

- [ ] **Every spec requirement maps to a task**

| Spec requirement                                  | Where                                                                                          |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `docs/cognitive-prose.md` canonical contract      | Task 1, Step 3                                                                                 |
| Seven sections, in order                          | Task 1, Steps 1 and 3; asserted by three tests                                                 |
| Opening move required                             | Task 1, Step 3, `## The opening move`                                                          |
| Reader's question order as positive contract      | Task 1, Step 3, `## The reader's question order`                                               |
| Prohibitions, each sourced                        | Task 1, Step 3; asserted by `test_every_prohibition_names_a_source`                            |
| Rationalization table unwritten and self-declared | Task 1, Step 3; asserted by `test_the_contract_records_the_rationalization_table_as_unwritten` |
| Scale as calibration, guarding over-correction    | Task 1, Step 3, `## Scale`                                                                     |
| Exemplar pair #209 against #20                    | Task 1, Step 3, `## The exemplar pair`                                                         |
| Prose as fourth commitment in `cognitive-debt.md` | Task 1, Step 5                                                                                 |
| `just sync-contracts` block for three skills      | Task 2, Step 3                                                                                 |
| Drift check in the root suite                     | Task 2, Step 1                                                                                 |
| Structural and sourcing check                     | Task 1, Step 1                                                                                 |
| No test asserts on prose quality                  | Held by construction — every assertion is structural                                           |
| No skill behavior changes                         | Task 2, Step 7 verifies by grep                                                                |

- [ ] **Run the whole suite from a clean tree**

```bash
git status --short
just format && just lint && just test
python3 -m unittest scripts.tests.test_cognitive_prose_doc -v
python3 -m unittest scripts.tests.test_suite_invocation -v
```

Expected: `git status --short` empty, all checks pass. The
`test_suite_invocation` run is the specific guard that the new module carries
its `sys.path` shim — it fails with
`ModuleNotFoundError: No module named 'helpers'` if Step 1's shim was dropped.

- [ ] **Open the pull request under the contract it defines**

This branch's own pull request body is the first written under
`docs/cognitive-prose.md`. Write it to the contract: open on why the change is
necessary, answer the reader's four questions in order, and cite the drift
check's verified failure as validation. A contract whose own introduction
violates it has answered the question of whether it works.

## What this plan does not do

- **It does not teach any skill to load the contract.** No `SKILL.md` is edited.
  That is the next piece, and it is where the eval-evidence norm first applies.
- **It does not reconcile the commit-body rules** already in `AGENTS.md`. Two
  sources of truth on emitted prose is a known open item, assigned to a later
  piece.
- **It does not resolve how to evaluate whether prose is humane.** The exemplar
  pair is the seed a rubric or corpus would need; the question stays open.
