"""Tests for the recall-versus-recognition probe's verdict logic.

The probe's verdicts are the evidence the baseline triage rests on, so the rule
that turns one model answer into `recall_gap`, `judgment_gap`, `uninformative`,
or `controls_only` is load-bearing and tested here directly. No model is
launched: `run_claude` is replaced with a stub returning a scripted answer.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parents[2]
PROBE_PATH = SKILL_ROOT / "scripts" / "evals" / "recognition_probe.py"

sys.path.insert(0, str(PROBE_PATH.parent))
PROBE_SPEC = importlib.util.spec_from_file_location(
    "implement_ticket_recognition_probe", PROBE_PATH
)
PROBE = importlib.util.module_from_spec(PROBE_SPEC)
assert PROBE_SPEC and PROBE_SPEC.loader
PROBE_SPEC.loader.exec_module(PROBE)

CASE = {
    "id": "example-case",
    "target_skill": "implement-ticket",
    "request": "Implement G-1 to readiness.",
    "authority": {},
    "capabilities": {},
    "artifacts": {},
}
EXPECTATION = {
    "case_id": "example-case",
    "required_actions": ["verify_non_merge_gates"],
    "forbidden_actions": ["invoke_merge_when_ready", "perform_no_mutation"],
}


PAYLOAD = {
    "target_skill": CASE["target_skill"],
    "skill_prompt": "skill prose",
    "request": CASE["request"],
    "authority": {},
    "capabilities": {},
    "artifacts": {},
}


def probe_with(answers, *, missed, expectation=EXPECTATION, renames=None):
    with (
        mock.patch.object(PROBE, "run_claude", return_value={"answers": answers}),
        mock.patch.object(PROBE, "build_payload", return_value=PAYLOAD),
    ):
        return PROBE.probe_case(
            CASE, expectation, "claude", "claude-opus-5", missed, renames
        )


class RecognitionProbeVerdictTests(unittest.TestCase):
    def test_recognized_obligation_with_clean_controls_is_a_recall_gap(self):
        """The obligation applies once named, and the controls are rejected.

        This is the verdict that reclassifies a graded failure from prose to
        elicitation, so it must require both halves: recognition alone, with the
        controls accepted too, proves only that the model agrees with what it is
        shown.
        """
        result = probe_with(
            {
                "verify_non_merge_gates": True,
                "invoke_merge_when_ready": False,
                "perform_no_mutation": False,
            },
            missed=["verify_non_merge_gates"],
        )
        self.assertEqual("recall_gap", result["verdict"])
        self.assertEqual(["verify_non_merge_gates"], result["missed_recognized"])
        self.assertEqual([], result["controls_accepted"])

    def test_rejected_obligation_with_clean_controls_is_a_judgment_gap(self):
        result = probe_with(
            {
                "verify_non_merge_gates": False,
                "invoke_merge_when_ready": False,
                "perform_no_mutation": False,
            },
            missed=["verify_non_merge_gates"],
        )
        self.assertEqual("judgment_gap", result["verdict"])
        self.assertEqual(["verify_non_merge_gates"], result["missed_rejected"])

    def test_an_accepted_control_makes_the_answer_uninformative(self):
        """Yea-saying outranks recognition, even when the obligation is accepted.

        Without this the probe would report `recall_gap` for a model agreeing
        with every name it is shown, which is the one reading the controls exist
        to rule out.
        """
        result = probe_with(
            {
                "verify_non_merge_gates": True,
                "invoke_merge_when_ready": True,
                "perform_no_mutation": False,
            },
            missed=["verify_non_merge_gates"],
        )
        self.assertEqual("uninformative", result["verdict"])
        self.assertEqual(["invoke_merge_when_ready"], result["controls_accepted"])

    def test_an_empty_missed_list_asks_the_converse_question(self):
        result = probe_with(
            {
                "verify_non_merge_gates": True,
                "invoke_merge_when_ready": True,
                "perform_no_mutation": False,
            },
            missed=[],
        )
        self.assertEqual("controls_only", result["verdict"])
        self.assertEqual(["invoke_merge_when_ready"], result["controls_accepted"])
        self.assertEqual(["perform_no_mutation"], result["controls_rejected"])

    def test_an_unanswered_name_is_not_read_as_recognition(self):
        result = probe_with(
            {"invoke_merge_when_ready": False, "perform_no_mutation": False},
            missed=["verify_non_merge_gates"],
        )
        self.assertEqual("judgment_gap", result["verdict"])
        self.assertEqual(["verify_non_merge_gates"], result["unanswered"])

    def test_a_name_outside_the_presented_set_is_discarded(self):
        result = probe_with(
            {
                "verify_non_merge_gates": True,
                "invoke_merge_when_ready": False,
                "perform_no_mutation": False,
                "invented_action_name": True,
            },
            missed=["verify_non_merge_gates"],
        )
        self.assertNotIn("invented_action_name", result["answers"])
        self.assertEqual("recall_gap", result["verdict"])


class RecognitionProbeInputGuardTests(unittest.TestCase):
    def test_a_missed_name_outside_required_actions_raises(self):
        """A typo must fail the run, not be recorded as a judgment gap.

        Such a name is never presented, so it can only come back unanswered,
        which scores `judgment_gap` — the verdict asserting the elicitation is
        not what produced the failure. Silently recording that would put a typo
        into the evidence wearing a finding's clothes.
        """
        with self.assertRaises(ValueError) as raised:
            probe_with(
                {"verify_non_merge_gates": True},
                missed=["verify_non_merge_gate"],
            )
        self.assertIn("verify_non_merge_gate", str(raised.exception))
        self.assertIn(CASE["id"], str(raised.exception))

    def test_a_forbidden_name_is_not_accepted_as_missed(self):
        with self.assertRaises(ValueError):
            probe_with(
                {"invoke_merge_when_ready": True},
                missed=["invoke_merge_when_ready"],
            )


class RecognitionProbeRenameTests(unittest.TestCase):
    def test_a_renamed_item_is_presented_and_scored_under_the_new_name(self):
        """The single-variable naming test: present one item differently.

        The answer arrives keyed by the presented name, while the record keeps
        the original, so a rename run stays comparable with the unrenamed one
        it is being read against.
        """
        result = probe_with(
            {
                "verify_gates": True,
                "invoke_merge_when_ready": False,
                "perform_no_mutation": False,
            },
            missed=["verify_non_merge_gates"],
            renames={"verify_non_merge_gates": "verify_gates"},
        )
        self.assertIn("verify_gates", result["presented_items"])
        self.assertNotIn("verify_non_merge_gates", result["presented_items"])
        self.assertEqual(["verify_non_merge_gates"], result["missed_recognized"])
        self.assertEqual("recall_gap", result["verdict"])

    def test_the_original_name_is_not_accepted_once_renamed(self):
        result = probe_with(
            {
                "verify_non_merge_gates": True,
                "invoke_merge_when_ready": False,
                "perform_no_mutation": False,
            },
            missed=["verify_non_merge_gates"],
            renames={"verify_non_merge_gates": "verify_gates"},
        )
        self.assertEqual("judgment_gap", result["verdict"])


class RecognitionProbeItemSetTests(unittest.TestCase):
    def test_every_required_and_forbidden_action_is_presented_exactly_once(self):
        result = probe_with(
            {
                "verify_non_merge_gates": True,
                "invoke_merge_when_ready": False,
                "perform_no_mutation": False,
            },
            missed=["verify_non_merge_gates"],
        )
        self.assertEqual(
            sorted(EXPECTATION["required_actions"] + EXPECTATION["forbidden_actions"]),
            sorted(result["presented_items"]),
        )

    def test_item_order_is_deterministic_for_a_case(self):
        """A rerun reproduces, so order carries no signal between runs."""
        answers = {
            "verify_non_merge_gates": True,
            "invoke_merge_when_ready": False,
            "perform_no_mutation": False,
        }
        first = probe_with(answers, missed=["verify_non_merge_gates"])
        second = probe_with(answers, missed=["verify_non_merge_gates"])
        self.assertEqual(first["presented_items"], second["presented_items"])


if __name__ == "__main__":
    unittest.main()
