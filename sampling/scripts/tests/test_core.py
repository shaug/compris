"""Behavioral evidence for the single transport, drawing, and vote policy."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
from sampling_helpers import ROOT, load_module  # noqa: E402


class SamplingCoreTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / "sampling/core.py"
        self.assertTrue(path.is_file(), "sampling/core.py must own the shared policy")
        self.core = load_module("tested_sampling_core", path)

    def test_policy_version_is_a_nonempty_string(self):
        self.assertIsInstance(self.core.POLICY_VERSION, str)
        self.assertTrue(self.core.POLICY_VERSION.strip())

    def test_modal_ties_ignore_insertion_order(self):
        for answers in (["merged", "blocked"], ["blocked", "merged"]):
            self.assertEqual(
                self.core.modal(Counter(dict.fromkeys(answers, 2))), ("blocked", 2)
            )

    def test_majority_is_strict_for_even_and_odd_counts(self):
        self.assertEqual(
            [self.core.majority_of(n) for n in (1, 2, 3, 4, 5)], [1, 2, 2, 3, 3]
        )

    def test_single_vote_round_trips_absence_and_preserves_all_counts(self):
        self.assertEqual(
            self.core.vote_single([None, None, "blocked"]),
            (None, 2 / 3, {"none": 2, "blocked": 1}),
        )

    def test_set_vote_counts_each_samples_choice_once(self):
        selected, votes = self.core.vote_set([["a", "a", "b"], ["a"], ["b"], ["a"]], 3)
        self.assertEqual(selected, ["a"])
        self.assertEqual(votes, {"a": 3, "b": 2})

    def test_wrongly_shaped_claim_remains_an_answer(self):
        self.assertEqual(self.core.claimed(["blocked"]), "['blocked']")
        self.assertEqual(self.core.claimed(1), "1")
        self.assertIsNone(self.core.claimed(None))

    def test_fenced_json_and_plain_object_are_extracted(self):
        for text in ('prefix {"answer": 1} suffix', '```json\n{"answer": 1}\n```'):
            self.assertEqual(self.core.extract_json_object(text), {"answer": 1})
        with self.assertRaises(ValueError):
            self.core.extract_json_object('["blocked"]')

    def test_transport_retains_the_complete_envelope(self):
        envelope = {
            "result": "answer",
            "model": "sample-model",
            "usage": {"output_tokens": 3},
        }
        completed = subprocess.CompletedProcess([], 0, json.dumps(envelope), "")
        with mock.patch.object(
            self.core.subprocess, "run", return_value=completed
        ) as run:
            self.assertEqual(
                self.core.run_claude_envelope("prompt", "claude", "chosen-model"),
                envelope,
            )
        self.assertEqual(
            run.call_args.args[0],
            ["claude", "-p", "--output-format", "json", "--model", "chosen-model"],
        )
        self.assertEqual(run.call_args.kwargs["input"], "prompt")
        self.assertEqual(self.core.result_text(envelope), "answer")

    def test_runtime_refusals_have_their_own_exception_type(self):
        for completed in (
            subprocess.CompletedProcess([], 1, "", "overloaded"),
            subprocess.CompletedProcess([], 0, "not JSON", ""),
            subprocess.CompletedProcess([], 0, "[]", ""),
        ):
            with (
                self.subTest(completed=completed),
                mock.patch.object(self.core.subprocess, "run", return_value=completed),
            ):
                with self.assertRaises(self.core.SampleUnavailable):
                    self.core.run_claude_envelope("p", "claude", None)
        with self.assertRaises(self.core.SampleUnavailable):
            self.core.result_text({"result": None})

    def test_json_drawing_retries_a_malformed_model_result(self):
        with mock.patch.object(
            self.core,
            "run_claude_envelope",
            side_effect=[
                {"result": '{"answer":'},
                {"result": '{"answer": 1}'},
            ],
        ) as run:
            self.assertEqual(self.core.draw_json("p", "claude", None), {"answer": 1})
            self.assertEqual(run.call_count, 2)

    def test_json_drawing_stops_after_three_malformed_results(self):
        with mock.patch.object(
            self.core, "run_claude_envelope", return_value={"result": "bad"}
        ) as run:
            with self.assertRaises(self.core.SampleUnavailable):
                self.core.draw_json("p", "claude", None)
        self.assertEqual(run.call_count, 3)

    def test_batch_drops_only_runtime_refusals_and_keeps_none_answers(self):
        draw = mock.Mock(
            side_effect=[None, self.core.SampleUnavailable("busy"), "alpha"]
        )
        self.assertEqual(self.core.draw_batch(draw, 3), [None, "alpha"])
        with self.assertRaisesRegex(RuntimeError, "unrecognised"):
            self.core.draw_batch(
                mock.Mock(side_effect=RuntimeError("unrecognised reply")), 1
            )

    def test_burst_redraw_counts_failures_across_both_rounds(self):
        refused = self.core.SampleUnavailable("busy")
        draw = mock.Mock(side_effect=[refused] * 5 + ["a", refused, "b", refused, "c"])
        with mock.patch.object(self.core.time, "sleep") as sleep:
            self.assertEqual(
                self.core.draw_with_tolerance(draw, 5), (["a", "b", "c"], 7)
            )
        sleep.assert_called_once_with(self.core.SCENARIO_RETRY_PAUSE_SECONDS)

    def test_partial_success_does_not_redraw(self):
        draw = mock.Mock(side_effect=["a", self.core.SampleUnavailable("busy")])
        with mock.patch.object(self.core.time, "sleep") as sleep:
            self.assertEqual(self.core.draw_with_tolerance(draw, 2), (["a"], 1))
        sleep.assert_not_called()

    def test_two_empty_rounds_raise(self):
        draw = mock.Mock(side_effect=self.core.SampleUnavailable("busy"))
        with mock.patch.object(self.core.time, "sleep") as sleep:
            with self.assertRaises(self.core.SampleUnavailable):
                self.core.draw_with_tolerance(draw, 3, pause=0)
        self.assertEqual(draw.call_count, 6)
        sleep.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()
