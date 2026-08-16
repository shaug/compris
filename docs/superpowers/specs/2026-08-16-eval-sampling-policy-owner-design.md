# One owner for the eval sampling policy

This is the design for giving the repetition-and-majority-vote grading policy a
single canonical source. Four real-model eval executors independently
reimplement how a `claude -p` sample is drawn and how repeated samples become
one graded answer. Three of them vote, and they no longer vote the same way.

## The problem

The policy exists in three independently maintained copies:

- [`skills/implement-ticket/scripts/evals/claude_executor.py`] — `NO_ANSWER`,
  `_modal`, `combine`, `_combine_ledger`, `--repetitions`, and the emitted
  `repetitions`/`agreement`/`votes`/`failed_samples` fields
- [`skills/ready-ticket/scripts/evals/claude_executor.py`] — `combine` and
  `--repetitions`
- [`triggering/executors/description_executor.py`] — a simpler variant of the
  same vote

A fourth executor, [`review-suite/scripts/evals/claude_executor.py`], draws a
single sample and never votes, but carries its own copy of the transport the
other three also duplicate: the `claude -p` subprocess call, the envelope
unwrap, and the fenced-JSON extraction.

### The divergence that changes recorded results

`implement-ticket` breaks a tie deterministically, through `_modal`'s `min()`
over the sorted candidates. `ready-ticket` uses `Counter.most_common(1)[0]`,
whose tie order follows insertion. On a 2–2 tie over four usable samples the two
return different answers, and `ready-ticket` returns a different answer again
depending on which sample happened to be drawn first:

```
votes: merged, merged, blocked, blocked
  implement-ticket  _modal        -> blocked
  ready-ticket      most_common   -> merged
  same votes, reversed draw order -> blocked
```

Two runs recorded by different executors are therefore not comparable on a tied
case, and one executor is not reproducible against itself. This is the sharp
edge: it is a silent difference in recorded evidence rather than a missing
feature.

### The divergences that are missing features

Concurrent drawing, burst tolerance (`SCENARIO_RETRY_PAUSE_SECONDS` and the
single redraw), non-string answer rendering (`claimed`), and per-criterion
ledger voting exist only in `implement-ticket`'s copy.

The extraction differs too, but harmlessly: `review-suite`'s
`extract_json_object` adds an `isinstance(value, dict)` guard the other three
lack. That guard is unreachable. All four slice from the first `{` to the last
`}` before parsing, and `json.loads` on a string in that shape returns a `dict`
or raises — a bare `["blocked"]` reply has no brace and already raises
`ValueError`. Adopting the guard is worth doing to make the contract explicit,
but it is not a bug fix and changes no result.

### The constraint

Each skill folder is a standalone distribution unit, installable outside this
repository, so a repo-root import is not available to a skill. This repository
already has the answer to exactly that problem: a canonical file at the root, a
byte-identical copy bundled into each consuming skill by `just sync-contracts`,
and a test that fails when a copy drifts. It is used for the review-suite
contracts, the shaping doctrine, and [`ledger/core.py`].

## The design

### A canonical module in three layers

A new root directory `sampling/`, alongside `ledger/`, with `sampling/core.py`
as the single source of truth. Three layers, because the four consumers need
different depths of it.

**Transport**, used by all four:

- `run_claude_envelope(prompt, claude_bin, model) -> dict` — the subprocess, the
  non-zero-exit failure, and the `json.loads` of stdout
- `result_text(envelope) -> str` — unwraps the `result` field
- `extract_json_object(text) -> dict` — the fence-and-brace scan

The envelope is returned rather than only its text because
[`review-suite/scripts/evals/claude_executor.py`] derives `model_from` and
`usage_from` off the same envelope. `extract_json_object` adopts the
review-suite version, whose explicit `isinstance` guard states a contract the
brace slicing already enforces.

**Drawing**, used by the three voting executors:

- `RESULT_ATTEMPTS = 3` and `draw_json(...)` — the malformed-response retry
- `draw_batch(draw_one, repetitions) -> list` — the concurrent map, dropping
  refused samples
- `draw_with_tolerance(draw_one, repetitions, pause) -> (samples, failed)` — one
  round, and on an empty round a `SCENARIO_RETRY_PAUSE_SECONDS` stand-down and a
  single redraw before raising

**Vote**, used by the three voting executors:

- `NO_ANSWER = "none"`
- `modal(counter) -> (answer, count)` — the sorted-`min` tie-break, as the one
  rule
- `majority_of(repetitions) -> int`
- `vote_single(values) -> (winner_or_None, agreement, votes)` — handles the
  sentinel round-trip
- `vote_set(sample_sets, majority) -> (sorted_list, votes)` — element-wise
  majority
- `claimed(value) -> str | None` — non-string answer rendering

`implement-ticket`'s `_combine_ledger` stays in `implement-ticket`; it has
exactly one consumer. It is rebuilt on canonical `modal` and `majority_of`, so
its tie-break is the shared one by construction rather than by coincidence.

### Distribution and drift

`just sync-contracts` gains a block copying `sampling/core.py` into the two
skills as `scripts/evals/sampling_core.py`. Both executors load it with the
`_load_core` pattern already used at [`skills/implement-epic/scripts/ledger.py`]
— `importlib.util.spec_from_file_location` against a `__file__`-relative path,
which is cwd-independent, and these executors run as subprocesses from a working
directory nobody controls.

[`triggering/executors/description_executor.py`] and
[`review-suite/scripts/evals/claude_executor.py`] load the canonical by
`__file__`-relative path too, but reach the real `sampling/core.py` rather than
a copy. Neither is a distribution unit, so a bundled copy would exist only for
symmetry and would be a third and fourth thing to drift.

