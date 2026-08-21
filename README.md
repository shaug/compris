# compris

*For when the planning is done, and the work begins.*

Agent skills that take one ticket and return a merged pull request.
`implement-ticket` resolves the ticket's live context, implements the change in
an isolated worktree, reviews the candidate through the repository's own review
suite, publishes a pull request, and delegates its lifecycle to `babysit-pr`,
which watches CI and re-reviews after every head change. `implement-epic`
traverses a live epic graph and drives the same path for each ready child.

`compris` is French for *understood* — what the suite claims at the moment work
changes hands.

**Why it exists.** Not to write code faster. Agents already generate correct
code faster than any human forms a theory of what it does, and the cost of that
shows up as **cognitive debt** — understanding that lives in developers' minds
rather than in the code, and fragments. It is not technical debt under another
name: technical debt is a property of the artifact, and cognitive debt is a
property of the people, which is why editing code cannot pay it down. When
agents are the primary vector of implementation, that debt is what accrues if
nobody intervenes. So throughput is the wrong headline number here. Every
constraint in this suite — work shaped to what a reviewer can hold, tickets
rather than local plan files, recorded rationale rather than a bare diff —
exists to keep the theory of the program in human minds while agents write the
code. [docs/cognitive-debt.md](docs/cognitive-debt.md) is the full statement,
including what the suite does not claim.

**Where it starts.** Not at the idea. Peer methodology libraries own the
thinking-it-through phase, and `ready-ticket` stops at an implementation-ready
ticket body without crossing into implementation. Compris begins once the ticket
is a contract.

**What holds it together.** Every candidate is reviewed before publication by
independent lenses — correctness, whole-solution simplicity, and local
implementation simplicity — reconciled into one verdict against a typed schema
its caller can validate. They fail closed: a review that cannot bind its
evidence to the candidate says so rather than returning a clean verdict it did
not earn.

