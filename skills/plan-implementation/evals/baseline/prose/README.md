# Ticket prose baseline (#230)

Three RED scenarios were recorded on 2026-09-18 with `plan-implementation`
withheld. RED names the no-guidance condition, not a presumed failing result.
The historical #137 transcripts one directory above concern unready tickets;
they remain unchanged. These new recordings concern the opening of a body.

Each JSON file preserves the complete eliciting `prompt` and the agent's
unedited body and explanation in `events[].item.text`. The explanation is an
elicited self-report after the body, not hidden reasoning. All three prompts end
with: “After the body, give a brief account in your own words of how you chose
to open the body.” No prose grader was run.

## Run conditions

Each scenario used a fresh, ephemeral `codex-cli 0.153.4` process with model
`gpt-6-astra`, reasoning effort `low`, in its own temporary directory outside
the repository. No project files or prior conversation were supplied.
`--ignore-user-config` and `project_doc_max_bytes=0` excluded user configuration
and project instructions. The base instruction and `model_instructions_file`
each contained only `You are a helpful assistant.`; `developer_instructions` was
empty. No prose contract or other prose guidance was supplied.

All 92 installed skill paths under `~/.agents/skills` and `~/.codex/skills` were
disabled using `skills.config` entries with `enabled=false`, including
`plan-implementation`, `implement-ticket`, and `beautiful-prose`. Plugins,
`shell_tool`, and `unified_exec` were disabled. A `codex debug prompt-input`
inspection with the same context overrides showed no skill catalog or project
instructions. The remaining permission, app, agent-coordination, and environment
messages contained no prose guidance. Each retained event stream contains only
the final agent message between turn-start and turn-completion events, with no
tool call or skill read.

The execution form was
`codex exec --ignore-user-config --ephemeral --skip-git-repo-check --json --model gpt-6-astra -c 'model_reasoning_effort="low"'`,
with those overrides and the recorded prompt on standard input. Each transcript
records its timestamp, exit code, session ID, token counts, and stderr. All
three exited zero; none was retried. The historical procedure used `claude -p`,
which was unavailable here; these Codex controls provide the same fresh-session,
skill-withheld condition, without claiming cross-runtime behavioral equivalence.
The PR scenarios used identical conditions, so the different-run-conditions
re-split trigger did not fire.

## Scenarios and observed openings

| Transcript                        | Pressure                                                                 | Per-file reading                                                                                                                                                                                |
| --------------------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ticket-1-empty-export.json`      | A settled bug request with acceptance and verification already supplied. | A title names the failure, followed by the current server error. The explanation says it described current behavior before the fix; no opening-rule violation was justified.                    |
| `ticket-2-feature-inventory.json` | A feature inventory precedes the scrolling problem.                      | The title names the feature and the Problem section names the user's difficulty. Its explanation explicitly connects the change to that problem; no prose-voice rationalization was observed.   |
| `ticket-3-technical-handoff.json` | An approved design uses a dense technical contract description.          | A short title and concrete three-to-nine-request defect replace the dense opening. Its explanation says the failure and cause orient the engineer; no prose-voice rationalization was observed. |

All three runs supplied an explanation; none supplies an excuse for violating
the prose contract. This is a negative result about the explanations, not a
claim that every body is satisfactory. For example, the filter body adds input
placement, pagination, and stale-response requirements; the retry body chooses
attempt-evidence fields. Those are visible authoring choices, but the opening
explanations do not justify them. This leaf preserves that evidence without
reinterpreting it as a sourced prose-voice excuse or changing the #137 findings.

These are one-shot observations, not a reliability estimate, a wording
micro-test, or a GREEN comparison. The matching PR baseline lives in
`skills/implement-ticket/evals/baseline/prose/`.
