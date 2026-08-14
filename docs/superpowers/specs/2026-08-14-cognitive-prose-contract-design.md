# The cognitive prose contract

This is the design for piece 1 of the cognitive prose program: the canonical
prose contract, its distribution into consuming skills, and the drift check that
keeps the copies honest. Nothing consumes the contract when this lands. Teaching
skills to load it is piece 2 and piece 3, recorded at the end of this document
and not designed here.

## The problem

compris shapes what a reviewer reads and says nothing about how it is written.

The entire pull-request-body obligation in the suite is one sentence at
[`skills/implement-ticket/SKILL.md:669`][implement-ticket]:

> describe the ticket-wide outcome, important non-goals, actual validation, and
> acceptance-ledger state

That is a content checklist. Four things must appear; nothing constrains form,
register, ordering, or what the reader experiences. An agent that emits four
paragraphs of dense agent-ese has complied in full. `carve-changesets` has less
than that — its per-changeset pull requests inherit no prose obligation at all.

The failure this permits is observable in this repository's own history.
[#20][pr20] opens:

> Adds `implement-ticket` as the reusable, runtime-neutral workflow for
> implementing exactly one standalone ticket or named epic child through safe
> review and delivery gates.

Four stacked modifiers, and no statement of what was wrong before. Its `Summary`
is five bullets that each open with an imperative verb — Extract, Establish,
Keep, Preserve, Add — which is the diff restated in prose. One bullet is a
five-item noun pile: "cross-system GitHub and Linear ownership, explicit
authority boundaries, current-candidate review gates, safe base-drift handling,
and post-merge dependency refresh." A reviewer learns nothing from that sentence
that `git diff --stat` would not have told them faster. [#60][pr60] opens the
same way, on "Add a coordinator-neutral delegated execution contract."

[#209][pr209] is the same repository, the same author, and later:

> Every module under `scripts/tests/` took its sibling `helpers.py` on the
> `sys.path` entry `unittest discover` happens to supply.

It opens on the defect, argues from the ticket in a `## Why`, names the commit
the bug predates, carries an explicit "why the shim rather than standardizing on
discovery" with a survey table, and proves in its reviewer notes that the new
guard was verified capable of failing.

So the voice already improved here. It improved in one person's head, and
nothing in the suite would stop a fresh agent from regenerating #20's prose
tomorrow.

This matters because prose is where cognitive debt is either paid or deferred.
[`cognitive-debt.md`][cognitive-debt] states the problem the suite exists to
solve: the theory of a program decaying out of human minds while agents write
the code. A correctly shaped changeset a reviewer cannot parse the description
of has not transferred the theory — it has only made the failure smaller. Shape
without prose wins the battle and loses the war.

## The standard this establishes

Prose compris emits is written for the human accountable to the codebase, not
for the agent that will parse it: **clear, understandable, and unambiguous —
never merely efficient.**

Agent idiom is token-efficient and human-hostile. It optimizes for the wrong
reader. That is the whole of the design principle, and every rule below is
downstream of it.

## Scope

The contract governs two surfaces:

- **pull request bodies** — `implement-ticket` at publication, and
  `carve-changesets` for each changeset pull request in a chain; and
- **ticket bodies** — `ready-ticket`.

Pull request bodies are the priority. Ticket bodies are in scope because a
reviewer treats the ticket as the source of truth for why the pull request
exists at all, so obfuscation there defeats a well-written pull request
downstream.

The contract explicitly does not govern:

- **`SKILL.md` prose.** [`skill-authoring.md`][skill-authoring] owns how a skill
  is written for an agent reader. That is a different subject with a different
  reader, and merging the two muddies both.
- **Code comments.** Out of scope, and not planned.
- **Commit bodies.** [`AGENTS.md`][agents] already rules on these with good and
  bad examples. Reconciling the two into one source of truth is piece 4.

## What ships

Four things, and no skill behavior changes.

1. `docs/cognitive-prose.md` — the canonical contract.
2. A `just sync-contracts` block distributing it into `references/` for
   `implement-ticket`, `carve-changesets`, and `ready-ticket`.
3. `scripts/tests/test_cognitive_prose_doc.py` — drift check and structural
   check.
4. A link from [`cognitive-debt.md`][cognitive-debt] naming prose as a fourth
   commitment alongside shape, publicity, and why-not-just-what.

### Why the canonical text lives in `docs/`

Doctrine in this repository lives in `docs/` —
[`cognitive-debt.md`][cognitive-debt] and
[`cognitive-shaping-doctrine.md`][doctrine] are both there. Cognitive prose is
doctrine, not a schema, so a root-level `prose/` directory parallel to
`review-suite/` would put the only doctrine in the repository outside `docs/`.

This has a deliberate consequence. Spec B of the shaping program is precisely
the job of bundling `docs/cognitive-shaping-doctrine.md` into consumers;
[`cognitive-driven-development.md:412`][cdd] records that what is missing there
is "only its *distribution* — nothing bundles it into a consumer and nothing
drift-checks it." Syncing from `docs/` here builds that mechanism first, on a
document with no consumers and nothing to break, so Spec B inherits a proven
path instead of inventing one.

The cost is that this piece settles a "how does `docs/` doctrine reach skills"
question Spec B was scoped to answer. That is accepted knowingly: the
lowest-risk possible pilot for a mechanism the repository has already committed
to is worth more than keeping the two programs formally separate.

### Why three skills get an unreferenced file

The sync block targets the three skills that piece 2 and piece 3 will teach to
load the contract. None of them references it when this lands.

That is the good seam rather than an oversight. The distribution mechanism lands
separately from the behavior change, which is what the shaping doctrine's own
breakdown rules ask for — separate mechanical restructuring from behavioral
change when that helps review. Piece 2 then becomes a pure prose edit against a
path already proven by a passing drift test. The cost is three unreferenced
files for one ticket's life, which is disk rather than context, since
`references/` files load on demand.

## The contract's contents

The contract needs two textual forms, because it addresses two distinguishable
failures. [`skill-authoring.md`][skill-authoring] governs that choice.

Structure is **wrong-shaped output**: the agent does the work and returns
something the reader cannot use. `skill-authoring.md:152` is explicit that a
prohibition cannot fix a shape problem, because "do not write X" leaves the
agent to substitute a shape of its own invention. So the ordering half is
written as a positive contract.

Voice is a **discipline violation**: the model can write plain English and
defaults away from it. `skill-authoring.md:114` prescribes a prohibition plus a
rationalization table for that shape.

`docs/cognitive-prose.md` carries seven sections.

### 1. The standard

The paragraph under "The standard this establishes" above, plus a link to
[`cognitive-debt.md`][cognitive-debt] as the problem it answers.

### 2. Scope

The two governed surfaces and the three explicit exclusions, as stated above.

### 3. The opening move

Required. One to two sentences establishing **why the change is necessary**, and
**how it solves the problem** where that fits in the same breath.

It is not required to be comprehensive. It is required to orient — a reader who
stops after the first two sentences should know what problem exists and roughly
what was done about it.

### 4. The reader's question order

A positive contract stating what the body *is*, ordered by the questions a
reader actually asks:

1. what was wrong;
2. what this does about it;
3. why this approach and not the obvious alternative, when a real alternative
   was weighed; and
4. how it was verified.

Ordered by the reader's questions, never by the repository's file layout. A body
organized as a walk through changed files has chosen the writer's convenience
over the reader's.

Sections 3 and 4 are what [#209][pr209] does. The contract cites it as the
worked exemplar rather than describing the shape abstractly.

### 5. The prohibitions

Each prohibition names the pull request it was observed in.
`skill-authoring.md:132` admits only sourced entries, and "a GitHub PR review
history entry" is a qualifying source.

| Prohibition                                                                                                                                  | Sourced to                                                                                 |
| -------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Do not restate the diff. A body whose content is recoverable from `git diff --stat` has spent the reader's attention without informing them. | [#20][pr20], five imperative-verb bullets                                                  |
| Do not stack modifiers where a verb would do.                                                                                                | [#20][pr20], "reusable, runtime-neutral workflow … through safe review and delivery gates" |
| Do not write a feature list as a sentence.                                                                                                   | [#20][pr20], the five-item noun pile                                                       |
| Do not open on what was added. Open on what was wrong.                                                                                       | [#20][pr20] and [#60][pr60], both opening on "Adds"/"Add"                                  |

### 6. Scale

Calibration, not a gate, mirroring the shaping doctrine's treatment of line
counts.

This section exists to guard a specific over-correction. "Cognitive prose" read
carelessly means "explain everything," and the presentational techniques that
motivated this work are large artifacts. They are not the target here. A
300-line change usually wants a few hundred words, and a body that grows into a
tutorial has traded one unreadable artifact for another.

### 7. The exemplar pair

[#209][pr209] annotated against [#20][pr20] — same repository, same author, same
subject matter, three weeks apart. The annotation names which move each does, so
the pair teaches rather than merely demonstrating.

## The rationalization table is deliberately unwritten

The contract ships with no rationalization table, and says so in its own text.

`skill-authoring.md:132` requires a table's rows to be sourced to something
carrying "the agent's own wording." #20 and #60 supply observed bad **output** —
enough to source every prohibition in section 5 — but not the
**rationalization** that preceded it, which is what the left column requires.
Inventing those rows is what that rule exists to forbid, and an invented row
"carries none of the format's evidentiary weight and can misdirect a reader into
trusting an unobserved failure mode as documented."

Populating it requires baseline transcripts recorded per
`skill-authoring.md:223`. That is piece 2's work, where a baseline must be
established before the prose change can be evaluated at all.

The consequence is that this contract's voice half is genuinely weaker than its
final form. The document states that limitation rather than leaving a reader to
assume the prohibitions are fully armed.

## Verification

Two tests, in `scripts/tests/test_cognitive_prose_doc.py`, in the root suite —
the canonical source is `docs/`, which is not `review-suite/`'s business, and
[`scripts/tests/test_cognitive_driven_development_doc.py`][cddtest] is the
precedent for testing a `docs/` file from there. The module carries the
`__file__`-relative `sys.path` shim that
[`scripts/tests/test_suite_invocation.py`][suitetest] enforces.

1. **Drift.** Each bundled copy under
   `skills/<skill>/references/cognitive-prose.md` matches
   `docs/cognitive-prose.md` byte for byte, for all three consuming skills.
   Modeled on [`test_bundled_contracts.py`][bundled].
2. **Structure and sourcing.** The document carries its seven required sections,
   and every row in the prohibitions table names at least one pull request as
   its source. The second half mechanically enforces the sourcing rule this
   design depends on, and fails the moment an invented prohibition is added.

No test asserts on prose quality. Nothing mechanical can, and a test that
appeared to would be the over-engineering `review-solution-simplicity` exists to
catch.

### Eval evidence

This piece changes no skill's normative prose. It adds a `references/` file that
no `SKILL.md` loads, so it governs no behavior yet, and [`AGENTS.md`][agents]'s
norm covers `references/` files "that govern behavior."

The reading is that this piece is exempt and piece 2 is where the obligation
lands. It is an honest reading rather than the only possible one — the file *is*
under `references/` — so **the pull request states this reasoning explicitly**,
rather than leaving a reviewer to wonder whether the norm was skipped or
considered. [#209][pr209] is the precedent for saying so in the body.

## What this design does not settle

**How to evaluate whether prose is humane.** This is unsolved and assigned to
piece 2, where the eval-evidence norm first applies. The honest options are a
model-judged rubric, which is expensive and noisy, or a mechanical check for
banned constructions, which is cheap and misses the actual failure. This piece
contributes the exemplar and counter-exemplar pair, which is the seed either
approach would need — a downpayment on the problem rather than a placeholder.

**Whether a contract is sufficient.** A contract constrains prose the agent was
already going to write. It cannot compel the investigation that produces a
reason, and #20's real failure was that nobody established why the change was
needed. If contract-only output still opens on what was added, the missing piece
is procedure rather than standard, and that is what piece 5 exists to answer.

## The remaining pieces

Recorded for ordering, not designed here.

2. **Pull request bodies adopt the contract** — `implement-ticket` at
   publication, `carve-changesets` per changeset. First piece to change
   normative prose, so the eval question is answered there.
3. **Ticket bodies adopt the contract** — `ready-ticket`. Same shape as piece 2,
   separate skill, separate corpus.
4. **`AGENTS.md` and `skill-authoring.md`** — pointers to the canonical
   contract, plus the commit-body reconciliation, so exactly one document rules
   on emitted prose.
5. **The `explain` skill** — the procedure that does the investigation a
   contract cannot compel. Last deliberately: built against a contract that
   already exists and has been exercised on real pull requests, so it answers a
   demonstrated gap rather than a predicted one. Whether it emits a rich
   standalone artifact, with diagrams and comprehension checks, or only writes a
   better body, is open.

<!-- inline reference link definitions. please keep alphabetized -->

[agents]: ../../../AGENTS.md
[bundled]: ../../../review-suite/scripts/tests/test_bundled_contracts.py
[cdd]: ../../cognitive-driven-development.md
[cddtest]: ../../../scripts/tests/test_cognitive_driven_development_doc.py
[cognitive-debt]: ../../cognitive-debt.md
[doctrine]: ../../cognitive-shaping-doctrine.md
[implement-ticket]: ../../../skills/implement-ticket/SKILL.md
[pr20]: https://github.com/shaug/compris/pull/20
[pr209]: https://github.com/shaug/compris/pull/209
[pr60]: https://github.com/shaug/compris/pull/60
[skill-authoring]: ../../skill-authoring.md
[suitetest]: ../../../scripts/tests/test_suite_invocation.py
