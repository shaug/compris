# Worktree isolation mechanics

Concrete mechanics for
[step 1, Create exclusive implementation state](../SKILL.md#1-create-exclusive-implementation-state).
Ported with attribution from superpowers' `using-git-worktrees` — the
isolated-workspace pattern, not its mechanics, which this file states directly
against Git.

## Prefer native harness tools

Check the available tool listing for a harness-provided worktree or isolation
tool before reaching for raw `git worktree` commands. Use it when present.

*Prevents:* a runtime that offers its own worktree tracking keeps bookkeeping
for every worktree it creates — for cleanup, for discovery, for concurrent-run
safety. A worktree created underneath it with a raw `git worktree add` call is
invisible to that bookkeeping: it exists on disk and in Git's own worktree list,
but the harness that later prunes, lists, or isolates worktrees on the caller's
behalf never learns it is there. That mismatch is phantom state — real on disk,
absent from the system supposed to account for it — and it surfaces later as a
worktree nobody's cleanup step considers, or a concurrent run colliding with one
the harness never knew to avoid.

## Sandbox fallback

When the environment denies worktree creation — sandboxing blocks filesystem
operations outside the current tree, or `git worktree add` fails on a permission
or path error the primary checkout does not otherwise have — do not treat the
denial as a hard stop, and do not silently continue as though full isolation
succeeded. Fall back to working in place: isolate the candidate by branch alone
inside the current checkout, and record the degraded isolation explicitly in the
run's evidence (for example:
`worktree: none, isolation: branch-only, reason: <the observed denial>`).

This fallback presumes the current checkout is already this run's own to mutate.
[Step 1's exclusivity rule](../SKILL.md#1-create-exclusive-implementation-state)
still applies without exception: a delegated worker, subagent, or equivalent
context whose current checkout is not already exclusively its own — for example,
one sharing a coordinator's or a sibling child's checkout — must not apply this
fallback silently. Treat the denial as a blocking condition instead and surface
it to the coordinator or caller; only standalone execution, which that same rule
already permits to mutate the primary context, may fall back in place.

*Prevents:* two failures on either side of the right behavior. Treating denial
as a blocker strands a ticket that a lesser isolation guarantee could still
deliver safely. Continuing without recording the degradation produces
"implementation state created" evidence that reads identically whether the run
achieved full worktree isolation or none — a caller trusting that evidence
assumes a guarantee (a second mutating context cannot collide with this one's
working tree) that branch-only isolation does not actually provide. Left
unqualified, the same fallback would also let a delegated worker read its denial
as license to mutate a checkout it does not exclusively own, defeating the
adjacent "never allow two implementation contexts to mutate the same candidate"
invariant instead of degrading gracefully around it.

## Placement precedence and consent

Choose the worktree directory in this order:

1. an explicit location named in caller or coordinator instructions;
2. an existing convention directory the repository or host environment already
   uses for worktrees — discoverable via `git worktree list` or a sibling
   worktree's own parent directory;
3. a default location.

Creating a worktree at a location that was not requested and does not match an
existing convention is a novel placement. State the chosen path in the run's
evidence or report; do not let it pass unremarked.

*Prevents:* an unannounced novel placement scatters worktrees across
inconsistent locations across runs, so a caller who later goes looking for one —
to inspect it, hand it to another context, or clean it up — has no deterministic
place to look. Surfacing the path costs one line and turns a guess into a fact
the caller can act on or object to.

## Guard the worktree path before creating it

Run both checks against the intended worktree path, from the primary checkout,
before `git worktree add` executes.

**Submodule guard.** Run `git rev-parse --show-superproject-working-tree` before
treating any directory as the repository root a worktree will be created from.
Non-empty output means that directory is itself a submodule inside a larger
superproject.

*Prevents:* creating a worktree against a submodule's own `.git` link while
mistaking it for a top-level repository root produces worktree metadata bound to
the wrong `.git` structure — the worktree can end up tracking the submodule's
gitlink state rather than the branch it was meant to isolate, or become orphaned
from the superproject that actually owns it.

**Ignore guard.** Run `git check-ignore -v <intended-worktree-path>` against the
intended path before creating it there.

*Prevents:* a worktree placed inside a path Git already treats as ignored sits
where routine ignored-file cleanup — `git clean -fdx`, a CI cache purge, an
editor's "clean workspace" action — can delete it without going through
`git worktree remove` and its own safety checks. None of those tools know or
care that the path holds a registered worktree; they only see an ignored
directory that is safe to delete by the same rule that made it ignored in the
first place. An ignored path is not automatically the wrong choice — a
repository's own `.worktrees/`-style convention directory is commonly gitignored
on purpose — but the check must actually run, and the placement decision must be
made with that deletion risk in view, not skipped.

## Clean-baseline validation run

Run the ticket's approved focused validation, at minimum, at the verified base,
before making any implementation edit — against the freshly created worktree
when one exists, or against the current checkout when the sandbox fallback
applies. The isolation path taken does not change this requirement; nothing
about branch-only isolation makes the base any more likely to already be broken.

*Prevents:* the change-demonstrating-test evidence and the acceptance ledger
both depend on a base-failing/head-passing or red-at-base/green-at-head
comparison. A base that is already broken invalidates that comparison silently —
a failure discovered mid-implementation cannot be attributed to the base or to
the change without a validation run recorded against the base first, and
re-establishing that baseline after edits have already started is no longer a
clean before/after comparison. Scoping this only to "the freshly created
worktree" would leave the sandbox-fallback path — already carrying a weaker
isolation guarantee — with no textual instruction to validate the base at all,
silently dropping the same protection where it is needed at least as much.

## Provenance-scoped cleanup

At [cleanup](cleanup-and-result.md), remove only the worktree this run itself
created, at the exact path recorded during this step. Never enumerate a
convention directory and remove every entry matching a naming pattern, and never
run a broad worktree sweep.

*Prevents:* a naming-pattern sweep of a shared convention directory —
`.worktrees/*`, or any host-level worktrees root — cannot distinguish this run's
disposable worktree from one a concurrent or unrelated run still owns. Matching
by pattern instead of by the exact recorded path turns an intended
single-candidate cleanup into data loss for whichever other run's worktree the
pattern also happened to match.
