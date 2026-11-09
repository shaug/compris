"""Canonical transport, sample drawing, and voting for real-model evaluations.

Skill distributions bundle this file byte-for-byte with just sync-contracts.
Changing drawing or voting behavior requires a POLICY_VERSION bump so recorded
results never compare two different graders under the same policy identity.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from collections import Counter
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

POLICY_VERSION = "1"
RESULT_ATTEMPTS = 3
SCENARIO_RETRY_PAUSE_SECONDS = 30
NO_ANSWER = "none"
T = TypeVar("T")


class SampleUnavailable(RuntimeError):
    """The runtime supplied no sample, distinct from a wrong model answer."""


def run_claude_envelope(prompt: str, claude_bin: str, model: str | None) -> dict:
    command = [claude_bin, "-p", "--output-format", "json"]
    if model:
        command.extend(["--model", model])
    try:
        completed = subprocess.run(
            command, input=prompt, text=True, capture_output=True, check=False
        )
    except OSError as error:
        raise SampleUnavailable(str(error)) from error
    if completed.returncode:
        raise SampleUnavailable(
            f"claude exited {completed.returncode}: {completed.stderr.strip()}"
        )
    try:
        envelope = json.loads(completed.stdout)
    except ValueError as error:
        raise SampleUnavailable("headless output was not one JSON object") from error
    if not isinstance(envelope, dict):
        raise SampleUnavailable("headless output was not one JSON object")
    return envelope


def result_text(envelope: dict) -> str:
    result = envelope.get("result")
    if not isinstance(result, str):
        raise SampleUnavailable("claude --output-format json returned no result text")
    return result


def extract_json_object(text: str) -> dict:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("the runtime returned no JSON object")
    value = json.loads(candidate[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("the runtime returned a non-object JSON value")
    return value


def draw_json(
    prompt: str, claude_bin: str, model: str | None, attempts: int = RESULT_ATTEMPTS
) -> dict:
    last_error = None
    for _ in range(attempts):
        text = result_text(run_claude_envelope(prompt, claude_bin, model))
        try:
            return extract_json_object(text)
        except ValueError as error:
            last_error = error
    raise SampleUnavailable(
        f"executor model returned malformed JSON after {attempts} attempts: {last_error}"
    )


def draw_batch(draw_one: Callable[[], T], repetitions: int) -> list[T]:
    """Draw concurrently, preserving order and legitimate None answers."""
    with ThreadPoolExecutor(max_workers=repetitions) as pool:
        futures = [pool.submit(draw_one) for _ in range(repetitions)]
        drawn = []
        for future in futures:
            try:
                drawn.append(future.result())
            except SampleUnavailable:
                pass
    return drawn


def draw_with_tolerance(
    draw_one: Callable[[], T],
    repetitions: int,
    pause: float = SCENARIO_RETRY_PAUSE_SECONDS,
) -> tuple[list[T], int]:
    if repetitions < 1:
        raise ValueError("repetitions must be at least 1")
    drawn = draw_batch(draw_one, repetitions)
    failed = repetitions - len(drawn)
    if not drawn:
        time.sleep(pause)
        drawn = draw_batch(draw_one, repetitions)
        failed += repetitions - len(drawn)
    if not drawn:
        raise SampleUnavailable(
            f"every one of the {repetitions} samples failed for this "
            f"scenario, twice, {pause}s apart"
        )
    return drawn, failed


def claimed(value) -> str | None:
    """Keep a wrongly shaped answer gradable rather than dropping its claim."""
    if value is None or isinstance(value, str):
        return value
    return str(value)


def modal(votes: Counter) -> tuple[str, int]:
    """Return the lexical minimum among equally most-voted answers."""
    top = max(votes.values())
    return min(answer for answer, count in votes.items() if count == top), top


def majority_of(repetitions: int) -> int:
    return repetitions // 2 + 1


def vote_single(values: Iterable[str | None]) -> tuple[str | None, float, dict]:
    votes = Counter(claimed(value) or NO_ANSWER for value in values)
    winner, agreement = modal(votes)
    return (
        None if winner == NO_ANSWER else winner,
        agreement / votes.total(),
        dict(votes),
    )


def vote_set(
    sample_sets: Iterable[Iterable[str]], majority: int
) -> tuple[list[str], dict]:
    votes = Counter(value for values in sample_sets for value in set(values))
    return sorted(value for value, count in votes.items() if count >= majority), dict(
        votes
    )
