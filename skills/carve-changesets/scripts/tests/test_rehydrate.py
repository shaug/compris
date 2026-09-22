from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import cli as cli_mod  # noqa: E402
import helpers  # noqa: E402
from gh_stack import (  # noqa: E402
    GhStackProfile,
    GhStackProfileBlocker,
    ProfileProbeResult,
    StackCapability,
)
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
from rehydrate import (  # noqa: E402
    ChangesetRecord,
    PullRequestRecord,
    RehydrationError,
    _validate_recovery_transition,
    adopt_legacy_chain,
    rehydrate_chain,
)
from status import _live_remote_heads, status_from_live  # noqa: E402


class RehydrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())
        self.repo, self.bare, self.source_sha = helpers.init_repo(self.temp_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir)

    def _materialize(
        self, indices: tuple[int, ...] = (1, 2)
    ) -> tuple[dict[int, str], list[PullRequestRecord]]:
        heads: dict[int, str] = {}
        prs: list[PullRequestRecord] = []
        previous = "main"
        for index in indices:
            branch = f"feature/report-{index}"
            helpers.run(self.repo, "git", "checkout", "-b", branch, previous)
            (self.repo / f"changeset-{index}.txt").write_text(f"changeset {index}\n")
            helpers.run(self.repo, "git", "add", f"changeset-{index}.txt")
            metadata = ChangesetMetadata(
                slug=f"part-{index}",
                index=index,
                source_branch="feature/report",
                source_sha=self.source_sha,
            )
            heads[index] = helpers.commit(
                self.repo,
                stamp_commit_message(f"feat: changeset {index}", metadata),
            )
            helpers.run(self.repo, "git", "push", "-u", "origin", branch)
            base = "main" if index == 1 else f"feature/report-{index - 1}"
            prs.append(
                PullRequestRecord(
                    number=100 + index,
                    head_branch=branch,
                    head_sha=heads[index],
                    base_branch=base,
                    state="MERGED" if index == 1 else "OPEN",
                    body=embed_pr_metadata(
                        f"## Overall Feature\n\nReport API\n\n## This Changeset ({index} of 2)\n",
                        metadata,
                    ),
                )
            )
            previous = branch
        return heads, prs

    def _fresh_clone(self) -> Path:
        clone = self.temp_dir / "fresh"
        helpers.run(self.temp_dir, "git", "clone", str(self.bare), str(clone))
        helpers.run(clone, "git", "fetch", "--prune", "origin")
        return clone

    @staticmethod
    def _supported_profile_probe() -> ProfileProbeResult:
        return ProfileProbeResult(
            status="supported",
            observed_version="gh stack version reviewed",
            observed_surfaces=(),
            profile=GhStackProfile(
                version="gh stack version reviewed",
                source_revision="reviewed",
                capabilities=frozenset({StackCapability.VIEW_JSON}),
            ),
            blocker=None,
        )

    def _materialize_named_native_stack(
        self,
    ) -> tuple[NativeStackSnapshot, list[PullRequestRecord]]:
        trunk_head = helpers.run(self.repo, "git", "rev-parse", "main")
        layers: list[NativeLayer] = []
        prs: list[PullRequestRecord] = []
        predecessor_branch = "main"
        predecessor_head = trunk_head
        for offset, (branch, legacy_index) in enumerate(
            (("layers/zeta", 9), ("layers/alpha", 3)), start=1
        ):
            helpers.run(self.repo, "git", "checkout", "-b", branch, predecessor_branch)
            path = f"native-{offset}.txt"
            (self.repo / path).write_text(f"native layer {offset}\n")
            helpers.run(self.repo, "git", "add", path)
            metadata = ChangesetMetadata(
                slug=f"native-{offset}",
                index=legacy_index,
                source_branch="feature/report",
                source_sha=self.source_sha,
            )
            head = helpers.commit(
                self.repo,
                stamp_commit_message(f"feat: native layer {offset}", metadata),
            )
            helpers.run(self.repo, "git", "push", "-u", "origin", branch)
            pr_number = 200 + offset
            pr = NativePullRequest(
                number=pr_number,
                url=f"https://github.com/acme/widgets/pull/{pr_number}",
                state="OPEN",
            )
            layers.append(
                NativeLayer(
                    branch=branch,
                    head=head,
                    base=predecessor_head,
                    merged=False,
                    queued=False,
                    needs_rebase=False,
                    pull_request=pr,
                )
            )
            prs.append(
                PullRequestRecord(
                    number=pr_number,
                    head_branch=branch,
                    head_sha=head,
                    base_branch=predecessor_branch,
                    state="OPEN",
                    body=embed_pr_metadata("Native layer\n", metadata),
                )
            )
            predecessor_branch = branch
            predecessor_head = head
        return (
            NativeStackSnapshot(
                trunk_branch="main",
                trunk_head=trunk_head,
                current_branch=layers[-1].branch,
                layers=tuple(layers),
            ),
            prs,
        )

    def test_rehydrates_full_chain_after_local_state_is_deleted(self) -> None:
        heads, prs = self._materialize()
        state_dir = self.repo / ".carve-changesets"
        state_dir.mkdir()
        (state_dir / "plan.json").write_text("{}\n")
        shutil.rmtree(state_dir)
        clone = self._fresh_clone()

        chain = adopt_legacy_chain(
            source_branch="feature/report", pull_requests=prs, cwd=clone
        )

        self.assertEqual("main", chain.base_branch)
        self.assertEqual(self.source_sha, chain.source_sha)
        self.assertEqual(
            ["part-1", "part-2"], [item.metadata.slug for item in chain.changesets]
        )
        self.assertEqual([heads[1], heads[2]], [item.head for item in chain.changesets])
        self.assertEqual([101, 102], [item.pr_number for item in chain.changesets])
        self.assertEqual(
            ["main", "feature/report-1"], [item.base for item in chain.changesets]
        )

    def test_edited_pr_prose_rehydrates_from_unchanged_metadata_block(self) -> None:
        _, prs = self._materialize()
        clone = self._fresh_clone()
        edited = [
            PullRequestRecord(
                **{
                    **pr.__dict__,
                    "body": (
                        "Reviewer-authored context.\n\n"
                        + pr.body.replace(
                            "Report API", "Improved report API explanation"
                        )
                    ),
                }
            )
            for pr in prs
        ]

        chain = adopt_legacy_chain(
            source_branch="feature/report", pull_requests=edited, cwd=clone
        )

        self.assertEqual([101, 102], [item.pr_number for item in chain.changesets])
        self.assertEqual(
            ["part-1", "part-2"], [item.metadata.slug for item in chain.changesets]
        )

    def test_contiguous_partial_chain_rehydrates_without_inventing_later_items(
        self,
    ) -> None:
        heads, prs = self._materialize(indices=(1,))
        clone = self._fresh_clone()

        chain = adopt_legacy_chain(
            source_branch="feature/report", pull_requests=prs, cwd=clone
        )

        self.assertEqual(1, len(chain.changesets))
        self.assertEqual(heads[1], chain.changesets[0].head)
        self.assertEqual(1, chain.changesets[0].metadata.index)

    def test_native_rehydration_uses_snapshot_order_not_suffixes_or_indices(
        self,
    ) -> None:
        snapshot, prs = self._materialize_named_native_stack()
        clone = self._fresh_clone()

        chain = rehydrate_chain(
            source_branch="feature/report",
            native_snapshot=snapshot,
            pull_requests=prs,
            cwd=clone,
        )

        self.assertEqual(
            ["layers/zeta", "layers/alpha"],
            [item.branch for item in chain.changesets],
        )
        self.assertEqual([9, 3], [item.metadata.index for item in chain.changesets])

    def test_ordinary_rehydration_requires_a_native_snapshot(self) -> None:
        self._materialize()

        with self.assertRaisesRegex(RehydrationError, "native snapshot is required"):
            rehydrate_chain(
                source_branch="feature/report",
                base_branch="main",
                cwd=self._fresh_clone(),
            )

    def test_status_without_refresh_authority_never_invokes_native_view(self) -> None:
        _, prs = self._materialize()
        clone = self._fresh_clone()
        client = mock.Mock()
        output = status_from_live(
            source_branch="feature/report",
            pull_requests=prs,
            cwd=clone,
            stack_client=client,
        )

        self.assertIn("NATIVE LOCAL TOPOLOGY  unavailable", output)
        self.assertIn("feature/report-1", output)
        self.assertIn("#101", output)
        self.assertIn("MERGED", output)
        self.assertIn("feature/report-2", output)
        self.assertIn("OPEN", output)
        client.view_json.assert_not_called()

    def test_status_with_refresh_authority_reconciles_native_topology(self) -> None:
        snapshot, prs = self._materialize_named_native_stack()
        clone = self._fresh_clone()
        payload = {
            "trunk": snapshot.trunk_branch,
            "currentBranch": snapshot.current_branch,
            "branches": [
                {
                    "name": layer.branch,
                    "head": layer.head,
                    "base": layer.base,
                    "isCurrent": layer.branch == snapshot.current_branch,
                    "isMerged": layer.merged,
                    "isQueued": layer.queued,
                    "needsRebase": layer.needs_rebase,
                    "pr": {
                        "number": layer.pull_request.number,
                        "url": layer.pull_request.url,
                        "state": layer.pull_request.state,
                    },
                }
                for layer in snapshot.layers
                if layer.pull_request is not None
            ],
        }
        client = mock.Mock()
        client.view_json.return_value = payload

        output = status_from_live(
            source_branch="feature/report",
            pull_requests=prs,
            cwd=clone,
            allow_stack_state_refresh=True,
            stack_client=client,
            profile_probe=self._supported_profile_probe,
        )

        self.assertIn("NATIVE LOCAL TOPOLOGY  available", output)
        self.assertLess(output.index("layers/zeta"), output.index("layers/alpha"))
        client.view_json.assert_called_once_with(allow_state_refresh=True)

    def test_status_refresh_loads_exact_native_pr_numbers(self) -> None:
        snapshot, prs = self._materialize_named_native_stack()
        clone = self._fresh_clone()
        payload = {
            "trunk": snapshot.trunk_branch,
            "currentBranch": snapshot.current_branch,
            "branches": [
                {
                    "name": layer.branch,
                    "head": layer.head,
                    "base": layer.base,
                    "isCurrent": layer.branch == snapshot.current_branch,
                    "isMerged": layer.merged,
                    "isQueued": layer.queued,
                    "needsRebase": layer.needs_rebase,
                    "pr": {
                        "number": layer.pull_request.number,
                        "url": layer.pull_request.url,
                        "state": layer.pull_request.state,
                    },
                }
                for layer in snapshot.layers
                if layer.pull_request is not None
            ],
        }
        client = mock.Mock()
        client.view_json.return_value = payload
        records = {pr.number: pr for pr in prs}
        loader = mock.Mock(side_effect=records.__getitem__)

        output = status_from_live(
            source_branch="feature/report",
            pull_request_loader=loader,
            cwd=clone,
            allow_stack_state_refresh=True,
            stack_client=client,
            profile_probe=self._supported_profile_probe,
        )

        self.assertIn("layers/zeta", output)
        self.assertEqual([mock.call(201), mock.call(202)], loader.call_args_list)

    def test_status_cli_defers_pr_discovery_to_exact_native_numbers(self) -> None:
        args = Namespace(
            source="feature/report",
            base="main",
            local_only=False,
            remote="origin",
            allow_stack_state_refresh=True,
        )
        record = mock.sentinel.record
        with (
            mock.patch.object(cli_mod, "pull_requests_for_source") as suffix_discovery,
            mock.patch.object(
                cli_mod, "pull_request_by_number", return_value=record
            ) as exact_lookup,
            mock.patch.object(cli_mod, "status_from_live", return_value="ok") as status,
            redirect_stdout(StringIO()),
        ):
            cli_mod.cmd_status(args)

            loader = status.call_args.kwargs["pull_request_loader"]
            self.assertEqual(record, loader(321))

        suffix_discovery.assert_not_called()
        exact_lookup.assert_called_once_with(321, remote="origin")

    def test_live_remote_heads_ignore_stale_tracking_refs(self) -> None:
        snapshot, _ = self._materialize_named_native_stack()
        clone = self._fresh_clone()
        branch = snapshot.layers[-1].branch
        cached = helpers.run(clone, "git", "rev-parse", f"refs/remotes/origin/{branch}")
        helpers.run(self.repo, "git", "checkout", branch)
        (self.repo / "advanced.txt").write_text("advanced\n")
        helpers.run(self.repo, "git", "add", "advanced.txt")
        advanced = helpers.commit(self.repo, "test: advance published layer")
        helpers.run(self.repo, "git", "push", "origin", branch)

        heads = _live_remote_heads(clone, "origin", (branch,))

        self.assertNotEqual(cached, advanced)
        self.assertEqual(advanced, heads[branch])

    def test_status_refresh_rejects_checkout_movement(self) -> None:
        snapshot, prs = self._materialize_named_native_stack()
        clone = self._fresh_clone()

        def move_checkout(*, allow_state_refresh: bool) -> dict[str, object]:
            self.assertTrue(allow_state_refresh)
            helpers.run(clone, "git", "checkout", "--detach", snapshot.layers[0].head)
            return {}

        client = mock.Mock()
        client.view_json.side_effect = move_checkout

        with self.assertRaisesRegex(RehydrationError, "moved the checkout"):
            status_from_live(
                source_branch="feature/report",
                pull_requests=prs,
                cwd=clone,
                allow_stack_state_refresh=True,
                stack_client=client,
                profile_probe=self._supported_profile_probe,
            )

    def test_status_refresh_blocks_unsupported_profile_before_view(self) -> None:
        clone = self._fresh_clone()
        client = mock.Mock()
        blocker = GhStackProfileBlocker(
            reason="unknown_version",
            observed_version="gh stack version unknown",
            observed_surfaces=(),
            mismatched_surfaces=(),
        )
        probe = mock.Mock(
            return_value=ProfileProbeResult(
                status="blocked",
                observed_version=blocker.observed_version,
                observed_surfaces=(),
                profile=None,
                blocker=blocker,
            )
        )

        with self.assertRaisesRegex(RehydrationError, "unknown_version"):
            status_from_live(
                source_branch="feature/report",
                cwd=clone,
                allow_stack_state_refresh=True,
                stack_client=client,
                profile_probe=probe,
            )

        probe.assert_called_once_with()
        client.view_json.assert_not_called()

    def test_status_refresh_rejects_requested_base_disagreement(self) -> None:
        snapshot, prs = self._materialize_named_native_stack()
        clone = self._fresh_clone()
        payload = {
            "trunk": snapshot.trunk_branch,
            "currentBranch": snapshot.current_branch,
            "branches": [
                {
                    "name": layer.branch,
                    "head": layer.head,
                    "base": layer.base,
                    "isCurrent": layer.branch == snapshot.current_branch,
                    "isMerged": layer.merged,
                    "isQueued": layer.queued,
                    "needsRebase": layer.needs_rebase,
                    "pr": {
                        "number": layer.pull_request.number,
                        "url": layer.pull_request.url,
                        "state": layer.pull_request.state,
                    },
                }
                for layer in snapshot.layers
                if layer.pull_request is not None
            ],
        }
        client = mock.Mock()
        client.view_json.return_value = payload

        with self.assertRaisesRegex(
            RehydrationError,
            "Requested base 'release'.*native trunk 'main'",
        ):
            status_from_live(
                source_branch="feature/report",
                base_branch="release",
                pull_requests=prs,
                cwd=clone,
                allow_stack_state_refresh=True,
                stack_client=client,
                profile_probe=self._supported_profile_probe,
            )

    def test_trailers_survive_propagation_rebase(self) -> None:
        _, _ = self._materialize()
        helpers.run(self.repo, "git", "checkout", "feature/report-1")
        (self.repo / "upstream.txt").write_text("upstream\n")
        helpers.run(self.repo, "git", "add", "upstream.txt")
        helpers.commit(self.repo, "feat: update first changeset")
        helpers.run(self.repo, "git", "checkout", "feature/report-2")
        helpers.run(self.repo, "git", "rebase", "feature/report-1")
        message = helpers.run(self.repo, "git", "show", "-s", "--format=%B", "HEAD")

        from metadata import parse_commit_message

        parsed = parse_commit_message(message)
        self.assertEqual(2, parsed.index)
        self.assertEqual("part-2", parsed.slug)
        self.assertEqual(self.source_sha, parsed.source_sha)

    def test_partial_chain_with_an_index_gap_fails_closed(self) -> None:
        self._materialize(indices=(1, 3))
        clone = self._fresh_clone()

        with self.assertRaisesRegex(RehydrationError, "missing index 2"):
            adopt_legacy_chain(
                source_branch="feature/report", base_branch="main", cwd=clone
            )

    def test_missing_required_commit_trailers_fail_closed(self) -> None:
        helpers.run(self.repo, "git", "checkout", "-b", "feature/report-1", "main")
        (self.repo / "plain.txt").write_text("plain\n")
        helpers.run(self.repo, "git", "add", "plain.txt")
        helpers.commit(self.repo, "feat: no trailers")
        helpers.run(self.repo, "git", "push", "-u", "origin", "feature/report-1")
        clone = self._fresh_clone()

        with self.assertRaisesRegex(
            RehydrationError, "Missing required changeset trailer"
        ):
            adopt_legacy_chain(
                source_branch="feature/report", base_branch="main", cwd=clone
            )

    def test_conflicting_pr_base_fails_closed(self) -> None:
        _, prs = self._materialize()
        clone = self._fresh_clone()
        conflicting = [
            PullRequestRecord(**{**prs[0].__dict__, "state": "OPEN"}),
            PullRequestRecord(**{**prs[1].__dict__, "base_branch": "main"}),
        ]

        with self.assertRaisesRegex(RehydrationError, "conflicts with allowed base"):
            adopt_legacy_chain(
                source_branch="feature/report", pull_requests=conflicting, cwd=clone
            )

    def test_trailer_and_pr_metadata_disagreement_fails_closed(self) -> None:
        _, prs = self._materialize()
        clone = self._fresh_clone()
        wrong = ChangesetMetadata("wrong", 2, "feature/report", self.source_sha)
        conflicting = [
            prs[0],
            PullRequestRecord(
                **{**prs[1].__dict__, "body": embed_pr_metadata(prs[1].body, wrong)}
            ),
        ]

        with self.assertRaisesRegex(RehydrationError, "metadata disagrees"):
            adopt_legacy_chain(
                source_branch="feature/report", pull_requests=conflicting, cwd=clone
            )

    def test_cross_repository_changeset_pr_fails_closed(self) -> None:
        _, prs = self._materialize()
        clone = self._fresh_clone()
        forked = [
            PullRequestRecord(**{**prs[0].__dict__, "is_cross_repository": True}),
            prs[1],
        ]

        with self.assertRaisesRegex(RehydrationError, "uses a fork head"):
            adopt_legacy_chain(
                source_branch="feature/report", pull_requests=forked, cwd=clone
            )

    def test_rehydrates_merged_v1_prefix_and_recovered_v2_suffix(self) -> None:
        heads, prs = self._materialize()
        successor = SourceIdentity("feature/report-corrected", "c" * 40)
        recovered = ChangesetMetadata(
            slug="part-2",
            index=2,
            source_branch=successor.branch,
            source_sha=successor.sha,
            source_lineage=(
                SourceIdentity("feature/report", self.source_sha),
                successor,
            ),
            recovery_from_head=heads[2],
        )
        helpers.run(self.repo, "git", "checkout", "feature/report-2")
        helpers.run(
            self.repo,
            "git",
            "commit",
            "--amend",
            "-F",
            "-",
            input_text=stamp_commit_message("feat: changeset 2", recovered),
        )
        recovered_head = helpers.run(self.repo, "git", "rev-parse", "HEAD")
        helpers.run(
            self.repo,
            "git",
            "push",
            "--force-with-lease",
            "origin",
            "feature/report-2",
        )
        prs[1] = PullRequestRecord(
            **{
                **prs[1].__dict__,
                "head_sha": recovered_head,
                "body": embed_pr_metadata(prs[1].body, recovered),
            }
        )
        clone = self._fresh_clone()

        chain = adopt_legacy_chain(
            source_branch="feature/report", pull_requests=prs, cwd=clone
        )

        self.assertEqual(self.source_sha, chain.root_source_sha)
        self.assertEqual(successor.sha, chain.source_sha)
        self.assertEqual(
            ("feature/report", "feature/report-corrected"),
            tuple(identity.branch for identity in chain.source_lineage),
        )

    def test_recovery_rejects_conflicting_v2_pr_provenance(self) -> None:
        heads, prs = self._materialize()
        successor = SourceIdentity("feature/report-corrected", "c" * 40)
        lineage = (SourceIdentity("feature/report", self.source_sha), successor)
        recovered = ChangesetMetadata(
            "part-2",
            2,
            successor.branch,
            successor.sha,
            lineage,
            heads[2],
        )
        conflicting = ChangesetMetadata(
            "part-2",
            2,
            successor.branch,
            successor.sha,
            lineage,
            "d" * 40,
        )
        helpers.run(self.repo, "git", "checkout", "feature/report-2")
        helpers.run(
            self.repo,
            "git",
            "commit",
            "--amend",
            "-F",
            "-",
            input_text=stamp_commit_message("feat: changeset 2", recovered),
        )
        recovered_head = helpers.run(self.repo, "git", "rev-parse", "HEAD")
        helpers.run(
            self.repo,
            "git",
            "push",
            "--force-with-lease",
            "origin",
            "feature/report-2",
        )
        prs[1] = PullRequestRecord(
            **{
                **prs[1].__dict__,
                "head_sha": recovered_head,
                "body": embed_pr_metadata(prs[1].body, conflicting),
            }
        )

        with self.assertRaisesRegex(
            RehydrationError, "conflicting recovered provenance"
        ):
            adopt_legacy_chain(
                source_branch="feature/report",
                pull_requests=prs,
                cwd=self._fresh_clone(),
                recovery_successor=successor,
            )

    def test_recovery_rejects_a_recovered_head_after_an_old_suffix_head(self) -> None:
        root = SourceIdentity("feature/report", self.source_sha)
        successor = SourceIdentity("feature/report-corrected", "c" * 40)
        first = ChangesetMetadata("part-1", 1, root.branch, root.sha)
        second = ChangesetMetadata("part-2", 2, root.branch, root.sha)
        third = ChangesetMetadata(
            "part-3",
            3,
            successor.branch,
            successor.sha,
            (root, successor),
            "3" * 40,
        )
        records = (
            ChangesetRecord(first, "feature/report-1", "1" * 40, "main", 1, "MERGED"),
            ChangesetRecord(
                second,
                "feature/report-2",
                "2" * 40,
                "feature/report-1",
                2,
                "OPEN",
            ),
            ChangesetRecord(
                third,
                "feature/report-3",
                "4" * 40,
                "feature/report-2",
                3,
                "OPEN",
            ),
        )

        with self.assertRaisesRegex(RehydrationError, "leading prefix"):
            _validate_recovery_transition(records, successor)

    def test_rejects_discontinuous_successor_lineage(self) -> None:
        heads, prs = self._materialize()
        lineage = (
            SourceIdentity("feature/report", self.source_sha),
            SourceIdentity("feature/skipped", "b" * 40),
            SourceIdentity("feature/report-corrected", "c" * 40),
        )
        invalid = ChangesetMetadata(
            "part-2",
            2,
            lineage[-1].branch,
            lineage[-1].sha,
            lineage,
            heads[2],
        )
        helpers.run(self.repo, "git", "checkout", "feature/report-2")
        helpers.run(
            self.repo,
            "git",
            "commit",
            "--amend",
            "-F",
            "-",
            input_text=stamp_commit_message("feat: changeset 2", invalid),
        )
        invalid_head = helpers.run(self.repo, "git", "rev-parse", "HEAD")
        helpers.run(
            self.repo,
            "git",
            "push",
            "--force-with-lease",
            "origin",
            "feature/report-2",
        )
        prs[1] = PullRequestRecord(
            **{
                **prs[1].__dict__,
                "head_sha": invalid_head,
                "body": embed_pr_metadata(prs[1].body, invalid),
            }
        )
        clone = self._fresh_clone()

        with self.assertRaisesRegex(RehydrationError, "discontinuous"):
            adopt_legacy_chain(
                source_branch="feature/report", pull_requests=prs, cwd=clone
            )


if __name__ == "__main__":
    unittest.main()
