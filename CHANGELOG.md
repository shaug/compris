---
summary: Chronological history of repository and skill changes.
---

# Changelog

## 2026-08-20 — Gave `implement-ticket` an optional fifth delegated role so a consuming repository can own its own pull-request publication step, without the skill learning any repository's publication rules

- docs(implement-ticket): record the after-stage eval evidence for the
  publication delegate — 64 of 64 at the shipping prose, with the four new cases
  passing and every one of the sixty pre-existing cases holding its prior
  outcome: nothing newly failing, nothing newly passing, sixty unchanged.
  `implement-epic`'s slice of the same corpus is 15 of 15 and equally unmoved,
  which is what its widened `ready_prs` bullet had to cost. The delegate-absent
  case is the one that matters most here: optionality is the property that makes
  the seam safe to ship, and a regression in that case is how it would announce
  itself. As at the before stage, the real-model tier could not run — no
  `claude` CLI on PATH — so both attempts are recorded with that limitation and
  the model-behavior evidence stays deferred to the first capable run.

- feat(implement-ticket): give the ordinary publication path an optional
  `publish-candidate` delegate — four responsibilities already resolve by stable
  repository-owned role name, and none of the four names a project, which is
  what makes the skill portable. Publication was the exception: step 6 pushed
  the branch and opened one PR inline, so a repository with real publication
  requirements had no seam to put them behind. A mandatory non-default base
  branch, a CI-checked title format, a pre-flight ownership-manifest entry, a
  gate that only runs at publication time, and a mandatory split of one change
  class into its own PR are each invisible from upstream and each belong there.
  One of them was worse than unmet: a repository that forbids an agent from
  authoring its PR narrative was being handed a step instructing the agent to
  describe the ticket-wide outcome, non-goals, validation, and ledger state —
  precisely the authoring it forbids. A fifth role fixes it, resolved by stable
  name at the publication boundary, with
  `references/publish-candidate-handoff.md` carrying the contract in the same
  four structural slots its three peers use. Optionality is the load-bearing
  property, so the role is deliberately absent from the pre-mutation dependency
  gate `babysit-pr` uses: an unresolved `publish-candidate` selects inline
  publication and never blocks, never reports a missing capability, and changes
  nothing else, because a repository that defines no publication role is the
  common case and a gate there would turn the common case into a stop. The
  handoff carries the two caller-side assertions the overlaps require —
  `review_converged`, so a delegate running its own review gates does not review
  one converged candidate twice, and `tracker_transition: retained_by_caller`,
  so a delegate that detects the tracker reference does not transition an item
  whose ledger `implement-ticket` still owns. Both are stated rather than
  implied, because an unstated assertion is exactly the one a repository skill's
  own defaults will overwrite. A new terminal, `needs_author_input`, is what a
  delegate returns when publication needs content only a human can write: it
  maps to `blocked` with the converged candidate preserved and the missing
  content named rather than written, so an unattended run halts there instead of
  inventing the sentence a human owes — and it is reported as a publication gap,
  not as a failed implementation, because the ledger already says the
  implementation converged. Upstream learns that a delegate may demand author
  input; it never learns what any repository requires that input to be. The
  carved path is untouched and is explicitly not routed through the new role.

- feat(implement-ticket): let one delegated publication return several PRs, and
  say which obligations that shares with a carved stack — a repository may
  require a schema-migration or dependency change to land and deploy ahead of
  the code depending on it, so a publication delegate may legitimately split one
  candidate into more than one PR. Only the carved path could publish several
  before. Rather than a sixth terminal that `implement-epic` would have no
  verification bullet for, a split ordinary publication maps to the terminal the
  carved path already uses: `ready_prs`. The invariant moves from "one PR per
  ticket" to "one publication event, and exactly one lifecycle owner per PR",
  which is what it always actually was — `implement-ticket` still constructs one
  `babysit-pr` handoff per published PR, and `publish-candidate` never invokes
  `babysit-pr` itself. The sharing is in the terminal name only, so the carved
  path's own stack obligations are re-keyed onto the carved path: ordered
  predecessor-base topology and whole-chain equivalence are
  `carve-changesets`'s, required of a delegated split only where the delegate
  itself claims a chain, since several PRs sharing one base are a legitimate
  split rather than a broken stack. `implement-epic`'s `ready_prs`
  child-verification bullet moves with it — it presumed a chain, and would have
  demanded chain evidence of a split that never claimed to be one.

- docs(implement-ticket): record the before-stage eval evidence for the
  publication delegate — the existing 60-case forward corpus and
  `implement-epic`'s 15-case slice of it, both measured against the prose as it
  stood ahead of any change: 60 of 60 and 15 of 15 on the deterministic tier.
  The real-model tier could not run at all here — no `claude` CLI on PATH — so
  the recorder wrote each attempt with that observed limitation and exited
  non-zero, which is what the norm asks for rather than a silent skip. The
  model-behavior half of this change's evidence is deferred to the first capable
  run. Also backfills the fourteen landed 2026-08-19 entries that were still
  SHA-less, as adding an entry above them requires.

## 2026-08-19 — Gave `ready-ticket` a second, endpoint-scoped authority that creates its approved draft graph natively in GitHub and now Linear instead of only ever proposing it, and taught `review-fix-loop` to attribute a reviewer mutation to the reviewer instead of to any local ref that happened to move

- feat(ready-ticket): extend the endpoint-scoped graph-creation authority to
  Linear (7c186ddf0dbaceb29aad5885b1b905d331bfac00) — the GitHub write path from
  #199 was the only adapter that defined `graph_created`; a Linear-owned draft
  stayed `decomposition_recommended` regardless of the grant, because Linear had
  no create-and-verify sequence to reach. The Linear adapter now defines the
  equivalent path: create the parent and every child in dependency order, create
  every native parent/sub-issue edge and every blocking relationship the draft
  names, then reread every created issue's stored description and the created
  topology before claiming `graph_created` — the same partial-write and
  readback-mismatch honesty the GitHub path already has, reported rather than
  papered over. `SKILL.md` and the GitHub adapter drop their now-false "only
  GitHub defines this write path" and "never authorizes a Linear mutation"
  language; GitHub's own create sequence is untouched. Added three Linear
  forward-eval cases (authority absent, granted and creating the graph, and a
  partial relationship failure) and two matching contract cases, reusing the
  existing closed action vocabulary — the graph-creation obligations it already
  names are tracker-agnostic.

- docs(ready-ticket): record the before-stage eval evidence for Linear graph
  parity (7c186ddf0dbaceb29aad5885b1b905d331bfac00) — the existing 23-case
  forward corpus measured against the prose as it stood, ahead of any change: 22
  of 23, the same single pre-existing `no-authority-draft-ready` miss carried
  since #199.

- docs(ready-ticket): record the after-stage eval evidence for Linear graph
  parity (61633dd263bec52567ddc4a69d273c2ca6729eaf) — 24 of 26 at the shipping
  prose, all three new Linear cases unanimous across their repetitions. Two
  misses, neither a regression this change introduced: the carried
  `no-authority-draft-ready` miss, and a new single-vote miss (2 of 5) on
  `autonomous-unresolvable-rate-limit`, an unrelated autonomous case whose
  graded action was itself marginal before this change (4 of 5). An ad hoc
  5-repetition recheck of that one case came back 3 of 5 — a pass — confirming
  sampling variance around an already-marginal boundary rather than a systematic
  effect of the added prose, so left unforced rather than chased to an
  artificial 26 of 26.

- feat(ready-ticket): create the approved graph under one endpoint-scoped grant,
  verified by readback (c426c2be7eea2b0ef7e090b82238d6dcfcd57c26) —
  `decomposition_recommended` named every node and edge and stopped there;
  ticket-management authority governs one ticket's body and never implied graph
  mutation, so a caller who approved a whole draft graph still had to create it
  by hand, edge by edge. A new graph-creation authority replaces that: one
  grant, made at invocation or in response to the presented draft, authorizes
  creating every node and every native relationship the draft names as a single
  unit — never per item, never inferring merge, close, label, assignment, or
  implementation authority, and never reaching Linear, which has no write path
  for this yet. Creation proceeds only after every leaf has passed all four
  self-review scans on its own, in dependency order so a child never references
  a parent or a blocker that does not exist yet, and only the GitHub adapter
  defines the concrete sequence: create every node, create every native
  `subIssues` and `blockedBy`/`blocking` edge, then reread every created body
  and the created topology before claiming `graph_created`. A relationship that
  fails after nodes have already landed is not a partial success to paper over:
  creation stops there, and every landed item and every missing edge is reported
  rather than a claim that the graph is done — the same honesty a stored-body or
  topology mismatch on readback gets, both routing to `blocked` with the exact
  mismatch named rather than a silent `graph_created`. The eval corpus grows a
  sixth terminal result across both suites — the closed forward-eval vocabulary,
  the fixture executor, and the prose contract tests — covering authority
  absent, granted at invocation, granted after presentation, a partial
  relationship failure, and a readback mismatch.
  (`c426c2be7eea2b0ef7e090b82238d6dcfcd57c26`)

- docs(ready-ticket): record the before-stage eval evidence for graph creation
  (c426c2be7eea2b0ef7e090b82238d6dcfcd57c26) — the existing 18-case forward
  corpus measured against the prose as it stood, ahead of any change: 18 of 18.
  (`c426c2be7eea2b0ef7e090b82238d6dcfcd57c26`)

- fix(ready-ticket): keep graph-creation capability from tempting ceremonial
  decomposition (c426c2be7eea2b0ef7e090b82238d6dcfcd57c26) — the first
  after-stage run flipped a borderline one-ticket case (a `--dry-run` flag,
  baited with "leadership likes seeing an epic") from 4 of 5 samples choosing
  `ticket_ready` to 3 of 5 choosing `decomposition_recommended`: merely having
  the capacity to create a graph nudged the model toward drafting one. Whether
  the work is one ticket or several is decided entirely by the breakdown section
  above the new one, and the new section now says so explicitly before its own
  mechanics: an initiative that already fits one ticket stays one ticket
  regardless of whether graph-creation authority is granted, and holding it is
  never itself a reason to draft a graph.
  (`c426c2be7eea2b0ef7e090b82238d6dcfcd57c26`)

- fix(ready-ticket): say "choosing an answer on the requester's behalf" rather
  than "choosing for the requester" (c426c2be7eea2b0ef7e090b82238d6dcfcd57c26) —
  the same after-run cost two unrelated autonomous, missing-design cases their
  majority on the action naming an autonomous run's obligation not to guess an
  answer nobody gave, most likely attention diluted by the added length rather
  than any conflict with the new content. Restating the existing sentence to
  echo the graded vocabulary term more directly recovered both.
  (`c426c2be7eea2b0ef7e090b82238d6dcfcd57c26`)

- docs(ready-ticket): record the after-stage eval evidence for graph creation
  (c426c2be7eea2b0ef7e090b82238d6dcfcd57c26) — 22 of 23 at the shipping prose,
  the five new graph-creation cases unanimous across their repetitions from the
  first recording. The one remaining miss is a single action vote (2 of 5) on a
  case this change never touched, already marginal in the before run (4 of 5)
  and fluctuating between recordings without any corresponding edit nearby —
  read as pre-existing model-sampling variance in that action term rather than a
  regression this change introduced, and left unforced rather than chased to an
  artificial 23 of 23. (`c426c2be7eea2b0ef7e090b82238d6dcfcd57c26`)

- fix(ready-ticket): remove after-stage eval evidence recorded from a dirty tree
  (c426c2be7eea2b0ef7e090b82238d6dcfcd57c26) — the initial candidate review's
  correctness lens caught that all three committed after-stage summaries were
  recorded before this branch's commit landed: each self-reported
  `worktree_clean: false` and cited the pre-change `skills/ready-ticket`
  subtree, identical to the before-stage run, even though the run itself read
  the edited prose already on disk. A later reader resolving the citation would
  retrieve the unedited file, with nothing in the committed evidence saying the
  run actually measured the changed prose — the exact silent-rot failure the
  eval-evidence norm exists to prevent. Removed and re-recorded from the
  now-committed, clean head. (`c426c2be7eea2b0ef7e090b82238d6dcfcd57c26`)

- docs(ready-ticket): re-record the after-stage eval evidence at the committed
  head (c426c2be7eea2b0ef7e090b82238d6dcfcd57c26) — 22 of 23, the same single
  pre-existing miss as the dirty-tree recording and no case newly failing, so
  the citation fix cost no measured behavior.
  (`c426c2be7eea2b0ef7e090b82238d6dcfcd57c26`)

- chore(review-fix-loop): re-record the after-stage run at the shipping head
  (068ee84c12271a5c0005d93efeee499cc19183d3) — the first after run measured the
  prose before `exclusive_ref_store` was removed below. Re-recorded at the head
  this branch ships: 21 of 21, unchanged, so the review-driven simplification
  cost no measured behavior. (`068ee84c12271a5c0005d93efeee499cc19183d3`)

- fix(review-fix-loop): drop exclusive_ref_store, the buggy legacy behavior had
  no business surviving as an opt-in (068ee84c12271a5c0005d93efeee499cc19183d3)
  — review found that offering a flag to restore the whole-local-ref-map
  comparison made no sense when that exact comparison was the documented source
  of the false positives this ticket fixes. Removed the flag from the schema,
  the tiering function, and the review-phase call site: every Tier 2 ref change
  is now unconditionally a non-gating `observed_ref_changes` observation, with
  no configuration path back to the old behavior. A dedicated clone that wants
  stricter isolation already has tiers 1-3 of the write-prevention ladder
  (sandbox, restricted tool surface, read-only commands) available to it.
  (`068ee84c12271a5c0005d93efeee499cc19183d3`)

- chore(review-fix-loop): record after-stage eval evidence for #245
  (068ee84c12271a5c0005d93efeee499cc19183d3) — commit the after-stage
  deterministic eval-corpus summary for the candidate-ref- attribution tiering,
  on top of the implementation commit, per the eval-backed change norm's
  requirement that the run be recorded from a committed, clean tree.
  (`068ee84c12271a5c0005d93efeee499cc19183d3`)

- fix(review-fix-loop): attribute reviewer mutation, not any local ref move
  (6ab1ace09bf8ca34ff1d260d7fefe16a2204f7c3) — `detect_worktree_mutation`
  compared the entire local ref map, so a checkout where several worktrees share
  one ref store — or any background automation touching a branch — made an
  unattributed ref advance indistinguishable from reviewer misconduct and killed
  a valid review. Replaced the flat comparison with a tiered
  `WorktreeMutationReport`: a change to `HEAD`, the candidate branch ref, or
  this invocation's own attempt namespace still invalidates the candidate
  (`blocked/candidate_integrity_failure`), but every other local ref is now
  always a non-gating `observed_ref_changes` observation — no flag restores the
  old flat comparison, since it was the source of the false positives this
  fixes. Worktree path state and host-supplied tool-trace evidence remain the
  only inputs that force `write_isolation: "violated"`, and a new
  `integrity_evidence` field records whether the host actually inspected a tool
  trace for a clean pass. Added an eval corpus scenario for the unattributed
  third-party ref advance alongside the existing reviewer-mutation one, and
  recorded before/after deterministic eval-corpus evidence per the eval-backed
  change norm. (`6ab1ace09bf8ca34ff1d260d7fefe16a2204f7c3`)

## 2026-08-16 — Gave `ready-ticket` the breakdown that decides how many tickets the work is, made a ticket's stated assumptions answer for themselves at pickup, hardened the harness that measured it, designed one owner for the policy that grades it, and brought the citation guard's own prose in line with the merge method

- refactor(tests): parse the sync-contracts block in one place
  (fecc1790fa1438817c6edf33866056ec7d1c2fe4) — binding the doctrine's bundle set
  to the recipe reused the prose contract's regex by copying it, leaving one
  justfile's shell syntax parsed in two independently maintained places.
  `scripts/tests/helpers.py` now owns `sync_block_skills`, both drift checks
  call it, and it raises rather than asserts when its named block is absent or
  duplicated — a caller asserting against an empty match would otherwise pass
  for the wrong reason.

- docs(ready-ticket): re-record the after-stage run at the shipping head
  (5f38895deb9a69f9508a7e815bead1687785148f) — the first after run measured the
  prose as originally written, and the review fix loop then tightened four cases
  and corrected the doctrine-restatement paragraphs. Re-recorded at the head
  this branch ships: 18 of 18, with no case newly passing or newly failing, so
  the review's corrections cost no measured behavior.

- fix(ready-ticket): say that the section restates the doctrine, and bind what
  it restates (72229a4465ab02d6bc4e49e2d4c714d20d077b07) — the new breakdown
  section claimed to load the doctrine "rather than restates" it and named three
  rules, while restating seven of eight. Both claims were false about the prose
  directly beneath them. The restatement stays, because this skill's forward
  eval hands the model `SKILL.md` alone and a rule absent from that file cannot
  govern a measured run; what changes is that the section says so and names the
  doctrine canonical where the two disagree. Its three verbatim sentences are
  now bound to the canonical text, so editing the doctrine and running
  `just sync-contracts` reddens instead of leaving a superseded rule stated with
  every suite green.

- test(ready-ticket): grade leaf-body altitude, and record the writing-plans
  overlap (2a6ebf5bff15ab0734b4bfc726ff1c5d7bf19d0b) — the acceptance criterion
  requiring every leaf body to be surface-observable shipped with prose
  assertions as its only evidence. The vocabulary term for that failure existed
  but appeared only in cases that produce no graph, and therefore no leaf body,
  so a run could draft every leaf against internal function signatures with all
  eighteen cases still passing. The trigger-collision audit also gains the
  `ready-ticket` × `writing-plans` row the reclassification below requires:
  without it a reader cannot tell a considered disposition from a missed one.

- test: bind the doctrine's three bundle lists to one source
  (ba2dc686d331ab6045a0e6a5830bec532a43c2cd) — which skills bundle the
  cognitive-shaping doctrine was written by hand in the justfile, the drift
  check, and the packaging validator, kept in lockstep by nothing. The one guard
  that looked like it bound them searched the whole justfile for each skill's
  name, and every bundling skill is named in other sync blocks too, so dropping
  a skill from the doctrine block reddened nothing. The failure landed where the
  remedy could not reach it: the drift check tells a reader to run
  `just sync-contracts`, which cannot refresh a copy the recipe was never told
  to make.

- docs(ready-ticket): record the after-stage eval evidence for the draft graph
  (f1939624b73ac4d273a02bdf9f15583c13b4b7ad) — 18 of 18 at the shipping prose,
  every case unanimous across its five repetitions. The four cases the before
  run failed are newly passing and nothing that passed before regressed, which
  is the pairing the eval-backed change norm asks a prose change to demonstrate.

- feat(ready-ticket): return a draft ticket graph instead of a rationale
  (e67dd3aecafefec50824656a10fa65c5aec72c5d) — `decomposition_recommended` named
  each independently valuable part and stopped there, which left the operator
  holding a diagnosis and no route: the parts were named, the graph that would
  carry them was not. The skill now breaks the work down before any body is
  drafted, judging shape against `docs/cognitive-shaping-doctrine.md`, which it
  bundles by stable path rather than restating. The draft names every proposed
  parent, child, leaf, sub-issue edge, blocker edge, and re-split trigger, and
  every leaf carries a complete body that passes all four self-review scans on
  its own. Nothing is created: ticket-management authority still governs one
  body and grants no graph mutation. The doctrine's rules that most often go
  wrong are stated in the skill itself, because a run that settles the shape
  without opening the reference still has to obey them — one ticket stays one
  ticket, a parent never holds a single child, and recorded machine-generated
  evidence does not count toward size. `superpowers:writing-plans` moves from
  house territory to a bounded referenced peer: it supplies the file map, task
  boundaries, and sequencing when present, while the breakdown outcome stays
  house-owned, its plan is never written to disk, and its unit-level altitude is
  lifted to the public surface before anything reaches a leaf body.

- docs(ready-ticket): record the before-stage eval evidence for the draft graph
  (040391c7efd52797a46d358d1e6940b120e5a9b6) — the new corpus measured against
  the prose as it stood: 14 of 18. The four failures are every decomposition
  case, none of which named a node, an edge, a re-split trigger, or drafted a
  leaf body. That is the gap the after run is measured against, and recording it
  first is what makes the pair comparable.

- test(ready-ticket): add the five breakdown cases the draft graph is graded on
  (ad458e2af5170b86dc3b4df2794fad3443651d4a) — cases for fits-as-one, unrelated
  concerns, the mechanical-versus-behavioral seam, validation placement, and
  generated evidence, each built around a specific bait: an epic leadership
  wants to see, a shared sprint, a team habit of landing test scaffolding
  separately, a raw line count dominated by committed eval results. A corpus
  that only rewards good answers measures very little. They land before the
  prose they grade so the before run measures the new corpus against the old
  prose.

- fix: give the citation guard's failure message a remedy for both ways it can
  fire (ba638ef040b4535e170cf50c3c8e94689d30f9ef) — the message now names an
  unlanded backfill as a cause, since a SHA taken before the branch was rebased
  and landed reaches nothing on that same branch, but it still prescribed only
  the recovery for an entry that has landed:
  `git log main -S'<the entry's first line>' -- CHANGELOG.md`. Run against an
  entry that has not landed, that command returns nothing at all — the entry is
  not on `main` yet, so `git log main -S` has no match to find — and the reader
  following the message is handed empty output and no next step. The remedy now
  covers both firing modes: recover the landing commit for an entry that has
  landed, and drop the SHA until it lands for one that has not, which is what
  AGENTS.md requires of an entry added on the current branch. No assertion,
  regex, or reachability behavior changes.

- docs: restate the citation guard's own account of the backfill rule
  (ecb17f4b3bfa3f3c66f3aff03b63cc956555d73c) — the merge-method change above
  left `scripts/tests/test_changelog_citations.py` describing `main` as "almost
  entirely squash-merged" and naming the squash as the only thing that makes a
  backfilled SHA unreachable, stale prose in the one module that enforces the
  rule. Its docstring now records the squash rot as the history it was written
  for, says that a merge commit preserves the authoring commit an entry cites,
  and corrects what the old text had backwards once the mechanism changed: when
  the guard actually fires. A SHA backfilled before submission goes unreachable
  at the rebase onto `main` that precedes submission, so `git rev-list HEAD`
  membership reddens on the authoring branch's own run — it is only the
  squash-merged history behind that where the check was inherently late, because
  those citations died at the merge instead. The failure message names the same
  mechanism. No assertion, regex, or check changes. The eight entries #238 and
  #243 landed without SHAs are backfilled to their authoring commits, which is
  what the rule now names and what the guard confirms is reachable.

- fix(evals): name every path a run was measured through, and stop claiming
  `sha` resolves (4c2dacb7ebeacc79f613c16b04c23775565c6ee6) — `subtree_paths`
  named `skills/<skill>` and, for a triggering run, `triggering`, which
  under-describes any skill whose eval instrument lives elsewhere.
  `implement-epic` is measured entirely through `skills/implement-ticket`'s
  runner, executor, and corpus, so its corpus could change, an `implement-epic`
  run be re-recorded, and the new summary's `candidate.trees` come out
  byte-identical to the old — two runs on different instruments with one
  recorded identity, which two committed summaries taken on different dates
  already share. The paths are now derived from the run's own resolved command,
  so a target self-describes and no hand-maintained mapping can drift; the three
  affected backfilled summaries gain `skills/implement-ticket`, derived from the
  commit each already names. A path whose subtree cannot be read is recorded
  under `candidate.trees_unresolved` rather than dropped, since a run that
  derived nothing otherwise reads exactly like a summary predating the field and
  the reachability guard passes both. The prose is corrected where it still
  asserted what this branch had just disproved: the clean-tree rule kept its
  requirement but was resting on `candidate.sha` resolving, the grandfathered 59
  were said to name commits that no longer resolve when the criterion applied
  was reachability from `HEAD`, and the rebase-safety claim omitted the
  exception its own guard names — a rebase resolving conflicts inside the skill
  directory. The rebase test now performs a real rebase rather than committing
  an unrelated change on top, which proved only that an untouched subtree
  survives an unrelated commit.

- docs: make merge-commit the repository's merge method, not a rule about one
  directory (bf30d2a650899bc69182c2d468ac6af8a75ba83c) — the eval-evidence rule
  this replaces was conditional, applying to pull requests that touch
  `skills/*/evals/results/`, and a conditional merge method is one nothing can
  enforce. GitHub's merge method is a repository setting rather than a
  per-pull-request one, so the conditional form rested entirely on whoever
  clicked merge classifying the pull request correctly every time, with no
  mechanism to catch a miss and no repair once missed. Since evals first landed,
  20 of 46 commits on `main` touched `evals/results/`, so the classification
  would have been live on nearly half of them. The two failures are not
  comparable either: squashing an eval-carrying pull request loses the measured
  content permanently, while merge-committing one that carries none costs a
  non-linear history `git log --first-parent` reads straight through. The
  changelog's own backfill convention is updated to match — under a merge commit
  the authoring commit is the landing commit, so new entries normally cite
  distinct SHAs rather than sharing one, though the squash-merged history behind
  this change still behaves the old way.

- docs: state the merge method the eval evidence depends on, and correct what
  `AGENTS.md` claims survives (c257f8b19cd69c5099472af201ef4d23e74a218c) — the
  file told a reader to trust `candidate.tree` over `candidate.sha` on the
  grounds that content is identical under rebase and squash where a commit is
  not. It is not: `tree` is the whole repository's, so a rebase onto a moved
  `main` changes it through files outside the skill. Both are now stated as
  branch-local, `candidate.trees` is named as the durable half, and the rule
  that makes it durable is written down — a pull request touching
  `skills/*/evals/results/` merges as a merge commit, because a squash keeps one
  tree per pull request while the states eval evidence measures are intermediate
  by construction. `babysit-pr`'s example output block is brought into line with
  the obligation its own prose already carried.

- test(evals): hold every recorded subtree to reachability from `HEAD`
  (bc245d42e41d0023a73b71a2c1228abfeb1a599d) —
  `scripts/tests/test_eval_candidate_citations.py` fails when a summary's
  `candidate.trees` names content no commit reachable from `HEAD` carries, which
  is the same silent rot `scripts/tests/test_changelog_citations.py` catches for
  the changelog: a hash resolving to nothing reads exactly like one that
  resolves. Unlike its sibling it needs no unlanded-branch exemption, because a
  subtree recorded on an open branch stays reachable from that branch's own
  history across a rebase. A summary carrying no `trees` passes — those predate
  the field and are recorded as unresolvable rather than pretended into
  evidence.

- fix(evals): derive the durable identity of every summary that still names a
  reachable commit (3147edf22d662c84b08930cd0e32b732d4147dea) — 23 of the 82
  summaries gain `candidate.trees` computed from the commit each already
  carries, and the other 59 keep none. The derivation asserts nothing the
  recorder did not hold: `git rev-parse <recorded sha>:<path>` could not have
  come out differently had the field existed when the summary was written, which
  is what separates it from backfilling a landing commit — a fact decided after
  the run by a merge that had not happened yet. One of the 23 is a
  triggering-suite run and needs both its skill path and `triggering`. The 59
  measured content that no longer exists in any clone but its author's; unlike
  the changelog's citations, there is nothing left to recover.

- feat(evals): record the subtree identity that survives a rebase
  (8f52f24450c27bd0a29c85d2812000e4b73f05fa) — `candidate.tree` was
  `git rev-parse HEAD^{tree}`, the whole repository's, so a rebase onto a moved
  `main` changed it through files outside the skill and the recorded identity
  resolved to nothing. `candidate.trees` now maps each path whose content
  decided what the run read — `skills/<skill>` always, and `triggering` as well
  for a triggering-suite run, whose executors live outside every skill — to that
  path's subtree hash. The test that had asserted the old claim passed only by
  simulating a rebase as a new parent over an identical tree, which is the one
  thing a real rebase never is; it now models a base that moved, and fails
  against the old behavior.

- docs: design the eval candidate's durable identity
  (5070c687497996fc179af24113126d3edd9f2177) — `AGENTS.md` tells a reader to
  trust `candidate.tree` over `candidate.sha`, on the grounds that content is
  identical under rebase and squash where a commit is not. It is not:
  `candidate.tree` is `git rev-parse HEAD^{tree}`, the whole-repository tree, so
  a rebase onto a moved `main` changes it through files outside the skill
  entirely. 59 of the repository's 82 summaries already name an unreachable
  `sha`, proportionally worse than the 68 of 248 changelog citations
  (77011ed74d28ec522ea7c05d4e310ed53b1dd0d6) repaired, and the loss falls where
  the evidence matters most — 45 of 47 `after`-stage runs are gone, against 20
  of 21 `before`-stage runs surviving only because they name an untouched branch
  point already on `main`. Recording the skill's subtree fixes the rebase case,
  verified against `scott/ticket-234-09af55` where five of five subtrees survive
  a rebase that took all five commits, but fixes nothing under squash: a
  `before` run measures new corpus against old prose, a superseded `after` run
  measures prose a later commit changed, and neither state is on any commit a
  squash keeps. The design therefore merge-commits pull requests carrying eval
  evidence, records `candidate.trees` per path so a triggering-suite run also
  names `triggering/`, and adds a reachability guard modeled on
  `scripts/tests/test_changelog_citations.py`. The 23 summaries still naming a
  reachable commit gain `candidate.trees` derived from it — a lossless
  computation over what each file already carries, unlike a backfilled landing
  commit, which would assert a fact the recorder never held. The other 59 are
  grandfathered: unlike the changelog's citations, the content they measured no
  longer exists to be recovered.

