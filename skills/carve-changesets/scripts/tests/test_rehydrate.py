from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import helpers
from metadata import (
    ChangesetMetadata,
    SourceIdentity,
    embed_pr_metadata,
    stamp_commit_message,
)
from rehydrate import (
    ChangesetRecord,
    PullRequestRecord,
    RehydrationError,
    _validate_recovery_transition,
    rehydrate_chain,
)
from status import status_from_live


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

    def test_rehydrates_full_chain_after_local_state_is_deleted(self) -> None:
        heads, prs = self._materialize()
        state_dir = self.repo / ".carve-changesets"
        state_dir.mkdir()
        (state_dir / "plan.json").write_text("{}\n")
        shutil.rmtree(state_dir)
        clone = self._fresh_clone()

        chain = rehydrate_chain(
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

    def test_rehydrates_v1_metadata_through_selected_non_origin_remote(self) -> None:
        _, prs = self._materialize(indices=(1,))
        clone = self._fresh_clone()
        helpers.run(clone, "git", "remote", "add", "upstream", str(self.bare))
        helpers.run(clone, "git", "fetch", "upstream")

        chain = rehydrate_chain(
            source_branch="feature/report",
            pull_requests=prs,
            cwd=clone,
            remote="upstream",
            prefer_remote=True,
        )

        self.assertEqual("upstream", chain.source_lineage[0].remote)
        self.assertEqual(
            chain.changesets[0].metadata,
            chain.changesets[0].pr_metadata,
        )

    def test_rehydrates_v2_metadata_through_selected_non_origin_remote(self) -> None:
        heads, prs = self._materialize(indices=(1,))
        successor = SourceIdentity("feature/report-corrected", "c" * 40)
        recovered = ChangesetMetadata(
            slug="part-1",
            index=1,
            source_branch=successor.branch,
            source_sha=successor.sha,
            source_lineage=(
                SourceIdentity("feature/report", self.source_sha),
                successor,
            ),
            recovery_from_head=heads[1],
        )
        helpers.run(self.repo, "git", "checkout", "feature/report-1")
        helpers.run(
            self.repo,
            "git",
            "commit",
            "--amend",
            "-F",
            "-",
            input_text=stamp_commit_message("feat: changeset 1", recovered),
        )
        recovered_head = helpers.run(self.repo, "git", "rev-parse", "HEAD")
        helpers.run(
            self.repo,
            "git",
            "push",
            "--force-with-lease",
            "origin",
            "feature/report-1",
        )
        prs[0] = PullRequestRecord(
            **{
                **prs[0].__dict__,
                "head_sha": recovered_head,
                "body": embed_pr_metadata(prs[0].body, recovered),
            }
        )
        clone = self._fresh_clone()
        helpers.run(clone, "git", "remote", "add", "upstream", str(self.bare))
        helpers.run(clone, "git", "fetch", "upstream")

        chain = rehydrate_chain(
            source_branch="feature/report",
            pull_requests=prs,
            cwd=clone,
            remote="upstream",
            prefer_remote=True,
        )

        self.assertEqual(
            ("upstream", "upstream"),
            tuple(identity.remote for identity in chain.source_lineage),
        )
        self.assertEqual(
            chain.changesets[0].metadata,
            chain.changesets[0].pr_metadata,
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

        chain = rehydrate_chain(
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

        chain = rehydrate_chain(
            source_branch="feature/report", pull_requests=prs, cwd=clone
        )

        self.assertEqual(1, len(chain.changesets))
        self.assertEqual(heads[1], chain.changesets[0].head)
        self.assertEqual(1, chain.changesets[0].metadata.index)

    def test_status_is_rendered_from_rehydration_without_local_files(self) -> None:
        _, prs = self._materialize()
        clone = self._fresh_clone()
        output = status_from_live(
            source_branch="feature/report", pull_requests=prs, cwd=clone
        )

        self.assertIn("feature/report-1", output)
        self.assertIn("#101", output)
        self.assertIn("MERGED", output)
        self.assertIn("feature/report-2", output)
        self.assertIn("OPEN", output)

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
            rehydrate_chain(
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
            rehydrate_chain(
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
            rehydrate_chain(
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
            rehydrate_chain(
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
            rehydrate_chain(
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

        chain = rehydrate_chain(
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
            rehydrate_chain(
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
            rehydrate_chain(
                source_branch="feature/report", pull_requests=prs, cwd=clone
            )


if __name__ == "__main__":
    unittest.main()
