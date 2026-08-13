# Can `writing-plans` be steered to behavioral altitude?

This is the recorded run of the experiment [the design document] posts under
"Recorded experiments". It is an **observation, not a decision**. It reports
what one run of `superpowers:writing-plans` returned when handed a spec written
entirely as surface-observable acceptance criteria, and whether that output met
the criterion the design document approved in advance. It selects none of the
three responses that document holds open, and it changes no skill contract.

The run was performed on 2026-08-12.

## The question and the approved criterion

The design document's worry is altitude, not depth. The peer produces unit-level
TDD bound to internals, while compris requires acceptance criteria observable at
the public surface. Its approved success criterion is conjunctive:

> Its Interfaces block does not name internal function signatures, and its test
> steps assert against observable behavior rather than against functions.

## Reproducing the run

**The pin.** `superpowers` was installed from the `claude-plugins-official`
marketplace at version **6.2.0**, recorded in
`~/.claude/plugins/installed_plugins.json` as `gitCommitSha`
`44c9b2d6e889982ac18c27d05a19fefe335194e1` — the exact pin the design document
names. The installed tree at
`~/.claude/plugins/cache/claude-plugins-official/superpowers/6.2.0/skills/`
carries the fourteen skills that pin is expected to carry, including
`writing-plans`.

**The isolation.** The run was dispatched into a fresh agent context that was
told nothing about this experiment, the altitude question, the success
criterion, or the three responses. It received only the instruction below and
the spec. A context that knew what was being measured would have steered the
result, and a steered result is indistinguishable from a genuine one at the
point it is read.

**The instruction**, verbatim apart from the spec body, which follows it:

