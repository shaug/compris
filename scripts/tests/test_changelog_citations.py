"""Every commit SHA `CHANGELOG.md` cites has to still name a reachable commit.

The changelog's backfill convention is the only machine-checkable link from a
narrative entry to the history that produced it, and its failure mode is
silent: a citation that resolves to nothing reads exactly like one that
resolves, so nobody discovers the rot until they try to follow it.

The rot this module was written for arrived through squash-merges: `main` was
squash-merged for most of this file's history, so a pull request contributing
several entries collapsed to one commit and every authoring SHA those entries
had backfilled was discarded at once — which is how 68 of the 248 citations
came to point at nothing. Squash merging is off now, and a merge commit
preserves the authoring commits it carries, so a landed authoring commit is
itself the SHA its entry cites. `AGENTS.md` requires a backfilled SHA to name
the commit that carried the entry onto `main`, and this module is what holds
the file to it.

When the guard fires depends on which mechanism invalidated the SHA. The check
is `git rev-list HEAD` membership, so a citation backfilled before its branch
was submitted reddens on that same branch: submitting rebases onto `main`
first, and a rebased `HEAD` no longer reaches the commit it replaced. It is the
squash-merged history behind that where the check is inherently late — those
citations stayed reachable on their own branch and died only at the merge, so
nothing turned red until the first change made after they had landed.
`AGENTS.md` closes the window from the other side by requiring a SHA to be
backfilled only once its entry has landed.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = REPOSITORY_ROOT / "CHANGELOG.md"

# The backfill citation, in both forms the file uses: `(<sha>)` in newer
# entries and ``(`<sha>`)`` in older ones. A backticked SHA *outside*
# parentheses is deliberately not a citation — the changelog uses that form to
# pin a peer repository's commit, which names history in another repository and
# is not expected to resolve here.
CITATION = re.compile(r"\((`?)([0-9a-f]{40})\1\)")


def _git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(REPOSITORY_ROOT), *arguments),
        capture_output=True,
        text=True,
    )


def _citations() -> list[tuple[str, str, int, str]]:
    """Return (sha, form, line number, entry title) for every citation."""
    lines = CHANGELOG.read_text().split("\n")
    found = []
    for index, line in enumerate(lines):
        for match in CITATION.finditer(line):
            entry = index
            while entry >= 0 and not lines[entry].startswith("- "):
                entry -= 1
            title = lines[entry][2:].strip() if entry >= 0 else "(no entry)"
            form = "backtick" if match.group(1) else "bare"
            found.append((match.group(2), form, index + 1, title))
    return found


class ChangelogCitationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.citations = _citations()

    def test_both_citation_forms_are_recognized(self) -> None:
        # A pattern covering only one of the two forms would leave every
        # citation in the other silently unchecked, which is the failure this
        # module exists to prevent rather than reproduce.
        forms = {form for _, form, _, _ in self.citations}
        self.assertEqual(forms, {"bare", "backtick"})

    def test_every_cited_commit_is_reachable_from_head(self) -> None:
        if _git("rev-parse", "--git-dir").returncode != 0:
            self.skipTest("not a git repository, so no history to check against")
        if _git("rev-parse", "--is-shallow-repository").stdout.strip() == "true":
            self.fail(
                "history is shallow, so an unreachable citation cannot be told "
                "apart from an unfetched one; run `git fetch --unshallow`"
            )

        history = _git("rev-list", "HEAD")
        self.assertEqual(history.returncode, 0, history.stderr)
        reachable = set(history.stdout.split())

        dangling = [
            (sha, line, title)
            for sha, _, line, title in self.citations
            if sha not in reachable
        ]
        self.assertEqual(
            dangling,
            [],
            "CHANGELOG.md cites commits that are not reachable from HEAD:\n"
            + "\n".join(
                f"  CHANGELOG.md:{line}  {sha}\n    {title[:72]}"
                for sha, line, title in dangling
            )
            + "\n\nA backfilled SHA names the commit that carried the entry onto "
            "`main`\n(see AGENTS.md). A SHA taken before the branch was rebased "
            "and landed\nnames a commit no ref reaches. If the entry has landed, "
            "recover its\nlanding commit with:\n"
            "  git log main --format='%H %s' -S'<the entry's first line>' -- "
            "CHANGELOG.md\nand take the last line, which is the commit that "
            "introduced that entry.\nIf it has not landed, that command returns "
            "nothing, because the entry is\nnot on `main` yet: drop the SHA and "
            "backfill it once the entry lands.",
        )


if __name__ == "__main__":
    unittest.main()
