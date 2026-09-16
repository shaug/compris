# Triggering and composition corpus

Does each skill fire on its own language, stay silent on a peer's, and compose
with installed peers at the seams? Forward evals ask whether a skill's prose
governs behavior once it is loaded; this corpus asks the prior question —
whether it is the one that loads at all.

## Layout

- `corpus.json` — the prompts. Positive prompts a skill must claim, negative
  prompts it must not, and the collision prompts where two skills' language
  overlaps. Carries no answers.
- `expectations.json` — the answer key, held separately. Each entry records the
  expected pick and why.
- `composition-cases.json` — peer-installed seam cases, each with its expected
  behavior and, where it could not run, the specific gap.
- `known-overlaps.json` — overlaps a recorded run actually observed, kept as
  data. Their disposition is documentation and user guidance in #128, never a
  description edit here: contorting a description to dodge a structural overlap
  is what the peer-skill convention forbids.
- `runner.py` — grades a corpus against the answer key through a fresh-process
  executor.
- `executors/` — the three tiers, below.
- `tests/` — behavioral tests, run by `just test`.

Give an evaluated router only `corpus.json`; never show it `expectations.json`.
The runner enforces this by building a payload of the prompt and the skill
catalog and nothing else — no case id, no `kind`, no filed-under skill.

## The three tiers

A recorded result always names the tier that produced it, because the tiers
answer different questions and must never be read as interchangeable.

| Tier          | Executor                            | What it establishes                                               |
| ------------- | ----------------------------------- | ----------------------------------------------------------------- |
| `headless`    | `executors/headless_executor.py`    | Which skill a real headless session actually loaded.              |
| `description` | `executors/description_executor.py` | Which skill a model picks when shown the catalog of descriptions. |
| `fixture`     | `executors/fixture_executor.py`     | That the harness works. No model reads anything.                  |

**Why the fallback applies to the whole runner.** Whether headless output
reliably reports skill invocation is unverified harness behavior. Issue #136
therefore scopes the `description` tier to every case rather than to collisions
alone, so the corpus is gradable even where the primary tier cannot observe an
invocation. The headless executor fails loudly rather than reporting "no skill"
when it cannot tell — recording an unobservable invocation as `none` would
silently pass every negative case.

**Why the fixture tier proves less than it appears to.** It answers from a rule
table, so it can only ever confirm the runner, the grader, and the output
contract. It says nothing about whether the descriptions steer a model, which is
why it is a distinct tier rather than a cheap substitute for one.

The `description` tier follows the micro-test protocol in
[`docs/skill-authoring.md`](../docs/skill-authoring.md): five repetitions per
prompt in independent processes, majority wins, and the agreement fraction is
recorded so a 3/5 result is never reported as though it were 5/5.

## Running it

```bash
just eval-triggering
```

```bash
just eval-triggering --executor "python3 triggering/executors/description_executor.py"
```

Recording a run as committed evidence goes through the eval-evidence norm in
[`AGENTS.md`](../AGENTS.md), which owns the summary format and its location:

```bash
just eval-record implement-ticket --suite triggering
```

## A negative case is not always "no skill"

A negative case asserts which skill must **not** win. That is a different claim
from asserting nothing wins, and conflating them is the easy mistake: "Implement
ticket 412." is a negative case for `plan-implementation`, and its expected pick
is `implement-ticket`, not nothing.

Peer-dependent expectations belong to the composition cases rather than here.
This corpus's catalog contains only what is actually installed, so a peer that
is absent cannot be picked — and an expectation naming it would fail for the
install state rather than for the routing.
