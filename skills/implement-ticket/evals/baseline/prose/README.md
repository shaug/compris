# Pull request prose baseline (#230)

Three RED scenarios were recorded on 2026-09-18 with `implement-ticket`
withheld, before writing any new prose rule. RED names the no-guidance
condition; it does not assert that the output failed. Each JSON file contains
the complete eliciting `prompt` and unedited response in `events[].item.text`,
including the agent's own explanation after the body. These explanations are
elicited self-reports, not a recording of hidden reasoning. No prose grader was
run.

## Run conditions

Each scenario used a fresh, ephemeral `codex-cli 0.153.4` process, model
`gpt-6-astra`, reasoning effort `low`, and a separate temporary working
directory outside the repository. No project files or conversation history were
supplied. `--ignore-user-config` and `project_doc_max_bytes=0` excluded user
configuration and project instructions. Both the base instruction and
`model_instructions_file` contained only `You are a helpful assistant.`;
`developer_instructions` was empty. No guidance about prose was supplied.

All 92 installed skill paths under `~/.agents/skills` and `~/.codex/skills` were
disabled through `skills.config` entries with `enabled=false`.
`implement-ticket` was withheld along with `plan-implementation`,
`beautiful-prose`, and every other discovered skill. Plugins, `shell_tool`, and
`unified_exec` were disabled. A `codex debug prompt-input` inspection with the
same context overrides confirmed that no skill catalog or project instructions
remained. Runtime permission, app, agent-coordination, and environment messages
remained; none supplied prose guidance. Every retained event stream contains
only the final agent message between turn-start and turn-completion events, with
no tool call or skill read.

The execution form was
`codex exec --ignore-user-config --ephemeral --skip-git-repo-check --json --model gpt-6-astra -c 'model_reasoning_effort="low"'`,
with the overrides above and each file's exact prompt on standard input. Exit
codes, timestamps, session IDs, token counts, and stderr are retained in each
transcript. All three exited zero. The empty working directories used identical
conditions for PR and ticket bodies, so the issue's different-run-conditions
re-split trigger did not fire.

The historical baseline procedure used `claude -p`; that executable was absent
here. Codex supplies the same fresh-session, skill-withheld condition with its
own controls. The exact prompts and responses are the evidence, not a claim that
the two runtimes behave identically. An initial executor probe used the CSV
scenario before the model was explicitly selected. Its output is preserved in
`pilot-csv-encoding.json`; its model identity was not captured, so it is not one
of the three controlled scenarios. No controlled scenario was retried.

## Scenarios and observed openings

| Transcript                           | Pressure                                                             | Per-file reading                                                                                                                                                                                       |
| ------------------------------------ | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `pr-1-csv-encoding.json`             | A small fix with change notes and passing tests.                     | Opens on corrupted names and the BOM fix. Its explanation says it chose the user-visible problem and fix. No rationalization for violating the opening rule was observed.                              |
| `pr-2-implementation-inventory.json` | Changed-file inventory appears before the user problem.              | Opens on reducing repeated requests and names opt-in behavior. A later Changes section repeats the file inventory, but its opening explanation does not justify that section or a voice violation.     |
| `pr-3-deadline-handoff.json`         | Immediate reviewer handoff and a modifier-heavy adapter description. | Opens on the timeout defect and correction. A later paragraph echoes the adapter description; the explanation says it put functional impact before consolidation, not why it retained those modifiers. |
| `pilot-csv-encoding.json`            | Executor setup probe of the CSV scenario.                            | Also opens on the user-visible defect and fix; the model was not captured, so this is supplemental provenance only.                                                                                    |

All three controlled runs produced an opening explanation. None supplies a
verbatim excuse for a prose-voice violation. The later inventory and modifier
echoes are observable output, but inventing an explanation for them would not
meet the rationalization-table sourcing rule. These are three single samples,
not a reliability estimate or a RED-to-GREEN comparison. The ticket-body
baseline is in `skills/plan-implementation/evals/baseline/prose/`; this change
does not edit the canonical contract or any skill obligation.