> I have a spec for a new tool and I need an implementation plan for it. Use the
> `superpowers:writing-plans` skill to produce that plan.
>
> Save the plan to this exact path (this overrides the skill's default plan
> location): `<scratch path>`
>
> Constraints on your actions (not on the plan's content): do not implement any
> of the plan, do not create git worktrees or branches, and do not create or
> modify any file anywhere except the single plan file at the path above. There
> is no existing codebase for this tool; it is a greenfield project.
>
> When you are done, reply with only the absolute path of the saved plan file.
>
> Here is the spec:

**The spec.** A greenfield tool was used rather than a live compris ticket, so
that the artifact could not be mistaken for authorized planning of scheduled
work. Its seven acceptance criteria are stated purely as observable command
behavior — stdout text, stderr text, and exit codes — in the house ticket form.
It is reproduced in full in [the spec], and the plan it produced is retained in
[the returned plan] — its content unaltered, carrying a prepended do-not-execute
note and the Markdown normalization `just format` applies to every file here.

**One caution about reproducing it.** A rerun will not return this plan.
Re-running the instruction at the same pin re-tests the question; it does not
regenerate this artifact. That is why the plan is committed here rather than
merely described — the claims below are auditable against the artifact that
produced them, not against a rerun that will differ.

## What returned

A 1,363-line plan as returned. The committed copy is 1,517 lines: 18 of those
are the prepended do-not-execute note, and the remaining difference is
`just format` reflowing prose to the repository's 80-column wrap. A header,
global constraints, a section resolving spec ambiguities, a file-structure map,
six tasks, and a final-verification section. Every task carries the **Files**
and **Interfaces** blocks the skill's template prescribes and a numbered
sequence of test-first steps.

### Interfaces blocks: internal signatures, in all six tasks

All six **Interfaces** blocks name internal function signatures with parameter
and return types. Task 3's, representatively:

```text
- Consumes: `linecap.gitrepo.tracked_files(root) -> list[Path]` and
  `linecap.gitrepo.repo_root(start) -> Path` from Task 2.
- Produces:
  - `linecap.report.Offender` — frozen dataclass with fields `path: str` … and `lines: int`.
  - `linecap.report.format_human(report: Report) -> str` …
  - `linecap.scan.count_lines(path: Path) -> int`
  - `linecap.scan.scan(root: Path, budget: int) -> Report` …
```

This is the skill operating as designed, not failing to follow the spec. Its own
task template requires it: the Interfaces block is specified as "exact function
names, parameter and return types", justified by the note that "A task's
implementer sees only their own task; this block is how they learn the names and
types neighboring tasks use." The block is addressed to a subagent executor, and
it names internals because that executor needs them.

### Test steps: both altitudes, with every criterion at the surface

The plan specifies 24 test functions across five files. They split cleanly:

| Tier                                                                         | Count | Asserts against                                |
| ---------------------------------------------------------------------------- | ----- | ---------------------------------------------- |
| `tests/test_acceptance.py`                                                   | 8     | the installed console script, via `subprocess` |
| `tests/test_gitrepo.py`, `test_scan.py`, `test_config.py`, `test_exclude.py` | 16    | imported functions, called directly            |

The acceptance tier asserts on exit code and exact stdout, through a session
fixture that resolves the installed `linecap` console script with `shutil.which`
and runs it as a subprocess:

```python
def test_two_offenders_exit_1_and_list_descending(run_linecap, git_repo: Path, add_file) -> None:
    add_file(git_repo, "src/big.py", 600)
    add_file(git_repo, "src/bigger.py", 900)
    add_file(git_repo, "src/small.py", 10)

    result = run_linecap(git_repo)

    assert result.exit_code == 1
    assert result.stdout.splitlines() == [
        "src/bigger.py: 900 lines (budget 500)",
        "src/big.py: 600 lines (budget 500)",
    ]
```

The unit tier imports the internals the Interfaces blocks declare and asserts on
their return values:

```python
from linecap.scan import count_lines

def test_count_lines_handles_undecodable_bytes(tmp_path: Path) -> None:
    target = tmp_path / "binary.bin"
    target.write_bytes(b"\xff\xfe\n\x00\x01\n")

    assert count_lines(target) == 2
```

Every one of the spec's seven acceptance criteria is covered by a named test in
the acceptance tier — none is left to the unit tier. The plan's final
verification asserts this itself, with a criterion-to-test table mapping all
seven, and requires the whole suite to run against a freshly reinstalled
package. Four of the six tasks write their unit tests first and their acceptance
test second; Task 1 and Task 4 write only acceptance tests.

## The result against the approved criterion

**The criterion is not met.** It is conjunctive, and its first half fails
outright:

| Half of the criterion                                        | Result    | Evidence                                                                                                    |
| ------------------------------------------------------------ | --------- | ----------------------------------------------------------------------------------------------------------- |
| Interfaces block does not name internal function signatures  | **Fail**  | All six blocks name them, with parameter and return types, as the skill's own template requires             |
| Test steps assert against observable behavior, not functions | **Mixed** | 8 of 24 tests drive the installed command; 16 call imported functions. All seven spec criteria sit in the 8 |

Recording the second half as mixed rather than as a pass or a fail is the honest
reading, and the distinction carries the finding. The criterion as written asks
whether the test steps assert against behavior; they partly do. The question
behind it — whether public-surface requirements survive the trip into
implementation tasks — got a different answer than the criterion's phrasing
anticipated: **every surface-observable criterion in the spec arrived as a
surface-level test**, and the internal-signature material appeared *in addition
to* that, not in place of it. The plan did not translate the spec down to unit
altitude. It preserved the spec's altitude and added a lower tier beneath it.

The design document's stated hypothesis — that the peer's own coverage check
maps behavior onto implementation tasks — is what the observation supports. The
mechanism was visible: the plan's self-review produced an explicit
criterion-to-test table, and every entry pointed at the acceptance tier.

## What this does and does not decide

**Left unselected.** The three responses the design document holds open — take
it as-is, post-process, structure only — remain unselected. One run does not
decide between them, and this ticket did not authorize the choice. The design
document and its three responses are unchanged.

**What a decision-maker can take from this.** Two things, and only as input:

- The failing half is a fixed property of the skill's template, not a steering
  failure that a better-written spec would avoid. No phrasing of a spec removes
  the Interfaces block, because the skill mandates it and its subagent executor
  depends on it.
- The failure and the surface coverage are separable. They landed in different
  parts of the artifact — internals in the Interfaces blocks and the unit tier,
  surface behavior in the acceptance tier and the coverage table — rather than
  being mixed together inside the same test steps.

**What this is not.** Not a gate, not a blocker, and not evidence about any
other superpowers skill or any other pin. One session, one spec, one plan.
Nothing here establishes what a second run would return.

<!-- inline reference link definitions. please keep alphabetized -->

[the design document]: ../../cognitive-driven-development.md#can-writing-plans-be-steered-to-behavioral-altitude
[the returned plan]: 2026-08-12-writing-plans-behavioral-altitude-plan.md
[the spec]: 2026-08-12-writing-plans-behavioral-altitude-spec.md