**Where it composes.** `compris` is the outer-loop companion to peer methodology
libraries such as [superpowers](https://github.com/obra/superpowers): it owns
ticket readiness, review production, and the post-publication pull-request
lifecycle, while peers own in-phase methodology — how to brainstorm, how to run
a red–green loop, how to debug a failure hypothesis-first. Install both for the
complete cycle from idea to merged pull request; `compris` is fully functional
without a peer installed. See
[Using beside peer skills](#using-beside-peer-skills) for the full division of
labor and composition rules.

## Installation

Install the plugin when you need any composed workflow. It packages every skill
together so stable-name dependencies such as `implement-ticket`,
`review-code-change`, and `babysit-pr` are available in the same fresh session.

### Claude Code

Add the repository marketplace, install the plugin, and start a fresh session:

```text
/plugin marketplace add shaug/compris
/plugin install compris@shaug
```

The equivalent non-interactive commands are:

```bash
claude plugin marketplace add shaug/compris
claude plugin install compris@shaug
```

### Codex

Codex CLI 0.117 or newer can add the repository marketplace and install the same
plugin:

```bash
codex plugin marketplace add shaug/compris
codex plugin add compris@shaug
```

The repository marketplace also appears in the Codex plugin browser. Start a
fresh Codex task after installation so the complete skill set is loaded.

### Individual skills

Standalone-capable skills can still be installed independently:

```bash
npx skills add shaug/compris
```

Codex users can also invoke `$skill-installer` with this repository. Prefer the
plugin for `implement-epic`, `implement-ticket`, `babysit-pr`,
`review-code-change`, or `carve-changesets`: installing one of those entrypoints
alone intentionally leaves required stable-name dependencies unavailable and
causes the workflow to fail closed.

## Repository Layout

- `skills/` — skill folders, each containing a `SKILL.md` and bundled resources
- `review-suite/` — canonical code-review contracts, validators, raw evaluation
  fixtures, and the result-blind replay evaluator shared by repository-owned
  review skills
- `justfile` — common tasks for testing, validation, and formatting

The skills:

- `skills/ready-ticket` — turn a vague idea or an unready GitHub or Linear
  ticket into an implementation-ready ticket body: validate the approved design,
  elicit the tracker-shaped residue, write acceptance criteria as observable
  public-surface behaviors, self-review the draft, and terminate in the body
  itself. Work exceeding one reviewable changeset comes back as a draft
  parent/child graph with a ready body per leaf, proposed and never created —
  unless one endpoint-scoped grant authorizes creating that exact graph and its
  native relationships in the owning tracker, GitHub or Linear, verified by
  readback before success. Fully standalone; it borrows
  `superpowers:brainstorming`'s questioning discipline and
  `superpowers:writing-plans`' breakdown method, and recommends `load-bearing`
  verification, only when those peers are present
- `skills/babysit-pr` — monitor one existing GitHub pull request through
  current-head CI, feedback, repository-owned re-review, mergeability, and an
  explicitly authorized completion policy
- `skills/implement-ticket` — implement exactly one standalone ticket or named
  epic child through isolated execution and initial repository-owned review,
  publish it once — inline, through an optional repository-owned
  `publish-candidate`, or as an explicitly authorized carved stack through
  `carve-changesets` — hand every published PR to `babysit-pr`, then verify
  tracker, mainline, and cleanup outcomes; this is the canonical owner of
  generic single-ticket execution rules consumed by `implement-epic`
- `skills/implement-epic` — traverse live GitHub or Linear epic graphs and
  delegate each selected child to `implement-ticket`, then refresh graph state
  and verify separately authorized epic closeout
- `skills/carve-changesets` — recompose a review-ready source branch into a
  stateless chain, delegate each changeset's review and fix loop to
  `review-fix-loop`, and delegate each published PR lifecycle to `babysit-pr`
- `skills/review-code-change` — orchestrate the repository-owned review lenses
  into one evidence-bound, deduplicated verdict
- `skills/review-correctness` — find material behavioral, security,
  compatibility, data-integrity, and validation failures in a code change
- `skills/review-solution-simplicity` — challenge whole-solution machinery that
  is not justified by real requirements or repository constraints
- `skills/review-code-simplicity` — reduce local cognitive load through
  behavior-preserving reuse, DRY, control-flow, and test simplification
- `skills/review-fix-loop` — take cooperative ownership of an existing committed
  candidate, run the complete repository review suite in a fresh read-only
  subagent by default, apply ticket-scoped fixes in isolated attempt worktrees,
  and repeat until review converges or a bounded stop condition is reached;
  supports a `local_commit` policy (every fix stays local — the operator
  publishes them separately) and an `update_pr` policy (one expected-old,
  fast-forward-only Git push immediately after convergence). `implement-ticket`
  delegates its initial candidate's review and fix loop to it under
  `local_commit`; `babysit-pr` delegates its post-publication review and fix
  loop to it under `update_pr`; `carve-changesets` delegates each changeset's
  local review and fix loop to it under `local_commit`, one invocation per
  changeset in chain order.

The composed implementation dependency chain is:

```text
implement-epic
└── implement-ticket
    ├── review-fix-loop             # initial candidate review/fix/converge loop
    │   └── review-code-change      # each review pass inside the loop
    ├── publish-candidate           # optional repository-owned publication
    ├── babysit-pr                  # ordinary lifecycle, one per published PR
    │   └── review-fix-loop         # after a head-changing fix (update_pr)
    │       └── review-code-change  # each review pass inside the loop
    ├── carve-changesets            # authority-gated oversized path
    │   ├── review-fix-loop         # each changeset's review/fix/converge loop
    │   │   └── review-code-change  # each review pass inside the loop
    │   └── babysit-pr              # each changeset PR lifecycle
    │       └── review-fix-loop     # after a head-changing fix (update_pr)
    │           └── review-code-change
    ┊
    ┈▷ ready-ticket                 # recommendation only, never invoked

carve-changesets
├── review-fix-loop                 # each changeset's review/fix/converge loop
│   └── review-code-change          # each review pass inside the loop
└── babysit-pr                      # each published PR lifecycle
    └── review-fix-loop             # after a head-changing fix (update_pr)
        └── review-code-change      # each review pass inside the loop
```

Solid edges are invocation. The single dashed edge is a recommendation:
`implement-ticket` names `ready-ticket` in a not-ready `blocked` result,
carrying the marker
`implement-ticket:requires-ready-ticket:<tracker>:<ticket-id>`, and the caller
decides whether to run it. Nothing invokes `ready-ticket` automatically, and
`ready-ticket` never invokes `implement-ticket`, so the recommendation cannot
close a cycle.

Compatible runtimes may provide named subagents or equivalent isolated
implementation and review contexts. Files under each skill's `agents/` directory
(`openai.yaml` for OpenAI runtimes, `claude-code.md` for Claude Code) are
optional discovery and adapter metadata, not part of the skills' portable
contracts.

Each review skill bundles a verbatim copy of the canonical `review-suite`
contract and schemas under its own `references/review-suite/` directory so the
skill remains self-contained when installed elsewhere. Edit only the canonical
files and refresh the copies with:

```bash
just sync-contracts
```

That recipe refreshes only the copies bundled inside this repository. Skills
installed elsewhere — under `~/.agents/skills`, a plugin directory, or any other
distribution — are snapshots taken at install time, and they keep running the
prose and contracts they shipped with until they are re-installed. The failure
is silent by construction: a stale review skill validates its own result against
the stale schema it bundles, so every part of the snapshot agrees with every
other part and a weakened review still reports a verdict. Compare an installed
distribution against this repository with:

```bash
just check-installed
```

It exits non-zero when an installed copy has drifted and names the differing
files. Because the failure it detects is a silent success, it refuses to succeed
silently itself: comparing nothing, being pointed at a directory that does not
exist, and failing to read part of a tree are all reported rather than passed
over. Only the built-in default location may be absent — that is the continuous
integration case, and it is the one case that exits zero with a note. A root
named explicitly through `--skills-root` or `$AGENTS_SKILLS_DIR` is an assertion
that it exists, so a typo is an error rather than a check that can never fail.

An installed copy is matched by the name its `SKILL.md` declares as well as by
its directory name, since the declared name is what a runtime loads: a stale
copy left under `review-correctness-old` is still a live review skill, and is
reported as drift rather than passed over as an unrelated directory. Either
match is enough, so a frontmatter this check reads wrongly cannot hide a copy
the plain directory name would have found. Runtime byproducts and the eval
summaries `just eval-record` appends are excluded, because neither changes what
an installed skill does. The comparison is against the working tree, so update
the checkout first if it may be behind.

## Using beside peer skills

These skills are designed to sit alongside peer methodology libraries —
[superpowers](https://github.com/obra/superpowers) and
[load-bearing](https://github.com/danshapiro/skill-load-bearing) — and to work
identically without them.

**Division of labor.** Peers own in-phase methodology: how to brainstorm, how to
run a red–green loop, how to debug a failure hypothesis-first. This repository
owns the outer loop: ticket readiness, authority grades, evidence contracts,
review production, and the post-publication pull-request lifecycle.

**Awareness mechanism.** A skill names a peer in prose, conditioned on that peer
appearing in the session skill listing. There is no install probe, no manifest
read, no package-manager call, and no dependency declaration. A missing peer is
a silent fallback to built-in behavior — never a `blocked` condition and never a
caveat on a result.

**The guarantee.** Nothing here degrades when a peer is absent. Peers supply
method; every quality outcome stays enforced by this repository's own validation
and review gates. Installing a peer should change how a phase is carried out,
never whether a contract is met.

### Composition rules

These resolve collisions that arise from co-installation. They are rules, not
preferences, because a collision left unresolved is settled differently on each
run — usually by whichever text was read most recently.

**1. A ticket satisfies brainstorming's design-approval gate because
brainstorming already ran.** `ready-ticket` consumes an approved design rather
than producing one: it validates the design, narrows its own elicitation to the
tracker-shaped residue a design cannot answer, and returns
`requires_brainstorming` naming the gap when a design-owned decision is missing.
Brainstorming applies *before* a ticket exists, never mid-pipeline. *Why:*
re-opening design questions against an approved contract reverses a decision the
requester already made, and it does so invisibly, because the reopened
discussion looks like diligence.

**2. Exactly one executor owns a unit of work.** Ticket-driven work stays in
`implement-ticket` regardless of peer plan headers. `writing-plans` stamps its
plans with an executor mandate naming its own sub-skills; that mandate does not
bind work driven by a tracker ticket. *Why:* two executors on one unit produce
two candidates for one ticket, and neither can be verified as the canonical one.

**3. Review production is house-owned inside the pipeline.** The review suite's
typed schemas, fail-closed evidence binding, and candidate-identity rules are
what make a verdict checkable by its caller. `requesting-code-review` applies
outside the pipeline, not within it. *Why:* a review whose result shape a caller
cannot validate is indistinguishable from no review, and the failure is silent.

**4. Only the pull-request option composes at the merge boundary.**
`finishing-a-development-branch` offers three integration options — merge
locally, push and create a pull request, or keep the branch. For tracked work,
only the pull-request option composes. The local-merge option bypasses the
review contracts, `babysit-pr`, and the tracker transition, and is out of
bounds. `babysit-pr` begins at an existing pull request; peer plan and spec
files are orientation only, while live pull-request and tracker state are
execution state. *Why:* a local merge produces delivery with no reviewed
candidate, no remote gate, and no tracker record — the three things the
post-publication lifecycle exists to establish.

**5. Known overlaps are documented, not dodged.** Some peers carry trigger
descriptions broad enough to cover any implementation work, and no edit to this
repository can fully resolve that from one side. Those overlaps are recorded in
the named-peer registry's trigger-collision audit in
[`docs/skill-authoring.md`](docs/skill-authoring.md) with their dispositions,
rather than worked around by contorting a description. *Why:* description-based
routing is winner-takes-attention, and a contorted description misroutes the
requests the skill was built for while still losing the contested ones.
[Issue #136](https://github.com/shaug/compris/issues/136) landed the
description-tier corpus that empirically exercises the audit's dispositions: 35
result-blind cases covering every skill in the suite at the time, five
repetitions each, majority wins. Its one recorded candidate overlap did not
reproduce on retest — see `triggering/known-overlaps.json` for the observation
and its refutation. Two tiers of that corpus remain unmeasured and are recorded
as gaps rather than claimed: the headless tier, whose ability to observe which
skill actually loaded is itself unverified, and the peer-installed composition
cases in `triggering/composition-cases.json`, which need a harness that does not
exist yet.

### Seam table

Where the two libraries meet, and what each seam does. Update this table as
seams land.

| Seam                                   | Peer                                         | What composes                                                                                                                                                                                                                  | Ticket                                              | Status  |
| -------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------- | ------- |
| Ticket authoring                       | `superpowers:brainstorming`                  | `ready-ticket` borrows the questioning discipline — one question at a time, intent before construction — and stops at design approval; it never creates a spec or plan file                                                    | [#124](https://github.com/shaug/compris/issues/124) | Landed  |
| Authoring-time assumption verification | `load-bearing`                               | Offered once in an interactive `ready-ticket` run when the drafted body rests on costly-to-falsify assumptions; the recommendation is recorded and passed over in an autonomous one                                            | [#124](https://github.com/shaug/compris/issues/124) | Landed  |
| Implementation breakdown               | `superpowers:writing-plans`                  | `ready-ticket` derives the file map, task boundaries, and sequencing itself and borrows the peer as the recommended method; the plan is scratch input, never a file, and its unit-level detail is lifted to the public surface | [#198](https://github.com/shaug/compris/issues/198) | Landed  |
| Not-ready routing                      | —                                            | `implement-ticket`'s not-ready `blocked` result names `ready-ticket` as the remediation path; a recommendation, never a dispatch                                                                                               | [#125](https://github.com/shaug/compris/issues/125) | Landed  |
| Pre-implementation verification        | `load-bearing`                               | Offered once in an interactive run when the ticket rests on costly-to-falsify assumptions; recorded and passed over in an autonomous one. Skips assumptions already verified at authoring time                                 | [#126](https://github.com/shaug/compris/issues/126) | Landed  |
| Implementation method                  | `superpowers:test-driven-development`        | Supplies the method for producing the house's change-demonstrating-test evidence; the evidence contract and its exemptions govern                                                                                              | [#126](https://github.com/shaug/compris/issues/126) | Landed  |
| Finding and feedback consumption       | `superpowers:receiving-code-review`          | Ported with attribution into `review-suite/consumption-disciplines.md`, bundled into the three skills that consume findings                                                                                                    | [#127](https://github.com/shaug/compris/issues/127) | Landed  |
| CI diagnosis                           | `superpowers:systematic-debugging`           | Recommended in `babysit-pr`'s CI-diagnosis loop after repeated failed fixes; its architecture escalation maps to the skill's blocked-with-evidence terminal                                                                    | [#127](https://github.com/shaug/compris/issues/127) | Landed  |
| Merge boundary                         | `superpowers:finishing-a-development-branch` | House territory. Composition rule 4 above records which of its three options composes                                                                                                                                          | [#128](https://github.com/shaug/compris/issues/128) | Landed  |
| Worktree isolation                     | `superpowers:using-git-worktrees`            | The isolated-workspace pattern, ported into `implement-ticket`'s one-ticket-one-worktree rule                                                                                                                                  | [#134](https://github.com/shaug/compris/issues/134) | Planned |
| Parallel dispatch                      | `superpowers:dispatching-parallel-agents`    | The post-parallel verification habit is ported; the dispatch mechanics are not                                                                                                                                                 | [#131](https://github.com/shaug/compris/issues/131) | Landed  |

The registry in [`docs/skill-authoring.md`](docs/skill-authoring.md) classifies
every peer skill into one of four forms — referenced peer, ported with
attribution, house territory, or no relationship — and is the authority when
this summary and the registry disagree.

## Quick Start

Run the core checks:

```bash
just check
```

Run skill-specific tests:

```bash
just test-carve-changesets
just test-review-suite
just test-babysit-pr
just test-ready-ticket
just test-implement-ticket
just test-implement-epic
just test-review-fix-loop
just eval-implement-ticket
just eval-implement-epic
just eval-review-fix-loop
```

Validate a review packet and result together:

```bash
python3 review-suite/scripts/validate.py pair packet.json result.json
```

Run deterministic local evaluation harnesses without an agent runtime:

```bash
just eval-carve-changesets
just eval-implement-ticket
just eval-implement-epic
just eval-review-fix-loop
```

The carve-changesets command first runs its objective integration self-test,
which checks clean-tree, plan, immutable-source, chain, equivalence, and
validation invariants. It then runs peer-shaped judgment cases through a fresh
process for each result-blind packet. The bundled executor is a deterministic
simulation of a compliant runtime, not a model evaluation. Pass any compatible
stdin/stdout JSON adapter with:

```bash
just eval-carve-changesets-executor "python3 /path/to/adapter.py"
```

The ticket-composition evaluator starts a fresh process for each case, with
fixture identity and grader expectations withheld. Its shared corpus targets
both `implement-ticket` and `implement-epic`; `just eval-implement-epic` filters
the same validated corpus to epic packets. Case artifacts carry raw, live-shaped
workflow state, including criterion-specific acceptance evidence bound to the
candidate or deployed SHA. The harness grades obligation mapping and
terminal-state selection. Its bundled reference executor is a deterministic
simulation of a compliant runtime, not a model. To forward-evaluate a real agent
runtime, pass its stdin/stdout JSON adapter through
`scripts/evals/run_forward.py --executor` and retain captured observations with
`--output-dir`. A Claude Code headless adapter is bundled:

```bash
just eval-implement-ticket-claude
```

`just eval-review-fix-loop` drives `review-fix-loop`'s own cross-cutting,
result-blind corpus: twenty scenarios that run the real `local_commit`/
`update_pr` engine against disposable Git repositories with scripted
reviewer/decide/apply_fix fixtures (no subprocess boundary, no model call, no
network) and grade the result against independently derived Git evidence. See
[its README](skills/review-fix-loop/evals/README.md) for the corpus contract.

### Result-blind review replay evaluation

`review-suite/evals/` is the canonical evaluator that measures what the review
skills actually do when a real agent runtime executes them repeatedly, rather
than asserting quality through expected JSON. It changes no review behaviour.
See [its README](review-suite/evals/README.md) for the protocol, the corpus
contract, and the grading interface.

Three commands cover it:

```bash
just test-review-suite                      # deterministic tests, no runtime
just audit-review-corpus                    # corpus integrity, no runtime
just eval-review-suite '<executor command>' # the only one that may cost money
```

`just test` includes the deterministic evaluator tests and never launches a paid
runtime. `just eval-review-suite` is deliberately absent from `test`, `lint`,
and `check`. The bundled real-runtime adapter needs the `claude` CLI on `PATH`:

```bash
just eval-review-suite "python3 review-suite/scripts/evals/claude_executor.py"
```

Each attempt starts a fresh process and receives one result-blind JSON request:
the target skill text, the raw review packet, the review contracts, and public
run identity. Expected findings, private grader labels, provenance, and even the
case name stay out of the payload, and `just audit-review-corpus` proves it by
inspecting the complete payload every case would produce. Spawn, timeout,
runtime, oversized-output, malformed, and protocol failures are reported
separately from a valid review and are never scored as clean.

The bundled `fixture_executor.py` is a deterministic simulation of a compliant
reviewer, not a model. Its runs are marked `simulation`, so no baseline report
can be produced from them. Run the runner directly for repeated attempts,
per-attempt records, and the aggregate report:

```bash
python3 review-suite/scripts/evals/runner.py \
  --executor "python3 review-suite/scripts/evals/claude_executor.py" \
  --runs 5 --report-out out/report.json
```

Cases are grouped into **strata** under `review-suite/evals/strata/`. A stratum
is the unit of valid comparison — same target skill, same declared dependency
closure, same runtime and model, same kind of ground truth — and each directory
is a complete corpus declaring its own target. `just audit-review-corpus`
discovers every one of them.

The frozen v1 baseline record lives in `review-suite/evals/baseline/v1/`: the
immutable configuration, the unscored pilot's per-stratum cost and latency
envelope, a per-stratum cost-ceiling proposal built from those numbers, the
grader calibration and adjudication record, a plan for satisfying the
two-independent-adjudication gate, the ground-truth sourcing and sanitization
record, and the baseline limitations.

Two things are deliberately still outstanding, and the configuration record says
so rather than implying otherwise: the scored strata are declared but not
populated, and no scored run may launch until the repository owner preregisters
a per-stratum cost ceiling and each private expectation has two independent
adjudications. Read
[the limitations record](review-suite/evals/baseline/v1/LIMITATIONS.md) before
quoting any figure — in particular, **the connector stratum is deferred, not
satisfied**, so connector-escape recall has never been measured and no
human-review figure may be reported as a connector figure.

The v2 scored closeout lives in `review-suite/evals/v2/`: the preregistered gate
manifest and decision record from `#59`, and `#57`'s own scored ablation
comparison — three independently-measured `s1-correctness-orchestrator`
configurations (each required pass isolated, then both together) plus the
reused, non-regressed `s2`/`s3` figures, each checked against the settled
per-case gate. It reports what clean proves, what it does not prove (in
particular, whether a passing numeric gate demonstrates a mechanism's own unique
causal contribution — it does not, on the evidence recorded there), and a
recommendation, not a removal decision, per mechanism. See
[its README](review-suite/evals/v2/README.md) for the full document set.

Following that evidence, the repository owner removed the verification-
sufficiency pass (`#93`): neither `#57`'s ablation matrix nor `#89`'s harder-
case validation (`discriminating-case-validation.md`) found demonstrated value
for it, and it carried a confirmed, twice-reproduced false-positive regression
on `session-continuation-summary` when run without the traversal pass. The
traversal (consumer/impact) pass and `consumer_impact_evidence` were unaffected
— that pass showed a real, reproducible gap in the same validation. The shared
review-result contract advanced `1.3 → 1.4` to drop
`verification_sufficiency_evidence`; see
[`review-suite/evals/v2/VERIFICATION-SUFFICIENCY-REMOVAL.md`](review-suite/evals/v2/VERIFICATION-SUFFICIENCY-REMOVAL.md)
for the full decision record.

### Connector-outcome curation and promotion

`review-suite/evals/curation/` turns a newly adjudicated connector finding into
a versioned curation record, and turns a group of curation records into a
conservative, evidence-backed promotion decision: a corpus case only, a global
rubric change, a repository-instruction change, or nothing. It is infrastructure
only, proven with synthetic fixtures, and never touches `baseline/v1/` or `v2/`.
See [its README](review-suite/evals/curation/README.md) for the disposition
vocabulary, the mechanical disclosure guardrail that fails closed on a leaked
source identifier, and the promotion rules.

```bash
just audit-review-curation  # curation and promotion-decision integrity, no runtime
```

## Prerequisites

- Python 3.11+
- Git
- GitHub CLI (`gh`) 2.37 or newer for PR workflows (the babysit-pr watcher
  requires `gh pr checks --json`)
- `skills-ref` on `PATH` for skill validation (optional but recommended)

## Notes

Each skill should be runnable and testable in isolation. Prefer adding tests
under the skill’s own `scripts/tests/` directory and wire them into the
`justfile`.
