from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import helpers  # noqa: E402
from metadata import (  # noqa: E402
    ChangesetMetadata,
    embed_pr_metadata,
    stamp_commit_message,
)
from native_stack import (  # noqa: E402
    NativeLayer,
    NativePullRequest,
    NativeStackSnapshot,
)
from rehydrate import PullRequestRecord, RehydrationError, rehydrate_chain  # noqa: E402


class NativeRehydrationTransitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.repo, self.bare, self.source_sha = helpers.init_repo(self.temp_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def _native_stack(
        self,
    ) -> tuple[NativeStackSnapshot, list[PullRequestRecord], Path]:
        trunk_head = helpers.run(self.repo, "git", "rev-parse", "main")
        layers: list[NativeLayer] = []
        pull_requests: list[PullRequestRecord] = []
        predecessor_branch = "main"
        predecessor_head = trunk_head
        for offset, (branch, historical_index) in enumerate(
            (("layers/zeta", 9), ("layers/alpha", 3)), start=1
        ):
            helpers.run(self.repo, "git", "checkout", "-b", branch, predecessor_branch)
            path = f"native-{offset}.txt"
            (self.repo / path).write_text(f"native layer {offset}\n")
            helpers.run(self.repo, "git", "add", path)
            metadata = ChangesetMetadata(
                slug=f"native-{offset}",
                index=historical_index,
                source_branch="feature/report",
                source_sha=self.source_sha,
            )
            head = helpers.commit(
                self.repo,
                stamp_commit_message(f"feat: native layer {offset}", metadata),
            )
            helpers.run(self.repo, "git", "push", "-u", "origin", branch)
            number = 200 + offset
            layers.append(
                NativeLayer(
                    branch=branch,
                    head=head,
                    base=predecessor_head,
                    merged=False,
                    queued=False,
                    needs_rebase=False,
                    pull_request=NativePullRequest(
                        number=number,
                        url=f"https://github.com/acme/widgets/pull/{number}",
                        state="OPEN",
                    ),
                )
            )
            pull_requests.append(
                PullRequestRecord(
                    number=number,
                    head_branch=branch,
                    head_sha=head,
                    base_branch=predecessor_branch,
                    state="OPEN",
                    body=embed_pr_metadata("Native layer\n", metadata),
                )
            )
            predecessor_branch = branch
            predecessor_head = head
        clone = self.temp_dir / "fresh"
        helpers.run(self.temp_dir, "git", "clone", str(self.bare), str(clone))
        helpers.run(clone, "git", "fetch", "--prune", "origin")
        return (
            NativeStackSnapshot(
                trunk_branch="main",
                trunk_head=trunk_head,
                current_branch=layers[-1].branch,
                layers=tuple(layers),
            ),
            pull_requests,
            clone,
        )

    def test_native_order_outranks_branch_suffixes_and_historical_indices(self) -> None:
        snapshot, pull_requests, clone = self._native_stack()

        chain = rehydrate_chain(
            source_branch="feature/report",
            remote="origin",
            native_snapshot=snapshot,
            pull_requests=pull_requests,
            cwd=clone,
        )

        self.assertEqual(
            ["layers/zeta", "layers/alpha"],
            [item.branch for item in chain.changesets],
        )
        self.assertEqual([9, 3], [item.metadata.index for item in chain.changesets])

    def test_materialized_suffix_restarts_at_trunk_after_merged_prefix(self) -> None:
        original, pull_requests, clone = self._native_stack()
        merged = replace(
            original.layers[0],
            merged=True,
            pull_request=replace(original.layers[0].pull_request, state="MERGED"),
        )
        materialized = replace(original.layers[1], pull_request=None)
        snapshot = NativeStackSnapshot(
            trunk_branch=original.trunk_branch,
            trunk_head=merged.head,
            current_branch=materialized.branch,
            layers=(merged, materialized),
        )

        chain = rehydrate_chain(
            source_branch="feature/report",
            remote="origin",
            native_snapshot=snapshot,
            pull_requests=(replace(pull_requests[0], state="MERGED"),),
            cwd=clone,
        )

        self.assertEqual(
            ["main", "main"],
            [item.base for item in chain.changesets],
        )

    def test_ordinary_rehydration_requires_native_truth(self) -> None:
        with self.assertRaisesRegex(RehydrationError, "native snapshot is required"):
            rehydrate_chain(
                source_branch="feature/report",
                remote="origin",
                base_branch="main",
                cwd=self.repo,
            )

    def test_legacy_native_layers_normalize_through_the_selected_remote(self) -> None:
        snapshot, pull_requests, clone = self._native_stack()
        helpers.run(clone, "git", "remote", "add", "upstream", str(self.bare))
        helpers.run(clone, "git", "fetch", "upstream")

        chain = rehydrate_chain(
            source_branch="feature/report",
            remote="upstream",
            native_snapshot=snapshot,
            pull_requests=pull_requests,
            cwd=clone,
        )

        self.assertEqual(
            ("upstream",),
            tuple(identity.remote for identity in chain.source_lineage),
        )


if __name__ == "__main__":
    unittest.main()
