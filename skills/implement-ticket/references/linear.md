# Linear ticket adapter

Use live Linear issue relationships and repository evidence when Linear owns the
ticket, parent, dependency, or status state.

## Preflight and scope

- Read the live issue body, state, parent or epic, project context, comments,
  and explicit blocking relationships.
- Read linked design documents and prior implementation PRs when they affect
  scope.
- Search for completed, canceled, duplicate, or superseding issues and PRs.
- Resolve repository, PR host, base, and local instructions independently.
- Apply the epic scope guard from native issue type/parent-child state plus
  explicit user scope.

Do not use list order, priority, labels, or an old prompt as dependency state
when explicit relations are available. If Linear cannot express a required
relationship, record that limitation; do not silently treat prose as equivalent
to a native blocker.

## Readiness and independent shipping

Verify every required outcome from a completed, canceled, duplicate, or
superseded blocker in its authoritative repository, artifact registry, tracker,
or environment. For same-repository code, verify the outcome on the base. For
cross-repository or operational prerequisites, verify the consumer uses the
required contract, version, configuration, approval, or environment state.

Treat a canceled or not-planned blocker with an unmet outcome as unresolved.
Read the parent outcome and relevant sibling contracts without selecting or
implementing sibling work. Return `blocked` if this ticket cannot ship
independently.

## PR linkage and transition

- Treat the live Linear issue body as the scope and acceptance contract.
- Preserve exact product rules such as timing, timezone, idempotency, skip,
  unavailable, migration, compatibility, rollout, and verification behavior.
- Use the repository's required Linear reference in branch, commit, and PR
  metadata.
- Keep one ticket per candidate, and publish it exactly once — as one ordinary
  PR, one ordered carved stack, or the several PRs a repository-owned
  `publish-candidate` may split an ordinary publication into. Allow an
  integration-driven completion transition only when all required acceptance can
  pass before merge; otherwise use a non-transitioning reference and close
  manually after post-merge evidence passes.
- Update or reopen Linear status only when that workflow state was actually
  reached, the criterion-specific ledger passes, and the completion policy
  authorizes the transition. A completed state is not acceptance evidence.
- After every PR of the publication is merged, or after a verified `all_merged`
  result, verify the complete result on the base and run every required
  post-merge acceptance item with separately granted environment and deployment
  authority. A subset merged does not reach this step.
- When the ticket is an epic child, reread affected native dependency
  relationships only after acceptance and the transition pass, then report newly
  unblocked work without selecting or mutating it.

Do not close or verify the parent epic. Report newly unblocked downstream work
without selecting it.
