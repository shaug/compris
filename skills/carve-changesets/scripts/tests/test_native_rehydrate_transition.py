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
    SourceIdentity,
    embed_pr_metadata,
    stamp_commit_message,
)
from native_stack import (  # noqa: E402
    NativeLayer,
    NativePullRequest,
    NativeStackSnapshot,
)
from rehydrate import PullRequestRecord, RehydrationError, rehydrate_chain  # noqa: E402
from validate import validate_live_chain  # noqa: E402


class NativeRehydrationTransitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.repo, self.bare, self.source_sha = helpers.init_repo(self.temp_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def _native_stack(
        self,
    ) -> tuple[NativeStackSnapshot, list[PullRequestRecord], Path]:
        helpers.run(self.repo, "git", "checkout", "feature/report")
        (self.repo / "native-2.txt").write_text("native layer 2\n")
        helpers.run(self.repo, "git", "add", "native-2.txt")
        self.source_sha = helpers.commit(self.repo, "complete native source")
        helpers.run(self.repo, "git", "push", "origin", "feature/report")
        trunk_head = helpers.run(self.repo, "git", "rev-parse", "main")
        layers: list[NativeLayer] = []
        pull_requests: list[PullRequestRecord] = []
        predecessor_branch = "main"
        predecessor_head = trunk_head
        for offset, (branch, historical_index, path) in enumerate(
            (
                ("layers/zeta", 9, "source.txt"),
                ("layers/alpha", 3, "native-2.txt"),
            ),
            start=1,
        ):
            helpers.run(self.repo, "git", "checkout", "-b", branch, predecessor_branch)
            content = helpers.run(self.repo, "git", "show", f"feature/report:{path}")
            (self.repo / path).write_text(content + "\n")
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

    def _completed_successor_stack(
        self,
        *,
        forged_downstream_predecessor: bool = False,
        prepend_unavailable_rewrite_event: bool = False,
        substitute_first_twin_predecessor: bool = False,
        substitute_twin_predecessor: bool = False,
    ) -> tuple[NativeStackSnapshot, list[PullRequestRecord]]:
        original, pull_requests, _ = self._native_stack()
        root = SourceIdentity("feature/report", self.source_sha)
        successor = SourceIdentity("feature/report-corrected", "c" * 40)
        old_first, old_second = (layer.head for layer in original.layers)
        first_recovery_head = old_first
        second_recovery_head = old_second
        if substitute_first_twin_predecessor:
            first_tree = helpers.run(
                self.repo, "git", "rev-parse", f"{old_first}^{{tree}}"
            )
            first_parents = helpers.run(
                self.repo, "git", "show", "-s", "--format=%P", old_first
            ).split()
            first_message = helpers.run(
                self.repo, "git", "show", "-s", "--format=%B", old_first
            )
            twin_args = [
                "git",
                "-c",
                "user.name=Twin Author",
                "-c",
                "user.email=twin@example.test",
                "commit-tree",
                first_tree,
            ]
            for parent in first_parents:
                twin_args.extend(("-p", parent))
            first_recovery_head = helpers.run(
                self.repo,
                *twin_args,
                input_text=first_message,
            )
            self.assertNotEqual(old_first, first_recovery_head)
            second_tree = helpers.run(
                self.repo, "git", "rev-parse", f"{old_second}^{{tree}}"
            )
            second_message = helpers.run(
                self.repo, "git", "show", "-s", "--format=%B", old_second
            )
            second_recovery_head = helpers.run(
                self.repo,
                "git",
                "commit-tree",
                second_tree,
                "-p",
                first_recovery_head,
                input_text=second_message,
            )
        if substitute_twin_predecessor:
            first_tree = helpers.run(
                self.repo, "git", "rev-parse", f"{old_first}^{{tree}}"
            )
            first_parents = helpers.run(
                self.repo, "git", "show", "-s", "--format=%P", old_first
            ).split()
            first_message = helpers.run(
                self.repo, "git", "show", "-s", "--format=%B", old_first
            )
            twin_args = [
                "git",
                "-c",
                "user.name=Twin Author",
                "-c",
                "user.email=twin@example.test",
                "commit-tree",
                first_tree,
            ]
            for parent in first_parents:
                twin_args.extend(("-p", parent))
            twin_first = helpers.run(
                self.repo,
                *twin_args,
                input_text=first_message,
            )
            self.assertNotEqual(old_first, twin_first)
            second_tree = helpers.run(
                self.repo, "git", "rev-parse", f"{old_second}^{{tree}}"
            )
            second_message = helpers.run(
                self.repo, "git", "show", "-s", "--format=%B", old_second
            )
            second_recovery_head = helpers.run(
                self.repo,
                "git",
                "commit-tree",
                second_tree,
                "-p",
                twin_first,
                input_text=second_message,
            )

        first_metadata = ChangesetMetadata(
            slug="native-1",
            source_lineage=(root, successor),
            recovery_from_head=first_recovery_head,
        )
        helpers.run(self.repo, "git", "checkout", original.layers[0].branch)
        helpers.run(
            self.repo,
            "git",
            "commit",
            "--amend",
            "-F",
            "-",
            input_text=stamp_commit_message("feat: native layer 1", first_metadata),
        )
        new_first = helpers.run(self.repo, "git", "rev-parse", "HEAD")

        helpers.run(
            self.repo,
            "git",
            "rebase",
            "--onto",
            new_first,
            old_first,
            original.layers[1].branch,
        )
        second_metadata = ChangesetMetadata(
            slug="native-2",
            source_lineage=(root, successor),
            recovery_from_head=(
                old_first if forged_downstream_predecessor else second_recovery_head
            ),
        )
        helpers.run(
            self.repo,
            "git",
            "commit",
            "--amend",
            "-F",
            "-",
            input_text=stamp_commit_message("feat: native layer 2", second_metadata),
        )
        new_second = helpers.run(self.repo, "git", "rev-parse", "HEAD")

        layers = (
            replace(original.layers[0], head=new_first),
            replace(original.layers[1], head=new_second, base=new_first),
        )
        recovered_prs = [
            replace(
                pull_requests[0],
                head_sha=new_first,
                body=embed_pr_metadata(pull_requests[0].body, first_metadata),
                head_rewrite_edges=(
                    *(
                        ((old_first, "f" * 40),)
                        if prepend_unavailable_rewrite_event
                        else ()
                    ),
                    (old_first, new_first),
                ),
            ),
            replace(
                pull_requests[1],
                head_sha=new_second,
                body=embed_pr_metadata(pull_requests[1].body, second_metadata),
                head_rewrite_edges=((old_second, new_second),),
            ),
        ]
        return (
            replace(
                original,
                current_branch=layers[-1].branch,
                layers=layers,
            ),
            recovered_prs,
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

        result = validate_live_chain(chain, cwd=clone)

        self.assertTrue(result.valid, result.diagnostics)

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

    def test_completed_successor_allows_a_rebased_downstream_parent(self) -> None:
        snapshot, pull_requests = self._completed_successor_stack()

        chain = rehydrate_chain(
            source_branch="feature/report",
            remote="origin",
            native_snapshot=snapshot,
            pull_requests=pull_requests,
            cwd=self.repo,
        )

        self.assertEqual(snapshot.layers[-1].head, chain.changesets[-1].head)
        self.assertEqual(
            ("feature/report", "feature/report-corrected"),
            tuple(identity.branch for identity in chain.source_lineage),
        )

    def test_completed_successor_rejects_a_forged_downstream_predecessor(
        self,
    ) -> None:
        snapshot, pull_requests = self._completed_successor_stack(
            forged_downstream_predecessor=True
        )

        with self.assertRaisesRegex(RehydrationError, "exact pre-recovery head"):
            rehydrate_chain(
                source_branch="feature/report",
                remote="origin",
                native_snapshot=snapshot,
                pull_requests=pull_requests,
                cwd=self.repo,
            )

    def test_completed_successor_rejects_a_twin_historical_predecessor(self) -> None:
        snapshot, pull_requests = self._completed_successor_stack(
            substitute_twin_predecessor=True
        )

        with self.assertRaisesRegex(RehydrationError, "exact pre-recovery head"):
            rehydrate_chain(
                source_branch="feature/report",
                remote="origin",
                native_snapshot=snapshot,
                pull_requests=pull_requests,
                cwd=self.repo,
            )

    def test_completed_successor_rejects_a_twin_first_predecessor(self) -> None:
        snapshot, pull_requests = self._completed_successor_stack(
            substitute_first_twin_predecessor=True
        )

        with self.assertRaisesRegex(RehydrationError, "exact pre-recovery head"):
            rehydrate_chain(
                source_branch="feature/report",
                remote="origin",
                native_snapshot=snapshot,
                pull_requests=pull_requests,
                cwd=self.repo,
            )

    def test_completed_successor_rejects_an_unavailable_earlier_rewrite(
        self,
    ) -> None:
        snapshot, pull_requests = self._completed_successor_stack(
            prepend_unavailable_rewrite_event=True
        )

        with self.assertRaisesRegex(RehydrationError, "exact pre-recovery head"):
            rehydrate_chain(
                source_branch="feature/report",
                remote="origin",
                native_snapshot=snapshot,
                pull_requests=pull_requests,
                cwd=self.repo,
            )

    def test_completed_successor_allows_retired_marker_text_in_human_prose(
        self,
    ) -> None:
        snapshot, pull_requests = self._completed_successor_stack()
        prose = "This changeset removes carve-changesets:metadata blocks.\n"
        pull_requests = [replace(pr, body=prose) for pr in pull_requests]

        chain = rehydrate_chain(
            source_branch="feature/report",
            remote="origin",
            native_snapshot=snapshot,
            pull_requests=pull_requests,
            cwd=self.repo,
        )

        self.assertEqual(snapshot.layers[-1].head, chain.changesets[-1].head)


if __name__ == "__main__":
    unittest.main()
