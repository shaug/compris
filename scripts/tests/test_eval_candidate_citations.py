"""Every subtree an eval summary cites has to still name reachable content.

A summary's `candidate.trees` is the only machine-checkable link from a
recorded measurement to the content it measured, and its failure mode is
silent: a subtree hash that resolves to nothing reads exactly like one that
resolves, so nobody discovers the rot until they try to follow it.

The check is reachability from `HEAD`, and under subtree identity it is
well-defined at every point in a change's life. A summary recorded on an open
branch names a subtree of that branch's own history, rebase included, because
a rebase that leaves the skill alone leaves its subtree alone. So this module
needs no unlanded-branch exemption, unlike its changelog sibling.

It turns red in two cases, and both are real. A pull request carrying eval
evidence was squash-merged, which keeps one tree per pull request and discards
the intermediate states eval evidence measures by construction — `AGENTS.md`
requires such a pull request to merge as a merge commit for exactly this
reason. Or a rebase resolved conflicts inside the skill directory, in which
case the recorded run measured content that never shipped and the answer is to
re-record.
"""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SUMMARIES = sorted(REPOSITORY_ROOT.glob("skills/*/evals/results/*.json"))


def _git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(REPOSITORY_ROOT), *arguments),
        capture_output=True,
        text=True,
    )


def _citations() -> list[tuple[str, str, str]]:
    """Return (summary path, repository path, subtree hash) for every citation.

    A summary carrying no `trees` is not a failure. Those predate the field
    and could not have their identity derived from a commit that still
    resolves; `AGENTS.md` records them as branch-local and unresolvable.
    """

    found = []
    for summary in SUMMARIES:
        recorded = json.loads(summary.read_text(encoding="utf-8"))
        trees = (recorded.get("candidate") or {}).get("trees") or {}
        for path, digest in sorted(trees.items()):
            found.append((str(summary.relative_to(REPOSITORY_ROOT)), path, digest))
    return found


def _reachable_subtrees(path: str) -> set[str]:
    """Every hash `path` has had across the commits reachable from `HEAD`."""

    commits = _git("rev-list", "HEAD").stdout.split()
    request = "".join(f"{commit}:{path}\n" for commit in commits)
    listed = subprocess.run(
        (
            "git",
            "-C",
            str(REPOSITORY_ROOT),
            "cat-file",
            "--batch-check=%(objectname) %(objecttype)",
        ),
        input=request,
        capture_output=True,
        text=True,
    ).stdout
    return {line.split()[0] for line in listed.splitlines() if line.endswith("tree")}


class EvalCandidateCitationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.citations = _citations()

    def test_some_summary_cites_a_subtree(self) -> None:
        # Without this, deleting the field from every summary — or writing it
        # under a key this module does not read — would turn the reachability
        # check green by emptying it, which is the failure this module exists
        # to prevent rather than reproduce.
        self.assertTrue(
            self.citations,
            "no summary under skills/*/evals/results/ carries "
            "candidate.trees, so the reachability check below is vacuous",
        )

    def test_every_cited_subtree_is_reachable_from_head(self) -> None:
        if _git("rev-parse", "--git-dir").returncode != 0:
            self.skipTest("not a git repository, so no history to check against")
        if _git("rev-parse", "--is-shallow-repository").stdout.strip() == "true":
            self.fail(
                "history is shallow, so an unreachable subtree cannot be told "
                "apart from an unfetched one; run `git fetch --unshallow`"
            )

        reachable: dict[str, set[str]] = {}
        dangling = []
        for summary, path, digest in self.citations:
            if path not in reachable:
                reachable[path] = _reachable_subtrees(path)
            if digest not in reachable[path]:
                dangling.append((summary, path, digest))

        self.assertEqual(
            dangling,
            [],
            "eval summaries cite subtrees that are not reachable from HEAD:\n"
            + "\n".join(
                f"  {summary}\n    {path} @ {digest}"
                for summary, path, digest in dangling
            )
            + "\n\nA recorded subtree stays resolvable only while the commit "
            "carrying it does\n(see AGENTS.md). A pull request touching "
            "skills/*/evals/results/ merges as a\nmerge commit rather than a "
            "squash for this reason. If one was squashed, the\nmeasured "
            "content is gone and the remedy is to re-record against a state "
            "that\nstill exists, saying in the summary that the original is "
            "unrecoverable.",
        )


if __name__ == "__main__":
    unittest.main()
