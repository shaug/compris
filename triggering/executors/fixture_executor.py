#!/usr/bin/env python3
"""Deterministic stand-in for a compliant router, used to exercise the harness.

This executor answers from a fixed rule table, not from a model. It exists so
the runner, the grader, the per-case output contract, and the recorded-summary
path can be tested and regression-guarded without spending money or requiring
model access.

It proves the harness works. It proves nothing about whether the skill
descriptions actually steer a model — no model reads them here — which is why
it declares the `fixture` tier, kept distinct from `headless` and
`description` everywhere the evidence is recorded.

Reads one result-blind packet on stdin, writes one JSON object on stdout.
"""

from __future__ import annotations

import json
import re
import sys

# Ordered rules: the first whose pattern matches decides. Order matters where
# one prompt legitimately contains another's vocabulary — "before merging, give
# this a proper review" carries merge language but is a review request.
RULES: tuple[tuple[str, str | None], ...] = (
    # Approved-design implementation planning is deliberately house-owned.
    (
        r"approved design.*(?:implementation plan|ticket graph)",
        "plan-implementation",
    ),
    # Peer-owned language: no compris skill may claim these.
    (r"\bbrainstorm\b", None),
    (r"red-green-refactor|test-driven development|failing test first", None),
    (r"\bdebug\b|diagnos|why (it|this) fails|work out why", None),
    (r"\bplan\b(?!.*\bticket\b)", None),
    # Review-suite entry point beats individual lenses and merge-adjacent words.
    (r"code review|review my change|proper review", "review-code-change"),
    (
        r"until the review (comes back )?clean|keep reviewing and fixing",
        "review-fix-loop",
    ),
    (r"over-engineered|simpler (architecture|design)", "review-solution-simplicity"),
    (r"duplication|control flow|simplify locally", "review-code-simplicity"),
    (r"bugs and security|security problems|against what it says", "review-correctness"),
    # Epic orchestration beats single-ticket execution when the graph is named.
    (r"\bepic\b|sub-issues|children of", "implement-epic"),
    # Branch recomposition.
    (
        r"too big for one pull request|stacked prs|carve my branch|split it into a stack",
        "carve-changesets",
    ),
    # Published-PR lifecycle.
    (r"babysit|watch pr|drive it to green|until it closes", "babysit-pr"),
    # Ticket authoring, before execution language.
    (
        r"turn it into a ticket|implementation-ready|no acceptance criteria",
        "plan-implementation",
    ),
    # Single-ticket execution.
    (r"implement ticket|from open to merged|open a pr for it", "implement-ticket"),
)


def select(prompt: str) -> str | None:
    lowered = prompt.lower()
    for pattern, skill in RULES:
        if re.search(pattern, lowered):
            return skill
    return None


def main() -> int:
    payload = json.load(sys.stdin)
    known = {entry["skill"] for entry in payload.get("catalog", [])}
    selected = select(payload["prompt"])
    if selected is not None and selected not in known:
        selected = None
    json.dump(
        {
            "selected_skill": selected,
            "tier": "fixture",
            "repetitions": 1,
            "agreement": 1.0,
        },
        sys.stdout,
        sort_keys=True,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