`sampling/scripts/tests/test_bundled_copies.py` mirrors
[`ledger/scripts/tests/test_bundled_copies.py`] in shape, over the two skills.

### Failure policy

Adopting the shared drawing layer gives every voting executor
`implement-ticket`'s handling: a sample the runtime refused becomes a dropped
sample counted in `failed_samples`, and an all-samples-fail round stands down
and redraws once.

The line is drawn at *the runtime gave us nothing* versus *the model gave us
something wrong*. [`triggering/executors/description_executor.py`] deliberately
fails loud on an unrecognised reply — recording it as `none` would convert a
broken response into a passing negative case — and that behavior is preserved.

Both the transport and `parse_answer` raise `RuntimeError` today, which makes
that distinction unimplementable as written. The canonical therefore defines
`SampleUnavailable(RuntimeError)`, raised only by the transport and drawing
layers, and `draw_batch` catches only that. A consumer's own answer-parsing
error is a different type and propagates.

### The `repetitions` field

`repetitions` becomes the *drawn* count everywhere, as `implement-ticket`
already reports it, rather than the requested count as
[`triggering/executors/description_executor.py`] reports it. This keeps
`sum(votes.values()) == repetitions` true — an invariant
[`triggering/tests/test_triggering_corpus.py`] already asserts — and keeps every
`agreement` denominator consistent with the samples it summarizes.

### Recording the policy a run was graded under

A recorded diff is drawn only when tier, suite, and model all match, because
comparing across any of them reports a change of question as behavioral
movement. Converging the tie-break and the failure handling changes the grader
itself, so a before/after pair straddling this change would compare two
different graders under the same tier name.

`sampling/core.py` therefore carries `POLICY_VERSION`, covering the whole
canonical rather than the vote alone — the drawing layer decides which samples
reach the vote, so it moves a recorded answer as surely as the count does.
[`scripts/record_eval_run.py`] imports it directly, being root code, and grows
`policy_for(command, tier)` shaped exactly like the existing `model_for`: the
constant for a real-model tier, `None` for a deterministic one, which has no
sampling policy to name. Summaries gain `policy` beside `model`, and
`previous_run` adds it to the match tuple.

Summaries recorded before the field carry no `policy` and will not diff against
new ones. That is the same consequence `model` already has, for the same reason,
and they are not backfilled. [`AGENTS.md`]'s "tier, suite, and model" becomes a
quadruple.

### Why no eval evidence

[`AGENTS.md`] requires recorded model-behavior evidence for a change to a
skill's normative prose — its `SKILL.md` or a governing `references/` file. No
such file changes here; the edits are to executor scripts, repository guidance,
and tests. The eval-backed change norm does not trigger, and this ships on tests
alone.

## Testing

`sampling/scripts/tests/test_core.py` covers the canonical directly:

- the 2–2 tie above resolving to the same answer regardless of draw order
- `majority_of` at even and odd repetition counts
- the `NO_ANSWER` sentinel round-tripping to `None`
- `claimed` rendering a non-string answer rather than crashing the vote
- `extract_json_object` finding a fenced object, and raising on a reply with no
  brace at all
- `draw_with_tolerance` reporting failed samples, and raising only after two
  empty rounds
- `SampleUnavailable` being caught by `draw_batch` where a consumer's parse
  error is not

Two tests exist for the drift specifically. `test_bundled_copies.py` checks
byte-identity of the two mirrored copies. A second test asserts the property the
finding actually cares about: that all three voting executors resolve the same
tie the same way. Byte-identity alone cannot establish that, because
[`triggering/executors/description_executor.py`] imports the canonical rather
than bundling it.

Existing suites need updating for `failed_samples` and the drawn-count
`repetitions`: both `test_forward_evals.py` modules,
[`triggering/tests/test_triggering_corpus.py`], and
[`scripts/tests/test_record_eval_run.py`] for the policy gate.

`sampling/scripts/tests` must be added to the `test` recipe's hardcoded
directory list in [`justfile`]; a suite absent from that list silently never
runs. Every new test module carries the `__file__`-relative `sys.path` shim
[`AGENTS.md`] requires.

## Provenance

Raised as a deferred, non-gating code-simplicity finding while reviewing [#237],
against [#234], and left out of that ticket because it reaches beyond
`skills/implement-ticket/`.

<!-- inline reference link definitions. please keep alphabetized -->

[#234]: https://github.com/shaug/compris/issues/234
[#237]: https://github.com/shaug/compris/pull/237
[`agents.md`]: ../../../AGENTS.md
[`justfile`]: ../../../justfile
[`ledger/core.py`]: ../../../ledger/core.py
[`ledger/scripts/tests/test_bundled_copies.py`]: ../../../ledger/scripts/tests/test_bundled_copies.py
[`review-suite/scripts/evals/claude_executor.py`]: ../../../review-suite/scripts/evals/claude_executor.py
[`scripts/record_eval_run.py`]: ../../../scripts/record_eval_run.py
[`scripts/tests/test_record_eval_run.py`]: ../../../scripts/tests/test_record_eval_run.py
[`skills/implement-epic/scripts/ledger.py`]: ../../../skills/implement-epic/scripts/ledger.py
[`skills/implement-ticket/scripts/evals/claude_executor.py`]: ../../../skills/implement-ticket/scripts/evals/claude_executor.py
[`skills/ready-ticket/scripts/evals/claude_executor.py`]: ../../../skills/ready-ticket/scripts/evals/claude_executor.py
[`triggering/executors/description_executor.py`]: ../../../triggering/executors/description_executor.py
[`triggering/tests/test_triggering_corpus.py`]: ../../../triggering/tests/test_triggering_corpus.py