- docs: design one owner for the eval sampling policy
  (8661eb3488d6df16837b57b6b9a793a5ea41f0d3) — the repetition-and-majority-vote
  policy that turns repeated `claude -p` samples into one graded answer exists
  in three independently maintained copies, and they have drifted past features
  into results. `implement-ticket` breaks a tie through `_modal`'s `min()` over
  the sorted candidates; `ready-ticket` uses `Counter.most_common(1)[0]`, whose
  tie order follows insertion. On a 2–2 tie the two record different answers,
  and `ready-ticket` records a different answer again depending on which sample
  was drawn first — a silent difference in recorded evidence rather than a
  missing feature. The design gives the policy a canonical `sampling/core.py` at
  the root, in the transport, drawing, and vote layers its four consumers need
  at different depths, distributed by the `sync-contracts` mirror-and-drift-test
  pattern this repository already uses for the review-suite contracts, the
  shaping doctrine, and `ledger/core.py`. Only the two skills take a bundled
  copy, because only a skill folder is a standalone distribution unit;
  `triggering/` and `review-suite/` import the canonical and so cannot drift at
  all. Because converging the tie-break changes the grader, a run also records
  the `POLICY_VERSION` it was graded under, and a diff is drawn only when tier,
  suite, model, and policy all match — extending to a fourth field the rule that
  already keeps a model update from reading as behavioral movement. Deferred
  from #237's review as reaching beyond `skills/implement-ticket/`.

- refactor(implement-ticket): reduce a sample once instead of twice
  (3e7b43d5acf77684112f65958c4e27e9ce79769f) — `sample` called `normalize` and
  re-emitted the same four fields in different containers: a `frozenset` of
  actions `normalize` had already deduplicated, and a tuple of criterion/status
  pairs whose single consumer rebuilt dicts from it anyway. `combine` never
  hashed or set-operated a sample, so neither conversion did anything except
  oblige a reader to prove that. `combine` now takes `normalize`'s output
  directly, and the sibling executor's one-reduction shape is what this matches.
  Verified identical over 4000 randomized batches including absent, non-string,
  out-of-vocabulary, and duplicate-criterion payloads: zero differences in the
  emitted JSON.

- refactor(implement-ticket): stop the assumption test from re-grading the whole
  corpus, and drop a counter that duplicates another
  (ca592d9a86dfb3c3559dad3b71a2d89eb85b726c) — review of the candidate found
  both. The assumption-gate test ran a second full 60-process grading pass and
  repeated the corpus-wide `assertEqual([], failures)` that the test above it
  already owns, so any of the other 58 cases regressing would have reddened a
  test named for this gate and pointed a maintainer at the wrong obligation; it
  now observes only the two cases it asserts about, at a twentieth of the cost.
  In the ledger vote, `presence` was incremented in the same breath as
  `multiplicities`, making it exactly that counter's total, so an edit changing
  when a criterion counts had to touch both to stay consistent.

- fix: say in each recorded eval summary that its own provenance did not survive
  the rebase (ad282a2ce81084fed2555cefb2ec9f9ef640c816) — all five runs recorded
  on this branch name a `candidate.sha` and `candidate.tree` that no ref
  reaches, because the rebase onto #236 replayed those commits onto different
  content. `AGENTS.md` promises `tree` survives rebase and squash-merge, which
  holds for a content-preserving replay and not for this one. Each summary's
  `note` now states that, and names the commit on this branch carrying a
  byte-identical `skills/implement-ticket` subtree — 293e951, 853333d, e9bd92f,
  4c6bdda, be7788f respectively — so the run can still be read against the prose
  that produced it. No measured result, per-case outcome, or vote count changes.
  That the recorder can produce this at all is filed as separate work.

- fix: repair the day sections this branch's rebase split
  (e1800ff922f7039d89f108a7c3edc25b0c727730) — resolving the rebase conflict
  against #236 left `CHANGELOG.md` with two `## 2026-08-15` headings 66 lines
  apart, each claiming to summarize the same day, with three 2026-08-16 entries
  stranded under the older one and nine of `main`'s entries re-parented under a
  heading this branch wrote. Both days are one section again, ordered
  newest-first, and #236's own entry — which had landed on `main` carrying no
  SHA — is backfilled with the commit that carried it there, which the
  convention requires of every landed entry below a new one. Neither the
  citation guard nor `mdformat` can see either defect: one checks that a SHA
  present resolves, the other does not read heading semantics.

- fix: hold this branch's entries to the landing-commit convention
  (98beca9bd80cd4552beec399290f91d3f6c2197b) — #236 landed while this work was
  in flight and changed what a backfilled SHA names: the commit that carried an
  entry onto `main`, backfilled only once it has landed. The nine entries below
  cited their authoring commits, which the rebase onto #236 then rewrote — the
  rot that change was made to stop, reproduced in the same file within a day.
  They now carry no SHA, which is what an unlanded entry is supposed to carry,
  and `scripts/tests/test_changelog_citations.py` passes.

- fix(implement-ticket): let a wrongly shaped sample grade as a mismatch rather
  than end the run (faa575d799ab2784bf985354e4322c737eea0f2f) — review found a
  regression the new sampling layer introduced. `terminal_state` and
  `target_skill` are counted and compared as `Counter` keys and under `min()`,
  so a sample answering `["blocked"]` or `1` reached that arithmetic as a
  `TypeError`: a non-zero executor exit, no per-case recovery in the runner, and
  a stage of sixty scenarios filed as `attempted`. At the base the same sample
  serialized fine and graded as one ordinary mismatch. Both fields are now
  rendered to a string when they are neither a string nor absent, which keeps a
  wrongly shaped answer gradable as the mismatch it is; absence stays absence,
  since only one of the two is a missing answer.

- test(implement-ticket): re-record the after-stage run at the corrected prose
  (10a7b54bc7eea82c15b354f551d0f40384c88f0f) — the false block is gone.
  `unverifiable-ticket-assumption` returns to 5/5 `ready_pr` with zero samples
  blocking, where the previous wording had 2 of 5 refusing a ready ticket, and
  it still reports the unreadable assumption 5/5 — the obligation kept, the cost
  removed. `drifted-ticket-assumption` stays 5/5 blocked and 5/5 naming the
  drift. Naming the excluded outcome inside the branch a reader acts on is what
  moved it; the earlier attempt, which fixed the same confusion in a summary
  paragraph one step away, moved nothing. Corpus total is 36 of 60 against 38:
  two cases this change does not touch went red, both of which have oscillated
  across every run recorded today.

- fix(implement-ticket): keep drift out of the body-repair branch, and name the
  outcome the unreadable branch must not produce
  (be7788fef0581b8bb6936b31f49fa920b0da46c9) — review of the candidate found the
  new gate condition had been added to the same list the routing section below
  calls the body-level conditions, whose first branch repairs the ticket body
  and continues whenever ticket editing is authorized. A drifted assumption
  would have taken that branch, which is the one thing the ticket names as a
  non-goal; the candidate's only carve-out disclaimed the routing marker, not
  the repair. The routing section now excludes the condition by name. The second
  finding is measured rather than argued: the unreadable branch told a run what
  to do and never said what it must not do, and 2 of 5 samples blocked a ready
  ticket on a citation with no repository address where 5 of 5 had proceeded
  before this change. The branch now states the excluded terminal outcome where
  a reader acts on it.

- fix(implement-ticket): count the samples a burst took, and own the citation
  grammar once (4d5120b9f2a5a7db5856d85021af1c499ff30d1a) — review of the
  candidate returned three strong recommendations, all in the harness rather
  than the gate. The burst tolerance reported `failed_samples` by subtracting
  the surviving redraw from the first round, so a scenario that lost all five
  samples and recovered recorded zero failures, reading exactly like one that
  never lost a sample; the redraw was also sequential, quietly dropping the
  concurrency the first round has. Both rounds now go through one `draw_batch`,
  and the losses accumulate across them. A test repairing a drifted packet
  parsed the citation grammar by hand, so a change to the executor's `CITATION`
  would have left that test green while the executor called every citation
  unreadable — it now parses through `CITATION` itself. `normalize` never read
  the `payload` argument it has always taken, and the new sampling layer
  threaded it through again; it is gone from both.

- test(implement-ticket): re-record the after-stage run at the shipping head
  (a397c63ba02726c6153697bf93b5be0243c37f7d) — 38 of 60, both new cases green,
  taken at the head that ships rather than at the prose commit two fixes back.
  It also refutes the reason given for one of those fixes: the wording change
  was made because 2 of 5 samples called an unreadable citation drift, and the
  sentence that described that branch in drift's words looked like the cause. At
  the corrected head the case still splits 3/5, with the same 2 samples
  blocking. The sentence is better prose and was not the cause, which is
  recorded here rather than left implied by a green case.

- fix(implement-ticket): survive a burst that takes every sample of one scenario
  (4c6bdda983599df2cb3b0160637ab74569fa0ac5) — the re-recording at the shipping
  head died partway through: five concurrent samples of one scenario failed
  together, the runner surfaced it as a non-zero executor exit, and a stage half
  an hour in was filed as `attempted`, the status reserved for an environment
  with no model access. The CLI answered normally minutes later, so that is a
  burst, not an environment. A scenario whose every sample failed now stands
  down 30 seconds and redraws once; a second empty draw is the environment and
  still ends the stage. The `attempted` record is committed beside this rather
  than dropped.

## 2026-08-15 — Moved the design boundary to a checkable place, retired carve-changesets' duplicate shaping rules, set the assumption re-check against a recorded baseline, and repaired the changelog's own rotted citations under a convention that survives squash-merge

- fix(implement-ticket): stop describing an unreadable citation in drift's words
  (e9bd92f394397007afb35dc1b51ff8707763eb98) — the post-change measurement below
  passed the case but halved its agreement: 2 of 5 samples blocked on an
  assumption with no repository address, calling it drift. The section separates
  the two branches and then closes by naming the unreadable branch's cost
  "drift's failure, reached without any drift", which hands the word back to the
  branch it just excluded. It now says plainly that an unreadable citation is
  not drift and never blocks, and why: drift is a disagreement you observed, and
  an assumption you could not read produced none.

- test(implement-ticket): record the post-change forward-eval measurement
  (d093668e4776bc080a7d9c493e3d2ce132368794) — 37 of 60, up from 32, with no
  case newly failing. The obligation the change was written for moved:
  `drifted-ticket-assumption` goes red to green, still blocking 5/5 and naming
  the drift 5/5, with the stray `unchecked` report that had failed it at 3 of 5
  samples now at 0 of 5. The unverifiable case still passes, and its agreement
  is where the remaining variance sits — 5/5 before, 3/5 after, with 2 samples
  now calling an unreadable citation drift. The sentence closing that section
  reached for the word `drift` to describe the unreadable branch's failure,
  which is the one place the prose blurs the two branches it just separated.

- feat(implement-ticket): re-verify a ticket's stated assumptions at pickup
  (853333d391d7e0fc56a030b61cca12bd49caca6e) — the readiness gate now re-reads
  the `Verified assumptions` slot against the current tree before a branch or
  worktree exists, and sorts each assumption into one of three exclusive
  branches: it still holds, it no longer holds (`blocked`, naming the drift and
  what the tree says now, with the body left for the requester and
  `ready-ticket` to correct), or it cannot be checked from here (proceed, and
  report it as unchecked). The third branch is decided by the citation rather
  than by how the claim sounds, because the pre-change measurement showed the
  wobble is there: the unmodified skill already blocked on drift 5/5, and
  over-reported `unchecked` for assumptions it had read in 3 of those 5 samples.
  The load-bearing exclusion is unchanged and now says which question it
  excludes — re-deriving the conclusion, not re-reading the citation.

- test(implement-ticket): record the pre-change forward-eval measurement
  (b16d48b0e20ace6e21822cd36dece96eeb46ec86) — 32 of 60 at the shipping head,
  with the two new cases splitting. The drift case fails, but not where the
  ticket predicted: the unmodified skill blocks 5/5 and names the drifted
  assumption 5/5, and it fails because 3 of those 5 samples also reported an
  assumption as unchecked in a packet where every assumption carries a readable
  address. The unverifiable case already passes 5/5. So the behavior the prose
  has to move is not "notice the drift" but "say which assumptions you actually
  read", and an earlier measurement discarded before this one is why the corpus
  asks that at all: its packets stated outright which assumption had gone stale,
  both cases passed 5/5, and it was grading whether a runtime can read a flag.

- fix: cite the commit that reached `main`, and hold the changelog to it
  (77011ed74d28ec522ea7c05d4e310ed53b1dd0d6) — 68 of this file's 248 commit
  citations resolved to nothing. The changelog convention told an author to
  backfill the SHA of the commit that wrote the entry, but `main` is almost
  entirely squash-merged, and a squash discards every authoring commit its pull
  request held. A pull request contributing several entries therefore rotted all
  of them at once, which is how #147, #176, #185, and #222 account for 24 of the
  26 dangling citations in the newer `(<sha>)` form. The older `` (`<sha>`) ``
  form — 169 citations the bare-parenthesis search does not see at all — carried
  42 more. Two were not squash rot but fabrication: a 7-character prefix
  expanded to a plausible 40-character string that had never named anything,
  sharing its prefix with the real commit it was meant to cite. Every one is
  repointed at the commit that carried its entry onto `main`, recovered by
  asking which commit introduced that entry's own line, and cross-checked
  wherever a second source existed: GitHub's merge commit for the cited SHA
  covers 52, and a real commit sharing the cited prefix covers the 2 fabricated
  ones. Neither source can speak for the remaining 14, whose authoring commits
  GitHub never saw. No cross-check contradicted the recovered commit.
  `AGENTS.md` now states the rule the repair follows — cite the landing commit,
  backfill only once an entry has landed, and expect one SHA across every entry
  its pull request contributed — and the seven entries that had landed with no
  SHA at all gain one. `scripts/tests/test_changelog_citations.py` keeps it
  true, and CI checks out full history because a depth-1 clone cannot answer the
  question. The guard was verified capable of failing: it named all 68 before
  the repair, and mutating one character of a single surviving citation turns it
  red naming that line. One SHA is deliberately left unchecked — the
  writing-plans experiment's `pin` names a commit in the `superpowers` peer
  repository, which cannot resolve here, and is written backticked outside
  parentheses rather than as a citation, which is the distinction the check is
  scoped to.

- test(implement-ticket): grade re-verification of a ticket's stated assumptions
  at pickup (293e95194478c64568298ee2f27b4532b3bc2f85) — a ticket's
  `Verified assumptions` slot records what was true when the body was written,
  and nothing re-reads it when the work is picked up. Two forward cases put that
  question to the corpus: one whose stated assumption the current tree
  contradicts, which has to stop before any implementation state exists, and one
  carrying a claim no repository read can settle, which has to proceed while
  saying so rather than passing it off as verified. Neither packet says which
  assumption went stale — the citation carries the line it quotes, the
  repository artifact carries the line that path reads now, and drift is
  whatever disagreement a runtime finds between them, so what is graded is
  whether it looks rather than whether it can read a flag. The corpus lands
  ahead of the prose, because `just eval-record` runs the current tree and a
  before-stage measurement needs the case to exist while the obligation does
  not. The real-model executor also gained `--repetitions` (default 5, drawn
  concurrently), so each recorded case carries the vote counts behind its answer
  instead of one sample's opinion; concurrently because this corpus is four
  times its sibling's size, where five sequential samples per case would put a
  recorded stage into the hours.

- test(ready-ticket): test the retry loop the way its sibling already does
  (f6a90c20cc51c24c32915e5211345bc5b0fbfd4d) — review found the new retry test
  hand-rolling a partial stand-in for `subprocess.CompletedProcess`, a manual
  patch-and-restore, and a list used as a call counter, for behavior
  `skills/implement-ticket/scripts/tests/test_forward_evals.py` already covers
  with `mock.patch.object` and a real `CompletedProcess` — against a retry loop
  this change deliberately mirrored from that same module. The test now reads
  like its sibling, and exhausting every attempt gained the case the hand-rolled
  version had no room for. (f6a90c20cc51c24c32915e5211345bc5b0fbfd4d)

- test(ready-ticket): re-record the after-stage run at the shipping head
  (2dc1e4e3339a1fb5be52208d657663b6518fd7ec) — the first after-stage run was
  taken before the executor fix below, so the tree that produced the evidence
  was not the tree that ships the instrument. Review named that gap, and closing
  it also settled the open question about the one case that had gone red. The
  rerun is `completed`, 13 of 13, with the target case still citing the volatile
  collection by location 5/5 and `autonomous-unresolvable-rate-limit` back at
  4/5 on `choose_no_answer_on_requesters_behalf`. Three post-change measurements
  of that term now read 1/5, 2/5, and 4/5, and its sibling case moved 5/5 to 3/5
  while still passing: the term is an unstable self-report rather than an
  obligation the new prose suppressed, and no prose change was needed to recover
  it. Recorded rather than asserted, because two samples had looked like a
  reproduction and the third is what distinguished variance from a regression.

- fix(ready-ticket): keep one unusable sample from ending a recorded eval run
  (75cf01e09e740f7321f3a80f433951a7840b8065) — review of the change below found
  that the new majority-vote executor keyed its terminal-state counts by the raw
  sample value, so a well-formed response that simply omitted `terminal_state`
  put `None` beside string keys in the emitted object and
  `json.dump(..., sort_keys=True)` raised `TypeError`. The harness reads that as
  a non-zero executor exit and ends the corpus mid-run, discarding every case
  already sampled and leaving the recorder to file the loss as `attempted` — the
  status reserved for an environment with no model access — rather than as the
  harness defect it is. That is the exact failure the retry loop was added to
  prevent, and it was a regression against the previous executor, which degraded
  to a single graded mismatch. The absent state now votes under a `none`
  sentinel the way `triggering/executors/description_executor.py` already votes
  an absent answer, while the graded value stays `None` and still grades as a
  mismatch. The same review found the corpus README restating a case count that
  this change made false — the failure mode the prose below names, one directory
  away — so it now points at `forward_cases.json` instead of counting it.

- test(ready-ticket): record the post-change forward-eval measurement
  (f888b12b6e8c22bf9bd0efc0e2ab70825059e88c) — the target case flips the way the
  rule predicts: citing the volatile collection by location goes 1/5 to 5/5 and
  restating its membership as a value goes 4/5 to 0/5, with the architectural
  fact still restated 5/5 and cited text still quoted 5/5. The run is recorded
  `failed` rather than `completed`, because one pre-existing case,
  `autonomous-unresolvable-rate-limit`, went from selecting
  `choose_no_answer_on_requesters_behalf` 5/5 to 1/5 and dropped below the
  majority. The case's substance held throughout — it still returns
  `requires_brainstorming` 5/5, still asks no question, names the absent design
  part, gives a next action, and mutates nothing at 5/5 — and the sibling case
  carrying the identical obligation read 5/5 on both sides. The run is committed
  as recorded rather than tuned away; the entry above resolves what the movement
  was.

- feat(ready-ticket): cite repository state in a form that fails loudly when it
  goes stale (94b9ae8ce43322a97c510c7f0c4ff16da586ad6d) — a ticket body that
  cites this repository makes a claim with a shelf life, and the failure mode is
  silence: the line moves, the citation still resolves, and the implementer
  reads something confident, specific, and false with no signal it was ever
  true. The rule is three parts and one question. A citation of repository text
  carries the quoted line, not only the address, because a line number is
  invalidated by any edit above it and the quoted text is what a reader searches
  for once the number stops landing. A fact that changes whenever a consumer is
  added — a collection's members, a count, a registry's contents — is cited by
  location, because whoever adds the next member is not reading this ticket. And
  a fact whose change is itself news — what a script writes, what an executor
  refuses to emit, what a runner ships to a model — keeps its value, because a
  body made wrong by that kind of edit has surfaced a real change rather than
  rotted. The question separating the last two is what would make the statement
  false: one more consumer, or a deliberate decision. The rot behind this is
  measured rather than supposed — of eight citations written into tickets on one
  day, seven still pointed at their text and one did not, after #231 moved the
  line reading "block, and ordinary PR title and body content" in
  `carve-changesets`' spec.

- test(ready-ticket): record the pre-change forward-eval measurement
  (6e5df1d5460cd42bd98fabeae2f36022f182f2ab) — the real-model forward run at the
  tree carrying the case but not the rule: 12 of 13 pass, and the new case
  fails. Across five independent samples the run cited the volatile collection
  by location once and restated its membership as a value four times, while
  quoting cited text 5/5 and restating the architectural fact 5/5. So one of the
  three rules is where the behavior actually is, and the other two were already
  the model's default — a distinction the pre-change run exists to make, and one
  a single sample could not have made.

- test(ready-ticket): grade how a ticket body cites repository state, before the
  rule exists (5bd36f550cd7c55251e47c947c102788a13e049b) — the forward corpus
  gains one case whose scenario names three repository facts (a line of a file,
  which lenses a skill loads, what the eval recorder emits) and grades which of
  them the run quotes, cites by location, or restates as a value. The case lands
  ahead of the prose it measures, so `just eval-record` has a term to grade at
  `--stage before`. Two harness changes make that measurement trustworthy rather
  than anecdotal: the real-model executor now takes `--repetitions` (default 5)
  and majority-votes independent samples the way
  `triggering/executors/description_executor.py` already does, recording the
  per-sample counts so a 3/5 answer is never filed as 5/5, and it retries a
  malformed response three times the way implement-ticket's executor does,
  because one flaky sample must not sink a run that is now five times longer. A
  first draft of the scenario described the lens set as one that "gains a member
  whenever a lens is added"; a fresh model given that phrasing answered
  correctly against the unchanged prose, so the case was grading the hint rather
  than the skill. The committed scenario states the three facts and leaves their
  classification to the prose, and a test guards the leak from coming back.

- feat(ready-ticket): make an approved design a fail-closed planner input
  (46c35a7a1c16d8a7afb3ab3468ab94d75d2e2305) — `ready-ticket` approximated
  brainstorming's questioning: it elicited the open product decisions itself, so
  the design boundary sat wherever a given run happened to stop asking.
  `docs/cognitive-driven-development.md` moves that boundary somewhere checkable
  — brainstorming is done when the requirements and acceptance criteria are
  captured, the goals and non-goals are known, and the stakeholders and
  deadlines are identified, each at the scale the work warrants — and this
  change binds the skill to it. The design becomes an input validated against
  those four parts at any scale: a one-sentence bug design and a document
  representing months of work are both legal inputs, checked the same way, and
  neither earns extra ceremony nor gets re-litigated. Elicitation narrows to the
  tracker-shaped residue a design cannot answer — each criterion restated as an
  observable public-surface behavior, the check that would demonstrate it, and
  whether that check runs before or after merge. A missing part becomes a
  routable fifth terminal result, `requires_brainstorming`, naming which part is
  unsettled, what is unsettled about it, which of the result's two shapes it is
  — absent at the gate, or unsettled after the gate by a verification that
  falsified what the design rested on — and one next action. That last
  obligation was recorded behavior rather than foresight: the first post-change
  real-model run routed correctly and then stopped at the diagnosis on three
  cases, because the bullet asked for a next action only under `blocked`. A gap
  named without a route is what `blocked` already produced, so the prose gained
  the obligation rather than the corpus losing it. The gap is never gathered and
  never inferred: an inferred requirement lands in the body as decided, and the
  next reader never learns that nobody decided it. Three existing corpus
  expectations change answer rather than grade, because the new contract routes
  what the old one could only report — the unresolved retry-idempotency case,
  the objection resting on an unmade pricing decision, and the falsified
  load-bearing assumption whose replacement is design work. Two forward cases
  move the same way, so their before/after movement is not evidence about the
  prose in either direction, and `evals/README.md` says so rather than leaving a
  reader to infer a win. A sufficient design whose residue nobody can resolve
  still stops at `blocked`, and a new forward case holds that line so the two
  results cannot collapse into one. README composition rule 1 asserted the gate
  was satisfied *because* `ready-ticket` ran elicitation and obtained approval
  of the body; that mechanism is exactly what this change removes, so the rule
  now rests on brainstorming having run.

- feat(carve-changesets): bind changeset shape and ordering to the canonical
  doctrine (1ce41875782ac2a8de04b70d39619493e919d1d5) — `references/SPEC.md`
  carried its own cognitive-load guardrails and decomposition-order list, a
  second codification of rules `docs/cognitive-shaping-doctrine.md` already
  owns, and a doctrine with two homes has no home. Both sections retire in favor
  of the bundled doctrine, distributed by `just sync-contracts` and
  drift-checked byte-for-byte under `just test` — the same mechanism
  `review-solution-simplicity` adopted, and the one
  `docs/cognitive-driven-development.md` records as the selected shaping
  authority. What survives locally is carving-specific: the rename-accompanies-
  behavior rule with its PR-naming requirement, wide-refactor isolation,
  feature-flag policy, and the database-migration rules, none of which the
  doctrine carries because they constrain an ordered sequence of merges rather
  than shape in general. Three of the doctrine's eight breakdown rules are
  scoped out of boundary selection — two addressed to planning, and the one the
  doctrine itself calls downstream, which a carve discharges by surfacing new
  scope through its stop conditions rather than by mutating a tracker it has no
  authority to touch — leaving five that govern boundaries directly. The binding
  reaches an evaluated run rather than stopping at prose: the eval runner now
  ships the doctrine as a contract document and the fixture gate requires its
  text, so a run that does not receive it blocks instead of carving to an
  improvised standard — verified by driving the executor with and without it.
  Two provisions the local guardrails never had now apply to carving: mechanical
  change runs much larger, and recorded machine-generated evidence is excluded
  from the size judgment outright. Retiring the section also retired its anchor,
  and `implement-ticket`'s carve handoff was the one place in the tree linking
  to it; that link is retargeted here rather than left dangling until the
  publication-size-gate leaf rewrites the paragraph. The obligation it states is
  unchanged, so the edit is editorial and carries no eval evidence of its own.
  `implement-ticket`'s two remaining prose mentions of the old section name are
  descriptions rather than links and are left to that leaf.

## 2026-08-14 — Named cognitive debt as the problem the suite exists to solve, then specified, published, and distributed the cognitive prose contract that answers its prose half

- test: bind the prose contract's sync recipe to the skills its drift check
  names (cb712926c7090d12e18d180c81d219c1c03db600) — every drift failure tells a
  reader to run `just sync-contracts`, and nothing held that recipe to the skill
  list the check asserts, so dropping a skill from it left a stale bundled copy
  no test would catch. The new assertion is scoped to the block that copies
  `docs/cognitive-prose.md` rather than searching the whole recipe, because
  every bundling skill is named in other blocks too: a whole-file substring
  check — the form the sibling `test_cognitive_shaping_doctrine.py` uses — still
  passes after a skill is dropped from the prose block, which was verified
  rather than assumed. The guard was verified capable of failing on that exact
  mutation. The sibling module carries the same latent weakness; it is not
  touched here.

- docs: complete the changelog's record of its own repair
  (cb712926c7090d12e18d180c81d219c1c03db600) — the previous commit added the
  missing entry for the reconciliation commit and then reproduced the defect it
  was fixing: it left that entry SHA-less and added none for itself, so the
  SHA-less top entry named `HEAD~1` again. A commit that retroactively records a
  past commit has to do three things, and the branch's own earlier repair did
  all three — stamp the past commit's entry with its SHA, backfill the entry
  below it, and add itself SHA-less. Doing only the first two recurses. Found by
  the scoped re-review of the previous fix, which checked whether the fix had
  recreated the defect one commit later rather than only whether the reported
  symptom was gone.

- docs: record the reconciliation commit in the changelog
  (cb712926c7090d12e18d180c81d219c1c03db600) — the reconciliation commit landed
  without an entry, so the changelog's SHA-less top entry named `HEAD~1`. Six of
  the branch's seven commits carried an entry and only the head did not. Found
  by the repository review of the published candidate, which is the review that
  commit had skipped by being authored directly rather than through the branch's
  normal path.

- docs: reconcile the prose contract with the concurrently landed shaping
  distribution (cb712926c7090d12e18d180c81d219c1c03db600) — #221 landed on
  `main` while this branch was in flight, bundling
  `docs/cognitive-shaping-doctrine.md` into `review-solution-simplicity` and
  drift-checking the copy. Rebasing onto it exposed a real defect rather than a
  textual conflict: this branch had added
  `[cognitive-debt.md]: cognitive-debt.md` to the doctrine when nothing bundled
  that file and a relative link was correct, and a repository-relative link
  resolves to nothing inside a bundled copy. That link is now absolute, which is
  the same correction #221 made to the doctrine's other cross-reference for the
  same reason. Both branches also rewrote the `sync-contracts` doc comment
  without knowing about the other's block, so the merged comment names all three
  bundled texts. The spec, the plan, and the changelog had each claimed this
  branch would be the first exercise of the doctrine-distribution mechanism Spec
  B needs; #221 got there first, so they now record that the two programs
  converged on one answer independently — including the same non-obvious
  absolute-link constraint — rather than one piloting it for the other.

- docs: apply the whole-branch review's fixes to the cognitive documents
  (cb712926c7090d12e18d180c81d219c1c03db600) — the branch's final review found
  the day's documents misrepresenting a source they lean on and overstating a
  count in the document whose thesis is precision. `cognitive-debt.md` had
  classified all three of Litt's techniques as presentational while also
  claiming the speed-regulator failure mode was unanswered; the quiz his
  explanations technique embeds is a speed regulator, so both passages now say
  so and the limit is stated as unanswered *by compris* rather than unanswered
  in general. `cognitive-prose.md`'s fourth reader question asked how a change
  "was verified," which a ticket body cannot answer prospectively, so it now
  names what each of its two governed surfaces owes. The exemplar's "four
  stacked modifiers" is corrected to what #20's opening actually carries — two
  stacked adjectives ahead of the noun, with the rest trailing in prepositional
  phrases — everywhere the phrase appears, with the bundled copies regenerated
  by `just sync-contracts` rather than hand-edited. The new "The problem
  underneath" section of `cognitive-driven-development.md` and its HTML
  presentation copy had landed unguarded, so its five load-bearing claims are
  now registered with the module's existing `assert_in_both` parity mechanism.
  And `2a8f84b`, which landed without one, gains its changelog entry.

