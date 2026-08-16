# The eval candidate's durable identity

This is the design for making an eval summary's `candidate` block name
repository state a later reader can still retrieve. It changes how a pull
request carrying eval evidence is merged, what `candidate_identity()` records,
and adds a guard holding the recorded identity to reachability. It does not
change what the evals measure or how they run.

## The problem

[`scripts/record_eval_run.py`][recorder] writes `candidate.sha` and
`candidate.tree` into every summary under `skills/<skill>/evals/results/`.
[`AGENTS.md`][agents] tells the reader which of the two to trust:

> `sha` names the commit, which rebase rewrites and squash-merge discards
> outright; `tree` names the content, which is identical under both, so it is
> `tree`, not `sha`, that a reader should expect to still resolve once a change
> has landed on `main`.

That is wrong, and it fails the same way [#236][pr236] found `CHANGELOG.md`
citations failing. `candidate.tree` is `git rev-parse HEAD^{tree}` — the
whole-repository tree. A rebase onto a moved `main` changes files outside the
skill, so the rebased commit carries a different top-level tree. Neither half of
the pair survives, and after a squash-merge both are unreachable from `main` for
anyone without the pre-rebase clone.

The rot is already at scale. Of the 82 summaries in the repository, 59 name a
`sha` unreachable from `HEAD` — proportionally worse than the 68 of 248 dangling
changelog citations #236 repaired. Only 16 carry a `tree` at all, the field
being recent, and 8 of those 16 resolve.

It is concentrated where the evidence matters most:

| stage      | resolves | dangles |
| ---------- | -------- | ------- |
| `after`    | 2        | 45      |
| `baseline` | 1        | 13      |
| `before`   | 20       | 1       |

A `before` run mostly survives by accident. Recorded at an untouched branch
point, it names the merge-base — a commit already on `main` — so nothing about
the branch's fate can take it away. The single exception proves the accident is
fragile: [#234][issue234]'s before-run was recorded after its new eval cases
were already committed, so it names a mid-branch state and dangles like the
rest.

The `after` run has no such luck. It names a branch-local commit by
construction, and 45 of 47 are gone. The two survivors came onto `main` through
[#235][pr235], the one recent pull request merged as a merge commit rather than
a squash. The run that says how the shipped prose actually behaves is the run
this repository has already lost, every time, since squash-merge became its
habit.

## Why recording the skill's subtree is necessary but not sufficient

The obvious repair is to record `git rev-parse HEAD:skills/<skill>` instead of
the whole-repository tree: unrelated files moving under a rebase cannot disturb
it, and it is what actually determines what the eval read. Running the
counterfactual against `scott/ticket-234-09af55`, whose five summaries name
pre-rebase commits that survive in that clone only as dangling objects, all five
subtrees are reachable from the rebased branch where none of the five commits
is.

Simulating that branch's squash-merge, none of the five survives — not as
subtrees, and not with `evals/results/` excluded from the hash either. The
reason is structural rather than a matter of hashing granularity:

- The `before` run measures the new eval corpus against the *old* prose. That
  combination exists only mid-branch, on no commit that ever lands.
- Every superseded `after` run measures prose a later commit on the same branch
  changed, which is why `a397c63` and `10a7b54` on that branch both re-record at
  the shipping head.

A squash-merge keeps one tree per pull request. Eval evidence is the one
artifact class in this repository whose value depends on *intermediate* branch
states remaining resolvable. No identity scheme can make reachable what git was
instructed to discard.

## The design

### Merge policy

A pull request that adds or changes any file under `skills/*/evals/results/`
merges as a merge commit, never a squash. Every authoring commit lands, so every
state a summary measured stays reachable from `main` permanently.

This is the part that makes retrieval possible; everything below only keeps the
recorded identity intact until the merge. It has ample precedent in this
repository: 37 pull requests through [#107][pr107] landed as merge commits, and
#235 is why the only two surviving `after` runs survive.

[`skills/babysit-pr/SKILL.md:357`][babysit] already obliges the caller to use
"the repository-approved merge method", so the policy belongs in `AGENTS.md` and
the skill needs no normative change. The example output block at line 398 says
"repository-approved squash method"; correcting it to match line 357 alters no
obligation and is editorial under the eval-backed change norm. A carved chain
needs no change either: `carve-changesets` already defaults its merge method to
`merge`.

The failure this policy prevents is unrepairable once it happens, which is worth
stating where the policy is written. A squash-merged pull request carrying eval
evidence turns the guard red on `main` with no way to repoint the citation — the
measured content is gone from every clone but the author's. The only remedy is
to re-record against a state that still exists and to say in the summary that
the original is unrecoverable.

### What `candidate_identity()` records

`candidate.trees`, a map from repository path to that path's subtree hash:

- `skills/<skill>` for every run. The skill directory holds both the prose under
  measurement and, at `skills/<skill>/scripts/evals/claude_executor.py`, the
  executor that produced the evidence — which is exactly the pair
  [`2dc1e4e` re-recorded to keep together][reroll].
- `triggering` additionally for a triggering-suite run, whose executors live in
  `triggering/executors/`, outside any skill.

The subtree is needed even under the merge policy above, because `AGENTS.md`
requires rebasing onto `main` before submitting a pull request and a rebase
rewrites the commits summaries name. On `scott/ticket-234-09af55` that is not
hypothetical: five of five `sha`s dangle after the rebase and five of five
subtrees survive it.

A map rather than a scalar because a scalar silently under-describes a
triggering-suite run, and because it extends to `review-suite/` for free if
`just eval-record` ever learns to drive those corpora.

No `evals/results/` exclusion is needed, which is worth stating because it is
not obvious: the subtree is captured before the summary is written, and under
the merge policy that parent commit lands, so the recorded hash stays resolvable
even though committing the summary changes the skill's subtree afterward.

`sha` and the whole-repository `tree` continue to be recorded as best-effort
context and are documented as branch-local. Summaries already written keep
`tree` meaning the whole-repository tree; recorded evidence does not get its
fields redefined underneath it.

### The guard

`scripts/tests/test_eval_candidate_citations.py`, a sibling of
[`test_changelog_citations.py`][changelog-guard]: every `candidate.trees` entry
in every summary must name a subtree reachable from `HEAD`, failing with the
same distinct message on a shallow clone rather than passing vacuously. CI
already checks out with `fetch-depth: 0`, added by #236 for the changelog guard,
so no workflow change is needed.

Reachability for a subtree means the hash appears as `<commit>:<path>` for some
commit reachable from `HEAD`, resolved with one `git rev-list` and one
`git cat-file --batch-check` per distinct path.

### What the guard does about an unlanded branch

Nothing, and it needs no exemption. Under subtree identity a summary recorded on
an open branch is reachable from that branch's own `HEAD` at every point in its
lifecycle, rebase included. The guard turns red only when a skill's content
changed after recording *and* history was squashed — the case the merge policy
prevents — or when a rebase resolved conflicts inside the skill directory, where
re-recording is the correct response rather than a false alarm.

This is a real difference from the changelog guard, which needs `AGENTS.md` to
close the window from the other side by deferring backfill until an entry lands.

### No backfilled landing commit

Under the merge policy the recorded `sha` already resolves on `main`, so there
is nothing to repair. The deeper reason not to adopt the changelog's backfill: a
changelog entry's fact of interest genuinely is which commit carried it onto
`main`, whereas a summary's fact of interest is what the eval read, which the
subtree names directly and immutably.

A landing commit would also be a fact the recorder never held. Which commit
carries a summary onto `main` is decided after the run, by a merge that has not
happened yet, so writing it in adds a claim nothing in the file can support.
That is the line this design draws around editing recorded evidence, and it is
narrower than "never touch these files" — see the backfill below, which stays on
the other side of it.

### Existing summaries

The 23 summaries whose `sha` is still reachable from `HEAD` gain
`candidate.trees`, derived from the commit each already names. The remaining 59
are grandfathered untouched: the guard checks only `candidate.trees`, so a
summary without it passes, and `AGENTS.md` states that such summaries are
branch-local and unresolvable — the treatment it already gives summaries
predating the `model` field.

This is a derivation, not an addition. `git rev-parse <recorded sha>:<path>` is
a lossless computation over data the summary already carries, reproducible by
anyone from the file itself, and it cannot say anything the recorder would not
have said had the field existed. That is what separates it from a backfilled
landing commit, which asserts something no recorded field implies.

Verified against the current tree: all 23 derive, and every derived entry is
reachable, so the backfill leaves the guard green rather than importing 23
failures. One of the 23 is a triggering-suite run and needs both
`skills/review-solution-simplicity` and `triggering`, which is the map shape
paying for itself on real data rather than on a hypothetical. Seven predate the
`suite` field and are treated as forward runs; all seven are confirmed
non-triggering by name, and the implementation fails loudly on a summary whose
suite it cannot determine rather than guessing.

The 59 measured content that no longer exists in any clone but their author's,
unlike #236's citations, which were recoverable because the history they should
have named was still on `main`. The pull request says so plainly rather than
implying a repair it did not make.

## Scope

Out of scope: what the evals measure, how they run, the tier and suite model,
and whether `just eval-record` can drive the review-suite corpora. The merge
policy applies to pull requests carrying eval evidence and leaves every other
pull request squash-merged.

<!-- inline reference link definitions. please keep alphabetized -->

[agents]: ../../../AGENTS.md
[babysit]: ../../../skills/babysit-pr/SKILL.md
[changelog-guard]: ../../../scripts/tests/test_changelog_citations.py
[issue234]: https://github.com/shaug/compris/issues/234
[pr107]: https://github.com/shaug/compris/pull/107
[pr235]: https://github.com/shaug/compris/pull/235
[pr236]: https://github.com/shaug/compris/pull/236
[recorder]: ../../../scripts/record_eval_run.py
[reroll]: https://github.com/shaug/compris/commit/2dc1e4e3339a1fb5be52208d657663b6518fd7ec
