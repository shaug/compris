#!/usr/bin/env python3
"""Fallback tier: ask a model which skill a prompt triggers, from descriptions alone.

The model sees the catalog of skill descriptions and one prompt, and answers
with the skill it would route to, or `none`. It never sees the expected answer,
the case's kind, or which skill the case was filed under.

This tier exists because the primary `headless` tier depends on unverified
harness behavior — whether headless CLI output reliably reports which skill was
invoked. Per issue #136 the fallback therefore applies to the whole runner, not
only to cross-collision cases.

Following the micro-test protocol in `docs/skill-authoring.md`, each prompt is
asked `--repetitions` times (default 5) in independent processes, the majority
answer wins, and the agreement fraction is recorded so a 3/5 result is never
reported as though it were 5/5.

Requires the `claude` CLI on PATH. Reads one result-blind packet on stdin,
writes one JSON object on stdout.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path


def _load_core():
    """Load the sampling policy from this executor's own location."""
    core_path = Path(__file__).resolve().parents[2] / "sampling" / "core.py"
    spec = importlib.util.spec_from_file_location("sampling_core", core_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


core = _load_core()

NONE_ANSWER = core.NO_ANSWER


def build_prompt(payload: dict) -> str:
    catalog = "\n\n".join(
        f"- {entry['skill']}: {entry['description']}" for entry in payload["catalog"]
    )
    names = ", ".join(entry["skill"] for entry in payload["catalog"])
    return "\n".join(
        [
            "You are the router that decides which skill, if any, a user's",
            "request should load. Below is the complete catalog of available",
            "skills with their trigger descriptions, followed by one user",
            "request.",
            "",
            "## Catalog",
            catalog,
            "",
            "## User request",
            payload["prompt"],
            "",
            "## Answer format",
            f"Reply with exactly one name from this list: {names}, or the word",
            f"'{NONE_ANSWER}' if no skill in the catalog should be loaded.",
            "Reply with the bare name and nothing else — no prose, no punctuation.",
        ]
    )


def run_claude(prompt: str, claude_bin: str, model: str | None) -> str:
    return core.result_text(core.run_claude_envelope(prompt, claude_bin, model))


def parse_answer(text: str, known: set[str]) -> str | None:
    """Map a model reply onto a catalog name or None, without guessing."""
    cleaned = re.sub(r"[^a-z0-9:_-]+", " ", text.strip().lower()).strip()
    for token in cleaned.split():
        if token in known:
            return token
        if token == NONE_ANSWER:
            return None
    # A reply naming nothing recognisable is not evidence of "no skill"; it is
    # an unusable answer, and recording it as `none` would silently convert a
    # broken response into a passing negative case.
    raise RuntimeError(f"unrecognised router answer: {text.strip()[:200]!r}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument("--model", default=None)
    parser.add_argument("--repetitions", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.repetitions < 1:
        raise SystemExit("--repetitions must be at least 1")
    payload = json.load(sys.stdin)
    known = {entry["skill"] for entry in payload["catalog"]}
    prompt = build_prompt(payload)

    answers, failed = core.draw_with_tolerance(
        lambda: parse_answer(run_claude(prompt, args.claude_bin, args.model), known),
        args.repetitions,
    )
    winner, agreement, votes = core.vote_single(answers)
    json.dump(
        {
            "selected_skill": winner,
            "tier": "description",
            "repetitions": len(answers),
            "failed_samples": failed,
            "agreement": agreement,
            "votes": dict(votes),
        },
        sys.stdout,
        sort_keys=True,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
