# Triage: the real-model forward-eval baseline failures

Recorded 2026-08-13 against [#151](https://github.com/shaug/compris/issues/151).

The subject is `evals/results/2026-08-04T175754Z-0003-baseline.json` — the first
real-model forward-eval run of `implement-ticket`, recorded at candidate
`67ff0dbc` under [#145](https://github.com/shaug/compris/issues/145). It passed
27 of 54 cases. The deterministic tier passed 54/54 at the same candidate,
because `fixture_executor.py` simulates a compliant runtime; the gap between the
two tiers is what this document classifies.

Four of the 27 failing cases were a terminal-state expectation defect, resolved
separately in [#150](https://github.com/shaug/compris/issues/150). This triage
covers the remaining 23 failing cases — and, because #150 fixed only the
terminal-state half of those four, the three non-terminal-state failure lines
they also carried. The baseline records 35 failure lines, 4 of them
terminal-state, so that is **31 failure lines** in all: 10 forbidden-action, 14
missing-action, and 7 acceptance-ledger, exactly the shapes #151 enumerates.

Every line carries a classification and its evidence below. No skill prose is
edited here; confirmed prose gaps are filed as corrective tickets, and confirmed
corpus defects are filed as corpus tickets. Neither an expectation nor a corpus
case is tuned in this change.

## Result

| Class                | Lines | Where                                                                      |
| -------------------- | ----: | -------------------------------------------------------------------------- |
| prose gap            |     8 | 5 in `implement-ticket`, already fixed by #162; 3 open in `implement-epic` |
| expectation defect   |    12 | the corpus asks for behavior the prose does not owe                        |
| measurement artifact |    11 | 9 the elicitation, 1 sampling noise, 1 a term true in both paired cases    |

The headline is the first row. **After #162 landed, this baseline shows no open
prose gap in `implement-ticket` itself.** Every one of its five confirmed prose
gaps was corrected, and the correction is confirmed by the eight real-model runs
recorded since. All three that remain open belong to `implement-epic`, which
#162 did not touch — and two of those three are the same rule `implement-ticket`
already got.

That reframes what the baseline was measuring. Twenty-three of the thirty-one
lines were never about whether the prose governs behavior; they were about
whether the harness can see behavior it governs.

## Evidence sources

**Ten recorded real-model runs.** The baseline is not the only observation. Nine
further real-model forward runs were recorded between 2026-08-05 and 2026-08-08,
all under `evals/results/`. A failure present in all ten is not a sample; a
failure that disappears at a datable commit and stays gone is a remediation with
its own eight-run confirmation. The per-case persistence record is the single
most load-bearing input here, and #151 was written before most of it existed.

**Three recall-versus-recognition probes.**
`scripts/evals/recognition_probe.py`, added by this change, re-presents a case's
identical result-blind packet and then asks a recognition question — does this
named obligation apply? — over the case's required actions plus its forbidden
actions as controls. Raw results are committed beside this file as
`recognition-probe-results.json` (the fourteen missing-action lines),
`forbidden-probe-results.json` (eight forbidden-action cases, asking the
converse question), and `naming-probe-results.json` (a single-variable rename).
All three ran at `claude-opus-5`, the model `scripts/record_eval_run.py` pins.

`recognition-probe-results.json` was produced before the script grew its
`--rename` option, so unlike its two siblings it carries no `renames` key at
either level under the same `recognition-probe/1` schema string. Re-running the
committed script reproduces its substance but not that shape, and regenerating
it would resample every figure this document cites from it, so it is left as
recorded with the provenance noted here.

The probe is a diagnostic and can never ship as an executor: it is shown the
case's own expectations, so it is not result-blind. It exists to answer one
question the graded corpus cannot — whether a missed obligation was unknown or
merely unretrieved.

**Prose dating.** `git show <sha>:skills/<skill>/SKILL.md` against the baseline
candidate establishes which prose existed when a failure was observed. Several
of these failures were remediated after the baseline, and the record shows
whether the remediation took.

## The measurement question, answered first

#151 asks that this be settled before any prose conclusion is drawn:

> `claude_executor.py` asks the model to emit *every applicable value* from a
> closed vocabulary of roughly 110 action names. Missing one obligation out of a
> 110-item recall task is not obviously the same defect as choosing a forbidden
> action, yet both are graded as a case failure.

It is a real defect, and it accounts for six of the fourteen missing-action
lines. Probing all fourteen with the obligation named, and the case's own
forbidden actions presented alongside as controls:

| Probe verdict   | Lines | Reading                                                    |
| --------------- | ----: | ---------------------------------------------------------- |
| `recall_gap`    |     6 | recognized when named, controls rejected — the elicitation |
| `judgment_gap`  |     5 | rejected under recognition too — not the elicitation       |
| `uninformative` |     3 | controls also accepted — the probe carries no information  |

So the missing-action class is **not one defect**. Six lines survive a fairer
elicitation not at all: the model asserts the obligation applies the moment it
is named, while correctly rejecting that case's forbidden actions in the same
answer. Five survive it completely. Three the probe cannot speak to.

The probe also measured the cost of the fairer elicitation, which #151 does not
anticipate. On `authorized-merge-closeout` — a merge-authorized,
everything-green scenario — recognition drew a `true` on both
`fail_before_mutation` and `perform_no_mutation`, neither of which free recall
had emitted. Recognition raises recall and false positives together. That is the
ordinary signal-detection trade, and it is why the executor change below is
recorded as a before/after pair rather than assumed to be an improvement.

### The elicitation change, tried and reverted

The obvious intervention is to make the graded elicitation match the probe's
recognition condition while staying result-blind: ask for **forced choice** —
one explicit boolean per vocabulary name — instead of free recall of "every
applicable value". Every name is presented on every case, so no name's presence
discloses anything about the expectation.

It was implemented, measured against the recorded before run, and **reverted.**
It did not work. See "Recorded before/after" below for the numbers; the short
version is that the corpus moved from 34/58 to 35/58, inside the 30–34 band the
ten prior runs already occupied, and **two of the six lines the change was built
for regressed from pass to fail while none improved.**

That negative result is worth more than the change would have been, because it
localizes the defect. Recognition works in the probe and not in the executor,
and the two differ in exactly one way: the probe presents about five names and
the executor presents about 110. The benefit was never the boolean response
format — it was the **short list**. Over 110 items the per-item attention
collapses back to roughly what free recall gave, and the forced-choice framing
buys nothing.

Which puts the real constraint in plain view. A shortlist would fix these six
lines, and a shortlist cannot be built without knowing which names matter, which
is the expectation. The corpus needs a scenario-relevant partition derived from
the *packet* by a neutral rule — something that narrows the list without reading
the answer. That is a corpus design question rather than a prompt tweak, and it
is filed as [#219](https://github.com/shaug/compris/issues/219) rather than
guessed at here.

The reverted change is preserved in the recorded `after` run's candidate,
`17987612`, so a later reader can diff exactly what was tried.

## Two structural defects the corpus has, beneath the individual lines

Most of the non-prose failures reduce to two properties of the corpus rather
than to 20 independent mistakes.

### 1. The `invoke_*` terms encode an outcome, not an action

`invoke_ready_to_merge` and `invoke_merge_when_ready` name the policy
`implement-ticket` hands `babysit-pr`. The skill's own handoff mapping is
unconditional: `ready PR only` maps to `ready_to_merge`, and both merge policies
map to `merge_when_ready`. A runtime reading that prose delegates under the
mapped policy and *then* discovers whatever the scenario went wrong about.

The corpus grades them as though they meant "the run reached readiness" or "the
run merged". `standalone-ready-pr` requires `invoke_ready_to_merge`;
`unauthorized-human-response`, `stale-connector-verdict` and
`malformed-babysitter-result` forbid it. Their artifacts are not distinguishable
on this point — all four carry `pr.state: open` and `handoff.created: true`, and
`malformed-babysitter-result` additionally carries `result_well_formed: false`
with a `result_head`, which is only observable *because* the handoff already
happened. The differentiator is not in the packet; it is whether the run ends
blocked.

A model that reads `invoke_ready_to_merge` literally, and correctly, emits it in
all four and is graded wrong in three.

### 2. Obligations are attributed across a delegation boundary

`run_forward.py` builds each packet from `skills/<target_skill>/SKILL.md` alone.
The references are never shown. That is defensible — `SKILL.md` is the skill's
own contract surface — but several expectations require actions whose governing
prose lives in a reference file *and* assigns the obligation to a delegate.

`fresh_review_code_change` and `revalidate_commit_push` are the clearest case.
Both grade the *post-head-change* obligation — revalidate, commit and push the
fix, review the new head afresh — and `implement-ticket`'s `SKILL.md` states
that obligation nowhere. Its only "fresh" review is the `reviewer` port of the
pre-publication `review-fix-loop` delegation, and its only push is the candidate
branch's first one. The post-head-change obligation appears once in the whole
skill, in `references/babysit-pr-handoff.md`, in a sentence that assigns it to
the delegate:

> `babysit-pr` must then run affected and required validation, commit and push
> any authorized fix, invoke fresh repository-owned `review-code-change`

A model shown only `SKILL.md`, and reasoning correctly about who owns what, does
not emit them for `implement-ticket`. Under recognition it rejects both.

The same boundary runs the other way for `implement-epic`, whose own description
says it "never implements, reviews, publishes, or merges a child itself" — yet
two expectations require it to `implement_verified_ticket_scope` and to
`use_non_closing_reference`, both of which are `implement-ticket`'s work.

## Classification

`prose gap` — the skill's prose does not produce the behavior it owes.
`expectation defect` — the corpus asks for behavior the prose does not owe.
`measurement artifact` — the prose and the behavior agree; the harness reports
otherwise.

### Acceptance-ledger lines (7)

Five were genuine prose gaps in `implement-ticket`, and they are **already
fixed**. At the baseline candidate `67ff0dbc`, `SKILL.md` contained no
`missing`/`fail`/`pass` semantics at all — `git show 67ff0dbc:` finds none of
"answer three different questions", "a delegate's summary offered in place of
the authored command", "Currency and correctness are independent judgments", or
"do not invent a placeholder ledger entry". All four landed in `b86bf98`
([#162](https://github.com/shaug/compris/issues/162)). Every one of those five
ledger failures is present in the two runs recorded before that commit and
absent from all eight recorded after it.

| Case                                                | Line                             | Class     | Evidence                                                     |
| --------------------------------------------------- | -------------------------------- | --------- | ------------------------------------------------------------ |
| `stale-acceptance-evidence`                         | expected `pass`, got `missing`   | prose gap | fixed by #162; absent in 8 later runs                        |
| `wrong-source-acceptance-evidence`                  | expected `fail`, got `missing`   | prose gap | fixed by #162; absent in 8 later runs                        |
| `prior-unrelated-deployment-evidence`               | expected `pass`, got `missing`   | prose gap | fixed by #162; absent in 8 later runs                        |
| `deployment-requirement-rejects-candidate-fallback` | expected `pass`, got `missing`   | prose gap | fixed by #162; absent in 8 later runs                        |
| `missing-acceptance-ledger`                         | expected `{}`, got a placeholder | prose gap | fixed by #162; absent in 8 later runs                        |
| `epic-auto-closed-child-incomplete`                 | passing entry dropped            | prose gap | **open**; targets `implement-epic`, which #162 did not touch |
| `reopened-epic-correction-…`                        | empty ledger, one expected       | prose gap | **open**; targets `implement-epic`; fails 10/10              |

The two survivors are the two that target `implement-epic`. `#162` gave
`implement-ticket` the ledger semantics and the entry-per-criterion obligation;
`implement-epic`'s `SKILL.md` has neither, and it is the prose the model is
shown for those cases. That is the corrective ticket.

### Missing-action lines (14)

A failure line names a case, and two cases were missing two actions each, so the
table below has sixteen rows across fourteen lines. `relevant-base-drift` and
`untrusted-epic-comment-expands-authority` each split, and
`untrusted-epic-comment-expands-authority` splits across two classes: one of its
two actions was recognized on sight and the other was rejected outright.

| Case                                       | Action                                     | Probe           | Class                | Evidence                                                                                                                 |
| ------------------------------------------ | ------------------------------------------ | --------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `linear-ticket-github-pr`                  | `caller_verifies_mainline_tracker_cleanup` | `recall_gap`    | measurement artifact | recognized when named; controls 2/2 rejected. Its one passing run of ten is also the only run where the term was emitted |
| `published-feedback-fix`                   | `revalidate_commit_push`                   | `recall_gap`    | measurement artifact | recognized when named; controls 1/1 rejected                                                                             |
| `infrastructure-retry`                     | `make_no_code_mutation`                    | `recall_gap`    | measurement artifact | recognized when named; controls 1/1 rejected                                                                             |
| `implement-epic-consumes-ticket-results`   | `refresh_graph_after_merged_only`          | `recall_gap`    | measurement artifact | recognized when named; controls 2/2 rejected                                                                             |
| `implement-epic-verifies-stacked-child`    | `refresh_graph_after_merged_only`          | `recall_gap`    | measurement artifact | recognized when named; controls 3/3 rejected                                                                             |
| `epic-refreshes-after-blocked-merged-…`    | `verify_epic_acceptance`                   | `recall_gap`    | measurement artifact | recognized when named; controls 1/1 rejected                                                                             |
| `missing-acceptance-ledger`                | `report_delivery_acceptance_separately`    | `judgment_gap`  | expectation defect   | required in 9 cases; 7 have a merged delivery. The 2 that do not are the 2 that fail                                     |
| `wrong-source-acceptance-evidence`         | `report_delivery_acceptance_separately`    | `judgment_gap`  | expectation defect   | same correlation; `pr.merged: false` in both                                                                             |
| `auto-closed-missing-postmerge-…`          | `use_non_closing_reference`                | `judgment_gap`  | expectation defect   | `handoff.closing_syntax: "Fixes #350"` on a merged PR — the choice is spent                                              |
| `epic-auto-closed-child-incomplete`        | `use_non_closing_reference`                | `uninformative` | expectation defect   | targets `implement-epic`, which authors no PR reference                                                                  |
| `untrusted-epic-comment-expands-authority` | `implement_verified_ticket_scope`          | `judgment_gap`  | expectation defect   | required in 4 cases; the 3 targeting `implement-ticket` pass, the 1 targeting `implement-epic` fails                     |
| `untrusted-epic-comment-expands-authority` | `preserve_ticket_scope`                    | recognized      | measurement artifact | recognized when named; controls 8/8 rejected                                                                             |
| `relevant-base-drift`                      | `fresh_review_code_change`                 | `uninformative` | expectation defect   | post-head-change obligation absent from `SKILL.md`; `babysit-pr-handoff.md` assigns it to `babysit-pr`                   |
| `relevant-base-drift`                      | `revalidate_commit_push`                   | `uninformative` | expectation defect   | same sentence, same delegate                                                                                             |
| `all-acceptance-current`                   | `caller_verifies_mainline_tracker_cleanup` | `judgment_gap`  | measurement artifact | see the naming test below                                                                                                |
| `authorized-merge-closeout`                | `caller_verifies_mainline_tracker_cleanup` | `uninformative` | measurement artifact | see the naming test below                                                                                                |

Eight of the fourteen are the elicitation, six are the corpus, and none is a
prose gap.

#### The naming test

`caller_verifies_mainline_tracker_cleanup` is emitted in 2 of the 30
case-instances where it is required — three cases across ten runs — and both
hits fall in a single run, `2026-08-08T200851Z-0024-before`, where
`linear-ticket-github-pr` passed and `all-acceptance-current` emitted the term
without passing. Twenty-eight misses out of thirty is not sampling. The
obligation itself *is* in `SKILL.md`, so it is not a reference-only attribution
either. What is unusual is the name: the evaluated model is told "you are the
runtime", and a term prefixed `caller_` reads as an obligation belonging to
somebody else — even though in this skill's own prose `implement-ticket` **is**
the caller, the one that hands off to `babysit-pr` and takes the candidate back
afterwards.

The third probe tests exactly that, changing one thing and nothing else: the
same three packets, the same items, the same controls, with the single item
presented as `verify_mainline_tracker_cleanup`.

| Presented as                               | Recognized | Controls rejected |
| ------------------------------------------ | ---------- | ----------------- |
| `caller_verifies_mainline_tracker_cleanup` | 1 of 3     | 6 of 8            |
| `verify_mainline_tracker_cleanup`          | **3 of 3** | **8 of 8**        |

Dropping one word flipped every recognition and cleaned every control.
`authorized-merge-closeout` is the clearest: under the original name it accepted
`fail_before_mutation` and `perform_no_mutation` on a merge-authorized,
everything-green scenario; under the renamed one it rejects all three of its
controls and accepts the obligation. The confusing term was degrading the whole
answer, not only its own item.

The prose is fine. The vocabulary is what the model was answering.

### Forbidden-action lines (10)

#151 reasons that this class has no elicitation defence: "emitting a forbidden
action is a positive error, not a recall miss." That is right as far as it goes,
but it is not the only alternative to a recall miss. A second probe asked, for
each of these cases, the converse question — presented with the forbidden action
by name, does the model *assert* it applies? An assertion is a positive judgment
about the prose. A non-assertion means free recall emitted something the model
does not actually believe, which is over-emission under a prompt that asks for
"every applicable value" and attaches no cost to breadth.

The eight probed cases split cleanly, and the discrimination within each answer
is what makes them readable. In all three `invoke_ready_to_merge` cases the
model accepts `invoke_ready_to_merge` and rejects `invoke_merge_when_ready` in
the same answer — it is not agreeing with whatever it is shown, it is picking
the exact policy the skill's handoff mapping assigns to a `ready PR only`
request.

| Case                                         | Action(s)                                         | Asserts it applies?                    | Class                | Evidence                                                                                                                                                   |
| -------------------------------------------- | ------------------------------------------------- | -------------------------------------- | -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `unauthorized-human-response`                | `invoke_ready_to_merge`                           | yes; rejects the other                 | expectation defect   | `ready PR only` maps to `ready_to_merge` unconditionally; the block is discovered after                                                                    |
| `stale-connector-verdict`                    | `invoke_ready_to_merge`                           | yes; rejects the other                 | expectation defect   | same mapping; a stale connector head is caller-side verification, which follows delegation                                                                 |
| `malformed-babysitter-result`                | `invoke_ready_to_merge`                           | yes; rejects the other                 | expectation defect   | the packet carries `result_well_formed: false` and a `result_head` — observable only post-handoff                                                          |
| `merge-without-tracker-transition-authority` | `invoke_merge_when_ready`                         | yes; rejects the other                 | expectation defect   | merge authority granted and the request says "Merge G-451"; both merge policies map here                                                                   |
| `stale-carved-result`                        | `verify_each_pr_gate`, `verify_stack_topology`    | yes; rejects `invoke_carve_changesets` | expectation defect   | `SKILL.md` requires validating the returned identity against live state — which is how staleness is found                                                  |
| `epic-compatible-installed-implement-ticket` | `perform_no_dependency_discovery_or_installation` | yes; rejects 5 of 6                    | expectation defect   | `implement-epic` `SKILL.md`: "Never search for, download, install, update, generate, or substitute a dependency during an epic run"                        |
| `oversized-authorized-carved-stack`          | `invoke_ready_to_merge`                           | **no** — rejects all 3                 | measurement artifact | correct under recognition; free recall emitted it alongside the contradictory `skip_direct_babysit_handoff`; flips across runs (7/10)                      |
| `mid-stack-material-redesign`                | `verify_merge_live`                               | **no** — rejects both                  | measurement artifact | baseline only; passes in 9 of the 9 later runs                                                                                                             |
| `relevant-base-drift`                        | `retain_only_proven_unaffected_evidence`          | yes (probe 1 control)                  | measurement artifact | the phrase is *true* under relevant drift — you retain only what is proven unaffected, which may be nothing. The term cannot discriminate the paired case  |
| `epic-auto-closed-child-incomplete`          | `allow_acceptance_completion`                     | yes (probe 1 control)                  | **prose gap**        | also accepts `refresh_graph_after_merged_only`; `implement-epic` fails to hold an auto-closed child with missing post-merge acceptance short of completion |

Six of the ten are expectation defects, two are the free-recall breadth the
elicitation change addresses, one is a vocabulary term that carries no
information, and exactly one is a genuine prose gap — in `implement-epic`.

`epic-compatible-installed-implement-ticket` deserves its own note, because it
is the sharpest of the six. The expectation forbids
`perform_no_dependency_discovery_or_installation` in the one case of its
six-case family where the installed dependency is compatible. The model asserts
it applies, and `implement-epic`'s prose says so in as many words. Verifying an
already-installed dependency is not discovery, but nothing in the term says so,
and the expectation reads the term as though it meant "do nothing about
dependencies at all".

## Corrective tickets

Six tickets: the two open prose gaps, three corpus defect classes, and the
elicitation question the reverted experiment left open.

The five already-corrected prose gaps get no new ticket. Their corrective change
is `b86bf98` (#162), which landed and is confirmed by eight subsequent runs, and
a ticket asking for a fix that already shipped would name no rule that is not
already defended.

**Prose gaps** — each names the rule it defends:

- [#214](https://github.com/shaug/compris/issues/214) — `implement-epic` has no
  acceptance-ledger status semantics or entry-per-criterion rule. Defends "one
  evidence entry per criterion" and "`missing`, `fail`, and `pass` answer three
  different questions". Covers 2 lines.
- [#215](https://github.com/shaug/compris/issues/215) — `implement-epic` permits
  acceptance completion for an auto-closed child whose post-merge acceptance is
  missing. Defends "a closed state caused by automation is delivery state, not
  acceptance proof". Covers 1 line.

**Corpus and harness defects** — filed as corpus tickets, not prose tickets, and
none of them is fixed here:

- [#216](https://github.com/shaug/compris/issues/216) — expectations require
  obligations across the delegation boundary. Covers 3 lines.

- [#217](https://github.com/shaug/compris/issues/217) — packets do not disclose
  run phase, so expectations forbid actions they already show happening. Covers
  8 lines.

- [#218](https://github.com/shaug/compris/issues/218) — three action terms carry
  no discriminating information, including the `caller_` rename the naming test
  measured. Covers 3 lines, and improves the answer quality on 3 more.

- [#219](https://github.com/shaug/compris/issues/219) — recover the six
  recall-lost obligations without showing the model an expectation. Filed
  *because* the forced-choice attempt failed: the six are proven answerable and
  still unrecovered, and the reverted experiment narrows the remaining solution
  space to list length. Covers 6 lines.

**No ticket** for the last 4 measurement artifacts. The 2
`caller_verifies_mainline_tracker_cleanup` lines are covered by #218's rename
rather than by any elicitation — a term that names the wrong actor stays wrong
however it is elicited. And `oversized-authorized-carved-stack` and
`mid-stack-material-redesign` are breadth and sampling rather than a defect to
file: both are rejected under recognition, and `mid-stack-material-redesign`
passes in all 9 runs after the baseline.

## Recorded before/after

Both runs are the full 58-case forward corpus at the real-model tier, pinned to
`claude-opus-5`, recorded through `just eval-record`. The only difference
between them is the elicitation.

| Stage    | Summary                               | Candidate  | Passed |
| -------- | ------------------------------------- | ---------- | -----: |
| `before` | `2026-08-13T175223Z-0026-before.json` | `42b52102` |  34/58 |
| `after`  | `2026-08-13T185942Z-0027-after.json`  | `17987612` |  35/58 |

Five cases newly passed and four newly failed. Against the ten prior real-model
runs — 27/54 once, then 30, 31, 31, 32, 33, 34, 34, 34, 34 of 58 — a single case
of net movement is indistinguishable from resampling.

The decisive part is not the total. It is what happened to the six lines the
change existed to fix:

| Line                                           | Before | After    |
| ---------------------------------------------- | ------ | -------- |
| `linear-ticket-github-pr`                      | fail   | fail     |
| `published-feedback-fix`                       | fail   | fail     |
| `infrastructure-retry`                         | fail   | fail     |
| `implement-epic-consumes-ticket-results`       | pass   | pass     |
| `implement-epic-verifies-stacked-child`        | pass   | **fail** |
| `epic-refreshes-after-blocked-merged-delivery` | pass   | **fail** |

None improved and two regressed, each on the exact obligation the probe had
shown the model recognizing on sight. `malformed-babysitter-result` also newly
failed on `forbidden actions: invoke_ready_to_merge` — the over-emission the
probe warned forced choice could invite, arriving on schedule.

So the change was reverted. `claude_executor.py` on this branch is
byte-identical to `42b52102`'s, and the elicitation the corpus runs is
unchanged.

Two notes a later reader will want:

The `before` run was recorded from a detached worktree at `42b52102`, the branch
point, so its candidate is a commit and tree resolvable without this branch. Its
`compared_to` is `null`, which is correct rather than broken: `#207` scopes a
diff to runs matching on tier, suite **and** model, and every real-model run
recorded before `#207` carries no `model` at all. This was the first run of this
corpus with an attributable subject, so it had nothing legitimate to compare
against, and the `after` run is its first real comparator.

The `after` run carries `worktree_clean: false`, and that is a real deviation
from the norm rather than a covered one. The dirty path was this file, edited
between the commit and the run's completion — and `evals/triage/` sits outside
the narrow `evals/results/` exemption `AGENTS.md` grants, so "any other
uncommitted change still makes a run unclean" applies to it.

What the deviation does not cost is retrievability, which is what the clean-tree
rule protects: every input the run actually reads — `SKILL.md`,
`forward_cases.json`, `forward_expectations.json`, and `claude_executor.py` —
was committed and unmodified at `17987612`, whose `sha` and `tree` both resolve.
The run reproduces from that commit. The flag is recorded rather than explained
away, and re-recording it would resample the comparison it is half of.