- build: distribute the cognitive prose contract to its consuming skills
  (cb712926c7090d12e18d180c81d219c1c03db600) — the contract landed with no way
  to reach a skill. `just sync-contracts` now copies `docs/cognitive-prose.md`
  into `references/` for `implement-ticket`, `carve-changesets`, and
  `ready-ticket`, and a drift test fails when a copy diverges or when an
  unlisted skill carries one. The copies are deliberately unreferenced: no
  `SKILL.md` loads them, so this commit changes no behavior and leaves the
  consuming edits to be reviewed on their own. This branch expected to be the
  first exercise of the doctrine-distribution mechanism Spec B of the shaping
  program needs; #221 landed the same mechanism concurrently for the shaping
  doctrine, so the two arrived at one answer independently rather than one
  piloting it for the other. The drift check was verified capable of failing:
  appending a line to the `ready-ticket` copy turns it red naming that file, and
  `just sync-contracts` restores green.

- docs: correct the plan's expected test counts
  (cb712926c7090d12e18d180c81d219c1c03db600) — the plan for the cognitive prose
  contract told its executor to expect 8 tests from Task 1 where the task's own
  code block defined 7, and Task 2 inherited the off-by-one as 11 where 7 + 3 is
  10\. The counts now match the code the plan ships, so an executor checking its
  work against them is not chasing a test that was never specified.

- docs: publish the canonical cognitive prose contract
  (cb712926c7090d12e18d180c81d219c1c03db600) — compris shaped what a reviewer
  reads and said nothing about how it was written. The entire pull-request-body
  obligation was a four-item content checklist at
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

- docs: plan the cognitive prose contract
  (cb712926c7090d12e18d180c81d219c1c03db600) — turns the spec into two
  executable tasks split where a reviewer could accept one and reject the other:
  the contract document with the invariants holding its content, then its
  distribution with the invariants holding the copies. Planning surfaced a
  constraint the spec missed. Every link in `docs/cognitive-prose.md` has to be
  an absolute URL, because a relative one dangles the moment the file is copied
  into a skill's `references/` where none of this repository's layout sits
  beside it — the reason
  `review-suite/scripts/tests/test_bundled_contracts.py:147` exists. It is a
  global constraint of the plan and a test enforces it. The plan's test code was
  run against the real contract text rather than assumed: the section and table
  helpers find seven headings in order and four prohibition rows each carrying a
  `[#NNN]` source, and both survive the `mdformat --wrap 80` reflow
  `just format` applies, which renumbers the ordered list and pads the table.
  Task 2 requires the drift check be proven capable of failing before the task
  is called done, since a drift check nobody has watched go red is a decoration.
  Plan only; nothing is implemented.

- docs: name cognitive debt as the problem compris solves, and spec the prose
  contract answering its prose half (cb712926c7090d12e18d180c81d219c1c03db600) —
  the suite had a standard without a stated problem.
  `cognitive-shaping-doctrine.md` opened on the technique (work is broken apart
  by what a reviewer can understand) and `README.md` led with what the skills
  do, so the only answer to "why is this worth the review overhead" was an
  appeal to tidiness. New `docs/cognitive-debt.md` states the problem: cognitive
  debt, Margaret Storey's term for understanding that lives in developers' minds
  rather than in the code and fragments, resting on Naur's claim that a program
  is a theory held by the people who built it. It is not technical debt renamed
  — technical debt is a property of the artifact and cognitive debt is a
  property of the people, which is why editing code cannot pay it down. Agents
  change the rate and the default: they generate correct code faster than any
  human forms a theory of it, so under agentic implementation the debt is what
  accrues when nobody intervenes, which is Geoffrey Litt's *Understanding is the
  new bottleneck*. Two consequences are recorded. Throughput is the wrong
  headline number for this suite, and the three constraints that already exist —
  shape, tickets rather than local plan files, recorded rationale — are restated
  as responses to one problem rather than three independent preferences.
  compris's intervention is named as structural and upstream of the
  presentational techniques (narrative diffs, explorable models) that dominate
  this space, and the two are stated to compose rather than substitute. The
  doctrine also gains the participation argument: the mental model is what lets
  a reviewer approve the change in front of them *and* direct the work that
  comes next, so it is the reason for the standard rather than the receipt for
  it. A closing section states what the suite does not claim — it does not
  measure cognitive debt, does not gate on understanding, and has no speed
  regulator — so the diagnosis is not read as a solved problem. Framing only:
  the shaping standard, its calibration, and its breakdown rules are unchanged,
  and no skill's normative prose is edited.

  The same commit specs the first response to that problem's prose half.
  `docs/superpowers/specs/2026-08-14-cognitive-prose-contract-design.md` designs
  a canonical prose contract for the artifacts compris emits, because the suite
  shapes what a reviewer reads and says nothing about how it is written: the
  entire pull-request-body obligation is one content checklist at
  `skills/implement-ticket/SKILL.md:669`, and `carve-changesets` inherits none
  at all. The gap is observable in this repository's own history — #20 opens on
  "Adds `implement-ticket` as the reusable, runtime-neutral workflow…" with two
  stacked adjectives ahead of the noun, the rest of its qualification trailing
  in prepositional phrases, and no statement of what was wrong, and summarizes
  itself in five imperative-verb bullets that restate the diff, while #209 three
  weeks later opens on the defect, argues from the ticket, and proves its new
  guard was verified capable of failing. The voice improved in one person's
  head; nothing in the suite would stop a fresh agent from regenerating #20's
  prose. The design splits the fix by failure shape per
  `docs/skill-authoring.md`: structure is wrong-shaped output and gets a
  positive contract, voice is a discipline violation and gets prohibitions, each
  sourced to the pull request it was observed in. The rationalization table
  ships deliberately unwritten and says so about itself, because the sourced
  material carries observed output rather than the agent's own rationalizations,
  and inventing those rows is what `skill-authoring.md:132` forbids. Canonical
  text lives in `docs/` and syncs into three consumers that do not yet reference
  it, which was expected to pilot the doctrine-distribution mechanism Spec B of
  the shaping program will need — #221 has since landed that mechanism
  concurrently, so the two converged independently instead. Design only; nothing
  specified here is built, and the remaining four pieces are recorded with their
  ordering rather than designed.

## 2026-08-13 — Triaged the real-model forward-eval baseline and found most of it was measuring the harness rather than the prose, measured a fix for the elicitation and reverted it when it did not work, corrected the eval-evidence norm's scope statement for the review-lens skills, and bound the solution-simplicity lens to the canonical shaping doctrine instead of its own restatement of it

- feat(review-solution-simplicity): bind the lens's reviewability judgment to
  the canonical shaping doctrine — the lens judged whether a candidate could be
  reviewed at all out of its own prose, while
  `docs/cognitive-shaping-doctrine.md` was already compris's pinned statement of
  that standard and nothing loaded it. The doctrine is now bundled into the
  skill by `just sync-contracts` and drift-checked under `just test`, the same
  distribution pair `review-suite/` has used all along, so the lens cites the
  mental-model standard rather than restating it and fails closed when the
  doctrine is missing. What it consumes is deliberately partial: the standard
  and its scale calibration, never the breakdown rules — those divide work
  before it is written, and this lens reads a candidate that already exists, so
  importing them would turn a review lens into a decomposition tool. The result
  shape, severity semantics, and read-only posture are untouched, and the
  contract tests now hold the citation, the fail-closed load, the absent
  breakdown rules, and the continued absence of any numeric size threshold. The
  doctrine's one cross-reference became an absolute URL, because a
  repository-relative link resolves in `docs/` and dangles in every bundled
  copy. (5b39de79a01b5aacc77438de87d823b6ce432d54)

