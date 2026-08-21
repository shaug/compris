# Claude Code adapter

Optional discovery metadata for Claude Code and Claude Agent SDK runtimes. It
does not constrain the skill's portable contract.

- Display name: Implement Ticket.
- Suggested prompt: "Use the implement-ticket skill to implement this ticket,
  run its initial review, choose the authorized ordinary or carved-stack
  publication path, and verify the authorized result."
- Isolated implementation state: create the ticket branch in a dedicated git
  worktree (for example via Claude Code's worktree support) owned exclusively by
  one mutating context.
- Fresh read-only review context: delegate to repository-owned `review-fix-loop`
  and, as its `reviewer` port, invoke repository-owned `review-code-change` in a
  subagent (Agent tool) restricted to read-only tools, giving it only raw
  candidate evidence — never the implementation transcript.
- Long waits: follow the selected delegate's monitoring contract; ordinary
  pending CI is not a blocker, so keep the task alive with background monitoring
  rather than returning early.
