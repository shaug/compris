from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from native_stack import (  # noqa: E402
    NativeLayer,
    NativePullRequest,
    NativeStackError,
    NativeStackSnapshot,
    TerminalState,
    TruthPhase,
    classify_truth_phase,
    parse_native_stack,
    reconcile_native_stack,
)
from rehydrate import PullRequestRecord  # noqa: E402

A_SHA = "a" * 40
B_SHA = "b" * 40
C_SHA = "c" * 40
VIEW_OPEN = json.loads(
    (TESTS_DIR / "fixtures" / "gh-stack" / "view-open.json").read_text()
)
OPEN_PR_101 = PullRequestRecord(
    number=101,
    head_branch="feature-1",
    head_sha="1" * 40,
    base_branch="main",
    state="OPEN",
    body="",
)
OPEN_PR_102 = PullRequestRecord(
    number=102,
    head_branch="feature-2",
    head_sha="2" * 40,
    base_branch="feature-1",
    state="OPEN",
    body="",
)


class NativeStackSnapshotTest(unittest.TestCase):
    def test_parses_ordered_native_layers(self) -> None:
        snapshot = parse_native_stack(VIEW_OPEN, trunk_head=A_SHA)

        self.assertEqual(snapshot.trunk_branch, "main")
        self.assertEqual(snapshot.trunk_head, A_SHA)
        self.assertEqual(snapshot.current_branch, "feature-2")
        self.assertEqual(
            tuple(layer.branch for layer in snapshot.layers),
            ("feature-1", "feature-2"),
        )
        self.assertEqual(
            (101, 102),
            tuple(
                layer.pull_request.number
                for layer in snapshot.layers
                if layer.pull_request
            ),
        )

    def test_rejects_noncontiguous_native_bases(self) -> None:
        payload = copy.deepcopy(VIEW_OPEN)
        payload["branches"][1]["base"] = B_SHA

        with self.assertRaisesRegex(
            NativeStackError,
            "feature-2.*base.*expected predecessor head 1111111111111111111111111111111111111111",
        ):
            parse_native_stack(payload, trunk_head=A_SHA)

    def test_rejects_duplicate_branches_and_multiple_current_layers(self) -> None:
        duplicate = copy.deepcopy(VIEW_OPEN)
        duplicate["branches"][1]["name"] = "feature-1"
        with self.assertRaisesRegex(NativeStackError, "duplicate branch feature-1"):
            parse_native_stack(duplicate, trunk_head=A_SHA)

        multiple_current = copy.deepcopy(VIEW_OPEN)
        multiple_current["branches"][0]["isCurrent"] = True
        with self.assertRaisesRegex(NativeStackError, "exactly one current layer"):
            parse_native_stack(multiple_current, trunk_head=A_SHA)

    def test_rejects_invalid_sha_and_unknown_pull_request_state(self) -> None:
        invalid_sha = copy.deepcopy(VIEW_OPEN)
        invalid_sha["branches"][0]["head"] = "short"
        with self.assertRaisesRegex(NativeStackError, "feature-1.*head.*full SHA"):
            parse_native_stack(invalid_sha, trunk_head=A_SHA)

        invalid_state = copy.deepcopy(VIEW_OPEN)
        invalid_state["branches"][0]["pr"]["state"] = "DRAFT"
        with self.assertRaisesRegex(NativeStackError, "feature-1.*PR state.*DRAFT"):
            parse_native_stack(invalid_state, trunk_head=A_SHA)

    def test_rejects_pull_request_state_that_disagrees_with_merged_flag(self) -> None:
        payload = copy.deepcopy(VIEW_OPEN)
        payload["branches"][0]["isMerged"] = True

        with self.assertRaisesRegex(
            NativeStackError,
            "feature-1.*merged flag.*PR state OPEN",
        ):
            parse_native_stack(payload, trunk_head=A_SHA)

    def test_rejects_merged_layer_after_open_layer(self) -> None:
        payload = copy.deepcopy(VIEW_OPEN)
        payload["branches"][1]["isMerged"] = True
        payload["branches"][1]["pr"]["state"] = "MERGED"

        with self.assertRaisesRegex(
            NativeStackError,
            "feature-2.*merged layer follows open layer feature-1",
        ):
            parse_native_stack(payload, trunk_head=A_SHA)

    def test_accepts_merged_prefix_before_open_suffix_at_current_trunk(self) -> None:
        payload = copy.deepcopy(VIEW_OPEN)
        payload["branches"][0]["base"] = B_SHA
        payload["branches"][0]["isMerged"] = True
        payload["branches"][0]["pr"]["state"] = "MERGED"
        payload["branches"][1]["base"] = A_SHA

        snapshot = parse_native_stack(payload, trunk_head=A_SHA)

        self.assertTrue(snapshot.layers[0].merged)
        self.assertFalse(snapshot.layers[1].merged)

    def test_accepts_fully_merged_historical_chain(self) -> None:
        payload = copy.deepcopy(VIEW_OPEN)
        payload["branches"][0]["base"] = B_SHA
        for layer in payload["branches"]:
            layer["isMerged"] = True
            layer["pr"]["state"] = "MERGED"

        snapshot = parse_native_stack(payload, trunk_head=A_SHA)

        self.assertTrue(all(layer.merged for layer in snapshot.layers))

    def test_accepts_sequentially_rebased_merged_history(self) -> None:
        payload = copy.deepcopy(VIEW_OPEN)
        payload["branches"][1]["base"] = C_SHA
        for layer in payload["branches"]:
            layer["isMerged"] = True
            layer["pr"]["state"] = "MERGED"

        snapshot = parse_native_stack(payload, trunk_head=A_SHA)

        self.assertEqual(C_SHA, snapshot.layers[1].base)

    def test_reconcile_rejects_remote_head_disagreement(self) -> None:
        snapshot = parse_native_stack(VIEW_OPEN, trunk_head=A_SHA)

        with self.assertRaisesRegex(
            NativeStackError,
            "layer feature-1 remote head mismatch: native 1111111111111111111111111111111111111111; remote bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ):
            reconcile_native_stack(
                snapshot,
                remote_heads={"feature-1": B_SHA, "feature-2": "2" * 40},
                pull_requests={101: OPEN_PR_101, 102: OPEN_PR_102},
            )

    def test_reconcile_rejects_supplied_published_local_head_disagreement(
        self,
    ) -> None:
        snapshot = parse_native_stack(VIEW_OPEN, trunk_head=A_SHA)

        with self.assertRaisesRegex(
            NativeStackError,
            "layer feature-1 local head mismatch: native 1111111111111111111111111111111111111111; local bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ):
            reconcile_native_stack(
                snapshot,
                local_heads={"feature-1": B_SHA},
                remote_heads={"feature-1": "1" * 40, "feature-2": "2" * 40},
                pull_requests={101: OPEN_PR_101, 102: OPEN_PR_102},
            )

    def test_reconcile_rejects_exact_github_base_and_state_disagreement(self) -> None:
        snapshot = parse_native_stack(VIEW_OPEN, trunk_head=A_SHA)
        wrong_base = PullRequestRecord(
            **{**OPEN_PR_102.__dict__, "base_branch": "main"}
        )
        with self.assertRaisesRegex(
            NativeStackError,
            "layer feature-2 GitHub PR #102 base mismatch: native predecessor feature-1; GitHub main",
        ):
            reconcile_native_stack(
                snapshot,
                remote_heads={"feature-1": "1" * 40, "feature-2": "2" * 40},
                pull_requests={101: OPEN_PR_101, 102: wrong_base},
            )

        wrong_state = PullRequestRecord(**{**OPEN_PR_102.__dict__, "state": "CLOSED"})
        with self.assertRaisesRegex(
            NativeStackError,
            "layer feature-2 GitHub PR #102 state mismatch: native OPEN; GitHub CLOSED",
        ):
            reconcile_native_stack(
                snapshot,
                remote_heads={"feature-1": "1" * 40, "feature-2": "2" * 40},
                pull_requests={101: OPEN_PR_101, 102: wrong_state},
            )

    def test_reconcile_retains_merged_historical_predecessor_base(self) -> None:
        payload = copy.deepcopy(VIEW_OPEN)
        for layer in payload["branches"]:
            layer["isMerged"] = True
            layer["pr"]["state"] = "MERGED"
        snapshot = parse_native_stack(payload, trunk_head=A_SHA)
        merged_prs = {
            101: PullRequestRecord(**{**OPEN_PR_101.__dict__, "state": "MERGED"}),
            102: PullRequestRecord(**{**OPEN_PR_102.__dict__, "state": "MERGED"}),
        }

        reconciled = reconcile_native_stack(
            snapshot,
            remote_heads={},
            pull_requests=merged_prs,
        )

        self.assertEqual(snapshot, reconciled)

    def test_reconcile_accepts_merged_pr_retargeted_to_trunk(self) -> None:
        payload = copy.deepcopy(VIEW_OPEN)
        payload["branches"][1]["base"] = C_SHA
        for layer in payload["branches"]:
            layer["isMerged"] = True
            layer["pr"]["state"] = "MERGED"
        snapshot = parse_native_stack(payload, trunk_head=A_SHA)
        merged_prs = {
            101: PullRequestRecord(**{**OPEN_PR_101.__dict__, "state": "MERGED"}),
            102: PullRequestRecord(
                **{
                    **OPEN_PR_102.__dict__,
                    "base_branch": "main",
                    "state": "MERGED",
                }
            ),
        }

        reconciled = reconcile_native_stack(
            snapshot,
            remote_heads={},
            pull_requests=merged_prs,
        )

        self.assertEqual(snapshot, reconciled)

    def test_reconcile_materialized_layer_uses_local_not_remote_head(self) -> None:
        materialized = NativeStackSnapshot(
            trunk_branch="main",
            trunk_head=A_SHA,
            current_branch="feature-one",
            layers=(
                NativeLayer(
                    branch="feature-one",
                    head=B_SHA,
                    base=A_SHA,
                    merged=False,
                    queued=False,
                    needs_rebase=False,
                    pull_request=None,
                ),
            ),
        )

        reconciled = reconcile_native_stack(
            materialized,
            local_heads={"feature-one": B_SHA},
            remote_heads={},
            pull_requests={},
        )

        self.assertEqual(materialized, reconciled)

    def test_reconcile_rejects_materialized_local_head_disagreement(self) -> None:
        materialized = NativeStackSnapshot(
            trunk_branch="main",
            trunk_head=A_SHA,
            current_branch="feature-one",
            layers=(
                NativeLayer(
                    branch="feature-one",
                    head=B_SHA,
                    base=A_SHA,
                    merged=False,
                    queued=False,
                    needs_rebase=False,
                    pull_request=None,
                ),
            ),
        )

        with self.assertRaisesRegex(
            NativeStackError,
            "layer feature-one local head mismatch",
        ):
            reconcile_native_stack(
                materialized,
                local_heads={"feature-one": C_SHA},
                remote_heads={},
                pull_requests={},
            )

    def test_truth_phases_are_distinct_from_terminal_states(self) -> None:
        self.assertEqual(
            TruthPhase.PROPOSED,
            classify_truth_phase(plan_validated=True, snapshot=None, reconciled=False),
        )
        materialized = NativeStackSnapshot(
            trunk_branch="main",
            trunk_head=A_SHA,
            current_branch="feature-one",
            layers=(
                NativeLayer(
                    branch="feature-one",
                    head=B_SHA,
                    base=A_SHA,
                    merged=False,
                    queued=False,
                    needs_rebase=False,
                    pull_request=None,
                ),
            ),
        )
        self.assertEqual(
            TruthPhase.MATERIALIZED,
            classify_truth_phase(
                plan_validated=True, snapshot=materialized, reconciled=False
            ),
        )

        published = parse_native_stack(VIEW_OPEN, trunk_head=A_SHA)
        self.assertEqual(
            TruthPhase.PUBLISHED,
            classify_truth_phase(
                plan_validated=True, snapshot=published, reconciled=True
            ),
        )

        merged = NativeStackSnapshot(
            trunk_branch="main",
            trunk_head=C_SHA,
            current_branch="feature-one",
            layers=(
                NativeLayer(
                    branch="feature-one",
                    head=B_SHA,
                    base=A_SHA,
                    merged=True,
                    queued=False,
                    needs_rebase=False,
                    pull_request=NativePullRequest(
                        number=101,
                        url="https://github.com/acme/widgets/pull/101",
                        state="MERGED",
                    ),
                ),
            ),
        )
        self.assertEqual(
            TruthPhase.MERGED,
            classify_truth_phase(plan_validated=True, snapshot=merged, reconciled=True),
        )
        self.assertNotEqual(TruthPhase.MERGED.value, TerminalState.ALL_MERGED)


if __name__ == "__main__":
    unittest.main()