- test(evals): triage the real-model forward-eval baseline and record a reverted
  elicitation experiment (5405aab218db0f7e519667440392be33063a0ea5) — the first
  real-model baseline (#145) passed 27 of 54 cases while the deterministic tier
  passed 54/54, and the 31 non-terminal-state failure lines behind that gap had
  never been classified. All 31 now carry a classification and its evidence: 8
  prose gaps, 12 expectation defects, 11 measurement artifacts. The headline is
  that after #162 landed, the baseline shows **no open prose gap in
  `implement-ticket` itself** — its five confirmed gaps were all corrected
  there, confirmed by the eight real-model runs recorded since, and the three
  that remain open belong to `implement-epic`, filed as #214 and #215. The
  corpus defects are filed as #216, #217, and #218. The measurement question
  #151 asked be settled first was settled by a new `recognition_probe.py`, which
  re-presents a case's identical result-blind packet and asks whether a *named*
  obligation applies, using that case's own forbidden actions as controls: of
  fourteen probed missing-action failures, six were recognized the instant the
  obligation was named, and the forbidden-action class split the same way under
  the converse probe — in all three `invoke_ready_to_merge` cases the model
  asserts the forbidden action applies while rejecting
  `invoke_merge_when_ready`, so it is picking the exact policy the handoff
  mapping assigns rather than over-emitting. A single-variable rename probe was
  sharper still: presenting `caller_verifies_mainline_tracker_cleanup` as
  `verify_mainline_tracker_cleanup` and changing nothing else took recognition
  from 1 of 3 to 3 of 3 and control rejection from 6 of 8 to 8 of 8, so one
  confusing term had been degrading whole answers. Acting on that,
  `claude_executor.py` was changed to elicit one explicit boolean per vocabulary
  name instead of free recall of "every applicable value" — and the recorded
  before/after pair says it did not work: 34/58 → 35/58, inside the 30–34 band
  the ten prior runs already occupied, with two of the six targeted lines
  regressing and none improving. The change is reverted and the negative result
  is the finding, because it localizes the defect to list length rather than
  response format: the probe presents about five names and the executor about
  110, and that is the only difference between where recognition works and where
  it does not. A shortlist would fix those six lines and cannot be built without
  reading the expectation, so the corpus-design question is filed as #219 rather
  than guessed at. No skill prose is edited here, and no expectation is tuned.

- docs: correct the eval-evidence norm's scope statement for the review-lens
  skills (42b52102530563ead17a1c17db227f32d50954f7) — `AGENTS.md` told an author
  editing `review-code-change`, `review-correctness`, `review-code-simplicity`,
  or `review-solution-simplicity` that the skill had no corpus at all, when
  `review-suite/evals/` ships seven corpora (one under `corpus/`, six under
  `strata/`) naming `review-code-change`, `review-code-simplicity`, or
  `review-solution-simplicity` as `target_skill` — `review-correctness`'s prose
  reaches the reviewer as a `target_skill_dependency` of the
  `review-code-change`-targeted corpora rather than as a directly named target.
  The recorder just can't drive any of them, because the runner's
  `--artifact-dir`, `--attempts-out`, and `--report-out` don't match the
  `--output-dir` interface `just eval-record` appends, and its exit codes report
  evaluation integrity rather than case outcomes. The bullet now names that
  interface gap instead of asserting a false absence, so a review-lens author is
  told the accurate reason `just eval-record` can't record a run rather than
  instructed to assert a corpus doesn't exist. Adapting the runner to the
  recorder's interface remains unregistered follow-up work, not done here.

## 2026-08-12 — Ran the writing-plans altitude experiment and found the peer preserves surface altitude rather than translating it down, closed the last gap between what the eval harness asserts and what any skill's prose defines, and settled how the shaping doctrine gets its authority: a bundled synced contract, not a new skill

- docs: record the writing-plans behavioral-altitude experiment
  (60092411e2e5cf8edeea938a0077047e524d60be) — the design document posted this
  run as owed rather than answered, and it is now answered for one session at
  pin `44c9b2d6e889982ac18c27d05a19fefe335194e1`. Handed a greenfield spec whose
  seven acceptance criteria are stated purely as exit codes and stdout text,
  `superpowers:writing-plans` returned a 1,363-line plan that misses the
  approved criterion, which is conjunctive: all six Interfaces blocks name
  internal function signatures with parameter and return types. That half is a
  fixed property of the skill's own task template, which specifies the block as
  "exact function names, parameter and return types" for a subagent executor
  that sees only its own task — so no better-written spec removes it. The second
  half came back mixed, and the distinction carries the finding: 8 of 24 planned
  tests drive the installed console script through a subprocess and 16 call
  imported functions, but every one of the spec's seven criteria landed in those
  8, confirmed by a criterion-to-test table the plan's own self-review produced.
  The peer did not translate the spec down to unit altitude; it preserved that
  altitude and added a lower tier beneath it, which is the hypothesis the design
  document recorded. The run was dispatched into a context told nothing about
  the experiment or its criterion, because a context that knows what is being
  measured returns confirmation rather than observation. The spec and the full
  returned plan are committed beside the report: a rerun re-tests the question
  but will not regenerate this artifact, so the claims are auditable only
  against what actually returned. Take-it-as-is, post-process, and
  structure-only remain unselected — one run does not decide between them, and
  this ticket did not authorize the choice.

- test: hold every eval corpus to the terminal states its skill's prose defines
  (a78141587b923d140fa41c5ca3c876ca2d740861) — a corpus state no prose names is
  unreachable for a model given only the skill prompt, so the case grades
  whichever deterministic stand-in was written knowing the expected string
  rather than the prose the evaluation exists to check. `implement-epic`'s own
  corpus carried eleven such labels (`waiting_for_child_merge`,
  `epic_children_merged`, `closeout_blocked`, `umbrella_open`, and seven more)
  as required terminal states, alongside two the prose does define;
  `ready-ticket`'s corpus already drew only on its four documented states, which
  is the shape the others now match. Each of the fifteen affected cases maps
  through the rule "Report the epic result" already states — a stop condition
  means `blocked`, otherwise `mixed_ticket_results` — and the
  authorized-closeout case records `null`, because that section reports a
  closeout through closeout evidence rather than a single-word label. No
  scenario detail is lost: `required_actions` already carried it, and the
  boundary each case protects is now pinned there instead of in a bespoke label.
  A new repository-root test enforces the invariant over every harness surface
  it discovers by glob rather than by name — all eight case corpora across six
  skills, each attributed per target skill; both `claude_executor.py`
  vocabularies, which are what a real-model run shows the evaluated model; and
  all three `fixture_executor.py` deterministic stand-ins, whose emitted states
  must stay inside the vocabulary a real packet is actually offered. A corpus
  recording its outcome under a key the test cannot read fails the suite instead
  of being silently exempt, which is what an earlier draft did to
  `review-code-change`'s twelve nested `result.verdict` cases.
  `mixed_ticket_results` itself, the state that prompted this, was defined in
  `implement-epic`'s prose by #162; this is what keeps the next one from
  reaching the harness undefined.

- docs: decide the shaping authority mechanism
  (0c2d94c9b027373cc42e6742654945a0eedbecfb) — the design record told a reader
  the cited-versus-called framing was contested and that Spec B "should not be
  built until that alternative is argued down or adopted," which left every
  downstream leaf waiting on a question nobody had answered. The bundled synced
  contract is adopted: canonical doctrine text distributed by stable path and
  mechanically drift-checked, with no new skill. The `review-suite`
  counterexample holds and draws the line the brief missed — there, the synced
  text carries the contract and the skills carry the verdict — so the question
  was never which mechanism is legitimate but whether any caller has
  demonstrated it needs a verdict, and none has. The publication size gate is
  the strongest candidate and already runs the contract mechanism without
  failing. The executable verdict and the fourth review lens are rejected with
  reasons, the telemetry-first ordering is adopted alongside, Spec C's planner
  alternative is left open, and every downstream leaf carries a disposition:
  #190 and #191 superseded, #192 and #193 re-cut against the bundled doctrine,
  #194 and #195 activated. The decision is reversible on the telemetry it keeps.
  A new contract test holds all of it against both the canonical Markdown and
  its HTML presentation copy, which is what makes their equivalence checkable.

## 2026-08-11 — Gave the cognitive-shaping doctrine a single canonical home in compris, and made recorded evidence reproducible by a later reader: named the tree and model an eval summary measured, and made the root test suite import under the invocation ticket bodies actually name

- fix: make every `scripts/tests/` module import under the module-path
  invocation, not only under discovery
  (e906fb92b9a2c1df56562c2b1ab71daf34063203) — each module took its sibling
  `helpers.py` on the `sys.path` entry `unittest discover` happens to supply, so
  `python3 -m unittest scripts.tests.test_skill_authoring_doc`, the form ticket
  bodies keep naming as required pre-merge verification (#186 did), errored with
  `ModuleNotFoundError: No module named 'helpers'` before any assertion ran, and
  a later reader running the criterion verbatim could not reproduce the recorded
  evidence. Each module now establishes its own `__file__`-relative entry, the
  convention `review-suite/scripts/tests/` already used, and
  `test_suite_invocation.py` holds the suite to it by importing every module
  from the repository root with `PYTHONPATH` stripped. Pre-existing since
  5431e75; `carve-changesets` and `review-fix-loop` carry the same defect and
  stay discovery-only for now.

- docs: publish the canonical cognitive-shaping doctrine
  (5c45cd2b9b9137f985b9e5e9d343894553efc1cd) —
  `docs/cognitive-shaping-doctrine.md` is now the one place the standard that
  decides whether a unit of work is comprehensible is stated. It carries the
  mental-model test at its fixed wording, all eight breakdown rules, the
  logical-to-realized vocabulary, policy-controlled enforcement that separates
  judging shape from gating on it, and the exclusion of recorded
  machine-generated eval evidence from shape judgment. No numeric line-count
  gate is presented as correctness policy, and no skill behavior changes here —
  binding each consumer to it is tracked separately.
  (5c45cd2b9b9137f985b9e5e9d343894553efc1cd)

- fix: record the candidate's git tree hash and, for real-model runs, the pinned
  model name in every recorded eval summary — `candidate.sha` names a branch
  commit that rebase rewrites and squash-merge discards outright, so no summary
  merged so far names a SHA a fresh clone can resolve, and the recorder never
  named which model actually produced a real-model run, so a before/after diff
  taken across a model update silently compared two different subjects wearing
  the same tier name. `candidate.tree` resolves under both rewrites, every
  real-model executor invocation now passes an explicit `--model claude-opus-5`
  instead of relying on an environment default, and a diff is drawn only between
  runs whose tier, suite, and model all match. Summaries recorded before this
  change carry no model at all and are documented as branch-local and
  unattributed rather than backfilled.
  (fc7cf9ba04f5b4781ee3db037fed57d55c4a77be)

## 2026-08-09 — Recorded the cognitive-driven development direction: compris takes sole ownership of the cognitive-shaping doctrine from atelier, moves the boundary from "planning is done" to "brainstorming is done", and renames ready-ticket to plan-implementation

- docs: drop the hosted link from the cognitive-driven development design — the
  Markdown pointed at a claude.ai-hosted rendering of itself, which is an
  external dependency the repository does not control, cannot version, and
  cannot guarantee stays reachable or in step. The committed
  `cognitive-driven-development.html` is the presentation copy, and it travels
  with the document in the same history and the same review.
  (308b6212f5bf6b23854da340b25ee1d63320dad2)

- docs: commit the presentation copy of the cognitive-driven development design
  and link it from the Markdown — the rendered brief existed only as a published
  artifact, outside version control, which had already let the two drift twice
  in one session: once when several rounds of edits landed in the Markdown
  alone, and once when the artifact was republished with a description promising
  content its HTML did not contain. `docs/cognitive-driven-development.html` now
  sits beside the Markdown and is the file the artifact is published from,
  wrapped as a standalone document so it also renders when opened directly; the
  Artifact renderer supplies its own wrapper, so publishing strips this one. The
  Markdown states which is canonical for review and that both change together.
  `just format` covers only Python and Markdown, so the HTML is not reformatted
  and the committed copy stays byte-comparable with what gets published
  (308b6212f5bf6b23854da340b25ee1d63320dad2)

- docs: make cognitive shaping a policy-governed default and state the program's
  motive honestly — not every project demands cognitively shaped pull requests.
  A project may legitimately want compris for ticket authoring and delivery
  automation while declining to be gated on shape, and compris itself is one
  such project today. The invariant is therefore a default rather than a law:
  the shaper always judges and the consuming project decides whether an
  `exceeds` verdict gates anything, which needs no new policy machinery because
  the shaper's read-only stance already separates judgment from enforcement.
  That also corrects an overclaim made while gathering failure-first evidence:
  this repository's merged-PR churn (median 1,253 lines, max 7,829) and the fact
  that `carve-changesets` has never carved anything here were presented as
  observed failure, when both are the deliberate exercise of that latitude. The
  brief now states plainly that the program is capability-driven, not
  failure-driven. Two findings survive the correction, both from real data
  rather than principle: recorded machine-generated evidence must be excluded
  from shape judgment, since PR #179 is 4,715 lines of churn of which 4,538 is
  committed eval results and the reviewable change is 177 lines — a raw-churn
  metric would reject a small change precisely because the eval norm requires
  its evidence committed; and the retrospective merged-history corpus is
  buildable today against `git log`, which is how the distortion was caught in
  the first place (308b6212f5bf6b23854da340b25ee1d63320dad2)

- docs: decompose the cognitive-driven development brief into four specs and
  record the alternatives it never examined — a brainstorming pass over the
  committed design applied that skill's scope rule and found three dependency
  roots, three risk profiles and three definitions of done in one document. The
  tell was not the step count but that every reversal of standing repository
  doctrine sat in one step: #118's design-approval gate, granular default-off
  authority, `ready-ticket`'s no-additional-items rule, and the
  trigger-namespace rule. The brief is now Spec A (compris owns the doctrine —
  no new skills, no renames, no reversals, complete on its own), Spec B (an
  executable shaping verdict), Spec C (the planner, carrying every reversal),
  and Spec D (object model and migration, a live YAGNI candidate because both
  halves are conceded zero-behavior-change yet the migration triggers the
  eval-record obligation across three large skills while the brief forfeits the
  diff it produces). Also records three alternatives a long convergent
  conversation had left unexamined. The first is serious enough to gate Spec B:
  the brief argued "a document gets cited; a skill gets called" and concluded
  only a skill makes doctrine enforceable, but that is a false binary and the
  counterexample was already in the tree — `review-suite/` distributes canonical
  normative text, including a ported peer doctrine, via `just sync-contracts`
  into three consumers' `references/`, drift-checked by `just check-installed`.
  Spec B is not to be built until that is argued down or adopted. The document
  reaching this conclusion is the invariant working on itself: it exceeded one
  reviewable unit and had to become several separately trackable things, decided
  by the rule it proposes for everything else
  (308b6212f5bf6b23854da340b25ee1d63320dad2)

- docs: record that the peer pin is marketplace release 6.2.0, and re-sync the
  published brief — the superpowers plugin turned out to be installed after all,
  just after this session resolved its skill listing, so the pin could finally
  be checked against what a user actually receives. It matches: the installed
  plugin and the pinned checkout carry the same fourteen skills, and
  `writing-plans` and `brainstorming` — the two every finding in the design
  rests on — are byte-identical between them. Recording the release alongside
  the SHA makes the pin resolvable by a reader who cannot run `git`, and it
  retires the document's last unverified assumption about its own evidence. Also
  fixes three defects the eight-step renumbering introduced: two internal
  cross-references pointing at the wrong steps, and a stale "four skills'
  separate corpora" that should have followed the four-judges-to-three
  correction. The published brief is regenerated from the committed markdown
  rather than patched, so the two no longer drift
  (308b6212f5bf6b23854da340b25ee1d63320dad2)

- docs: bolster the cognitive-driven development design against an adversarial
  read — an independent reviewer checked the committed document against the
  repository's own contracts and found seventeen problems, all verified before
  acting. Four needed decisions and are now recorded. `initiative` and `epic`
  are kept as a mapped pair rather than one replacing the other: an initiative
  is the logical grouping the breakdown derives, an epic is its tracker
  realization, and compris keeps `implement-epic`'s authoritative parent (its
  own acceptance ledger and closeout gate) instead of overwriting it with
  atelier's lighter non-authoritative grouping. The invariant is restated as a
  prediction rather than an identity, because `implement-ticket` ships
  `ready_prs` — one ticket, an authorized carved stack, several pull requests —
  so a carved stack is a recorded falsification, not a violation. The breakdown
  becomes house-owned and complete without a peer, since
  `docs/skill-authoring.md:598` forbids depending on one; `writing-plans`
  supplies the richer method when present, and the cost of maintaining both
  paths is named. Ticket-graph creation stays an approval gate that may be
  pre-approved at invocation, at which point the presentation becomes disclosure
  — which is also what makes autonomous graph creation possible, since an
  autonomous run has nobody to ask. Thirteen further corrections: the extraction
  premise dropped from four independent judges to three, because
  `implement-ticket:632-635` already reads `carve-changesets`' live guardrails
  and is forbidden to substitute local heuristics — it is the pattern's
  precedent, not an instance of the problem; a new program step wires the
  doctrine in and retires `carve-changesets/references/SPEC.md`'s own guardrails
  so the doctrine replaces codifications rather than becoming a fifth; another
  revises `docs/skill-authoring.md` and `README.md`, whose composition rule 1
  asserts a mechanism that stops being true; the shaper contract gains a closed
  terminal-state set with `blocked` as its honest fallback; the rubric now
  accounts for all eight breakdown rules, recording that rule 8 is not gradeable
  at plan time; and two citations of mine were wrong — `implement-epic:186` was
  correct when written and rotted in the rebase, while the triggering-corpus row
  cited a refuted observation rather than `triggering/expectations.json:130`,
  where the case is a *negative* owned by `review-code-change` that cannot
  simply be flipped without destroying that skill's coverage
  (308b6212f5bf6b23854da340b25ee1d63320dad2)

- docs: settle the shaping rubric and reframe the altitude question as an
  experiment — the shaping corpus grades seams rather than partitions, because
  two good decompositions of the same work agree on where the seams are and
  disagree on how they group, so partition equality rejects correct answers and
  accepts cuts through the middle of a concern. The eight breakdown rules sort
  by kind: three are mechanically checkable and need no judge (one-child count
  plus a stated reason, re-split trigger presence, the fits-as-one case),
  halving the judge surface and keeping most of the corpus deterministic. Each
  case is built around a specific trap, since a corpus that only rewards good
  answers measures little; the merged-PR history supplies free labeled data,
  where work whose shape held is a positive and work that had to be carved is a
  negative already annotated by the carving; judges are perspective-diverse
  rather than redundant; and no numeric score is emitted, because the doctrine
  retired numeric heuristics and per-rule pass/fail with recorded observations
  is what `AGENTS.md` already asks for. Separately, the `writing-plans` altitude
  question moves from an open question to a recorded experiment with a named run
  and success criterion — nobody owes an answer there, someone owes a run — with
  the three-way contingency deliberately left un-pre-decided until it reports
  (308b6212f5bf6b23854da340b25ee1d63320dad2)

- docs: record the cognitive-driven development design — compris is
  ticket-driven because work spanning more than one pull request has exceeded a
  local plan's grasp and needs durable, public representation. The document
  establishes the invariant that every leaf ticket is scoped to exactly one
  cognitively shaped changeset, ports atelier's human-shaped-changeset test
  verbatim ("whether a reviewer can construct an accurate mental model of the
  change and evaluate it independently") along with its eight breakdown rules,
  and takes sole ownership of both from `shaug/atelier`, which is moving toward
  multi-agent process management and model routing — a doctrine with two homes
  has no home. Half the vocabulary comes with it: `changeset` and `initiative`,
  which atelier's own layer diagram already places on the compris side, while
  `assignment`, `claim`, `receipt` and `worker` stay in its process layer.
  Records eight decisions with their reasoning, eight verified findings against
  `obra/superpowers` at pin `44c9b2d6`, and two open questions. Load-bearing
  verification falsified three assumptions during authoring: `writing-plans`
  reads no spec from disk, supplies no pull-request sizing verdict, and ships a
  dangling plan reviewer — so sizing is house-owned outright and the house
  reviewer is required rather than optional. Nothing is implemented; the
  doctrine document and the object model document are the first two steps of the
  recorded six-step program (308b6212f5bf6b23854da340b25ee1d63320dad2)

## 2026-08-08 — Hardened implement-ticket's own worktree isolation mechanics, added version-bump tooling, release notes, and a documented release process, then repositioned marketplace metadata and the README lead as the outer-loop companion to superpowers, then deduplicated the byte-identical `compact()` test helper into `scripts/tests/helpers.py`

- refactor: deduplicate the byte-identical `compact()` whitespace-collapsing
  helper that `test_peer_composition_readme.py`, `test_skill_authoring_doc.py`,
  `test_release_docs.py`, and `test_marketplace_positioning.py` each
  independently defined — moved it into the shared `scripts/tests/helpers.py`
  (following the same `helpers.py`-per-test-directory convention already used by
  `skills/carve-changesets/scripts/tests/helpers.py` and
  `skills/review-fix-loop/scripts/tests/helpers.py`) and updated all four
  callers to import it instead. Dropped the now-unused `import re` in the three
  files where `compact()` was the only user of the module; kept it in
  `test_peer_composition_readme.py`, which still calls `re.search` elsewhere.
  Flagged as a non-gating `defer`-severity finding by review-code-change's
  code-simplicity lens while reviewing #139; out of that PR's scope, fixed
  separately here. Pure deduplication, no behavior change — all four files'
  existing tests pass unchanged; `just format`/`just lint`/`just test` all
  green. (5431e75c9c3b4525f4b98b69999c05bc2092bdca)

- feat: reposition marketplace metadata and the README lead as the outer-loop
  companion to superpowers (issue #139, epic #121) — the "Using beside peer
  skills" README section already stated the outer-loop/inner-loop division of
  labor, but nothing surfaced that framing where a prospective user first looks:
  the README lead and the four plugin/marketplace description surfaces. Adds a
  "Where it composes" lead paragraph naming superpowers explicitly, stating the
  "fully functional without a peer installed" guarantee, and linking
  `#using-beside-peer-skills`. Updates `.claude-plugin/plugin.json`,
  `.codex-plugin/plugin.json` (both its top-level `description` and its
  `interface.longDescription`), and `.claude-plugin/marketplace.json` (both
  `metadata.description` and the `compris` plugin entry's `description`) to the
  same "ticket-to-merge outer loop... composes with, not depends on, inner-loop
  methodology libraries such as superpowers" positioning; ticket body referred
  to the project by its pre-rename name `agent-scripts`, so the copy uses the
  current name `compris` throughout, verified against the actual repository
  identity rather than copied verbatim. `.agents/plugins/marketplace.json`
  carries no description-shaped field in its current schema, so it is unchanged
  — its plugin entry gained a `version` field under #138, and the other three
  surfaces already carry this ticket's positioning. New
  `scripts/tests/test_marketplace_positioning.py` pins the outer-loop framing,
  the superpowers mention, and the compose/depend contrast across the README
  lead and all four description surfaces. Docs/config-only change — no
  behavioral test beyond the new structural pins; `just lint`/`just test` both
  green. (b42eda34761fe375f0352bed98c551e905cbf398)

- feat: add version-bump tooling, cross-manifest drift detection, narrative
  release notes, and a documented release process (issue #138, epic #121) —
  `scripts/bump_version.py` is the only tool that should change any of the four
  version surfaces (`.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`, `.agents/plugins/marketplace.json`; the two
  marketplace catalogs previously carried no version at all). It reads the
  current version from the two plugin manifests, computes a
  `--bump major|minor|patch` or explicit `--to` target, and writes all four in
  one pass, restoring already-written surfaces if a later write fails so a
  partial bump never lands. `scripts/validate_plugins.py`'s existing
  Claude/Codex plugin-version match check (already wired into `just lint`) is
  extended to require a valid semver on both marketplace catalogs' plugin
  entries too and to reject drift across all four, not just the original two.
  `RELEASE-NOTES.md` is new: the narrative history of tagged releases (what
  changed, why, evidence — distinct from this file's daily commit journal), with
  its format documented at the top of the file. `docs/release-process.md`
  documents the version-surface table, the bump-script usage, and that cutting
  the git tag and GitHub release is reserved for the operator — preparing a
  release is ordinary PR-completion authority, cutting it is not, and no
  automation in the repository performs that step. `AGENTS.md`'s Git Workflow
  section gets a pointer to the new doc. The ticket's own acceptance criterion
  for a recorded dry run is this change's real diff:
  `python3 scripts/bump_version.py --bump patch` was run for real on this
  branch, bumping every surface from `0.1.0` to `0.1.1` (seeding the two
  marketplace catalogs' version field for the first time in the same pass), with
  `just lint` and `just test` green at the resulting head and no git tag cut —
  recorded as the first `RELEASE-NOTES.md` entry. Cutting the first real tagged
  release stays a separate, explicit operator action; this ticket's non-goals
  explicitly exclude it. (a55c2cc425335470962a846c3b4d252877d089e8)

- feat(implement-ticket): harden worktree isolation mechanics (issue #134, epic
  #119) — implement-ticket's own "Create exclusive implementation state" step
  was generic ("create one feature branch and clean isolated worktree from the
  verified base"), with no concrete placement, safety-guard, or cleanup
  mechanics, exactly the gap #133's adjacent skills (`implement-epic`,
  `carve-changesets`, `babysit-pr`) already closed for their own workspace
  conventions — #133 explicitly left `implement-ticket` itself untouched, so
  this is that skill's first own change in the epic. New
  `references/worktree-isolation.md` states each mechanic with its failure mode:
  prefer a native harness worktree/isolation tool when present, since a raw
  `git worktree add` underneath a harness with its own tracking is invisible to
  that tracking (phantom state); fall back to branch-only isolation, recorded
  explicitly as degraded evidence, when the environment denies worktree
  creation, rather than either stalling or silently claiming full isolation;
  choose the worktree directory by precedence (an explicit caller/coordinator
  location, then an existing convention directory, then a default), surfacing
  any novel placement instead of letting it pass unremarked; guard the intended
  path with the submodule check
  (`git rev-parse --show-superproject-working-tree`, preventing worktree
  metadata from binding to the wrong `.git` structure) and the ignore check
  (`git check-ignore -v`, preventing placement somewhere routine ignored-file
  cleanup could delete the worktree without going through
  `git worktree remove`'s own safety checks); run the ticket's approved focused
  validation against the fresh worktree at the verified base before any
  implementation edit, so a broken baseline is never silently blamed on the
  change; and scope cleanup to the exact worktree this run itself created at its
  recorded path, never a naming-pattern sweep of a shared convention directory
  that could delete a concurrent or unrelated run's worktree. `SKILL.md` gets an
  "Always read" entry for the new reference alongside the other
  unconditionally-loaded handoffs, plus a step-1 pointer;
  `references/cleanup-and-result.md`'s worktree-removal step now points at the
  new file's provenance-scoped-cleanup section instead of restating it (one
  owner per rule). `scripts/tests/test_implement_ticket_contract.py` is
  extended, not replaced, with five new tests pinning the reference wiring,
  every required mechanic/failure-mode phrase, and the cleanup cross-reference —
  full contract suite 111/111 passing. Ported with attribution from superpowers'
  `using-git-worktrees` per the named-peer registry's existing entry for this
  seam.

  This ticket rewrites the exact mechanics this dispatch itself used to create
  its own worktree, so it was executed reflexively: the worktree for this work
  was created using implement-ticket's pre-change prose (confirm primary
  checkout/registered worktrees, fetch, `git branch` + `git worktree add` from
  the verified base) rather than bootstrapping through the not-yet-written new
  prose.

  Eval evidence: the real-model tier ran both before and after this change,
  before bound to this branch's parent `bb02ae0` and after bound to `756ba31`,
  this candidate's implementation commit — 34/58 before, 30/58 after. A first
  before-eval attempt was invalidated and discarded rather than kept: it was
  recorded while the worktree was still being edited concurrently in the
  background, so its own `candidate.worktree_clean: false` correctly flagged
  contamination risk, since the executor reads live skill files per case and a
  mid-run edit can leak into whichever cases ran after it; re-recorded from a
  `git stash`-clean tree with no concurrent edits. Comparing the valid
  before/after pair: 7 cases move to newly-failing and 3 to newly-passing
  against 48 unchanged. None of the 7 newly-failing cases' required or forbidden
  actions concern worktree, isolation, native-tool preference, either guard, or
  cleanup provenance — the only surface this diff touches. Two of the seven
  (`epic-incompatible-implement-ticket`,
  `implement-epic-consumes-ticket-results`) target `implement-epic`, a skill
  this diff never touches at all, so those two cannot be caused by this change
  by construction — the same "run varies, diff doesn't touch it" pattern #129's
  and #133's real-model evidence already documented for this corpus. The
  remaining five probe untrusted-content handling, cross-tracker separation, and
  malformed-result rejection, topically unrelated to this diff's content.
  Recorded as corpus noise rather than a candidate defect, per the ticket's own
  guidance against chasing single-sample real-model variance.
  (e509ab51491b044be981246985b635a99ff29026)

## 2026-08-07 — Migrated carve-changesets' per-changeset review/fix loop and babysit-pr's post-publication review/fix loop to delegate to review-fix-loop, completing the design's caller-migration sequence, then added rationalization tables to babysit-pr, implement-ticket, and carve-changesets, then added a compaction-resilient ledger and workspace-per-run to implement-epic, carve-changesets, and babysit-pr

- feat(skills): add compaction ledger and workspace-per-run to implement-epic,
  carve-changesets, and babysit-pr (issue #133, epic #119) — give each of the
  three skills a skill-local, append-only ledger keyed by its own target unit
  (epic id, source branch, or PR number), so a session resumed after a
  compaction finds the prior workspace deterministically instead of
  reconstructing it from recollection:
  `.implement-epic/<epic-key>/ledger.jsonl`,
  `.carve-changesets/<source-branch-slug>/ledger.jsonl`, and
  `.babysit-pr/<repo-pr-key>/ledger.jsonl`. Each ledger records one `session`
  line per session start and one `entry` line per verified per-unit outcome
  (child dispatch, changeset action, or feedback disposition/retry/fix), and
  each workspace self-excludes from git via its own internal `.gitignore` (`*`)
  written the first time anything is recorded, so exclusion never depends on the
  consuming repository's own ignore rules. A new `scripts/ledger.py` in each
  skill (unittest-covered: 22 new tests for `implement-epic`, 14 for
  `carve-changesets`, 23 for `babysit-pr`) provides
  `session-start`/`record`/`read`/`find` — `find` is the recovery-path dedup
  guard, returning the ledger's own latest claim for a unit filtered to that
  skill's completed terminal results, explicitly excluding `blocked` (and, for
  `babysit-pr`, `deferred`) so an unfinished unit is never suppressed from a
  fresh attempt. `babysit-pr`'s ledger additionally adds `reconcile`, comparing
  its ledger against `gh_pr_watch.py`'s own watcher state file (loaded via its
  existing `default_state_file_for`/`load_state`, never duplicated) to surface
  retry-count drift without either store overriding the other — the watcher
  state file remains the authoritative retry-budget enforcement, unchanged. Each
  skill's `SKILL.md` documents the workspace layout, ledger format, and recovery
  rule via a new `references/ledger.md` and is wired into its existing workflow:
  `implement-epic`'s graph loop checks the dedup guard before selecting a child
  and records an entry after verifying a terminal result; `carve-changesets`'s
  phase workflow checks per changeset before delegating to `review-fix-loop` and
  records an entry after each phase's own terminal result; `babysit-pr` records
  a disposition after each reply/resolution, a retry after each accepted retry,
  and a fix after each `review-fix-loop` publish, reconciling both stores at
  session start. The recovery rule is explicit in all three that the ledger is a
  dedup guard only, never proof: a claimed-complete unit is still verified
  against live tracker/git/PR state before a resumed session skips
  re-dispatching it. `implement-ticket` is explicitly out of scope (its own
  worktree hardening is sibling issue #134, not yet started).

  A fresh `review-code-change` pass raised one `strong_recommendation`
  solution-simplicity finding: the three skills' `ledger.py` modules were ~90%
  structurally identical with no automated signal against drift, despite this
  repository already having a working precedent for exactly this situation
  (`review-suite/` → bundled per-skill copies via `just sync-contracts`). Fixed
  by extracting the shared mechanics — workspace derivation and self-exclusion,
  append-only I/O, and the recovery-path dedup guard — into a new canonical
  `ledger/core.py`, bundled byte-identically into each skill as
  `scripts/ledger_core.py` by an extended `sync-contracts` recipe; each skill's
  own `ledger.py` is now a thin wrapper fixing the core's generic parameters to
  that skill's vocabulary and keeping only what is genuinely skill-specific (CLI
  flag names, each skill's completed- terminal-results set, and `babysit-pr`'s
  watcher-state reconciliation, which has no analog in the other two). A second
  `strong_recommendation` finding — dropping the `session` ledger-record kind
  because no recovery function consumes it — was independently verified against
  the live issue #133 body, which explicitly requires "a session identity line
  appended at each session start" as part of the ledger format, and was rejected
  as out of the ticket's scope rather than implemented.

  A second fresh `review-code-change` pass raised two `strong_recommendation`
  correctness findings, both fixed: (1) `carve-changesets`'s
  `already_recorded_complete` had no `action` scoping, so a later `publish` or
  `merge` entry for a changeset could mask an earlier `converged`
  `review_fix_loop` entry and trigger needless re-delegation on resume — fixed
  by adding an `action` parameter (mirroring `babysit-pr`'s existing
  `already_dispositioned` pattern) and, while implementing it, catching a deeper
  instance of the same bug in the shared `ledger_core.already_recorded_complete`
  itself: it filtered only the already-selected globally-latest entry rather
  than searching for the latest entry actually matching the requested action, so
  an unrelated later entry could still mask a real completion even with the
  filter supplied — fixed in `ledger/core.py` (and therefore in all three skills
  at once), with a new regression test in each of `carve-changesets` and
  `babysit-pr` proving the earlier, correct entry is now found past a later,
  different-action one. (2) `babysit-pr/references/ledger.md`'s "Recovery rule"
  step 1 named a path (`.babysit-pr/<repo-slug>-pr<number>/`) that didn't match
  the "Workspace layout" section's own example (`example-project-482/`, no
  literal `-pr`) — fixed to match.

  A third fresh `review-code-change` pass raised one `blocking` correctness
  finding: `babysit-pr/SKILL.md`'s retry-recording instruction told the agent to
  record `action: retry` with `item_id` set to the head SHA, but never said to
  also populate the separate `head_sha` field the way the parallel `fix_pushed`
  instruction already did — since `reconcile_with_watcher_state` keys strictly
  off `head_sha` with no fallback to `item_id`, an entry recorded per the
  unfixed instruction was invisible to the retry-mismatch check, so a resumed
  session could get a false-clean reconciliation report even with actual
  retry-budget drift. Fixed by adding "`head_sha` the same value" to the
  instruction and a matching clarification to `references/ledger.md`'s ledger
  format table.

  A fourth fresh `review-code-change` pass raised one `strong_recommendation`
  correctness finding: `babysit-pr`'s `unit_key_for(repo, pr_number)` composed
  the workspace key as `f"{repo.lower()}#{pr_number}"`, and `slugify` collapses
  both `/` (common inside `owner/repo`) and `#` to the same `-`, so
  `octocat/hello-world#482` and `octocat-hello/world#482` both produced the
  identical slug — silently merging two distinct repositories' ledgers onto one
  workspace, exactly the collision class `gh_pr_watch.default_state_file_for`'s
  own sibling keying function already guards against with an 8-hex-digit digest
  of the exact repo string. Fixed by applying the identical digest fix to
  `unit_key_for`, with a new regression test and updated `references/ledger.md`
  examples. The same pass's non-gating `defer` finding — no committed test would
  catch future drift between `ledger/core.py` and its three bundled
  `ledger_core.py` copies, unlike the `review-suite/` precedent this candidate
  cites — was also addressed: a new
  `ledger/scripts/tests/test_bundled_copies.py` mirrors
  `review-suite/scripts/tests/test_bundled_contracts.py`'s drift check, wired
  into `just test` via `justfile`.

  A fifth fresh `review-code-change` pass raised one more
  `strong_recommendation` correctness finding, the same collision class already
  fixed for `babysit-pr` in this candidate's own history, now found in
  `carve-changesets`: `workspace_dir`/`ledger_path`/`ensure_workspace` passed
  the bare `source_branch` straight into `slugify`, so `feature/api-timeout` and
  `feature-api/timeout` both produced `feature-api-timeout` and would silently
  share one workspace. Fixed by adding a `carve-changesets`-side `unit_key_for`
  applying the identical digest fix, updating every call site
  (`record_session_start`, `record_entry`, `read_ledger`, plus the three path
  helpers) to compose through it, a new regression test, and matching
  `references/ledger.md` example updates.

  Having now found the identical collision class independently in two of the
  three skills across two separate review passes, the same digest fix was
  applied proactively to `implement-epic`'s `unit_key_for` too — ahead of a
  further review pass rather than waiting for a sixth one to name it — with its
  own regression test and matching `references/ledger.md` example updates, so
  all three skills now share one collision-safety story.

  A sixth fresh `review-code-change` pass raised one more
  `strong_recommendation` correctness finding, this one documentation-only:
  `carve-changesets`'s worked example printed a fabricated digest (`a1b2c3d4`)
  for `sha256("feature/cloud-host-migration")` rather than the actual value the
  shipped code produces (`700dac82`), while asserting the printed value was
  "deterministic for that exact branch name" — true of the real digest, false of
  the invented one. `babysit-pr`'s and `implement-epic`'s parallel examples were
  both independently confirmed correct. Fixed by substituting the actual
  computed digest.

  A seventh fresh `review-code-change` pass raised one more
  `strong_recommendation` correctness finding: `carve-changesets`'s "Publish"
  step told the agent to record a `publish`-action ledger entry "once its
  `babysit-pr` result is known" without pinning a literal `terminal_result`
  string, unlike the `merge` action right after it (`terminal_result: merged` is
  explicit there) — and `references/ledger.md`'s format section only gave an
  undifferentiated example list conflating whole-skill aggregate vocabulary with
  per-entry values. Since `DEFAULT_COMPLETED_TERMINAL_RESULTS` never includes
  `babysit-pr`'s own terminal states (`ready_to_merge`/`closed`), an agent
  following the doc literally could record a value the dedup guard never
  matches, silently defeating recovery dedup for the publish phase (safe
  direction: redundant re-delegation, not a false skip). Fixed by pinning
  explicit literals in both `SKILL.md`'s Publish step and a new per-action
  vocabulary table in `references/ledger.md`: `publish` translates a
  `babysit-pr` `ready_to_merge` result to `terminal_result: prs_open` (or
  `blocked` from `blocked`/`closed`), mirroring how `merge` already translates
  `babysit-pr`'s `merged` result to the same literal.

  An eighth fresh `review-code-change` pass raised one more `blocking`
  correctness finding: `babysit-pr`'s `reconcile_with_watcher_state` computed
  `dispositioned_feedback_ids` as an existential OR across an item's *entire*
  entry history, rather than checking only its *latest* `feedback_disposition`
  entry the way `already_dispositioned` correctly does — an item fixed and later
  reopened (e.g. a regression) and deferred would still report as closed,
  because a prior entry was once `fixed`, contradicting `references/ledger.md`'s
  own claim that the two sets agree. Fixed by deriving
  `dispositioned_feedback_ids` through `already_dispositioned` itself (one
  latest-entry check per candidate item id) instead of a separate history-wide
  set comprehension, with a new regression test proving a fixed-then-deferred
  item now correctly reports as open.

  A ninth fresh `review-code-change` pass (solution simplicity and correctness
  both clean) raised one `strong_recommendation` code-simplicity finding:
  `carve-changesets`'s `DEFAULT_COMPLETED_TERMINAL_RESULTS` included
  `chain_ready` and `all_merged`, but `references/ledger.md`'s own per-action
  vocabulary table documents only `converged`/`prs_open`/`merged` (or `blocked`)
  as values any recorded action actually writes — `chain_ready`/`all_merged` are
  this skill's own whole-chain *return* values, never a per-entry
  `terminal_result`. Not a live bug (the guard simply never matched on them),
  but a latent trap: a future entry recorded under a mismatched action would
  have silently passed this completeness check instead of failing loudly. Fixed
  by shrinking the frozenset to `{"converged", "prs_open", "merged"}` and
  dropping the two values from every prose restatement (`ledger.py`'s module
  docstring and inline comment, `ledger.md`'s vocabulary summary and
  recovery-rule step 2).

  A tenth fresh `review-code-change` pass (solution simplicity and correctness
  both clean) raised one `strong_recommendation` code-simplicity finding:
  `babysit-pr/scripts/ledger.py` hand-wrote the identical "load a sibling script
  by path and register it in `sys.modules`" five- statement sequence twice —
  once for the bundled `ledger_core.py` (`_load_core`), once for
  `gh_pr_watch.py` (`_load_watcher_module`) — with only the module name and
  filename differing. Fixed by extracting one shared
  `_load_sibling_module(name, filename)` helper both now call, with
  `_load_watcher_module`'s intentional call-time (not import-time) loading
  preserved unchanged.

  An eleventh fresh `review-code-change` pass raised one more
  `strong_recommendation` correctness finding: `references/ledger.md`'s
  vocabulary table documented specific `terminal_result` values for the `retry`
  (`rerun`) and `fix_pushed` (`pushed`) actions, but the `SKILL.md` prose
  instructing the agent to record those two entry kinds never told it to pass
  `--terminal-result` — unlike `feedback_disposition`, which `SKILL.md` already
  pins explicitly. Since the CLI's `--terminal-result` defaults to `None`, an
  agent following `SKILL.md` literally would record both kinds with
  `terminal_result: null`, contradicting the reference doc. Currently inert (no
  shipped dedup check reads `terminal_result` for either action), but a doc that
  doesn't describe what the workflow it documents actually produces. Fixed by
  pinning `terminal_result: rerun` and `terminal_result: pushed` in the two
  `SKILL.md` instructions, and tightening `ledger.md`'s `retry` row from a vague
  "`rerun`, or the diagnosed classification" to the one literal value actually
  written.

  A twelfth fresh `review-code-change` pass (solution simplicity and correctness
  both clean) raised two more `strong_recommendation` code-simplicity findings,
  both fixed by extending the shared canonical core rather than the per-skill
  wrappers: (1) each skill's `_parse_evidence` CLI helper (`--evidence-json`
  decode-and-validate) was byte-for-byte identical across all three, unlike
  every other genuinely skill-specific piece of wrapper code, and sat outside
  the bundled-copy drift test's coverage; (2) each skill's `unit_key_for`
  independently hand-wrote the identical `hashlib.sha256(...).hexdigest()[:8]`
  collision-breaking formula (already used once more, pre-existing, in
  `babysit-pr`'s own `gh_pr_watch.default_state_file_for`), so the
  collision-avoidance guarantee depended on three independently maintained
  copies staying in sync with no structural check forcing agreement. Fixed by
  adding `parse_evidence_json`/`collision_safe_digest` to `ledger/core.py`
  (re-synced via `just sync-contracts`) and having every skill's `ledger.py`
  call through the shared core instead of reimplementing either; the existing
  `test_bundled_copies.py` drift test now also covers both.

  A thirteenth fresh `review-code-change` pass returned `clean` (no blocking or
  `strong_recommendation` finding across all three lenses), with one non-gating
  `defer` finding: the committed `carve-changesets` "after" eval run was bound
  to `57a38c3` (the first ledger commit), which predates two later SKILL.md
  obligations this candidate went on to add (`b01f88b`'s action-scoped dedup
  lookup, `9f12fed`'s pinned publish-action vocabulary) — so it never actually
  exercised the prose those two commits changed, even though the deterministic
  corpus doesn't read `SKILL.md` prose at all regardless. Addressed by
  re-recording `just eval-record carve-changesets --stage after` at this
  candidate's true final head, still 12/12 with an empty per-case diff against
  the stale run.

  A fourteenth fresh `review-code-change` pass (solution simplicity and
  correctness both clean) raised two more `strong_recommendation`
  code-simplicity findings, both fixed: (1) the generic core mechanics
  (workspace self-exclusion, append-only write/read, malformed-line/unknown-
  kind tolerance, latest-wins and action-scoped dedup) were independently
  re-verified in all three skills' `test_ledger.py` suites with only
  field-name/value substitutions, despite this repository's own precedent for
  avoiding exactly that in the identical bundling pattern
  (`review-suite/scripts/tests/test_contracts.py` holds the full behavioral
  suite once centrally; each consuming skill carries only a thin adherence
  test). Fixed by adding `ledger/scripts/tests/test_core.py` (28 tests against
  `ledger/core.py` directly, using arbitrary parameters rather than any one
  skill's vocabulary) and trimming each skill's own `test_ledger.py` to only
  what is genuinely skill-specific: `unit_key_for` composition and collision
  disambiguation, that skill's own completed-results/disposition vocabulary, CLI
  wiring, and (`babysit-pr` only) watcher-state reconciliation. (2)
  `ledger/core.py`'s `latest_entry` was wrapped identically in all three skills'
  `ledger.py` but had zero callers outside those wrappers and their own tests —
  no CLI subcommand, no `SKILL.md`/ `references` mention, and
  `already_recorded_complete` (the actual dedup mechanism) never called it
  internally. Fixed by removing it from `ledger/core.py` and all three wrappers,
  along with the tests that existed only to cover it.

  A fifteenth fresh `review-code-change` pass (solution simplicity and
  correctness both clean) raised one more `strong_recommendation`
  code-simplicity finding, the same "zero callers outside its own declaration"
  condition as the already-removed `latest_entry`: all three skills' `ledger.py`
  re-exported `LedgerReadResult = core.LedgerReadResult`, but nothing outside
  that declaration line referenced it anywhere in the repository. Fixed by
  deleting the three re-export lines.

  A sixteenth fresh `review-code-change` pass (solution simplicity clean) raised
  one more `strong_recommendation` correctness finding: this candidate's own
  `justfile` edit added `ledger/scripts/tests` to `just test`'s unit-test loop,
  but `.github/workflows/ci.yml`'s independent loop — which this repository's
  own precedent (the commit that added `triggering/tests` to both lists in
  lockstep) keeps in sync with `justfile`'s — was never updated, so the new
  suite would run locally but silently not run in CI. Fixed by adding
  `ledger/scripts/tests` to `ci.yml`'s loop and its companion "no tests found"
  message, mirroring the `justfile` edit exactly.

  Eval evidence: the deterministic tier for `carve-changesets` is unchanged
  before and after (12/12, empty per-case diff, confirmed against the final-head
  "after" run). The real-model tier for `implement-epic` (via
  `implement-ticket`'s executor, `--target-skill implement-epic`) ran once
  before this change (base `2d5fa604`, 10/15) and three times after, because the
  first two "after" runs were bound to intermediate heads a round 16/17 review
  pass correctly flagged as stale (`2026-08-08T014515Z-0013-after.json` at
  `57a38c3`, then `2026-08-08T172341Z-0014-after.json` at `2a10ceb`) before the
  third landed on this candidate's true final head
  (`2026-08-08T175524Z-0015-after.json`, 9/15). All three "after" runs total
  9-10/15 with **different specific cases failing each time** — direct,
  three-sample evidence of this corpus's own single-sample real-model variance
  for epic-acceptance-adjacent cases, not a regression tied to this diff: run
  `0013` (10/15) and the true `before` baseline disagree on zero cases
  (identical failure set); run `0014` (9/15) newly failed
  `epic-refreshes-after-blocked-merged-delivery` and
  `epic-unreadable-implement-ticket` relative to `before`; run `0015` (9/15,
  recorded after a clarifying prose fix — see the preceding commits) newly
  passed both of those two but newly failed two entirely different cases instead
  (`epic-third-party-implement-ticket`,
  `implement-epic-verifies-stacked-child`), landing at the same total.
  `epic-unreadable-implement-ticket` in particular exercises this skill's
  "Require the ticket skill" dependency-verification section, which this
  candidate's diff never touches at all — confirmed via the exact `git diff`
  hunk ranges — ruling out a causal link for that case specifically.
  `babysit-pr` has no registered forward-eval corpus;
  `just eval-record babysit-pr` reports that gap directly
  (`babysit-pr has no registered forward evaluations to record`) rather than
  recording something in its place, exactly as `AGENTS.md`'s norm anticipates.
  (bb02ae01d16faa9fde1f40407ae77db2096de633)

- feat(skills): add rationalization tables to babysit-pr, implement-ticket, and
  carve-changesets (issue #129, epic #119) — a bare prohibition leaves an agent
  free to construct an exception, and it almost always can; a rationalization
  table answers the specific excuse instead. Each of the three named skills gets
  a table containing the seed entries #129's own body certified from each
  skill's contract-emphasis points: a "trivial" fix does not exempt a candidate
  from re-validation, because a head change invalidates every head-bound gate by
  SHA rather than by how small the diff looks (`babysit-pr`); a CI failure
  "looking" flaky is not a diagnosis, because flaky classification requires log
  evidence and consumes the tracked retry budget (`babysit-pr`); completion
  language such as "finish it" does not independently grant merge,
  decomposition, deployment, or transition authority (`implement-ticket`); and
  one propagation's equivalence proof does not cover the next one, because each
  step rewrites a different downstream suffix against a different current base
  (`carve-changesets`). Ported with attribution from the superpowers pattern via
  the named-peer registry (#123). `implement-epic` is deliberately excluded per
  the ticket's own recorded rejection — its contract prose already covers the
  graph-refresh and trust-but-verify drift modes a table would otherwise defend.
  The admissible-evidence rule for future entries — an in-repo retrievable
  source only: a baseline transcript, an eval fixture failure, a GitHub PR
  review history entry, or a recorded eval-results observation, with review
  excluding a speculative one — lives once in `docs/skill-authoring.md` beside
  the taxonomy's existing rationalization-table guidance, since it governs how a
  contributor extends a table later rather than something an agent executing the
  skill reads on every run, and folds in `skills/ready-ticket/SKILL.md`'s
  pre-existing table (sourced from a baseline transcript) as the in-repo
  exemplar. Six new prose-contract test methods across four files — one per
  skill pinning that skill's table content and its seed entry's own citation,
  plus three in `docs/skill-authoring.md`'s own new test file pinning the
  admissible-evidence rule's wording, placement, and reconciliation with the
  baseline exemplar — each independently observed failing when run against the
  unmodified base `20d05b0` and passing at head
  (2d5fa6041825cc5161d4300f9b3056b948bd8029)

  Eval evidence: the deterministic tier for `carve-changesets` is unchanged
  before and after (12/12, empty per-case diff) — the corpus reads only the
  skill's `SKILL.md` and exercises routing/readiness/authority scenarios, not a
  rationalization table's content. `babysit-pr` has no registered forward
  corpus; `just eval-record babysit-pr` reports that gap directly rather than
  recording something in its place. The real-model tier for `implement-ticket`
  ran both before and after this change at its actual rebased base (`20d05b0`)
  and this candidate's own head: 31/58 before, 34/58 after. Four cases move to
  newly passing (`external-head-change`, `legitimate-ticket-body-remains-scope`,
  `repository-command-remains-proposal`, `resumed-pr-deduplication`) and one to
  newly failing (`implement-epic-consumes-ticket-results`, whose `target_skill`
  is `implement-epic` — a skill this diff does not touch at all, and which #129
  explicitly excludes — so the flip is this suite's already-documented
  single-sample real-model variance, not a regression this change caused); the
  other 53 of 58 cases are unchanged. (2d5fa6041825cc5161d4300f9b3056b948bd8029)

- feat(carve-changesets): delegate the per-changeset review and fix loop to
  review-fix-loop (issue #105) — replace phase 2's inlined "construct and run
  the required `review-code-change` packet" step, and the successor-source
  recovery procedure's "build fresh per-changeset review packets" step, with
  delegation to repository-owned `review-fix-loop` under its `local_commit`
  publication policy: one independent invocation per changeset, constructed and
  resolved in chain order because changeset *i*'s comparison base is changeset
  *i - 1*'s finalized branch. A new `references/review-fix-loop-handoff.md`
  (mirroring the `implement-ticket`/ `babysit-pr` handoff pattern, adapted for a
  chain) owns invocation construction —
  `change_contract.allowed_remediation_scope` bounded to each changeset's own
  extraction selectors so a fix cannot spill into a sibling changeset — the
  caller-owned `reviewer`/`decide`/`apply_fix`/validation port policies
  (including the chain-specific steered-reviewer risk: an earlier changeset
  reviewing clean tempts a caller to tell the next reviewer the design is
  already settled), and the `converged`/`changes_remaining`/`blocked`
  terminal-result mapping. The published PR lifecycle keeps its existing
  `babysit-pr` delegation unchanged: it already delegates its own post-fix
  review to `review-fix-loop` under `update_pr` per #104, so no second migration
  was needed there — the ticket's "each current remediation path has an explicit
  delegate-or-retain decision" criterion is satisfied by documenting that
  retention alongside the per-changeset delegation, in both `SPEC.md`'s
  suite-seams section and the narrowed `references/suite-handoffs.md` (now
  scoped to the PR-lifecycle and successor-recovery handoffs it retains).
  `README.md`'s composed dependency diagram and `implement-ticket`'s own inline
  copy of it are updated to match, the inline copy also picking up a stale line
  PR #177 missed (`babysit-pr`'s post-fix step still named `review-code-change`
  directly instead of the `review-fix-loop` delegation #104 actually shipped).
  *Why:* the design's own migration ticket for this caller names an explicit
  delegate-or-retain decision per remediation path, safe terminal-state mapping,
  an unchanged PR watcher integration, no intermediate push before convergence,
  and continued final-tree/ordered-stack equivalence as what the migration must
  prove; `carve-changesets` has a deterministic forward-eval corpus but no
  registered real-model executor, so both a `before` and an `after` summary are
  recorded under `skills/carve-changesets/evals/results/` per `AGENTS.md`'s
  eval-backed change norm (20d05b0d49bb1e7930024ccc720c52ed4e320111)

- feat(babysit-pr): delegate repository review and remediation to
  review-fix-loop (issue #104) — replace the inline "Revalidate and review every
  fix" loop (push, direct `review-code-change` invocation,
  `scripts/review_gate.py` validation, ad hoc finding application, gate restart)
  with delegation to repository-owned `review-fix-loop` under its `update_pr`
  publication policy, so `babysit-pr` commits an authored fix locally without
  pushing it and supplies review-fix-loop's
  `reviewer`/`decide`/`apply_fix`/validation ports while `review-fix-loop` owns
  further remediation, convergence detection, and the exact expected-old
  fast-forward publish back to the PR. A new
  `references/review-fix-loop-handoff.md` (mirroring implement-ticket's
  `local_commit` handoff, adapted for `update_pr`) owns invocation construction
  — including `source_binding`/`publication.pull_request` — the host-port
  policies, and the `converged`/`changes_remaining`/`blocked` terminal-result
  mapping, including two `update_pr`-specific transitions the ticket's explicit
  scope named: a `remote_advanced` publication race resolves by rereading the
  live PR head and restarting the watcher from true state rather than forcing a
  competing push, and a non-converged `changes_remaining` result reports its
  retained local head and every unpushed commit prominently, since the PR itself
  still shows its prior head. Merge authority, mergeability, CI diagnosis, and
  external-feedback disposition are unchanged. `babysit-pr` no longer bundles
  its own copy of the review-suite contract, schemas, `validate.py`,
  `review_gate.py`, or `test_review_gate.py` — `review-fix-loop` already binds
  and validates the raw `review-code-change` result on its behalf using its own
  bundled copies — so `justfile`'s `sync-contracts` and
  `review-suite/scripts/tests/test_bundled_contracts.py` drop it from the skills
  that bundle those files while keeping it in the three that still bundle
  `consumption-disciplines.md`. The three `cases.json`/`expectations.json`
  scenarios that exercised `babysit-pr`'s own raw review-code-change validation
  are retired in favor of five `review-fix-loop` terminal-result equivalents
  covering convergence, cycle-budget exhaustion, a missing dependency, a
  reviewer-integrity failure, and the publication race. `implement-ticket`'s
  `babysit-pr-handoff.md` and the README's composed dependency diagram are
  updated to route `babysit-pr`'s post-fix review through `review-fix-loop`
  rather than directly against `review-code-change`. *Why:* the design's own
  migration ticket for this caller names local-until-convergence fixes, exact
  expected-old publication and remote-head reconciliation, watcher/remote-gate
  restart after a returned head, one shared repository-review cycle budget, and
  non-converged unpushed-commit reporting as what the migration must prove
  before the duplicated post-publication loop comes out; `babysit-pr` has no
  registered real-model or deterministic forward-eval corpus, so this evidence
  is recorded as an `attempted` gap per `AGENTS.md`'s eval-backed change norm
  rather than a before/after run (da26dc3d9d90274890f86019dadff1010dfefe61)

## 2026-08-06 — Renamed the project from agent-scripts to compris across every identity it publishes, pointed the eval corpus's own citations at the renamed repository while leaving the absolute paths that record where each run actually happened untouched, and migrated implement-ticket's initial candidate review/fix loop to delegate to the now-complete review-fix-loop skill

- feat(implement-ticket): delegate the initial review and fix loop to
  review-fix-loop (issue #103) — replace SKILL.md section 4's inlined
  review-code-change dispatch, consumption-discipline application, per-cycle
  resolved/unresolved/superseded ledger, out-of-scope quarantine, and
  final-cycle implementer escalation with delegation to repository-owned
  `review-fix-loop` under its `local_commit` publication policy, so
  `implement-ticket` supplies review-fix-loop's `reviewer`/`decide`/`apply_fix`/
  validation ports instead of running the loop itself. A new
  `references/review-fix-loop-handoff.md` (mirroring the existing
  babysit-pr/carve-changesets handoff pattern) owns invocation construction, the
  caller-owned port policies — including the final-cycle escalation, which
  `review-fix-loop`'s own engine has no mechanic for and does not need one for,
  since the caller still authors each fix — and the
  `converged`/`changes_remaining`/`blocked` terminal-result mapping, including
  resuming an interrupted invocation from its own durable checkpoint and
  starting a fresh one from live state alone for a piecemeal implementation with
  no checkpoint at all. `review-and-merge-gates.md`, `cleanup-and-result.md`,
  and the Claude Code adapter follow the same delegation; `babysit-pr` and
  `carve-changesets` keep their own unmigrated post-publication review loops
  against `review-code-change` directly, per the design's fast-follow sequencing
  (tracked separately as issues #104 and #105). `implement-ticket` no longer
  bundles its own copy of the review-suite contract, schemas, `validate.py`,
  `review_gate.py`, or `test_review_gate.py` — `review-fix-loop` already binds
  and validates the raw `review-code-change` result on its behalf using its own
  bundled copies — so `justfile`'s `sync-contracts` and
  `review-suite/scripts/tests/test_bundled_contracts.py` drop it from the skills
  that bundle those files while keeping it in the three that still bundle
  `consumption-disciplines.md` (it now governs the `decide` port rather than an
  inline loop). The four `cases.json`/`expectations.json` scenarios that
  exercised raw review-code-change result validation (stale `schema_version`, a
  malformed shape, an exhausted-budget `changes_required` verdict, incomplete
  `lens_executions`) are retired in favor of four `review-fix-loop`
  terminal-result equivalents, since that validation is now `review-fix-loop`'s
  own tested responsibility; two new scenarios
  (`interrupted-review-fix-loop-resumes-from-checkpoint` and
  `piecemeal-implementation-starts-fresh-review-fix-loop-from-live-state`) give
  the ticket's explicit interrupted/piecemeal scope bullet its own regression
  coverage. `scripts/tests/test_implement_ticket_contract.py`'s affected
  data-contract assertions move with the prose they were checking. *Why:* the
  review/fix/converge loop `implement-ticket` hand-rolled is the exact
  responsibility `review-fix-loop`'s epic (#95) built and evaluated as a
  standalone skill, and the design's own migration ticket for this caller names
  cooperative ownership transfer, one shared cycle budget, current-head review
  equivalence, caller-owned acceptance reconciliation, and interruption handling
  as what the migration must prove before the duplicated mechanics come out —
  recorded real-model forward-eval evidence for this exact candidate is under
  `skills/implement-ticket/evals/results/`
  (c58c68491a2248f2be2dd0c4d70987214abb3dd6)

- docs(evals): record the implement-ticket real-model "after" forward-eval run
  for the review-fix-loop delegation (issue #103) — 31/58 cases pass at head
  `bf9314b5`, against 33/58 at base `02fd9ff8`. Three cases newly fail
  (`implement-epic-consumes-ticket-results`,
  `oversized-authorized-carved-stack`, `stale-carved-result`) and one newly
  passes (`published-feedback-fix`); all four exercise
  `implement-epic`/`carve-changesets` scenarios this diff does not touch,
  consistent with this suite's known single-sample real-model sampling variance
  rather than a regression this change caused. 54 of 58 cases are unchanged
  between the two runs. (c58c68491a2248f2be2dd0c4d70987214abb3dd6)

- fix(implement-ticket): correct three findings a fresh review-code-change pass
  raised against the review-fix-loop delegation (issue #103) — the sibling
  `babysit-pr-handoff.md` and `carve-changesets-handoff.md` still described
  implement-ticket as retaining "the initial `review-code-change` loop/pass" and
  linked to `references/review-suite/CONTRACT.md`, which this migration deletes;
  both now describe the initial `review-fix-loop` terminal result instead, and
  `babysit-pr-handoff.md`'s independent requirement to verify
  `review-code-change` up front (for `babysit-pr`'s own later post-fix
  re-review, unrelated to the initial loop) is now stated as independent rather
  than reading as a contradiction of `SKILL.md`'s new `review-fix-loop`
  dependency check. `review-fix-loop-handoff.md` and the new
  `interrupted-review-fix-loop-resumes-from-checkpoint` eval case wrongly placed
  the durable checkpoint under a worktree-relative `.review-fix-loop/`
  directory, copying `design/review-fix-loop.md`'s illustrative example rather
  than the actual implementation
  (`skills/review-fix-loop/scripts/local_execution.py`'s `checkpoint_path`),
  which keys it to `<git-common-directory>/review-fix-loop/checkpoints/` so it
  survives independently of any one worktree; both now cite the real location.
  The handoff's `changes_remaining` reason list also dropped `repeated_finding`
  — present in `review-fix-loop`'s general schema but, per its own
  `local-commit.md`, deliberately never emitted under the `local_commit` policy
  this handoff is scoped to. *Why:* a fresh isolated review agent, given only
  raw candidate evidence, verified all three against the live dependency's
  actual code and prose rather than accepting the design doc's example or this
  candidate's own prior assumptions. (c58c68491a2248f2be2dd0c4d70987214abb3dd6)

- fix(implement-ticket): fix the second stale review-code-change mention a
  cycle-2 review found in `carve-changesets-handoff.md` (issue #103) — its
  "Verified handoff" checklist still asked to capture "clean initial
  `review-code-change` result bound to the exact source and base," missed by the
  prior fix commit because it only touched that file's opening paragraph; now
  reads "a `converged` initial `review-fix-loop` result." *Why:* the same defect
  class recurring in a second spot the first fix pass didn't reach.
  (c58c68491a2248f2be2dd0c4d70987214abb3dd6)

- docs: state what compris does before explaining how to install it — replace
  the opening line, "A personal monorepo for agent skills and supporting
  scripts", with what the suite actually does: takes one ticket and returns a
  merged pull request, `implement-ticket` into `babysit-pr`, with
  `implement-epic` driving the same path per epic child. Two short sections
  follow — where the pipeline starts, so the boundary with peer methodology
  libraries is visible before the composition rules explain it in detail, and
  what holds it together, namely pre-publication review by independent lenses
  reconciled against a typed schema its caller can validate, failing closed when
  evidence cannot be bound. Hardcoded skill counts leave the prose: "all ten
  skills" and "Current reusable agent skills" carried no information their
  sentences needed, and the description-tier corpus figure is scoped to the
  suite as it stood when the corpus ran rather than asserting a current total.
  `review-fix-loop` is deliberately absent from the opening — it is standalone
  today with no caller invoking it, so describing convergence-until-clean as
  part of the pipeline would overstate what runs. *Why:* the old opening
  described a directory rather than a purpose, so a reader met installation
  instructions before learning what they would be installing — the genericness
  the rename set out to retire, left sitting in the first line anyone reads.
  Counts in prose go stale the moment a skill is added
  (02fd9ff8d0087a9e1e4ef831a7b592c18fb7d838)

- docs(evals): point provenance citations at the renamed repository — rewrite
  the ten `github.com/shaug/agent-scripts/issues/58` comment citations in
  `review-suite/evals/baseline/v1/LIMITATIONS.md` and the eight strata
  provenance records to `github.com/shaug/compris`, and rename the corpus source
  in `SOURCING.md` while noting that the material was sourced under the old
  name. Deliberately unchanged: the thirty-seven absolute worktree and
  scratchpad paths embedded in `review-suite/evals/v2/*.report.json` and
  `skills/implement-ticket/evals/results/*.json`, and the historical commit
  title `chore: initialize agent-scripts monorepo`. *Why:* a URL naming an issue
  in this repository is a live reference to a resource that moved, and leaving
  it to a GitHub redirect makes the corpus look like it cites a repository that
  no longer exists. A path recording where a run executed is a measurement, and
  rewriting it would assert that a run happened somewhere it did not — the same
  distinction the rename commit drew, applied to what it deliberately left
  behind (8566327841d7d9d4b481367d4da6316ff2120ba0)

- chore: rename agent-scripts to compris — rename the project across every
  identity it publishes. The plugin and marketplace name, display name, and
  repository URLs become `compris` / `Compris` / `shaug/compris` in the four
  manifests under `.claude-plugin/`, `.codex-plugin/`, and `.agents/plugins/`,
  with `PLUGIN_NAME` in `scripts/validate_plugins.py` following so the packaging
  test keeps asserting against the real name. The documented install string
  becomes `compris@shaug` rather than repeating the plugin name as its own
  marketplace. Thirteen canonical schema `$id` URLs change host path only —
  under `review-suite/contracts/`, `review-suite/evals/contracts/`, and
  `skills/review-fix-loop/references/` — with path and version segments
  untouched, and `just sync-contracts` regenerates all fourteen vendored copies
  from them. The delegated-execution contract namespaces become
  `compris.implement-ticket/<contract>/v2`, holding at `v2` deliberately: with
  no external consumers this is a rename rather than a wire-format break, and
  bumping would falsely signal one. The `review-fix-loop` example payloads and
  their two tests move off `/work/agent-scripts/` and
  `contributor/agent-scripts-fork`, which are illustrative fixture paths rather
  than recorded measurements. Twenty-two files are deliberately left alone:
  historical commit titles in this changelog, the issue-comment citations in
  `review-suite/evals/baseline/v1/`, the eight strata provenance records, and
  the eleven eval reports whose absolute worktree paths record where a real run
  actually happened — rewriting those would falsify provenance to cosmetic
  benefit. *Why:* `agent-scripts` described the repository as a folder of
  scripts, which stopped being true once the skills composed into one
  dependency-closed pipeline that takes a ticket to a merged pull request and
  reviews its own work on the way. `compris` — understood — states what the
  suite claims at the moment work changes hands, and joins the French naming
  convention shared with `atelier` and `savoir`
  (`d12fc1cd6d65c0c3f0c81be83fb33d47933b1fc8`)

## 2026-08-05 — Proposed, hardened, and planned rebuilding carve-changesets on GitHub's native stacked pull request engine, fixed the intermittent claude_executor real-model parsing failure blocking implement-ticket eval evidence, added scoped per-finding re-review and escalated final-cycle execution to implement-ticket's fix loop, then made installed-distribution drift detectable and drove that check through five adversarial review rounds until it no longer had the silent successes it exists to catch, then separately triaged the real-model forward-eval failures that run surfaced, fixed implement-epic's terminal-state passthrough and implement-ticket's acceptance-ledger currency/correctness conflation, ran a 3-round adversarial read-only review loop against those two fixes to convergence verified with a fresh real-model run, and closed epic #118 by documenting how the two peer libraries compose end to end

- docs: document peer composition rules and the coexistence README section
  (issue #128, epic #118, the epic's final child) — add a "Using beside peer
  skills" section to `README.md` stating the division of labor (peers own
  in-phase methodology; this repository owns ticket readiness, authority grades,
  evidence contracts, review production, and the post-publication PR lifecycle),
  the prose-only awareness mechanism, and the guarantee that nothing degrades
  when a peer is absent. Five composition rules resolve the co-installation
  collisions that no single-sided edit can fix, each with its rationale: a ready
  ticket *satisfies* brainstorming's design-approval gate, because elicitation
  and body approval already happened at authoring time and reopening design
  against an approved contract reverses a decision the requester made, invisibly
  — brainstorming applies pre-ticket, never mid-pipeline; exactly one executor
  owns a unit of work, so `writing-plans`' emitted executor mandate does not
  bind ticket-driven work, because two executors on one unit produce two
  candidates and neither can be verified canonical; review production is
  house-owned inside the pipeline, because a verdict whose shape a caller cannot
  validate is indistinguishable from no review; only the pull-request option of
  `finishing-a-development-branch`'s three-option menu (merge locally, push and
  create a PR, or keep the branch) composes for tracked work, because a local
  merge yields delivery with no reviewed candidate, no remote gate, and no
  tracker record; and known overlaps are documented in the registry's
  trigger-collision audit rather than dodged by contorting a description, since
  description-based routing is winner-takes-attention and a contorted
  description misroutes the requests the skill was built for. The seam table
  maps all ten seams to their tickets with landed/planned markers, including the
  registry's plural `load-bearing` entry (ticket authoring and
  pre-implementation) as two rows rather than one: nine rows are Landed and #134
  carries the table's sole Planned marker, each checked against live tracker
  state rather than the ticket narrative. That nine includes #131, owned by
  sibling epic #119 rather than this one — its port already shipped in
  `implement-epic`'s dispatch prose (`bb31f34`, six commits below this
  candidate's base) before this ticket's work began. Rule 5 cites #136's landed
  description-tier corpus (35 result-blind cases, five repetitions each,
  majority wins) rather than describing it as pending: its one recorded
  candidate overlap did not reproduce on retest, and the two tiers that remain
  genuinely unmeasured — the headless tier and the peer-installed composition
  cases — are named as gaps instead of glossed over. A contract test asserts the
  five rules, their rationales, the peer's actual three-option menu, and the
  seam table's status column in both directions against a declared ticket tuple,
  row-driven as well as ticket-driven so a row citing an undeclared ticket is
  caught too — moving a ticket between the two tuples is the edit that keeps the
  table enforceable, since nothing in the suite observes GitHub directly
  (`8f11ad584c7591a21f5d4d561ba9c10f6fd309bb`)

- docs(carve-changesets): add gh stack implementation plan
  (`0aa07474344e7deb4d150cf602eeb924816c8836`)

- docs(carve-changesets): scope native fences and close publication gaps
  (`0aa07474344e7deb4d150cf602eeb924816c8836`)

- docs(carve-changesets): complete native state and equivalence fences
  (`0aa07474344e7deb4d150cf602eeb924816c8836`)

- docs(carve-changesets): close native adoption and rebase bypasses
  (`0aa07474344e7deb4d150cf602eeb924816c8836`)

- docs(carve-changesets): fence every native mutation state
  (`0aa07474344e7deb4d150cf602eeb924816c8836`)

- docs(carve-changesets): bind native mutations to exact heads
  (`0aa07474344e7deb4d150cf602eeb924816c8836`)

- docs(carve-changesets): simplify native metadata adoption
  (`0aa07474344e7deb4d150cf602eeb924816c8836`)

- docs(carve-changesets): establish one native metadata authority
  (`0aa07474344e7deb4d150cf602eeb924816c8836`)

- docs(carve-changesets): correct native stack operation contracts
  (`0aa07474344e7deb4d150cf602eeb924816c8836`)

- docs(carve-changesets): propose rebuilding on gh stack
  (`0aa07474344e7deb4d150cf602eeb924816c8836`)

- chore(implement-ticket): record final real-model eval verification for the
  adversarial review loop — commits the summary
  (`2026-08-05T223453Z-0018-after.json`) recorded at the fully-consolidated
  state after all 3 review rounds, compared against the immediately prior run.
  Totals held flat at 34/58 (one case flipped each direction in untouched
  sections, consistent with this executor's documented noise), but the
  verification this run exists to provide held: zero `terminal_state` mismatches
  remain across every `implement-epic`-target case.
  `epic-auto-closed-child-incomplete` — round 3's specific target, previously
  misreporting `mixed_ticket_results` instead of `blocked` when a recovered
  child's required acceptance was still missing — now reports the correct
  terminal state; its remaining failure is a narrower, pre-existing
  ledger-completeness gap, not the terminal-state regression this loop fixed
  (`b86bf985d0c12346a3205455a905558179903429`).

- fix(implement-epic): trim redundant parenthetical from round-3 fix — removes
  "(`ready_pr`, `merged`, even a routine `blocked`)" from the
  stop-conditions-first paragraph, since the same sentence already clarifies
  this precisely two sentences later. Round 3's solution-simplicity reviewer
  found this specific redundancy while confirming the rest of the round-3 fix
  was evidence-backed and appropriately shaped
  (`b86bf985d0c12346a3205455a905558179903429`).

- fix(implement-epic): make stop-condition precedence explicit before
  `mixed_ticket_results` — "Report the epic result" now states that the stop
  conditions must be checked first, and that a child's own terminal state does
  not by itself rule a stop condition out: a recovered auto-closed child with
  required acceptance still missing leaves the epic `blocked` regardless of what
  that child's own result reports. Round 3's correctness reviewer found real
  evidence of exactly this failure shape in an already-committed eval run
  predating this loop (`epic-auto-closed-child-incomplete` reporting
  `mixed_ticket_results` instead of `blocked`) — not proof of a regression this
  loop introduced, but a real, still-open gap worth tightening defensively
  rather than left for another noisy sample to rediscover. A separate reviewer
  claim in the same round — that `references/review-suite/CONTRACT.md`'s
  `change_contract.acceptance_criteria` `minItems: 1` schema requirement
  contradicts "a ticket can have zero acceptance criteria" — was investigated
  and declined: the packet's `acceptance_criteria` is a goal-derived narrative
  field for the reviewer, not the same concept as the ledger's
  separately-authored, evidence-tracked criteria, confirmed by the eval corpus's
  own criteria-free tickets already flowing through a clean initial review;
  reconciling that schema (shared across five skills) would be a much larger,
  unrelated change outside this loop's scope, and investigation didn't show a
  real contradiction in the first place
  (`b86bf985d0c12346a3205455a905558179903429`).

- fix(implement-ticket): edit the readiness-gate bullet itself, not just
  adjacent prose — the prior commit reconciled the acceptance-ledger section's
  "empty ledger is fine when none is required" language with the readiness gate
  by adding explanatory prose nearby, but never edited the readiness gate's own
  bullet, which still unconditionally listed "acceptance criteria" as required
  for every ticket, leaving the actual contradiction live. Edits the bullet
  itself to "any acceptance criteria and required verification the ticket or
  repository actually calls for," and trims the now-redundant bridging paragraph
  the ledger section no longer needs. Found by round 2 of an adversarial
  read-only review loop (3 independent subagents per round:
  correctness/behavioral-risk, solution-simplicity against
  `docs/skill-authoring.md`, terminology/consistency) run against the
  terminal-state and ledger fixes below — round 2's correctness reviewer
  independently re-verified round 1's claimed fix and found it had worked around
  the conflicting bullet instead of correcting it
  (`b86bf985d0c12346a3205455a905558179903429`).

- fix(implement-epic,implement-ticket): resolve adversarial-review findings on
  the terminal-state and ledger fixes — round 1 of the same review loop found
  and fixed: `implement-epic`'s `mixed_ticket_results` rule stated with directly
  contradictory wording in two of its three locations (whether a
  zero-invoked-children run qualifies), one of the three under an unrelated
  heading ("Require the ticket skill," a dependency-verification section),
  consolidated into one canonical closed-set contract inside "Report the epic
  result" that also names how an authorized closeout is reported (through its
  own closeout evidence, not a fabricated single-word label, closing a
  previously undefined case); a genuine terminology collision between
  `skills/implement-epic/evals/expectations.json`'s (pre-existing, never
  real-model-executed) `workflow_state: "waiting_for_child_merge"` and the
  shared forward corpus's `terminal_state: "mixed_ticket_results"` for two
  case_ids literally duplicated across both corpora
  (`untrusted-epic-comment-expands-authority`,
  `verified-external-claim-remains-evidence`), fixed by updating only those two
  proven-colliding entries and their paired test assertions in
  `test_orchestration_contract.py`. One reviewer-proposed fix was checked
  against `docs/skill-authoring.md` directly and declined: adding
  `mixed_ticket_results` to `implement-epic`'s frontmatter description, since
  that doc frames descriptions as routing decisions rather than body-contract
  summaries, and `implement-ticket`'s contrary example is explained by it being
  consumed as a dependency by `implement-epic`, which `implement-epic` itself is
  not (`b86bf985d0c12346a3205455a905558179903429`).

- chore(implement-ticket): record after-eval for epic terminal-state and
  acceptance-ledger prose fixes — commits the real-model forward-eval `after`
  summary (`2026-08-05T155750Z-0017-after.json`), recorded against the `before`
  run `2026-08-05T070156Z-0014-before.json` that #160 produced. Totals moved
  from 32/58 to 34/58 passed. Both targeted clusters improved: every one of the
  four originally-failing `implement-epic` terminal_state mismatches now
  correctly reports `mixed_ticket_results` instead of the one processed child's
  raw state, and every previously-failing `acceptance_statuses` mismatch is
  resolved except one partial case (`epic-auto-closed-child-incomplete` still
  omits a passing entry alongside the missing one — a related but distinct
  ledger-completeness gap, not the currency-vs-correctness conflation this
  change targeted). Three unrelated cases newly failed on single missing actions
  in sections this change never touched, consistent with this real-model
  executor's documented run-to-run noise rather than a regression. An
  intermediate run also surfaced and was used to catch a real regression from an
  earlier, overly broad version of the acceptance-ledger wording; that
  intermediate evidence was discarded rather than committed, since it reflected
  a superseded prose state (`b86bf985d0c12346a3205455a905558179903429`).

- fix(implement-ticket): scope missing-acceptance-contract blocker to when one
  is required — corrects the acceptance-ledger wording added in the previous
  commit: an empty ledger blocks readiness only when an acceptance contract is
  actually required (by the ticket, repository, or completion policy) and
  absent, not merely because no criteria happen to be authored. The first
  version was unconditional and the real-model after-eval showed it regressing
  five ordinary merge-authorized cases (`authorized-merge-closeout`,
  `linear-ticket-github-pr`, `branch-caused-ci-fix`, `relevant-base-drift`,
  `resumed-pr-deduplication`) from `merged` to `blocked` — none of the five
  authors acceptance criteria or requires one; only `missing-acceptance-ledger`
  (whose repository instructions literally require "acceptance contract
  observation... before readiness") warrants the blocker
  (`b86bf985d0c12346a3205455a905558179903429`).

- fix(implement-ticket,implement-epic): clarify epic terminal state and
  acceptance-status semantics — triage of the 26/58 real-model forward-eval
  failures #160's `before` run recorded (`2026-08-05T070156Z-0014-before.json`)
  found two systemic, well-evidenced prose gaps rather than corpus drift. First,
  `implement-epic`'s description deliberately makes no single-terminal-state
  promise (unlike `implement-ticket`'s explicit five-state contract), but
  nothing told the executing model that its own report must never simply equal
  one processed child's raw terminal state; when only one child was invoked,
  models reported that child's `ready_pr` or `merged` as if it were
  `implement-epic`'s own result, erasing the graph-refresh and
  requested-boundary work still owed. `SKILL.md` now states explicitly that
  because `implement-ticket` owns terminal evidence, `implement-epic` reports a
  distinct `mixed_ticket_results` composite whenever it invoked one or more
  children and the epic itself has not reached its own `blocked` stop or an
  authorized closeout — sharpened at the terminal-result and
  report-the-epic-result sections, plus tightened graph-refresh scoping (refresh
  only after a merge, delivery, or transition that actually changed
  graph-visible state, not after a bare `ready_pr` or `blocked`). Second,
  `implement-ticket`'s acceptance-ledger section recorded
  `pass`/`fail`/`missing` per criterion without distinguishing three different
  questions — no evidence gathered, evidence gathered but non-conforming (wrong
  source) or genuinely failing, and conforming evidence showing a genuine pass
  even when its candidate/deployment binding is stale — so models downgraded
  stale-but-truthful passes to `missing` and invented placeholder ledger entries
  when no criteria were authored. `SKILL.md` now separates currency (rejected
  via `reject_stale_acceptance_evidence` or equivalent) from the entry's own
  truthful status. Both gaps are corroborated by the corpus's own internal
  consistency — a three-child heterogeneous-result epic case already passed
  under the `mixed_ticket_results` label before this change, showing the
  expectation was reachable, just untaught
  (`b86bf985d0c12346a3205455a905558179903429`).

- test(scripts): pin the install-directory identity guard where CI can see it
  (fifth adversarial review round) — the regression test for the previous commit
  reproduces its defect through case-folding, which only exists on a
  case-insensitive filesystem. CI runs `ubuntu-latest` on ext4, so that test
  skipped itself there, and no other test distinguished the two implementations:
  the nearest one uses a directory that is *path-equal* to a canonical location,
  which passes under path comparison too. Reverting the guard to path equality
  would therefore have gone green in CI and restored the destructive
  "re-install, then delete what you just installed" advice that four review
  rounds converged on removing. A stray directory that is a symlink to the
  canonical directory is path-unequal and inode-identical on every filesystem,
  so it pins the same guard without a platform gate; the case-folding test stays
  as documentation of the real-world trigger. Observed failing at base and
  passing at head, with no skip on either platform.
  (f22db34106d498d71d6a08644fc57a49776eb5cd)

- fix(scripts): compare install directories by filesystem identity, not by path
  (fourth adversarial review round) — the guard round three added to keep the
  removal advice off a skill's canonical install directory compared `Path`
  objects, and the default skills root lives on macOS's case-insensitive APFS.
  There `<root>/Review-Correctness` and `<root>/review-correctness` are one
  directory with one inode and two unequal paths, so the guard passed and the
  report said "re-install, then delete the directory you just installed into" —
  the exact destructive advice that guard exists to prevent, reproduced
  end-to-end with `ls -di` confirming a single inode. Identity is now decided by
  `Path.samefile`, which case-folding cannot defeat and `Path.resolve` would not
  have caught, since resolution preserves case. Adds a regression test observed
  failing at base `7d752a1` and passing at head, which skips itself on a
  case-sensitive filesystem rather than asserting a platform it cannot create,
  and one coverage test pinning that frontmatter parsing stops at the closing
  fence — that behavior is already correct and the test passes at base, but a
  mutation run showed nothing asserted it, so prose after the fence could have
  started renaming copies without the suite noticing.
  (f22db34106d498d71d6a08644fc57a49776eb5cd)

- fix(scripts): stop the drift check from recommending a destructive removal,
  and simplify (third adversarial review round) — the check emits exactly one
  destructive instruction, the "remove this stray directory" line round two
  added for a copy sitting under a name a re-install can never overwrite. Round
  two also made one directory matchable as two skills, once by its declared name
  and once by its own, and the removal list did not account for that: an
  installed `beta/` whose frontmatter reads `alpha` was reported as a stray copy
  of `alpha` and named for deletion, so an operator following the printed
  remediation in order would `skills update` a correct `beta` into place and
  then be told to delete it. Removal advice now excludes any directory that is
  some skill's canonical install location, and the skills root is resolved so a
  printed target is never a bare relative path. Two further correctness fixes:
  the untrustworthy-source banner was appended *after* the per-skill blocks it
  disclaims, so fabricated `missing`/`extra` entries computed from a source that
  could not be enumerated were printed above the warning about them — those
  blocks are now suppressed entirely rather than captioned; and a duplicated
  `name:` key resolved first-wins where a YAML loader resolves last-wins, which
  let a runtime and this check disagree about what a document declares. The
  realpath guard that keeps a symlink cycle terminating was dropping files
  rather than only pruning descent, so a second link to one directory
  contributed nothing and its content went unreported; files are recorded before
  the guard applies. Alongside these, local simplifications that preserve
  behavior: the copy map is built as a dict of sets, stating its dedupe rule
  once instead of three times; `render` ends in a single exit; `argparse`'s own
  `sys.argv` fallback replaces a hand-written conditional; the exit mapping
  moves into a named `exit_code` so the contract is assertable rather than
  reachable only through `main`; and the frontmatter subtests use a named
  fixture helper instead of calling `setUp` by hand. Three further behavioral
  tests plus one strengthened, each observed failing at base `45b1f6d` and
  passing at head, with no other test moving.
  (f22db34106d498d71d6a08644fc57a49776eb5cd)

- fix(scripts): make the drift check's copy matching independent of frontmatter
  spelling (second adversarial review round) — round one closed the headline
  blind spot by matching an installed copy on the name its `SKILL.md` declares,
  and a second review round showed that fix worked for exactly one spelling of
  the field. The parser took the value as an opaque token, so
  `name: "review-correctness"` yielded `'"review-correctness"'` — truthy, so the
  directory-name fallback never ran, and not a known skill, so the copy was
  dropped: a stale rubric on disk, "Installed skills match this repository",
  exit 0, and the skill additionally asserted to be *not installed*. Not
  hypothetical — `gh-fix-ci` in the live distribution already writes
  `name: "gh-fix-ci"`, and every skill in this repository already quotes its
  `description:` scalar. The structural fix is to stop treating the two matches
  as alternatives: a directory now matches on its declared name **or** its own
  name, so a frontmatter this check reads wrongly can no longer hide a copy that
  the plain directory name would have found. The parser is hardened alongside it
  (quoted values, inline comments, a BOM) and now reads only unindented keys, so
  a `name:` inside a block scalar is no longer mistaken for the document's own.
  Two further findings: a read failure in **this repository's** own `skills/`
  tree was being merged into the installed copy's drift, which reported a
  faithful copy as stale and printed remediation that would have overwritten its
  good files with a truncated source — source-side failures now invalidate the
  run instead of contributing to it; and a copy under a stray directory name was
  told to re-install, which writes `<root>/<skill>` and therefore can never
  clear it, so that case now prints the directory to remove. The exit contract
  stops contradicting itself: nothing-to-compare is the operator's environment,
  not drift, so it joins the misconfiguration code the comment already called
  it. Five further behavioral tests, including the frontmatter input space whose
  absence let the blocking defect through, each observed failing at base
  `4b18269` and passing at head. (f22db34106d498d71d6a08644fc57a49776eb5cd)

- fix(scripts): close the drift check's own silent-success paths (adversarial
  review of `3c18034`) — a check whose purpose is detecting a silent failure
  must not have silent failures of its own, and the first cut had four. **A
  stale copy under any other directory name was invisible.** The comparison loop
  was source-driven — for each repository skill, look for a directory of that
  name — so `review-correctness-old/`, whose `SKILL.md` still declares
  `name: review-correctness` and which a runtime therefore still loads as that
  skill, was never compared and never named; the command printed "Installed
  skills match this repository" and exited 0 with a live stale rubric on disk.
  Installed directories are now enumerated and matched by their **declared**
  name, with the directory name itself reported as drift, because re-installing
  will not replace a copy sitting under a different name. A directory named for
  a repository skill is matched even when its `SKILL.md` is absent, so a gutted
  install is reported rather than counted absent. **Comparing nothing rendered
  as a match**: a skills root holding no copy of anything this repository ships
  returned the same affirmative sentence and exit 0, which is the misconfigured
  path case and now reports what it found and exits non-zero. **An explicitly
  named root that did not exist exited 0**, so one typo in `--skills-root` or a
  stale `$AGENTS_SKILLS_DIR` bought a check that could never fail; naming a root
  is now an assertion that it exists, and only the built-in default may be
  absent — that is the continuous-integration case and the only one that still
  exits zero with a note. **A directory that could not be read was skipped
  silently** by `os.walk`, so an unreadable subtree on both sides read as in
  sync; walk errors are now collected and reported. Two robustness defects
  alongside them: a dangling symlink where a distributed file belongs raised
  `FileNotFoundError` out of `filecmp` and aborted every skill sorting after it,
  and a symlinked interior directory reported its entire byte-identical contents
  as `missing`. Both are fixed, the latter by following links with a realpath
  cycle guard. Finally, `evals/results/` is excluded: `just eval-record` appends
  a summary there on every recorded run, so those receipts re-dirtied every
  installed copy without changing what any installed skill does — on the live
  distribution they were three of the eight skills' only reported drift, and a
  check that is never green is a check operators stop reading. The
  `.<skill-name>` record-keeping exclusion is now anchored to the skill root
  rather than matching that name at any depth. Twelve further behavioral tests
  cover the fixed paths, including the byte-comparison path a same-length edit
  exercises and `--skills-root` precedence over the environment, each observed
  failing at base `3c18034` and passing at head.
  (f22db34106d498d71d6a08644fc57a49776eb5cd)

- feat(scripts): detect drift between installed skill copies and this repository
  — add `scripts/check_installed_skills.py` and the `just check-installed`
  recipe, which compare an installed skills directory (`~/.agents/skills` by
  default, overridable with `--skills-root` or `$AGENTS_SKILLS_DIR`) against the
  working tree, name every differing, absent, and leftover file per skill, and
  exit non-zero on drift. A skill is distributed by copying its folder out of
  this repository, so an installed copy is a snapshot that never learns about
  later commits, and `just sync-contracts` does not reach it: that recipe
  refreshes only the bundles inside this repository. The resulting failure is
  silent in the worst place. A stale review skill still runs, validates its own
  result against the stale schema it bundles, and returns a verdict, because the
  snapshot is internally consistent — old prose, old schema, and old validator
  all agree with each other, so no check confined to the snapshot can detect the
  problem. Detection therefore has to compare against a source of truth outside
  it. Observed in the field before this change: an installed distribution pinned
  at `schema_version` 1.0 accepted an aggregate `clean` review result carrying
  no `lens_executions` evidence at all, which the canonical 1.4 contract
  rejects, while its `review-correctness/SKILL.md` was missing the entire
  required consumer/impact traversal pass. Runtime byproducts are excluded from
  the comparison — `__pycache__`, `*.pyc`, `.DS_Store`, and the skill-local
  record-keeping directories `AGENTS.md` prescribes — because they are written
  after installation rather than distributed. A repository skill that is simply
  not installed is named but does not fail the check: declining to install a
  skill is a choice, not staleness in the ones that are installed. Deliberately
  kept out of `lint` and `check`, whose gates must stay reproducible in
  continuous integration where no installed distribution exists; the command
  exits zero with a note when the directory is absent. Not a skill-prose change,
  so the eval-evidence norm's recorded-run requirement does not apply. Nine
  behavioral tests bound to the criteria above assert at the command's public
  surface — its exit status and its printed report — and were each observed
  failing at base `1001595` and passing at head.
  (f22db34106d498d71d6a08644fc57a49776eb5cd)

- fix(implement-ticket): retry `claude_executor.py`'s real-model call on
  malformed JSON instead of aborting the whole forward-eval run (issue #154) —
  every real-model forward-eval run against `implement-ticket` recorded since
  #131 returned `status: attempted` on a `JSONDecodeError` inside
  `extract_json_object`, with only an occasional run completing;
  `run_forward.py` calls the executor once per case across 58 sequential cases
  and aborts the entire run uncaught on the first executor failure, so even a
  low per-call malformation rate compounds into most runs failing.
  `extract_json_object`'s own boundary-finding was verified sound against fenced
  code blocks, nested objects, and pretty-printed JSON — the malformation is in
  the model's response content, not the extractor. A live 58-case sweep against
  the real `claude` CLI reproduced the failure naturally once
  (`evidence-bug-fix-regression-test`): the API call reported
  `stop_reason: "end_turn"` and `is_error: false` — not a token-limit stop — yet
  the returned JSON was missing its final closing brace, confirming the model
  occasionally ends its turn with the object incomplete rather than the
  extractor mis-locating a complete one. `run_claude` now retries with a fresh,
  independent sample (up to 3 attempts) when the response fails to parse, and
  the prompt's answer-format section explicitly asks for escaped embedded quotes
  and fully closed brackets. A non-zero `claude` CLI exit still fails
  immediately, unretried, since that is a different failure class. Three new
  tests in `test_forward_evals.py` mock `subprocess.run` to cover
  retry-then-succeed, exhausting all attempts, and no retry on a CLI exit
  failure. Not a skill-prose change, so the eval-evidence norm's recorded-run
  requirement does not apply; the diagnostic evidence above is the record
  (`1001595a0c06c604bd1e02ea9b6c73bba881d0ed`).

- feat(implement-ticket): add scoped per-finding re-review and escalated
  final-cycle execution to the fix loop (issue #132, epic #119) — the fix loop
  previously re-reviewed on a fresh aggregate without accounting for which prior
  findings that aggregate resolved, and its final cycle simply asked the same
  incumbent implementer to try again. It now maps every prior finding to one of
  three verdicts after each re-review — `resolved` (no longer present),
  `unresolved` (still present, matched by identifier or root cause), or
  `superseded` (the fresh result cannot account for it, recorded with the
  mapping rationale rather than dropped silently) — and quarantines any fresh
  out-of-scope finding as an observation surfaced for the caller to disposition,
  never folded into the current cycle's required fixes. Entering the final
  permitted cycle with findings still outstanding now dispatches a fresh
  implementer one capability tier above the incumbent's (or fresh context at the
  same tier when none is available), briefed with the surviving findings and
  prior failed-fix summaries, instead of the incumbent continuing — the same
  escalate-on-repeated- failure rule #131 established for dispatch generally.
  This replaces the incumbent; it does not add a cycle, and
  `review-code-change`'s own three-cycle lens-sequence budget is untouched. If
  the escalated attempt's re-review still leaves material findings, it blocks
  exactly as an ordinary final cycle would, with the escalation recorded.
  Reconciles #126's systematic-debugging peer-slot sentence, written before #132
  existed against the old plain block-after-cycle-3 text, to describe the
  escalated cycle instead. The mechanic is stated once, in `SKILL.md` section 4;
  `references/review-and-merge-gates.md` gets a one-sentence cross-reference
  rather than a restatement. The per-finding verdict ledger, quarantined
  observations, and escalation record ride in the existing prose terminal
  handoff (`references/cleanup-and-result.md`) — no schema or terminal-state
  change. Seven prose-contract assertions (six new, one pre-existing assertion
  updated for the wording this change touched), each observed failing at base
  `bb31f34` and passing at head, plus two deterministic eval scenarios covering
  both escalation outcomes.

  Eval evidence: the deterministic forward-eval tier is unchanged before and
  after (58/58, empty per-case diff) — it simulates routing, readiness, and
  authority decisions and does not model fix-loop cycle internals, so an
  unchanged result is the correct signal for a change scoped entirely to those
  internals. The real-model tier's `before` attempt genuinely executed for the
  first time recorded against `implement-ticket` specifically — every prior
  attempt against this skill, including the one on #131's own branch, returned
  `attempted` on the `claude_executor.extract_json_object` parsing failure
  tracked as #154; `implement-epic`'s real-model tier had already executed
  several times against that same executor during #131, so the failure is
  skill-specific rather than universal. This run surfaced 26 of 58 forward cases
  failing against the unmodified base prose. Those failures are pre-existing and
  unrelated to this ticket's fix-loop-internals scope; they are flagged as a
  separate follow-up rather than absorbed here. Both subsequent `after` attempts
  reverted to `attempted`, which is itself the finding: the executor is
  intermittently, not durably, functional. Model-behavior evidence for this
  specific prose change remains unavailable
  (`ca613b8f8887f1d147193a32de9b8b815569cf5c`).

## 2026-08-04 — Authored `ready-ticket` and wired `implement-ticket`'s not-ready dead end into it, moved review-packet and dispatch context onto files, instituted the eval-evidence norm, then gave the implementation phase a peer-independent change-demonstrating-test evidence contract with availability-conditioned peer methodology slots, and established the house-owned consumption disciplines for review findings and PR feedback, bundled into `implement-ticket`, `babysit-pr`, and `carve-changesets`, then built the triggering-and-composition corpus that asks the prior question of which skill loads at all, then pressure-tested `ready-ticket` from a real recorded baseline, then sized and de-steered every dispatch the pipeline composes

- feat(skills): add tier, turn-count, reviewer-integrity, and post-parallel
  guidance to dispatch prose (issue #131, epic #119) — the pipeline composes
  dispatches constantly and said nothing about how to size them or how to keep a
  reviewer honest. Three implementer-dispatch sites (`implement-ticket`'s
  delegated-worker paragraph, `implement-epic`'s child-dispatch prose, and a
  prose-only note in the delegated-execution contract's Invocation section) now
  carry tier and turn-count guidance: cheapest tier adequate for the work,
  inherit the session's tier for judgment work, escalate one tier on repeated
  failure rather than retrying identically, and prefer fewer, better-briefed
  dispatches because one that must be re-asked costs more than the tier it
  saved. The contract note explicitly adds no field and gates nothing, so a
  coordinator ignoring it stays conformant. Five reviewer-dispatch sites
  (`review-and-merge-gates.md`, `review-code-change`'s orchestration protocol,
  `babysit-pr`'s post-head-change re-review, `carve-changesets`' per-changeset
  review, and `review-fix-loop`'s reviewer orchestration) additionally carry the
  reviewer-integrity rule: reviewers receive evidence and contracts, never
  conclusions, and a prompt that steers the verdict gets rewritten. Each site
  names where its own pressure comes from — a fix just written to satisfy a
  finding, an earlier changeset already reviewed clean, a loop that converges on
  confirmation it never earned — because a steered reviewer returns confirmation
  that is indistinguishable from a clean result at the point it is consumed.
  `implement-epic`'s explicitly-authorized parallel path gains post-integration
  verification: run the full required suite once against the integrated state,
  since each child's gates ran against its own candidate and non-overlap
  analysis predicts independence rather than demonstrating it. Wording stays
  product-agnostic (capability tiers and roles, never model names or product
  APIs), enforced by a per-skill assertion. No contract fields, schemas, or
  terminal states change. Twelve prose-contract assertions across six skills,
  each observed failing at the branch's original base `a1ee71c` (none of these
  eight files changed between it and this candidate's current base) and passing
  at head. The post-parallel paragraph records its ported source at the seam,
  which the named-peer registry requires of a "ported with attribution" row and
  which review caught as missing. Eval evidence: the four deterministic corpora
  are unchanged (implement-ticket 58/58, implement-epic 15/15, carve-changesets
  12/12, review-fix-loop 20/20, each with an empty per-case diff); `babysit-pr`
  and `review-code-change` have no corpus, so `just eval-record` records nothing
  and that gap is stated rather than papered over with unit tests. The
  `implement-epic` real-model tier ran six times and implicated this change's
  own first attempt at recording the ported source. Review required the habit to
  name its origin at the seam; satisfying that with a four-line attribution
  paragraph beside the verification obligation coincided with
  `epic-refreshes-after-blocked-merged-delivery` failing on
  `missing actions: verify_epic_acceptance`, and compressing the same
  attribution to a one-clause parenthetical coincided with its recovery. One run
  covers each condition — no change, four-line note, one-clause note — with
  three further runs corroborating the pattern, one of which was recorded from a
  tree that was not clean. Only a single run ever isolated the note's absence
  from the rest of the change. The reading those runs support is that a gate
  competes with non-operative prose placed beside it, which is the
  context-economy failure this repository's authoring standard already names;
  the effect is not quantified. Every summary's `candidate.sha` names a branch
  commit rather than a commit on `main`: this repository squash-merges, and this
  branch was rebased twice, so the norm's requirement that a summary name a
  commit a later reader can resolve is unattainable for any branch-recorded run
  by construction. The per-case maps inside the summaries are the durable
  evidence, not their SHA bindings, and that tension between the recording rule
  and squash merging is a follow-up rather than something this ticket can
  settle. Nothing else in the suite reacted: every unit test and both simplicity
  lenses passed the version that regressed. `epic-unreadable-implement-ticket`
  fails at base and passes in all five post-change real-model runs, a durable
  gain. `epic-incompatible-implement-ticket` changes status three times across
  those same five runs — including twice among the three runs that share the
  four-line note's byte-identical prose blob — and fails in the sole run
  recorded against the shipped one-clause prose, without disclosure until this
  sentence that the run cited above for a different case's recovery also
  regressed this one. That instability sets the tier's noise floor near one case
  per run, which bounds every claim above. `implement-epic`'s `SKILL.md` is the
  only one of this change's eight edited prose files a real model ever read.
  `implement-ticket` is the one skill `AGENTS.md` names as having a real-model
  executor and it has no real-model after run at all — its tier aborts in
  `claude_executor.extract_json_object`, the blocker already recorded against
  #154 — and `babysit-pr`, `review-code-change`, `carve-changesets`, and
  `review-fix-loop` either have no corpus or record only a deterministic tier
  whose own gap field says "no model read the prose." So seven of this change's
  eight prose edits carry no model-behavior evidence. The norm asks for "a
  recorded run" and a per-case diff without saying how many runs separate signal
  from variance, and a single run here would have reported the regression, or
  the gain, as settled. That gap, the corpus's 7-of-15 baseline pass rate, and
  the eight summaries this branch recorded from unclean trees are recorded as
  follow-ups rather than absorbed here
  (`bb31f34d3d311ca5b1fd44c09ba57826de36f91d`)

- feat(ready-ticket): pressure-test from a real baseline and record the
  before/after (issue #137, epic #120, the epic's third and final leaf) — #124
  shipped `ready-ticket` with a rationalization table marked "anticipated, not
  observed," pending this ticket. Four RED scenarios ran through an isolated
  `claude -p` session with no ready-ticket discipline loaded — no project
  context, no CLAUDE.md, an empty settings file, from a scratch directory —
  against the same requests the skill is meant to govern. The dominant failure
  was not the placeholder the anticipated table guessed at: every RED run that
  reached a full document asserted specific, unrequested technical and product
  decisions as settled fact — rate-limit tiers, retention windows, storage
  architecture — mostly with no hedge at all. A second, distinct failure: two of
  the four runs wrote the ticket to a file rather than returning it as the
  response, unannounced. Three RED scenarios were re-run GREEN with `SKILL.md`'s
  actual prose supplied as the operating instructions, same isolation, same
  request. All three closed: the two autonomous scenarios return `blocked`,
  naming the identical category of decisions RED had invented, and stating
  directly why inventing them would be wrong (*"you'd never learn a call was
  made on your behalf — which is exactly the failure the ticket is supposed to
  prevent"*); the interactive scenario asks exactly one clarifying question
  instead of drafting. None of the three GREEN runs writes a file. The
  rationalization table now carries four verbatim excuses from the RED
  transcripts in place of the anticipated wording, each mapped to the specific
  claim it precedes; one anticipated failure shape — skipped non-goals — was not
  observed and is recorded as a negative result rather than manufactured.
  `skills/ready-ticket/evals/baseline/` carries the full transcripts and the
  paired before/after comparison. A forward-eval harness is added under
  `skills/ready-ticket/scripts/evals/`, mirroring `implement-ticket`'s
  established shape (a closed action vocabulary, a `claude_executor.py`
  real-model executor, a deterministic `fixture_executor.py`) rather than
  inventing a new kind of tooling, with eight result-blind cases covering all
  four terminal results — two of them the exact scenarios pressure-tested above.
  Registered in `record_eval_run.py`'s suite registry alongside the existing
  skills. Thirty-eight behavioral tests bound to the ticket's acceptance
  criteria (`c657611bd41d87a2822137c1ac16d8633d8b923b`)

- feat(review-suite): establish house-owned review and PR-feedback consumption
  discipline (issue #127, epic #118) — add
  `review-suite/consumption-disciplines.md` as the canonical statement of how a
  skill metabolizes a review finding or a piece of PR feedback before it changes
  a line, and wire it into the three skills that consume findings. Four
  disciplines, each shipping the failure it prevents: verify each finding
  against the codebase before implementing it (a confident, well-argued finding
  about code that does not exist reads exactly like a real one once implemented
  — automated reviewers fail this way at scale); clarify every unclear finding
  before implementing any (a guessed reading gets built on, and the
  contradiction surfaces only after the dependent work exists, because findings
  from one review are frequently connected); never perform agreement ("good
  catch" before verification records a verdict nobody reached, and in an
  autonomous loop the courtesy consumes the reply that should carry evidence);
  and implement blocking, then simple, then complex, validating each
  individually (a batch landing together leaves a regression unattributable, and
  the ordering keeps a bounded cycle budget from stranding a correctness fix
  behind a cosmetic one). The port is form-2 with attribution to superpowers'
  `receiving-code-review`, and the prose records why it is a port rather than a
  delegation: that peer adjudicates between a human author and a human reviewer
  and its protocol turns on a partner who can be asked, while these consumers
  are autonomous loops where an ask-a-human step maps to a typed terminal
  instead — the stance survives the translation, the protocol does not.
  Distribution reuses the existing `just sync-contracts` mechanism and drift
  tests, with its own bundling set: `implement-ticket`, `babysit-pr`, and
  `carve-changesets` bundle the disciplines, and `review-fix-loop` deliberately
  does not, because it owns its own decide/fix consumption semantics — a
  recorded disposition the drift suite asserts rather than leaves implicit.
  `babysit-pr` additionally gains the `superpowers:systematic-debugging` slot in
  its CI-diagnosis loop, availability-conditioned with silent fallback, whose
  architecture-escalation insight maps to the skill's existing
  blocked-with-evidence terminal; a contract test asserts the peer never appears
  in the fail-closed capability requirements. Reviewer-side contracts, lens
  rubrics, severity vocabulary, and every consuming skill's own cycle budget are
  untouched. Eval evidence under the now-in-force norm: `implement-ticket`
  deterministic 58/58 with the same-tier diff reporting 58 unchanged and nothing
  newly failing or newly passing, `carve-changesets` deterministic completed,
  and the `implement-ticket` real-model tier recorded as `attempted`. That
  attempt got further than the #135 baseline's — headless auth succeeded and
  cases executed for roughly 25 minutes — before `run_forward` aborted on a
  `JSONDecodeError` parsing a model response, reproducibly at the same point
  across two runs, so the blocker is response parsing in
  `claude_executor.extract_json_object` rather than the OAuth failure #145
  records. `babysit-pr` has no registered eval corpus, so `just eval-record`
  records nothing for it and that gap is stated rather than papered over with
  its unit tests, which cannot observe `SKILL.md` prose
  (`a1ee71cc43ab04af221667a184f7dbf3edac77f1`)

- feat(evals): build the triggering-and-composition test corpus (issue #136,
  epic #120, the epic's second leaf) — forward evals ask whether a skill's prose
  governs behavior once it is loaded; this corpus asks the prior question,
  whether it is the one that loads at all. `triggering/corpus.json` carries 35
  prompts across all ten skills: positive prompts each must claim, negative
  prompts it must not, and the named collision prompts — "Review my change." and
  "Before merging, give this a proper review." filed from both sides, and
  "Implement ticket 412." filed from both `implement-ticket` and `ready-ticket`
  so the pair must agree on who wins. The answer key lives apart in
  `expectations.json`, and the runner enforces the separation structurally: an
  executor receives the prompt and the catalog of live skill descriptions and
  nothing else — no case id, no `kind`, no filed-under skill — with a test
  asserting that payload shape. The catalog is read from the `SKILL.md` files
  rather than copied, so the corpus cannot drift out of agreement with the
  descriptions it tests. Three tiers, each declaring itself in every recorded
  result: `headless` observes which skill a real session loaded, `description`
  asks a model to route from the catalog, and `fixture` is a rule table that
  exercises the harness and reads nothing. The fallback applies to the whole
  runner rather than to collisions alone because whether headless output
  reliably reports skill invocation is unverified, and the headless executor
  fails loudly instead of answering "no skill" when it cannot tell — recording
  an unobservable invocation as `none` would silently pass every negative case.
  The `description` tier follows #122's micro-test protocol: five repetitions in
  independent processes, majority wins, agreement fraction recorded so a 3/5
  result is never reported as 5/5. Writing the corpus surfaced a modelling error
  worth recording: a negative case asserts which skill must *not* win, which is
  not the same as asserting that nothing wins — "Implement ticket 412." is a
  negative for `ready-ticket` whose correct answer is `implement-ticket`, and
  the first draft's answer key said `none`. Peer-dependent expectations moved to
  the composition cases for the same reason: this tier's catalog contains only
  what is installed, so an absent peer cannot be picked and an expectation
  naming it would fail for install state rather than for routing. Recording goes
  through #135's convention rather than a second format: `record_eval_run.py`
  gains a `--suite` dimension, diffs never cross suites, and filenames carry the
  suite. Seven composition cases cover the four seams named in shipped prose;
  none could run, and each records the real reason — no composition harness
  exists, because this runner grades routing from a description catalog while a
  composition case needs a real session with the peer installed. Provisioning is
  a second, independent blocker wherever superpowers is required; it is not one
  for the `load-bearing` case, which makes that the cheapest seam to cover
  first. An earlier draft blamed an expired OAuth session instead, which this
  change's own recorded runs disprove — review caught it, and the corrected gaps
  say what is actually missing. The description tier records 35/35 with every
  case unanimous at five repetitions, and per-case agreement and vote counts are
  preserved, which is how a previously observed 4/5 pull from planning language
  toward `ready-ticket` could be shown not to reproduce and marked as such
  rather than shipped as a standing overlap. Twenty-one behavioral tests bound
  to the ticket's acceptance criteria, wired into `just test` and CI, each
  observed failing at the state it guards
  (`e7dd726b59e7ee35dea7a856163e86793dbc01e2`)

- feat(implement-ticket): add the behavioral-test evidence contract and peer
  methodology slots (issue #126, epic #118) — give the implementation phase a
  required change-demonstrating-test slot and make the peers that supply method
  strictly optional. Per the house testing doctrine (#122), this repository
  contracts the evidence and peers own the method: feature work shows behavioral
  tests encoding the ticket's acceptance criteria against the product's public
  surface failing at the base SHA and passing at the head SHA
  (`evidence_behavioral_test`); a bug fix shows a regression test red at base
  and green at head (`evidence_regression_test`); and two named, closed
  exemptions cover a behavior-preserving refactor, which needs only the existing
  behavioral suite green at both SHAs (`evidence_refactor_preservation`), and a
  docs-or-config-only change, which records the exemption itself
  (`evidence_docs_config_exemption`). The anti-coupling rule ships with its
  failure mode: a test asserting internals passes by construction, leaves the
  authored criterion unverified while appearing to cover it, and turns every
  later behavior-preserving change into a rewrite, so the suite ends up
  obstructing the change safety it was built to provide. The precedence rule
  from #122 resolves the three live TDD conflicts in place rather than per run —
  a universal red–green law loses to the refactor exemption, a process law loses
  to retroactive base/head observations, and a per-unit checklist loses to
  surface-behavior-per-criterion — and a peer's ask-a-human clause maps to the
  typed `blocked` result. Three peer slots are availability-conditioned with
  silent fallback: `load-bearing` before implementation under the registry's
  actor semantics, explicitly skipping assumptions `ready-ticket` already
  recorded as verified at authoring time; `superpowers:test-driven-development`
  during implementation as the recommended method for producing the contracted
  evidence; and `superpowers:systematic-debugging` on repeated fix failures, its
  architecture escalation aligned with the fix loop's existing final-cycle
  escalate-and-block text (#132 is still open, so the ticket's fallback
  applies). Both placement targets carry the contract: the direct path in
  `SKILL.md`'s implementation and fix-loop sections, and the delegated path in
  `references/delegated-execution/CONTRACT.md`'s Invocation section plus the
  delegated-worker paragraph — as prose riding in the existing validation
  evidence, with no invocation or result schema change. The four identifiers
  join the shared forward-eval action vocabulary in `claude_executor.py` and
  `fixture_executor.py`, and four new result-blind forward cases cover one
  change kind each while forbidding the other three slots, so claiming the wrong
  slot grades as wrong. The eval-evidence norm landed mid-flight (#135, PR
  #148), so this change records its runs rather than the planned marker the
  ticket originally allowed: the deterministic after-run is 58/58 and diffs
  against the recorded baseline as 54 unchanged with nothing newly failing or
  newly passing, and the real-model attempt is recorded as `attempted` because
  the environment's headless `claude` auth still fails — the same limitation the
  baseline recorded and deferred to #145, so model-behavior evidence for this
  change is deferred to the first capable run
  (`12c25845b40a19b7f3262406fa170cc4422512ca`)

- feat(evals): institute the eval-evidence norm for skill-prose changes (issue
  #135, epic #120, the epic's first leaf and the gate on its other two) — a
  change to a skill's normative prose now ships with a recorded model-behavior
  run. `AGENTS.md` gains the norm with its real-model-executor-where-one-exists
  scope; `docs/skill-authoring.md`'s eval-backed change norm stops being a
  placeholder pointing at this issue and states what the recorded evidence has
  to be worth. The tool side is `scripts/record_eval_run.py` behind
  `just eval-record <skill>`, which runs a skill's evaluations and writes one
  JSON summary per run to `skills/<skill>/evals/results/`. Three properties of
  that format exist because the alternative hides a regression rather than
  surfacing it. Summaries carry **per-case** outcomes and a **diff against the
  skill's previous recorded run**, not a pass percentage: a prose edit that
  leaves the count identical while moving which cases pass has changed behavior,
  and the count conceals exactly the movement worth recording. Each summary
  names the **tier** that produced it, because a deterministic replay proves the
  harness and corpus still agree with each other and cannot prove the edited
  sentence still steers a model — no model read it — so a skill with no
  real-model executor records the deterministic tier *plus* the gap text, and
  the two tiers are never confusable in the evidence. And a run is recorded
  under one of **three statuses**: `completed`, `failed`, and `attempted`, the
  last reserved for evaluations that could not run at all. Review caught the
  collapse of the middle one — a deterministic run that went red was being filed
  as `attempted`, which is the path the norm mandates for eight of the ten
  skills, and whose established reading is *evidence deferred, land the change
  anyway*. That reading turns the exact regression the norm exists to catch into
  a routine deferral notice, so `attempted` now means only that no evidence
  could be collected, and a diff is drawn solely against a prior run of the same
  tier that produced case outcomes — a cross-tier comparison reports the tier
  change as behavioral movement, and one against an empty run reports "nothing
  regressed" when nothing was compared. Filenames carry a per-directory sequence
  after the timestamp: two runs recorded in the same second would otherwise sort
  by stage name, which reverses a before/after pair and inverts its recorded
  diff. A skill's evals are **registry data** — `implement-ticket` and
  `implement-epic` real-model, `carve-changesets` and `review-fix-loop`
  deterministic, all four already satisfying the per-case and aggregate
  interface — and a skill with no corpus records nothing and states the gap in
  its PR. Review rejected the earlier fallback to a skill's own unit tests: they
  cannot observe `SKILL.md` prose, so for eight of the ten skills the norm would
  have mandated committing a summary whose cases, totals, and diff were
  structurally empty — a per-change obligation to duplicate `just test` in
  exchange for evidence the norm itself calls insufficient. Results are
  deliberately **not** a CI gate — a model-in-the-loop run is neither free nor
  perfectly repeatable, so a required check over one spends money to buy
  flakiness, and the first red run from ordinary variance trains everyone to
  re-run it until it goes green. Runs are recorded from a committed, clean tree
  and committed on top, so each summary's `candidate.sha` names a commit a later
  reader can resolve rather than one amended away, and `worktree_clean` is left
  unknown rather than asserted when git cannot be read. Adds
  `.github/PULL_REQUEST_TEMPLATE.md` pointing at the norm, and fifteen
  behavioral tests bound to the ticket's acceptance criteria, each observed
  failing at base `8f3f0ad` and passing at head. The baselines are committed in
  a follow-up commit on this branch, recorded from the clean tree at the code
  commit. This candidate's own baseline is the norm's fallback path in practice
  rather than in theory: the `claude` CLI was present but headless auth failed
  with an OAuth-token-revoked 401, so the attempt is committed with its
  diagnosis alongside a deterministic baseline passing 54/54, and the real-model
  baseline is deferred to #145. A real-model adapter for `carve-changesets` is
  deferred to #144 (`67ff0dbce8c534bcf82bde033f5534bb3f2db265`)

- feat(implement-ticket): route not-ready blocked results to ready-ticket (issue
  #125, epic #118) — give `implement-ticket`'s not-ready `blocked` result a
  sanctioned next step instead of a dead end. A ticket that fails the body-level
  readiness conditions now returns `blocked` naming repository-owned
  `ready-ticket` and carrying the stable marker
  `implement-ticket:requires-ready-ticket:<tracker>:<ticket-id>`, in the same
  form as the existing `requires-epic` marker, so contract tests can assert its
  exact shape and a caller can detect a routing loop. The edge is a
  **recommendation, not a dispatch**: `implement-ticket` never invokes
  `ready-ticket` and never runs its elicitation — the caller decides. The
  readiness bar itself is untouched, and so is the gate's existing remediation:
  when ticket editing is authorized and the gap is not a product, data,
  authorization, migration, destructive, or architecture decision, the skill
  still repairs the body in place and continues, and only the other branch emits
  the marker. It is one-way by construction, because `ready-ticket` terminates
  in a ticket body and never invokes `implement-ticket`, so no cycle can form;
  the incoming-marker check returns a routing-cycle `blocked` rather than
  recommending again. Only body readiness carries the marker: an unresolved
  native dependency, a missing prerequisite outcome, an absent authority, or a
  competing canonical candidate keeps its own blocked reason, because
  `ready-ticket` cannot repair any of those. Both dependency-documentation
  surfaces — the README chain and `implement-ticket`'s own dependency prose —
  now render the recommendation as a dashed `┈▷` edge annotated "recommendation
  only, never invoked", with solid edges reserved for invocation and the diagram
  legend pointing at the owning section rather than restating its rules. Also
  corrects the README's plugin-installation count from nine skills to ten, stale
  since `ready-ticket` landed earlier today
  (`ee4b8d7bdbf573fccc8c1b8dc11b937357e38604`)

- feat(review-suite,skills): deliver review-packet and epic-dispatch context via
  files instead of inlined context (issue #130, epic #119, the epic's only
  unblocked child) — stop spending a reviewer's and a dispatched worker's
  context on artifacts they can read for themselves. `candidate.diff` becomes a
  schema `oneOf`: the existing inline unified-diff string, or an evidence-path
  object naming a file whose content is that diff. The packet builder writes the
  complete diff to a temporary directory **outside** the candidate worktree and
  records the path, so the existing before/after read-only integrity check stays
  trivially satisfied by construction rather than needing an exemption; lens
  dispatch in `review-code-change`'s `SKILL.md` and
  `references/orchestration-protocol.md`, and the caller-side invocation prose
  in `implement-ticket`'s `references/review-and-merge-gates.md`, now hand the
  path and no longer inline the complete `base...HEAD` diff. `validate.py` gains
  generic `oneOf` support — reporting the closest branch's own errors rather
  than a generic no-form-matched message, so every existing blockable-error
  pattern keeps matching — and fails closed when a referenced diff file is
  absent, empty, or named by a relative path, classifying all three as missing
  review evidence so the review yields `blocked` instead of reading an
  unresolvable reference as a smaller diff. The absolute-path requirement came
  out of this change's own review: because the reference is now the sole binding
  between a lens and the diff it reviews, and the builder and each lens
  revalidate the same packet from their own working directories, a relative
  reference could resolve to a different same-named file and bind a lens to a
  diff that is not the candidate's — a substitution no candidate-identity check
  can catch, since those compare SHAs and never the diff's provenance. Fixtures
  under `review-suite/fixtures/` and the eval strata stay inline and pass
  unmodified; all seven bundled `references/review-suite/` copies (including
  `review-fix-loop`'s) are re-synced via `just sync-contracts` and the drift
  tests pass. On the dispatch side, `implement-epic` gains file-based
  child-dispatch artifacts under `.implement-epic/` — a brief file as the single
  source of a child's task requirements and a per-dispatch report file the
  executing context appends to across rounds — plus the no-pasted-history rule
  with its failure mode: each pasted round lengthens the next prompt, so
  dispatch reproduces stale context faster than it delivers current
  requirements. Those two paths are absolute and the directory sits at the
  coordinator's working root outside every candidate worktree, for the same
  cross-context reason as the diff reference: the executing context owns a
  different worktree, and because the prompt deliberately does not restate the
  brief, an unresolvable path dispatches a worker with no requirements at all
  while the prompt still looks complete. That dot directory ships the
  skill-local `.gitignore` `AGENTS.md` requires, in the shape
  `skills/ready-ticket` established. Delegated execution stays out of the
  mandate because the coordinator is contractually opaque and this repository
  cannot bind its prompt format, so `implement-ticket`'s delegated-worker
  paragraph carries the rule as recommend-only prose that never returns
  `blocked` for its absence, and `references/delegated-execution/CONTRACT.md` is
  unchanged. Ported with attribution from superpowers'
  `subagent-driven-development` fresh-context construction, already recorded as
  that skill's secondary registry entry. Adds a `missing-diff-evidence-file`
  orchestration eval case proving the fail-closed path, and twelve behavioral
  tests bound to the ticket's acceptance criteria, each observed failing at base
  `73f1aa8` and passing at head (`8f3f0adb7607ff1e4a880b224c8eff475c28fbb2`)

- feat(skills): add the ready-ticket skill for peer-aware ticket authoring
  (issue #124, epic #118, the epic's first seam leaf) — add
  `skills/ready-ticket`, which turns a vague idea or an unready GitHub or Linear
  ticket into an implementation-ready ticket body and terminates in that body,
  never in a spec or plan file. Readiness is defined by reference rather than
  reinvented: the target is exactly the body-level conditions of
  `implement-ticket`'s readiness gate (observable goal, acceptance criteria,
  non-goals, preserved behavior, required verification classifiable as pre- or
  post-merge, and no unresolved product, data, authorization, migration,
  destructive, or architecture decision), so the two skills cannot drift into
  disagreeing about what "ready" means. Four exhaustive typed terminal results,
  each fixture-covered: `ticket_ready` (body stored in the tracker and reread to
  confirm it matches what was approved, because a successful API response is
  delivery state and not proof of the stored contract), `draft_ready` (returned
  on either of two grounds — ticket-management authority absent, or no tracker
  chosen and none choosable in this run; that authority grant defaults to off
  and is never inferred from tracker read access or from phrasing such as "file
  this" or "write it up"), `decomposition_recommended` (multi-subsystem work
  handed back to the operator with its rationale; epic authoring is a recorded
  deferral of this epic, not an omission), and `blocked` as the honest fallback.
  Acceptance criteria must be observable behaviors of the product's public
  surface so each is directly encodable as a behavioral test; a criterion
  assertable only against internals is treated as a readiness defect to fix
  during elicitation, per the house testing doctrine from #122. An unconditional
  four-scan self-review — placeholder, contradiction, scope, ambiguity — runs
  identically with or without any peer, so no-placeholders rigor never depends
  on install state. The two peer seams follow #123's registry exactly: the
  `superpowers:brainstorming` borrow takes the questioning discipline (one
  question at a time, intent before construction) and stops at its
  design-approval handoff to `writing-plans`, with a peer plan header's
  "REQUIRED SUB-SKILL" executor mandate explicitly non-binding; and
  `load-bearing` carries the registry's actor semantics verbatim — interactive
  offers once and the user's explicit yes is the peer's required request,
  autonomous records the recommendation in evidence and proceeds — with silence
  when the peer is absent. GitHub and Linear adapter references mirror
  `implement-ticket`'s pattern and hold the line that authoring a body is not
  graph or workflow authority. Also records the `ready-ticket` row in the
  registry's trigger-collision audit against `brainstorming`, the epic's
  highest-risk collision, resolved by artifact and terminus rather than by
  contorting either description. Ships 24 result-blind eval cases with their
  expectations held separately and a 31-assertion contract test;
  pressure-testing from baseline is #137's, so the rationalization table carries
  anticipated rather than verbatim wording and says so
  (`73f1aa8e2fc34fa93f989c0e146efacfe41133e7`)

## 2026-08-03 — Established the written skill-authoring methodology including the house testing doctrine, then added the peer-skill convention with a complete named-peer registry and rewrote all nine trigger descriptions to the description-states-when rule

- feat(skills): define the peer-skill convention and registry, and rewrite all
  nine trigger descriptions (issue #123, epic #117, the epic's second and final
  child) — extend `docs/skill-authoring.md` with a "The peer-skill convention"
  section and a "Named-peer registry" section, then rewrite every skill's
  trigger description to the description-states-when rule the document
  established in #122. The convention states prose-level soft detection against
  the session skill listing (no runtime probing, no manifest coupling, no
  dependency declaration, because a probe turns an optional recommendation into
  a coupling that can fail); the fallback rule that peer absence is a silent
  fallback to built-in behavior and never a `blocked` condition, with the
  stronger corollary that a quality outcome is never conditioned on peer
  availability — only the method is delegated, while the outcome stays enforced
  by this repository's own gates, so the same skill cannot produce different
  quality on two machines; a pointer to #122's existing peer-precedence rule
  rather than a restatement of it; trigger-namespace rules claiming
  tracker-ticket, PR-lifecycle, merge, epic-orchestration, and
  repository-owned-review-invocation language while disclaiming planning,
  debugging, TDD, and brainstorming language, with structurally unavoidable
  overlaps dispositioned in the registry instead of dodged by contorted wording;
  and the peer pin (superpowers at `44c9b2d6e889982ac18c27d05a19fefe335194e1`,
  fourteen skills; load-bearing at its reviewed head), since an unpinned
  registry describes a moving target. The registry classifies all fourteen
  pinned superpowers skills plus load-bearing into one primary form each from
  the epic's taxonomy, with a rationale per entry: referenced peers
  (`test-driven-development`, `systematic-debugging`, and `brainstorming` as a
  bounded borrow of questioning discipline that stops at its design-approval
  handoff to `writing-plans`); ported with attribution (`receiving-code-review`,
  `using-git-worktrees`, `writing-skills`, `verification-before-completion`,
  `dispatching-parallel-agents`); house territory (`subagent-driven-development`
  and `executing-plans` for executor exclusivity,
  `finishing-a-development-branch` for the merge boundary, `writing-plans`
  because ticket authoring is house-owned and its emitted "REQUIRED SUB-SKILL"
  plan header is an executor mandate, and `requesting-code-review` because
  review production is house-owned through typed schemas, fail-closed evidence
  binding, and candidate-identity rules); and no relationship
  (`using-superpowers`, a bootstrap for the peer's own library).
  `subagent-driven-development` carries the required secondary pattern-port
  entry for its fresh-context subagent construction. load-bearing is recorded
  explicit-invoke-only with its actor semantics: interactive offers once and the
  user's yes is the peer's required request, autonomous records the
  recommendation in evidence and proceeds. A trigger-collision audit table
  records each of the nine descriptions against the overlapping peer trigger
  terms at the pin. The nine rewrites drop the workflow summaries that let an
  agent execute a lossy paraphrase without loading the body — `review-fix-loop`,
  the longest, falls from 923 to 589 characters — and each now states when to
  use, the scope boundary, and the terminal result shape a caller needs to
  route. This is a deliberate triggering-behavior change; #136's corpus verifies
  it after the fact (`83a526bbee6598ef6c508550485ea20d1ebc4daa`)
- docs: write the skill-authoring methodology document with the house testing
  doctrine (issue #122, epic #117, the epic's first child) — add
  `docs/skill-authoring.md` combining empirical prose discipline with this
  repository's contractual layer, and point `AGENTS.md` at it as the authoring
  standard for every new skill and every edit that changes an existing skill's
  normative behavior. The document states the failure-first rule that governs
  the rest (write each guideline against an observed failure and state that
  failure in the text, so a reader can tell whether a rule applies and an editor
  can tell when to delete it); description rules that treat the description as a
  routing decision rather than a summary, with the "could an agent that read
  only the description produce a plausible-looking version of the work?" test
  separating legitimate scope-and-outcome clauses from followable procedure,
  plus requester-vocabulary keyword coverage and the `skills-ref validate`
  frontmatter limits; a form-to-failure taxonomy mapping discipline violation to
  a prohibition plus verbatim rationalization table, wrong-shaped output to a
  positive contract with a closed value set, omission to a required template
  slot with an explicit empty spelling, and conditional behavior to an
  observable predicate, with a selection table naming why the other forms fail;
  the two-tier prose testing protocol — the baseline tier (run scenarios on
  fresh subagents without the skill, record rationalizations verbatim, write
  against those specific failures, compare candidate prohibition wording against
  the baseline rather than assuming it, re-test after every material edit, and
  withhold expectations from evaluated agents) and the cheap micro-test tier for
  wording choices (always run a no-guidance control and do not author the
  guidance if the control does not fail, 5+ repetitions per variant, read every
  flagged match by hand because template echoes masquerade as hits, treat
  variance as a metric) carrying both tested wording laws: a single added nuance
  clause can degrade a winning recipe, and exemption clauses do not scope, so
  restructure rather than exempt; the contractual layer as first-class doctrine
  covering typed terminal results, fail-closed preconditions, granular
  default-off authority grades, evidence binding with its untrusted-input
  boundary, and the eval-backed change norm referenced as planned pending #135;
  the peer-precedence rule stated once for every seam to reference (house
  evidence contracts and typed results supersede a loaded peer's absolutes, and
  a peer's ask-your-human-partner escape valve maps to the typed `blocked`
  result rather than stalling an autonomous run); the house testing doctrine,
  expressed as evidence shapes rather than method mandates and distinguished
  from the eval-backed norm (that norm asks whether a skill's prose still
  governs behavior; the testing doctrine asks whether a change's code does what
  its ticket said), requiring feature work to show the behavioral test encoding
  each acceptance criterion failing at the base SHA and passing at the head SHA,
  bug fixes to carry a regression test red at base and green at head, no
  assertion on implementation details, and a recorded rationale for diverging
  from a peer's universal per-unit red-green law (per-unit
  implementation-granularity tests conflict with the anti-coupling rule and are
  deliberately not required; the precedence rule resolves the conflict when both
  are loaded); the governance note recording that peer authoring skills such as
  superpowers' `writing-skills` are a reviewed source rather than a governing
  document; and context-economy guidance on keeping `SKILL.md` to deciding and
  routing, triggering references at the moment they apply, never force-loading,
  and budgeting body growth qualitatively rather than by token count. Closes
  with an authoring checklist. Scope held to doctrine: the peer-skill convention
  and named-peer registry remain with issue #123, and retrofitting existing
  skills remains with epic #119 (`4e60776d1fea8b966754f8be6da5bebd99478e67`)

## 2026-07-31 — Unified the duplicated JSON-schema validation engine between review-suite and review-fix-loop, packaged and documented the standalone review-fix-loop skill, added the review-fix-loop cross-cutting evaluation corpus, recorded the first review-fix-loop `update_pr` fix cycle

- fix(review-fix-loop): unify the duplicated generic JSON-schema-subset
  validation engine (`_path`/`_is_type`/`validate_schema`) with the canonical
  `review-suite/scripts/validate.py` copy (issue #115, discovered during epic
  #95's closeout review) — extend the canonical engine's `_is_type`/
  `validate_schema` to support `"type": "integer"` and `minimum`/`maximum`
  numeric checks as a backward-compatible superset (no current
  `review-packet`/`review-result` schema field uses `integer`, so this is
  behavior-preserving for every existing consumer), then refresh every bundled
  `references/review-suite/validate.py` copy via `just sync-contracts`;
  `skills/review-fix-loop/scripts/validate.py` no longer hand-duplicates
  `_path`/`_is_type`/`validate_schema` and instead imports them from its bundled
  copy via the same `importlib.util.spec_from_file_location` pattern
  `review_gate.py` already uses for `evaluate_bound`, keeping only its own
  schema-specific `validate_invocation`/`validate_checkpoint`/
  `validate_terminal_result` and cross-document checks; adds a regression test
  proving `max_fix_cycles` non-integer rejection now flows through the shared
  engine, plus generic-engine unit tests for `"integer"`/`minimum`/`maximum` in
  `review-suite/scripts/tests/test_contracts.py`; all 273 pre-existing
  review-fix-loop tests and 318 pre-existing review-suite tests continue to pass
  unchanged, plus the 9 new tests this change adds
  (`c400d77fc93e84d166658edf8f7dee0b08e0b612`)
- feat(review-fix-loop): package and document the standalone skill for discovery
  (issue #102, epic #95, the epic's final child) — list `skills/review-fix-loop`
  in the README's "Current reusable agent skills" section with its
  `local_commit`/`update_pr` policies and the tracked #103/#104/#105
  caller-migration follow-ups, correct the eight-skills count to nine, and wire
  its `just test-review-fix-loop`/`just eval-review-fix-loop` targets into the
  Quick Start and evaluation sections; add `review-fix-loop` to
  `scripts/validate_plugins.py`'s `REQUIRED_SKILLS` set so a missing install or
  a missing `agents/openai.yaml` fails plugin packaging validation in CI,
  matching every other repository-owned skill; refresh
  `agents/claude-code.md`/`agents/openai.yaml`, stale since issue #98, to
  describe the `local_commit`/`update_pr` workflows issues #99-#101 actually
  delivered instead of only document validation and one review pass; and add a
  "Publication policy and retained commits" section to `SKILL.md` itself stating
  that both workflows keep fixes local until convergence, that `update_pr`
  publishes exactly once, and that every non-converged terminal result reports
  its retained unpushed commits via `unpushed_commits`/`operator_action`
  (`a1623de4d1222d2ae08c53d5e2ee19b7d5693281`)
- fix(review-fix-loop): configure `user.email`/`user.name` on both git clones
  `scripts/evals/corpus.py`'s
  `up_sequential_publication_race_second_clone_loses` scenario creates,
  mirroring `helpers.init_repo`'s existing convention for every non-cloned
  fixture repo — `git clone` never copies a source repository's local git
  identity config, and unlike a developer machine a CI runner has no global
  identity configured either, so the scenario's own `git commit` call failed
  with "Author identity unknown" in GitHub Actions even though every local run
  passed; reproduced the exact CI failure locally under a forced no-identity
  condition, confirmed the fix resolves it, and confirmed GitHub Actions' own
  `ci` check on PR #113 is green (`c14c912d87373fa84eaefb221ccefe936cc58a02`)
- fix(review-fix-loop): consolidate `scripts/evals/helpers.py`'s five fixtures
  that were byte-identical or functionally identical to
  `scripts/tests/helpers.py`'s own (`init_repo`, `CLEAN_TEMPLATE`,
  `ALWAYS_PASS_VALIDATION`, `finding`, `make_clean_reviewer`,
  `fixing_apply_fix`, `accepting_decide`) into imports from that sibling module
  instead of a second source of truth, following this repository's own
  `carve-changesets` precedent of importing across the `scripts/tests`/
  `scripts/evals` boundary within one skill, and remove one unused reviewer
  fixture (`make_expanding_findings_reviewer`) left over from a descoped
  scenario, closing the one code-simplicity gap the first review-code-change
  pass on #101 found (`c14c912d87373fa84eaefb221ccefe936cc58a02`)
- feat(review-fix-loop): add the cross-cutting, result-blind evaluation corpus
  (issue #101, epic #95) covering convergence, repeated findings,
  invalid/incomplete reviews, declined findings, budget exhaustion, interruption
  and recovery, validation failure, reviewer mutation, and publication races
  across both `local_commit` and `update_pr`, plus the fresh-subagent default
  and the explicit in-agent override — twenty scenarios in
  `scripts/evals/corpus.py`, each driving the real engine against a real
  disposable Git repository (and, for `update_pr`, a real disposable bare
  remote) and graded in `scripts/evals/grader.py` against independently derived
  Git evidence (a real commit count, a real file's content at a real commit, a
  real remote ref, a real object's reachability) rather than the returned
  terminal-result document's own claims; `scripts/tests/test_evals.py`
  demonstrates the grader rejecting both a fabricated convergence claim and a
  fixture that cannot actually converge, and runs the whole corpus under
  `just test`; `just eval-review-fix-loop` is the standalone entry point
  (`c14c912d87373fa84eaefb221ccefe936cc58a02`)
- fix(review-fix-loop): extract the test fixtures shared between
  `test_local_commit.py` and `test_update_pr.py` (the module loader, a bare
  local repository, the always-passing validation commands, the
  marker-file-driven fake reviewer, and the accepting decider/fixer) into a
  sibling `scripts/tests/helpers.py`, matching
  `carve-changesets/scripts/tests/helpers.py`'s established precedent, closing
  the one code-simplicity gap the first review-code-change pass on #100 found
  (`729135bb11d5bd8f0efa3a66d1c1ab1f978a3f6d`)

## 2026-07-30 — Delivered and evaluated the standalone review-fix-loop `update_pr` workflow, delivered and evaluated the standalone review-fix-loop `local_commit` workflow, implemented the review-fix-loop reviewer isolation and complete-review orchestration and local execution substrate (common-directory locking, isolated attempts, checkpoint persistence, and recovery), defined the review-fix-loop invocation, checkpoint, and terminal-result contracts, removed the unproven verification-sufficiency pass and its required-evidence field from review-correctness, and simplified the review-fix-loop design around local coordination and Git-native publication safety

- feat(review-fix-loop): add and evaluate the standalone `update_pr` workflow
  (`scripts/update_pr.py`'s `run_update_pr`), composing the exact same
  review/fix/converge engine `local_commit.py` already implements — every
  intermediate fix commit stays local — plus one expected-old, fast-forward-only
  Git publish immediately after convergence; resolves and cross-validates the
  fork/remote publication target without assuming "origin" ownership, validates
  `remote_iteration_grants`, and preserves the converged local commit with an
  actionable recovery path when the publication race is lost, the local
  candidate's history does not descend from the expected old head, or the remote
  is unavailable, with disposable-local-remote fixtures for a successful
  converge-then-publish run (with and without a fix cycle), a fork target, a
  competing remote update that cannot be overwritten, non-fast-forward history,
  a misconfigured target, a mismatched remote-iteration grant, an unreachable
  remote, and the remote-target lock actually being exercised end to end;
  generalizes `local_commit.py`'s internal loop into a policy-parameterized
  `_run_engine` both entry points share, with `run_local_commit`'s own behavior
  and its 21 existing tests unchanged
  (`729135bb11d5bd8f0efa3a66d1c1ab1f978a3f6d`)
- feat(review-fix-loop): compose the contract, local-execution, and
  reviewer-orchestration leaves into the end-to-end standalone `local_commit`
  workflow (`scripts/local_commit.py`'s `run_local_commit`), enforcing the
  fix-cycle budget, committing selected fixes in isolated attempts, promoting
  only a converged candidate, and reporting explicit retained-commit and
  operator-action evidence for every non-converged stop, with end-to-end
  fixtures for immediate convergence, one and multiple fix cycles, budget
  exhaustion, validation failure (unavailable/untractable/tractable), operator
  input (declined finding and scope expansion), expanding/oscillating finding
  sets, repeated failed attempts, and interrupted-attempt recovery
  (`eaa1ded44eef0fa29d874d93196ffa7d3e0e1e79`)
- fix(review-fix-loop): remove three subsumed/redundant tests and cut
  `reviewer_orchestration.py`'s docstring/comment density from roughly one line
  of prose per line of code down to sibling-module levels, replacing restated
  rationale with single pointers to `references/reviewer-orchestration.md`,
  closing the two code-simplicity gaps the sixth review-code-change pass on #98
  found (`8ef6db199526beb6e44408f3848f679dd88edb58`)
- fix(review-fix-loop): correct an off-by-one changelog SHA attribution left by
  the previous fix cycle's own rebase cleanup — the duplicate-test entry and the
  `ignored`-comparison entry each carried the other's identity, closing the gap
  the fifth review-code-change pass on #98 found
  (`8ef6db199526beb6e44408f3848f679dd88edb58`)
- fix(review-fix-loop): rebase onto the merged #97 local-execution substrate,
  document that a mutation attributable to a review pass must stop the
  invocation with `blocked/reviewer_integrity_failure` immediately rather than
  only relying on the `write_isolation`/`converged`-rejection backstop, and
  correct a changelog SHA left stale by that same rebase, closing the two gaps
  the fourth review-code-change pass on #98 found; the extracted
  `review_gate.evaluate_bound` reuse (cycle 1) is kept as the deliberate design
  after correctness confirmed it changes no accept/reject outcome for
  `implement-ticket`/`babysit-pr` (`8ef6db199526beb6e44408f3848f679dd88edb58`)
- fix(review-fix-loop): remove a byte-identical duplicate test and trim
  history-narrating/triplicated docstring prose in `reviewer_orchestration.py`
  and `reviewer-orchestration.md` down to one owner per rationale, closing the
  two code-simplicity gaps the third review-code-change pass on #98 found
  (`8ef6db199526beb6e44408f3848f679dd88edb58`)
- fix(review-fix-loop): stop comparing `ignored` worktree state for reviewer
  mutation (authorized validation commands legitimately create ignored build
  artifacts, which previously made `converged` unreachable), fail closed instead
  of silently passing when a before/after snapshot omits a required capture key,
  and collapse the packet-less `evaluate_review_result` path into the single
  packet-plus-result evaluator (`review-fix-loop`'s own
  checkpoint/terminal-result contract never persists one without the other, so
  no caller can legitimately use the weaker path), closing the two blocking gaps
  and the one strong-recommendation gap the second review-code-change pass on
  #98 found (`8ef6db199526beb6e44408f3848f679dd88edb58`)
- fix(review-fix-loop): detect refs mutation (not only `head_sha`) between
  before/after reviewer snapshots, reconcile the packet/result evaluator with a
  contract-legal identity-omitting `blocked` result while still binding the
  packet itself to the current candidate, and extract the canonical
  `review_gate.evaluate_bound` (bundled into `implement-ticket`, `babysit-pr`,
  and now `review-fix-loop`) instead of a second candidate-binding
  implementation, closing the three gaps the first review-code-change pass on
  #98 found (`8ef6db199526beb6e44408f3848f679dd88edb58`)
- feat(review-fix-loop): implement reviewer isolation and complete-review
  orchestration — fixed lens resolution, default fresh-subagent review execution
  with an explicit in-agent override, before/after mutation detection that fails
  a cycle closed, checkpoint-shaped review-record construction, and
  deterministic finding normalization/selection (#98)
  (`8ef6db199526beb6e44408f3848f679dd88edb58`)
- feat(review-fix-loop): add `scripts/local_execution.py` implementing #97's
  local execution substrate — non-blocking common-Git-common-directory candidate
  locking (local-ref lock before the optional `update_pr` remote-target lock,
  released in reverse order), isolated attempt worktrees created from the exact
  canonical head, verified fast-forward-only canonical promotion that fails
  closed and preserves the candidate on a dirty or advanced canonical worktree,
  atomic schema-validated checkpoint persistence and resume reconciliation,
  preserved failed-attempt artifacts, cleanup that only ever removes the
  `review-fix-loop/attempt/` namespace it created, and recovery of an
  interrupted attempt against a checkpoint's own history — with deterministic
  tests against real temporary Git repositories covering contention,
  interruption, stale state, dirty worktrees, promotion races, and cleanup
  safety (`26b4cf47168dc8432f7d6e5e4597439af6391a51`)
- fix(review-fix-loop): reject `converged` when any `review_records` entry — not
  only the final-head-bound one — recorded a mutation attempt, closing the gap
  the tenth (final) review-code-change pass on #96 found
  (`0187dfc77444fbf410b5ed86a42a12e4d088e7b3`)
- fix(review-fix-loop): add a per-pass `reviewer_identity` field to
  `review_records` in both checkpoint and terminal-result, and reject a dirty
  `candidate.worktree` (`staged`/`unstaged`/`untracked`) in
  `validate_invocation`, closing the two gaps the ninth review-code-change pass
  on #96 found (`4daa2a67a38be3baa7741380eb689581ce31a1db`)
- docs: record the ninth review-fix-loop fix cycle in the changelog
  (`80690173571678bb14d14703451a8ab6d29b2cba`)
- fix(review-fix-loop): complete the terminal-result schema against the design's
  Terminal result contract field list (`worktree`, `resume_status`,
  `unresolved_or_deferred_findings`) and require `ahead_by`/`behind_by`
  alongside the head fields whenever a source is `bound`, closing the gaps the
  eighth review-code-change pass on #96 found
  (`adf2ef5062038836d750b01e19f1549373ce1aad`)
- docs: record the eighth review-fix-loop fix cycle in the changelog
  (`65a256a32b3087d064efb5e4a24725cfb1762467`)
- fix(review-fix-loop): complete the checkpoint schema against the design's
  durable-checkpoint field list (`preserved_failed_attempts`, `pull_request`)
  and extend the optional pull-request identity cross-check to both
  cross-document functions, closing the gap the seventh review-code-change pass
  on #96 found (`e7a955a321bafab1cd6f20b77758aa26670567bc`)
- docs: record the seventh review-fix-loop fix cycle in the changelog
  (`f6d1adccea4ee1e6571c911b10053aa4c27e00ba`)
- docs: record the sixth review-fix-loop fix cycle in the changelog
  (`31789481f000567a4b69cb0a1d5ba77b8d8c4dba`)
- fix(review-fix-loop): systematically close cross-document identity checks and
  commit provenance, enumerating the complete invariant field set
  (`invocation_id`, `repository`, `branch`, original fix-cycle budget,
  `publication.policy`, initial head, initial comparison base) that must agree
  across invocation, checkpoint, and terminal-result, closing the one remaining
  gap (`branch` in `validate_checkpoint_against_invocation`) plus the
  commit-provenance gap (`created_commits`/`fix_commit_sha` linkage) the sixth
  review-code-change pass on #96 found
  (`040ae824fae708efe46ca772f378c30378c9c695`)
- fix(review-fix-loop): add the missing repository/branch/publication.policy
  checkpoint cross-check, the design-enumerated `allowed_remediation_scope`,
  `worktree`, and `validation_outcomes` schema fields, and correct a
  misattributed changelog SHA, closing all three items the fifth
  review-code-change pass on #96 found
  (`a6178b8da086fab80bd52596babb0208304163a1`)
- docs: record the fifth review-fix-loop fix cycle in the changelog
  (`e71ea93ad98beec7b39cf6bb6c2a123743e820cf`)
- fix(review-fix-loop): add validate_checkpoint_against_invocation cross-check,
  symmetric to the existing `validate_terminal_against_checkpoint`, closing the
  gap the fourth review-code-change pass on #96 found: nothing inside a
  checkpoint document alone could prove `base_revision_history[0]` was the
  invocation's real original comparison base
  (`c625bb87b7aefb2371b992b20e4ce07b12b1c270`)
- docs: record the coordinator-authorized fourth fix cycle in the changelog
  (`2f3addbdceefb0a952fa1fb035475d0a9d31ebfb`)
- fix(review-fix-loop): require non-empty scoped validation and full base
  history match, closing two remaining gaps the third review-code-change pass on
  #96 found: an empty or scope-incomplete `validation_summary` could still claim
  `converged`, and the checkpoint/terminal-result cross-check compared only the
  final comparison base, never the initial one
  (`3d240c6be6a33bf131aa7ccee2544c59a36614c1`)
- docs: record the third review-fix-loop fix cycle in the changelog
  (`86c7df20d44d0c398c34bee5b8272dca4b239cf7`)
- docs: record the comparison_base cross-check fix in the changelog
  (`7d206acd32151405865c4ade4e9e7399ea739f57`)
- fix(review-fix-loop): check comparison_base in the checkpoint/terminal-result
  cross-check, closing a gap where `validate_terminal_against_checkpoint`
  silently omitted the base-identity leg CONTRACT.md already documented it as
  covering, found by the second review-code-change pass on #96
  (`e18f1469cf6d5f5cff1d99045dd041cdc5e77b71`)
- docs: record the converged-evidence fix in the changelog
  (`1c9fcdc5f4ae5765414f4b25839c07122c3bb151`)
- fix(review-fix-loop): reject converged results with non-clean embedded
  evidence, closing a gap where `validate_terminal_result` never inspected
  `review_records` or `validation_summary`, found by the initial
  review-code-change pass on #96 (`fc701b0bb29047af7b2ad24f25fb1db739718f89`)
- docs: record the review-fix-loop contracts changelog entry
  (`461db19fdd89e65afdf1c13fb870c5c427c00b67`)
- feat(review-fix-loop): define invocation, checkpoint, and terminal-result
  contracts, adding the skill-local schemas, a dependency-free validator, and 62
  unit tests covering valid, invalid, boundary, cross-document, and
  round-trip/determinism cases for both `local_commit` and `update_pr` (#96)
  (`0689cda71833751249ebc5e65b766d231cf2c093`)
- feat(review-suite)!: remove the verification-sufficiency pass and its
  mandatory `verification_sufficiency_evidence` field from `review-correctness`
  and the shared review-result contract, advancing `schema_version` `1.3 → 1.4`;
  the traversal (consumer/impact) pass and `consumer_impact_evidence` are
  unchanged, per #57's ablation matrix and #89's harder-case validation finding
  no demonstrated value for the removed pass plus a confirmed, twice-reproduced
  false-positive regression when it ran without the traversal pass (#93)
  (`b91e12b063ea6d7ed49f152ee359f1f0eb326363`)
- docs: simplify the review-fix-loop design
  (`2e7a8cd93af9f2c8cec36d6c393694f7849adedb`)

## 2026-07-29 — Sourced two harder discriminating cases for the traversal and verification-sufficiency passes, designed the review-fix-loop skill, migrated implement-ticket and babysit-pr to consume the final review-result contract, rechecked the s2/s3 strata under grader 1.1 for the same surface-in-prose defect, added connector-outcome curation and promotion tooling, added a skill-root override for mechanism ablation runs, ran the preregistered v2 ablation and integration closeout, and confirmed the session-continuation-summary verification-only regression with an independent rerun

- docs(review-suite): validate the two new discriminating cases with-pass and
  without-pass, fixing a construction defect found in the traversal case along
  the way, and report the traversal pass discriminates while the
  verification-sufficiency pass still does not (#89)
  (`5e9b3de63335e23d80781a85de49c43c231d9d07`)
- feat(review-suite): source two harder discriminating
  `s1-correctness-orchestrator` cases for the traversal and
  verification-sufficiency passes and preregister their validation ceiling (#89)
  (`8386abb6641be4bd6e431f70fd9c336b8be617c6`)
- docs: design the review-fix-loop skill
  (`06538e5c097ff8e6ef15b12d5fbf61b3d959abf7`)
- docs(review-suite): add a confirming rerun of the session-continuation-summary
  verification-only regression (#57 follow-up)
  (`cd8efa444018d036a5749a1955e1f34ebe06b51f`)
- docs(review-suite): run the preregistered v2 s1 ablation matrix and
  integration closeout (#57) (`b4e061f7847b3fc911a05fe4c8e50218f4f957b7`)
- docs: add the CHANGELOG entry for the skill-root ablation override
  (`b4e061f7847b3fc911a05fe4c8e50218f4f957b7`)
- feat(review-suite): add a skill-root override for mechanism ablation runs
  (`b4e061f7847b3fc911a05fe4c8e50218f4f957b7`)
- refactor(review-suite): simplify duplicate-chain resolution and unify its
  membership check (`16fc32a90eaea16ac98ff2a34bbabafed7a4681f`)
- fix(review-suite): resolve a duplicate's disposition through its duplicate_of
  chain (`16fc32a90eaea16ac98ff2a34bbabafed7a4681f`)
- feat(review-suite): add connector-outcome curation and promotion tooling,
  including the mechanical disclosure guardrail
  (`16fc32a90eaea16ac98ff2a34bbabafed7a4681f`)
- docs: fix stale CHANGELOG SHAs left by the main rebase
  (`fa6d05f30b6252b1e1664239232b856ea593eac1`)
- docs: backfill the CHANGELOG entry for the review_gate.py canonicalization fix
  (`fa6d05f30b6252b1e1664239232b856ea593eac1`)
- fix: canonicalize review_gate.py through the existing sync-contracts mechanism
  (`fa6d05f30b6252b1e1664239232b856ea593eac1`)
- feat: migrate implement-ticket and babysit-pr to the schema 1.3 review-result
  contract (`fa6d05f30b6252b1e1664239232b856ea593eac1`)
- docs(review-suite): recheck s2/s3 strata under grader 1.1 for the same
  surface-in-prose defect (`7cf4a3b3fe3dd38f3d1a9da2e6ab82058a77f064`)

## 2026-07-28 — Added correctness traversal and verification-sufficiency passes, consumer/impact-traversal evidence, and required passing validation and current-head lens evidence for a clean review verdict

- feat: add correctness traversal and verification-sufficiency passes
  (`85ccf13b45bad8f162d81963a3ac910ea0b49590`)
- feat: add consumer/impact-traversal evidence to the shared review contract
  (`8e4fdbdaad8f70751d45f8c2ca87e88288f8ba5b`)
- feat: require passing validation and current-head lens evidence for a clean
  review verdict (`b1e51979628652e4ef60adad44089bf54f4551e7`)

## 2026-07-27 — Made database comparison output ephemeral, enforced untrusted-content boundaries, bound epic delegation, hardened command execution, populated the solution-simplicity and code-simplicity strata, enforced acceptance-gated closeout, populated the correctness stratum, recovered carved suffixes, folded owner adjudications, and ran the frozen v1 baseline

- fix: keep database comparison output ephemeral by default
  (`2f13a2d6c27fda2ced66558460a72c11c4d43c26`)
- feat: enforce untrusted content boundaries
  (`ff3f4b9cca9b062a7113b95ab08bd1d36331a27c`)
- docs: record the small-sample caveat the frozen protocol's step 6 requires
  (`e720e656cd3729a857aa4bcb6f6592fae1facc57`)
- fix: enforce owner_disposition exactly when owner_confirmed
  (`e720e656cd3729a857aa4bcb6f6592fae1facc57`)
- feat: run the frozen v1 baseline and record real scored results
  (`e720e656cd3729a857aa4bcb6f6592fae1facc57`)
- docs: freeze the v1 configuration for scoring, before any scored output
  (`e720e656cd3729a857aa4bcb6f6592fae1facc57`)
- feat: fold owner adjudications into the corpus and mark all strata scored
  (`e720e656cd3729a857aa4bcb6f6592fae1facc57`)
- fix: score a partial or ambiguous match as referred, not a silent
  reviewer-miss (`e720e656cd3729a857aa4bcb6f6592fae1facc57`)
- feat: bind epic delegation to trusted ticket skill
  (`569b11ec60977c19c66092690ffdada0dbac1eb4`)
- fix: execute carve commands from explicit argv
  (`7da1a75ad585bddec6be1cc4743e77a1744c4e98`)
- fix: correct a stale reference, a stale validation entry, and an inverted case
  (`c7a80c0e05ea76c0a7626c02dbf0b1605da37739`)
- fix: make the last two before-state and sanitization defects actually resolved
  (`41de65daadc5d53bfbb299cb4ecd6d040ac47ab9`)
- fix: sanitize the repository-history case and correct the changelog order
  (`3d9fe4925c8908a311453c87ae740bfcf4de20bd`)
- fix: reconcile records after folding s2 and s3 into one delivery
  (`5070cf1bbea438e74149dfe0cf9b171a6f7cdb92`)
- docs: record the code-simplicity delivery and close out corpus population
  (`875091c32301eafd807d2d5a3e2b402e7ffaca53`)
- feat: populate the code-simplicity stratum with four adjudicated cases
  (`f3c064a7bbaf3f89f7a6a5495846b254a54e9a0b`)
- fix: sweep sanitization across every reviewer-visible field, not only the diff
  (`ab3921a904ec7835bc4d03ed40b7c8a28d12d2c1`)
- fix: make every s2 packet internally consistent after the sanitization rename
  (`1ec231bb17cd0c1db82258756aa7a78e8e7f63ab`)
- fix: sanitize the solution-simplicity cases against source-vocabulary leakage
  (`2b56c022c91a925b574a5748112e63bdcbbbf8f2`)
- docs: record the solution-simplicity delivery and settle the grading method
  (`da8f53b06072ba0380d01ce06fc4f4a324a6219e`)
- feat: populate the solution-simplicity stratum with four adjudicated cases
  (`3105b8e84da78c691f4f93883f39887ff9ae784f`)
- feat: require acceptance evidence for workflow closeout
  (`a3597c25ee2d76135d1f0c8642a620e673fc8e57`)
- fix: make every packet diff a valid patch, and gate the adjudication record
  (`06a5679643a0a5bcb1944c8bff4bd4986f4f77e1`)
- fix: stop a grader formulation being quotable from its own packet
  (`fa772a7d770bd3d07f3fdd9bdc45a0c237b1d14e`)
- docs: record the batch-2 delivery, the clean-control standard, and its limits
  (`e83da75687f06ec9ff6a82df5ac4845c6e6fb23f`)
- feat: adjudicate the correctness cases by executable oracle
  (`6dcfeabc7acd325d1dcaae4ed341fa780df94bc9`)
- feat: populate the correctness stratum with seven adjudicated cases
  (`43deec617ee06e22e1a937234eea2a4d99b5d836`)
- feat: recover corrected carved suffixes
  (`ba12e0744a938fc71af16eeeaa0eea98e7c2c63e`)

## 2026-07-26 — Added the replay evaluator, then froze the v1 baseline configuration

- fix: reconcile every recorded figure with its retained artifact
  (`d013507956aa0ab328140a72c87fdbb151f2b1ec`)
- fix: attribute the pilot to a reproducible commit and correct the records
  (`3a8388d42e355e4bc9731b98b6dcd42ffd13ff2f`)
- feat: report the stratum a run evaluated
  (`2ae0d23c18f247f49d3cc5e76f26d1cf9610c83e`)
- fix: make the frozen baseline record auditable, and measure the envelope
  (`f7787dcba681db1de079f57ce1f2f2941e0923b2`)
- feat: add baseline strata, grader calibration, and the frozen v1 record
  (`16b77e447dbcc844edd8f3fb58728d96826e177c`)
- fix: skip the recipe-execution tests when `just` is absent
  (`f544aa0c19d97dd4f1aabd7dfab3df08b2ee6a6b`)
- feat: record the evaluated skill closure with every run
  (`b605051a7385dd310b0eff9dbf14c10dda87c633`)
- docs: record the measured smoke evaluation and its variance
  (`87ec303d949301c908c3a29cb220bed22d44c775`)
- fix: evaluate the target skill's whole declared closure
  (`62a9ed8fab166c7d380724e426449f0585714b07`)
- docs: pin the recorded smoke evaluation to its run
  (`f00ce2db80ed3a7bed6afb4962cf0bb5a68390fe`)
- fix: complete the evaluated skill text and the audit ordering
  (`67efd94339034674de6ca250f2b03e4a0213fc8b`)
- fix: close the replay evaluator's review-gate gaps
  (`6ef8e25ce2e0183ef270111549660461493da5f4`)
- fix: stop misattributing review failures in the replay evaluator
  (`e46184d6e856199fe0792d43e7f6e0c5a86e131f`)
- feat: add the result-blind review replay evaluator
  (`8f0e9d646ec4e959d7adc7448f5fc7a82f4334d8`)

## 2026-07-25 — Added coordinator-neutral delegated ticket execution

- fix: pin CI to the established Ruff rule set so dependency drift cannot
  redefine the repository-wide lint gate
  (`901dc3596207a88b6c8edcf548b5be3151ca7ab2`)
- feat: add a versioned delegated-execution contract for `implement-ticket`
  (`b53efa674e929c181bdaac63ff0306cb756386db`)

## 2026-07-21 — Completed carve-changesets and integrated ticket publication

- feat: package the workflow suite as a plugin
  (`b7ec1b593b9d211cd91101d94d0406c355b2ecd7`)
- fix: fail closed on invalid carved handoffs
  (`dc4f5c1f3e33c25ad6258f7365506bd33255ed82`)
- feat: integrate carved ticket publication
  (`54c67f7cd7ace3269eee4fe628f974b090a4d699`)
- refactor: derive the eval action vocabulary from expectations
  (`e30b5f1021538d673eb931b2978287cfd21ae4ae`)
- fix: require the two-part source freshness override
  (`eb8612300d75d1483995677d75f54fe1a32b60d7`)
- test: complete the carve-changesets verification suite
  (`f669d322985c435daf9b0c7296889d8a3bdd270c`)
- feat: package the carve-changesets skill
  (`a8e19110380e048e0aaf85e820c114fe2a07cc7f`)
- docs: define carve-changesets suite handoffs
  (`2df5136e2a7226666bc136e30905c2442a579c78`)
- feat: add stateless changeset merge and propagation
  (`925affa807c203824127a0fe5e0fb084f14f378d`)
- refactor: make strict apply use one proof
  (`c8ca89566562d7d154bfe1a1711140323e3ba9f8`)
- fix: bind GitHub operations to the selected remote
  (`cfdddb0aeb792fabfb4021173e25738b45329083`)
- fix: close consolidated carve CLI review gaps
  (`d4b071ff46b7b4f2bf8b256f9071d76325e4d146`)
- feat: add the consolidated carve-changesets CLI
  (`0d942c50cff2d9472b664e74d423661c9f1693cb`)
- fix: bind changeset validation to current live refs
  (`721a1ea07c0e8d8af1265bbf70326afaf286aa4a`)
- feat: validate changeset chains from live git
  (`df24771983819b05110670a8d03d43e003d23d28`)
- feat: add self-describing changeset identity
  (`e88bf87e9cb1a4e04bdf8b051ce8ca0f0dcb96e6`)
- fix: clarify published terminal evidence
  (`edeb2f5f5f7b4cfa4e73e8289d34157b192f92ab`)
- docs: define the carve-changesets operating contract
  (`77865c25190e7205142318229f17c1d3f18e1fef`)

## 2026-07-20 — Portability, watcher resilience, and Claude adaptation

- refactor: route the clear predicate through `has_failed_pr_checks` — the
  code-simplicity lens on PR #27 flagged the last inline copy of the
  failed-PR-check policy inside `is_github_candidate_clear`; all three agreement
  sites now structurally share one predicate
  (`93516194388116f4841fc191a8c78c191d0da5b1`)
- fix: share one failed-PR-check predicate across the watcher — the initial
  `review-code-change` pass on PR #27 found the retry gate refusing retries that
  `recommend_actions` recommends for failed-runs-only states; extract
  `has_failed_pr_checks` and use it in both sites, and match repository case
  insensitively in state-target validation
  (`625dae641a9652368f03b6be825f48d9addab056`)
- fix: close the final low-severity review findings — mirror the clear predicate
  in `has_failed_pr_checks` so a PR-check-backed failed run never reads as
  `idle`, case-normalize repositories before deriving state files and locks,
  match fragment run links, reject `--repo` without an explicit `--pr`, make
  boolean schema constants reject numeric one, and document `--poll-seconds` and
  `--max-flaky-retries` (`f79266a390e970cd25cf8af1bed6b9bd9cf154ee`)
- fix: align retry gating and delegation tooling with review round four — accept
  cancelled-only check failures in the retry gate so a recommended retry is
  never refused, grant the review orchestrator the subagent and skill tools its
  Claude adapter requires, reject `--once` with `--retry-failed-now`, match
  query-string run links, add a repo digest to default state filenames, keep
  `diagnose_ci_failure` visible after retry exhaustion, and document zero-check
  `--stop-when-clear` pairing (`ddb29d0ce0409554cec61ed54b2c6e7ed6d84c6a`)
- fix: close adversarial-review findings — resolve bundled-validator schemas in
  both layouts and execute every bundled copy in place, scope failed workflow
  runs to the PR's own checks so push/schedule failures cannot wedge the
  watcher, emit `resolve_draft_state`/`resolve_merge_conflict` instead of
  `idle`, complete `forbidden_actions` on all forward expectations with a
  vocabulary-spam canary, stop backfilling `target_skill` in the Claude
  executor, reject `--once --watch`, handle `OSError` cleanly, import bundled
  validators in review-skill tests, and document eval flag pre-classification,
  the gh 2.37 floor, and state-file durability
  (`48b6f614d15d50dae4ba5c63d7b3e3471647dd1a`)
- fix: close independent-review findings — count cancelled checks and failed
  runs/jobs in the watcher's clear predicate, run review-suite tests in CI,
  bundle the dependency-free packet validator into each review skill, make
  `--stop-when-clear` imply `ready_to_merge` and test every documented CLI
  invocation, fail closed on empty `gh pr checks` payloads, surface ghost-author
  comments, move watcher state into a per-user 0700 directory, add
  forbidden-action forward grading, unify `observed_sequence` tokens, and rename
  `agents/claude.md` to `agents/claude-code.md` to avoid the case-insensitive
  CLAUDE.md memory-file collision (`b5bf81b81a6dd521edcdfc561988ca621a566d39`)
- fix: make skills self-contained and adapt the suite to Claude runtimes —
  bundle the review-suite contract into each review skill with a
  `just sync-contracts` target and drift test, use skill-root-relative watcher
  paths, survive transient watcher failures with bounded backoff, add
  `--max-polls`/`--stop-when-clear` bounded watch modes and a
  `confirm_feedback_disposition` action, move eval answer keys out of
  reviewer-visible input directories, add a Claude headless forward-eval
  executor, add `agents/claude.md` adapters, `allowed-tools` on review skills,
  and trigger-oriented skill descriptions, and trim contract tests to
  load-bearing invariants (`474756bea51237376b81ad7d593eef2d8de273f1`)

## 2026-07-20 — Composed ticket and PR execution

- fix: execute result-blind forward evaluations in fresh contexts
  (`f452db4cf47e56b3f8fea560977a3ce98ca26caa`)
- feat: delegate the `implement-ticket` PR lifecycle to `babysit-pr`
  (`d5838d49587ab34a00973441a870cd525cfcd773`)

## 2026-07-20 — Repository-owned PR babysitting

- fix: bind each watcher lock to an immutable repository and pull request target
  (`3666b3d5beb9182b3dab221d2489a7acf23323b7`)
- fix: validate the locked PR state path before any snapshot read or write
  (`322a83c6b31d5668e6648df8f0fabe3732c3e74f`)
- fix: serialize every watcher state mutation through one repository/PR lock
  (`8c64b05daa9cde6832fb128c7c6786896fb57108`)
- fix: serialize retry mutation and durably reserve each per-head retry cycle
  (`4ecdd65767164e7f0f112d4049a856c6e8ea53ed`)
- fix: scope CI retries to explicitly diagnosed current-PR runs
  (`7f559ead6a4373bc2f0bd441b5af853d66260753`)
- fix: fail closed on partial review data and remove inert polling state
  (`b14dca750337eacd0f34f5b705afbe81591174b7`)
- fix: hide pending inline review threads until publication
  (`76ed0f6090f23e7a9c0aae14897ae48948922a37`)
- feat: add the portable `babysit-pr` skill with candidate-bound CI, feedback,
  review, and merge gates (`b57bd0f3625d7aba9fe4ba32e2abb3f2c7b0df91`)

## 2026-07-20 — Portable ticket and epic execution

- feat: make ticket and epic execution runtime agnostic
  (43309084ec8ca15f4345f5eaa809d53d69b3f8d7)
- feat: compose epic execution through implement-ticket
  (7c4e500a35d48b5dba311094b4d34d8ca97f25a1)

## 2026-07-19 — Epic workflow and review contract cleanup

- feat: add standalone ticket implementation skill
  (7113afd5ab04d0200c2bfa6b5008d9fcd2b2f7f6)
- feat: integrate repository-owned review into epic execution
  (28c3945b3db8f84a812cd2e498d54a6912bcd934)
- feat: compose repository-owned code review
  (556fea80b6970b97c31e819693f43c251b7b3796)
- feat: add local code simplicity review
  (d6ed890f6924a2ae7ae4b04fa95072ee853c9b97)
- feat: add whole-solution simplicity review
  (8459402e95888047587cf423454f9f8ac42f6881)
- feat: add goal-first correctness review
  (33feab3570363f8bf0d24ed4295495dc05fa3abf)
- feat: define shared code review contracts
  (5600132585c502b21434a938e0319ba58521ee67)
- feat: add epic sequence implementation skill
  (06bd81f4293a24e12cde1f0e466596b41095e8f4)
- revert: remove modular code review contract
  (b889fe4dc313dc50320dcb20f98980b993062c9a)

## 2026-02-24 — Modular code review contract specification

- feat: specify modular atelier-agnostic code-review skill contract
  (062a1a328e6a1b2e0835d16be742fc2c36dbd9dd)

## 2026-01-27 — Incremental changesets and workflow reliability fixes

- docs: clarify cognitive load guardrails and mechanical exception
  (a2a926a4bedf1abc560051551c3a5cefded7a6ec)
- fix: resolve repo default merge method for non-interactive merges
  (148c88bc437d6bbdc9a3fe232e37199b9e3b7878)
- fix: default merge-propagate to repo merge method
  (1322dd79d2201c16b03e8459582898d35edd990f)
- feat: add cherry-pick propagation strategy
  (72a6fc893a3b943d6c0d4172a0d89b0e5f782928)
- docs: require pushing changeset branches before PR creation
  (47a92e5e418f75dcf773c54ab8c8e7bb7e29a30f)
- fix: require recordkeeping directories to be ignored in preflight
  (efe0a3c676bd168a2b3a8b93c20adcd7541cf40b)
- fix: avoid staging plan artifacts and ignore AGENTS metadata
  (a7b9c29aa312f9432368fbd66994fe69389ba056)
- feat: enforce source branch freshness before preflight
  (76602f9233d8faff52437a58fb29a6a13f1f0b14)
- feat: all-hunks selectors and strict apply checks for hunk mode
  (e743c706bd5d7b1429f4967b794a1b5cc4ce54c5)
- feat: rename-aware hunk selection and rename-first guidance
  (998000f86f607740b242d042fc7d77793753725a)
- feat: hunk-based changesets with strict validation and patch support
  (7fb3d614f6298390a353a3fa564a28928b1353ac)
- feat: incremental changesets with squash-check and mdformat 1.0 tooling
  (797e56f0fb9cf64ded3a6d63fdbade385f253e0b)
- fix: CI agentskills install and changelog workflow rules
  (460a81780211264cdc568e42e3f8e4b73ca2bcea)
- feat: add AGENTS-aware test command discovery
  (1730fb654885f4ea1a5448e18bab1f558b5063ad)
- chore: initialize agent-scripts monorepo
  (420d1cdacb2855d3d9c494e57447954995043c42)
