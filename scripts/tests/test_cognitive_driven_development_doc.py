"""Contract invariants for the shaping-authority decision in the design record.

`docs/cognitive-driven-development.md` left the shaping authority's mechanism
contested and told the reader Spec B "should not be built until that
alternative is argued down or adopted." These tests hold the recorded decision
that closes it: one selected mechanism, a stated reason for every rejected
alternative, an explicit answer to the `review-suite` sync/drift counterexample,
and a disposition for every downstream leaf.

The Markdown is canonical and the HTML is a presentation copy of the same
content, so every load-bearing claim is asserted against **both**. That is what
makes their equivalence checkable: the two files are worded and structured
differently by design, so only the stable claims can be compared, and those are
exactly the ones a reader would be misled by if they drifted.

Repository-wide rather than skill-scoped, so these live here alongside
`test_cognitive_shaping_doctrine.py` rather than inside any one skill.
"""

from __future__ import annotations

import html as html_module
import re
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from helpers import compact  # noqa: E402

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DESIGN_MARKDOWN = REPOSITORY_ROOT / "docs" / "cognitive-driven-development.md"
DESIGN_HTML = REPOSITORY_ROOT / "docs" / "cognitive-driven-development.html"

# The wording that told a reader the mechanism was still open. Its absence is
# what "no longer unresolved" means; leaving it in place beside a recorded
# decision would leave the document contradicting itself. Matched in lower case
# because the two copies carry these phrases in headings, kickers and prose.
UNRESOLVED_MARKERS = (
    "the contest is unresolved",
    "should not be built until",
    "not yet ruled out",
    "gated on the bundled-contract alternative",
)

# Exactly one mechanism is selected, and it is named in one sentence rather
# than left for a reader to infer from tone.
SELECTED_MECHANISM = compact(
    """
    The selected mechanism is the bundled synced contract: canonical doctrine
    text, distributed by stable path and mechanically drift-checked, with no new
    skill.
    """
)

# Every alternative the design left live, and the evidence-based reason it was
# rejected or adopted. A decision that names its choice without disposing of
# the alternatives is a preference, not a decision.
ALTERNATIVE_DISPOSITIONS = (
    compact(
        """
        Rejected: an executable shaping verdict. No caller has demonstrated it
        needs a verdict rather than a contract.
        """
    ),
    compact(
        """
        Rejected: shape as a fourth review lens. It answers a question no caller
        is asking, at the one moment the answer cannot be acted on.
        """
    ),
    compact(
        """
        Not ruled on: build only the missing edge. It varies Spec C's planner
        rather than Spec B's authority, and Spec C stays independent of this
        decision.
        """
    ),
    compact(
        """
        Adopted alongside: the telemetry-first ordering. It is the instrument
        that would make a later executable verdict an evidence-driven choice
        rather than a second convergence.
        """
    ),
)

# The counterexample the ticket requires an explicit answer to. Both halves
# matter: that the mechanism is real, and what it demarcates. Written without
# code markup, since both copies have theirs stripped before comparison.
COUNTEREXAMPLE_CLAIMS = (
    compact(
        """
        The counterexample holds. review-suite/ distributes canonical normative
        text that just sync-contracts bundles verbatim into each consumer and a
        bundled-contract test drift-checks under just test, with no skill
        involved.
        """
    ),
    compact(
        """
        In review-suite/ the synced text carries the contract and the skills
        carry the verdict.
        """
    ),
)

# The evidence that decides it, and the one thing that keeps this decision
# reversible rather than final.
DECIDING_EVIDENCE = compact(
    """
    The publication size gate already runs the contract mechanism: it loads
    carve-changesets by stable name, reads its live guardrails, and is
    forbidden to substitute local heuristics. That is text loaded by stable
    name and judged in place, and it has not failed.
    """
)

REVERSIBILITY = compact(
    """
    This decision is reversible on evidence rather than on argument.
    """
)

