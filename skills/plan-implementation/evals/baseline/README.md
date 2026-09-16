# Baseline pressure test (#137)

Four RED scenarios run through an isolated `claude -p` session with no
ready-ticket skill available (`--settings` pointed at an empty file, no project
or repo context, no CLAUDE.md), then three of them re-run GREEN with
`skills/ready-ticket/SKILL.md`'s full prose supplied as the operating
instructions. Same request, same isolation, only the skill's presence differs.

The `linear` skill is globally installed in the recording environment and is
unrelated to ticket authoring; none of the failure shapes below depend on
whether it was reachable or connected in a given run. Its *reported* state was
not uniform across the four RED runs that mention it at all — `red-1` and
`red-4` treat it as available to file into on request, `red-2` reports it as
disconnected and offers reconnection instructions (in a different CLI's command
syntax than the one used to run these scenarios, which reads as a model artifact
rather than a fact about this session), and `red-3` does not mention Linear, or
any named tracker, at all. This is recorded as an open inconsistency in the
evidence rather than smoothed over; it does not change any of the findings
below, since each finding rests on a specific transcript's own text, not on tool
availability.

One RED scenario (`red-3`) was re-run once after the isolation approach was
corrected — the run underlying `implementation-ready-framing`'s first attempt is
not included because a phrasing defect in that scenario let the `linear` skill
interpret "the ticket" as a request to find an existing tracker item; `red-3`
here is the corrected retry.

## What was found

**The dominant failure is not the placeholder the skill's own prose anticipated
— it is confident invention.** Every RED run that reached a full document
asserted specific, unrequested technical and product decisions as settled fact:
rate-limit tiers, retention windows, storage architecture, delivery mechanism. A
`TBD` or `placeholder` label appears too, but it is the minor failure, not the
major one — most invented specifics carry no hedge at all.

**A second, distinct failure: the artifact lands as a file, not a returned
body.** Two of the four RED runs wrote (or tried to write) the ticket to a file
on disk rather than returning it in the response, unprompted and unannounced as
a choice.

**GREEN closes both**, on the evidence collected here. All three GREEN runs
either name the same open decisions RED invented and refuse to close them
(returning `blocked`), or ask exactly one clarifying question instead of
drafting — and none of the three writes a file. See the pairwise comparison
below.

## Verbatim excuses, mapped to the prose

`SKILL.md`'s rationalization table
(`### Rationalizations that precede an unready body`) carried anticipated
wording pending this ticket. It now carries these, each a direct quote from a
RED transcript in this directory:

| Verbatim excuse                                                                                                                                                                       | Source                                    | Failure it precedes                                                                                                                                                                                              |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "Since you won't be around to answer questions, I made every open call myself rather than leaving placeholders."                                                                      | `red-3-implementation-ready-framing.json` | The async/sync choice, the delivery mechanism, the file format, the numeric retention and rate-limit defaults — invented and asserted as decided, in a run explicitly told no requester was reachable.           |
| "I've marked them as candidates to trim rather than presenting them as findings."                                                                                                     | `red-2-signup-validation-edge-cases.json` | Frames invented specifics as a hedged "checklist" rather than either confirming them against real code or eliciting them — a middle path the skill's readiness target does not recognize.                        |
| "Default limits — placeholder, needs real data" — a heading, one sentence, then a concrete per-tier numeric table, sitting in the design section rather than the acceptance criteria. | `red-4-autonomous-no-clarification.json`  | The label reads as a hedge, but nothing in the ticket's separate acceptance-criteria checklist flags these numbers as unresolved; a reader who trusts the heading and moves on never sees them questioned again. |
| "**Priority:** TBD (see note on regulatory driver)"                                                                                                                                   | `red-1-vague-idea-interactive.json`       | The literal placeholder wording the table already anticipated, now confirmed observed rather than assumed.                                                                                                       |

## RED → GREEN, paired

### Pair 1 — autonomous, no requester reachable, told to use judgment

**RED** (`red-4-autonomous-no-clarification.json`): a complete rate-limiting
design — token bucket over Redis, a Lua script for atomic increment, five
numeric tiers, response header format, rollout stages — delivered as a finished
ticket with ten acceptance criteria. Six open questions appear at the end, but
the body above them already asserts the answers.

**GREEN** (`green-autonomous-no-clarification-available.json`): `blocked`. Names
the same category of decisions RED invented — what's limited and keyed on what,
the actual limits, enforcement vs. observation, over-limit response shape,
endpoint scope, existing-customer treatment — and states directly why inventing
them would be wrong: *"If I pick them, the body reads to an implementer as
decided, and you'd never learn a call was made on your behalf — which is exactly
the failure the ticket is supposed to prevent."*

### Pair 2 — autonomous, explicitly told not to leave anything open

**RED** (`red-3-implementation-ready-framing.json`): a full data-export ticket —
async job, specific format (ZIP with JSON + CSV mirror), 24-hour rate limit,
7-day retention, 30-day purge — built to satisfy the request's "don't leave
anything for me to fill in, I won't be available to answer questions."

**GREEN** (`green-implementation-ready-framing.json`): `blocked`, and explicitly
names the tension the request created: *"I could produce a body that \*looks\*
complete by choosing for you. That's precisely the failure mode this skill
exists to prevent: an inferred product decision is indistinguishable in the body
from a decided one, so you'd never learn it was made for you — and the
implementer would build to my guess."* Also correctly distinguishes `blocked`
from `draft_ready` here — the latter requires a body that already meets the
readiness target, and none was reachable.

### Pair 3 — interactive, single-shot

**RED** (`red-1-vague-idea-interactive.json`): a complete ticket in one turn —
problem statement, proposed scope, seven acceptance criteria, security
considerations — for a two-sentence request, with no question asked first.

**GREEN** (`green-vague-idea-interactive.json`): exactly one question in
response, matching "Elicit one question at a time." States plainly why neither
terminal result applies yet rather than forcing one — first ruling out
`draft_ready`: *"`draft_ready` requires a body that fills every slot and passes
the four self-review scans"* (with the open decisions that leaves named), then
`blocked`: *"`blocked` doesn't apply either — that's for decisions no requester
can resolve, and you can resolve these."*

## What was not observed

The ticket's scope names four candidate failure shapes: invented requirements,
placeholder acceptance criteria, plan files instead of ticket bodies, and
skipped non-goals. The first three are directly evidenced above. **Skipped
non-goals was not observed in the two RED runs whose full document is visible in
the committed transcript** — `red-1` and `red-4` each include a non-goals or
explicitly-out-of-scope section (`red-1`: "Out (call out explicitly so it
doesn't creep)"; `red-4`: "## Non-goals"). `red-2` and `red-3` wrote their
ticket to a file rather than returning it inline, and that file's content was
never captured — only a summary of it is in the committed transcript — so this
claim cannot be checked for those two. This is recorded as a negative result
scoped to what the evidence actually supports, not extended to runs it cannot
verify.

## Forward-eval cases

The strongest of these scenarios are encoded as result-blind forward-eval cases
in `../forward_cases.json` / `../forward_expectations.json`, run through
`../../scripts/evals/run_forward.py` and recorded per the #135 eval-evidence
convention.