# Every downstream Spec B leaf, named together with the disposition it carries.
# `superseded`, `re-cut` and `activated` are the closed vocabulary; a leaf
# missing from this table is a leaf whose owner cannot tell whether to build it.
# Each phrase pairs the leaf with its verdict, so adjacency is asserted rather
# than inferred — a bare leaf number would not do, since #192, #193 and #194 are
# each mentioned again outside the table.
DOWNSTREAM_DISPOSITIONS = (
    "#190 — seam-based shaping corpus and evaluator superseded",
    "#191 — the typed, read-only shaping skill superseded",
    "#192 — carve-changesets shape delegation re-cut",
    "#193 — implement-ticket publication-size gate re-cut",
    "#194 — predicted shape and actual outcome activated",
    "#195 — reviewability and operator-effort telemetry activated",
)

# The stable name the activated and re-cut work builds against. Without it the
# disposition says what to do and not what to do it against.
STABLE_CONTRACT_NAME = "docs/cognitive-shaping-doctrine.md"


def strip_html(markup: str) -> str:
    """Reduce the presentation copy to the prose a reader actually sees.

    Each tag becomes a space, since dropping it outright would weld the words
    on either side together. That leaves a space before any punctuation that
    followed a tag — `<code>just test</code>,` — which the rendered page does
    not show, so it is closed again here.
    """
    without_style = re.sub(
        r"<style\b.*?</style>", " ", markup, flags=re.DOTALL | re.IGNORECASE
    )
    without_comments = re.sub(r"<!--.*?-->", " ", without_style, flags=re.DOTALL)
    spaced = html_module.unescape(re.sub(r"<[^>]+>", " ", without_comments))
    return re.sub(r"\s+([,.;:!?])", r"\1", spaced)


def strip_markdown(source: str) -> str:
    """Reduce the canonical copy to the same prose, dropping its own markup.

    Emphasis and table pipes are Markdown's counterpart of the tags stripped
    from the presentation copy. Removing both is what lets one claim be
    asserted against two files that are deliberately formatted differently.
    """
    without_emphasis = re.sub(r"\*{1,2}|`", "", source)
    return without_emphasis.replace("|", " ")


class ShapingAuthorityDecisionTests(unittest.TestCase):
    """Assert the decision against both copies, one claim at a time."""

    @classmethod
    def setUpClass(cls):
        cls.copies = {
            "markdown": compact(strip_markdown(DESIGN_MARKDOWN.read_text())),
            "html": compact(strip_html(DESIGN_HTML.read_text())),
        }

    def assert_in_both(self, claim: str):
        for copy_name, text in self.copies.items():
            with self.subTest(copy=copy_name):
                self.assertIn(claim, text)

    def test_the_mechanism_is_no_longer_presented_as_unresolved(self):
        for marker in UNRESOLVED_MARKERS:
            for copy_name, text in self.copies.items():
                with self.subTest(copy=copy_name, marker=marker):
                    self.assertNotIn(marker, text.lower())

    def test_one_selected_mechanism_is_named(self):
        self.assert_in_both(SELECTED_MECHANISM)

    def test_every_live_alternative_is_disposed_of_with_a_reason(self):
        for disposition in ALTERNATIVE_DISPOSITIONS:
            with self.subTest(disposition=disposition[:48]):
                self.assert_in_both(disposition)

    def test_the_review_suite_counterexample_is_answered_explicitly(self):
        for claim in COUNTEREXAMPLE_CLAIMS:
            with self.subTest(claim=claim[:48]):
                self.assert_in_both(claim)

    def test_the_deciding_evidence_and_its_reversibility_are_recorded(self):
        self.assert_in_both(DECIDING_EVIDENCE)
        self.assert_in_both(REVERSIBILITY)

    def test_every_downstream_leaf_carries_a_disposition(self):
        for disposition in DOWNSTREAM_DISPOSITIONS:
            with self.subTest(leaf=disposition[:4]):
                self.assert_in_both(disposition)

    def test_the_activated_work_names_its_stable_contract(self):
        self.assert_in_both(STABLE_CONTRACT_NAME)


if __name__ == "__main__":
    unittest.main()
