"""Load-bearing contract invariants for docs/cognitive-shaping-doctrine.md.

Checks stable identifiers in the doctrine's own normative text, not phrasing.
The document is repository-wide rather than skill-scoped, so its own tests live
here rather than inside any one skill's test suite, exactly as
`test_skill_authoring_doc.py` does for the authoring standard. Its distribution
is repository-wide for the same reason: a consuming skill bundles the doctrine
so it stays self-contained when installed, and the drift check that keeps every
bundled copy honest belongs beside the canonical text rather than inside one
consumer.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from helpers import compact, sync_block_skills  # noqa: E402

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOCTRINE = REPOSITORY_ROOT / "docs" / "cognitive-shaping-doctrine.md"

# Skills that load the doctrine rather than restating it. Each bundles the
# canonical text so it still resolves when the skill is installed outside this
# repository, exactly as `review-suite/` is bundled today.
BUNDLING_SKILLS = ("review-solution-simplicity", "carve-changesets", "ready-ticket")
BUNDLED_NAME = "cognitive-shaping-doctrine.md"

# The one consumer that also restates part of the doctrine inside its own
# `SKILL.md`, because its forward eval hands the model that file alone and
# never loads a reference alongside it.
RESTATING_SKILL = "ready-ticket"

# The sentences that restatement carries word for word. Equality can bind only
# these; see the test below for what it deliberately leaves unbound.
RESTATED_VERBATIM = (
    "unit of work is correctly shaped when a reviewer can construct an accurate"
    " mental model of the change and evaluate it independently",
    "Committed eval results, generated fixtures, and lockfiles are part of the"
    " change and part of nothing anyone reads.",
    "A change carrying 177 reviewable lines and 4,538 lines of recorded eval"
    " results is a 177-line change.",
)

# The doctrine is compris's own claim. It names no upstream project, because
# there is no external owner to attribute and a citation would imply one.
FOREIGN_SOURCES = ("atelier",)

MENTAL_MODEL_STANDARD = compact(
    """
    A unit of work is correctly shaped when a reviewer can construct an
    accurate mental model of the change and evaluate it independently.
    """
)

# All eight. The doctrine must account for every one; dropping any is how a
# rule set quietly becomes a summary of itself.
BREAKDOWN_RULES = (
    "Keep an initiative executable as one ticket when it is already reviewable",
    "Never decompose to a single child",
    "Separate unrelated concern domains",
    "Prefer additive foundations before disruptive transitions",
    "Separate mechanical restructuring from behavioral change when that helps review",
    "Keep validation with the behavior it proves",
    "Identify re-split triggers before implementation",
    "Create follow-up work when implementation or review reveals new scope",
)

# What the criterion forbids is a *gate*, not a number. The doctrine carries
# calibration figures on purpose — an unanchored "can a reviewer understand
# it?" collapses to always-yes — so these patterns match enforcement, the
# bound and the verb that would make a figure pass/fail.
NUMERIC_GATE_PATTERNS = (
    r"(?:at most|no more than|fewer than|up to|must not exceed|may not exceed"
    r"|a maximum of|a limit of)"
    r"\s+[\d,]+\s+(?:new or changed |changed |added )?lines",
    r"[\d,]+[- ]line (?:limit|cap|threshold|maximum|budget|target)",
    r"(?:reject|refuse|block|fail|gate)\w*\s+(?:\w+\s+){0,3}"
    r"(?:over|above|beyond|exceeding)\s+[\d,]+",
)

# The calibration figures only stay non-binding while the document says so.
NON_GATE_DISCLAIMERS = (
    "Line counts inform that judgment. They never decide it.",
    "calibration, not a gate",
)


class CognitiveShapingDoctrineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = compact(DOCTRINE.read_text())

    def test_the_doctrine_identifies_compris_as_its_owner(self):
        self.assertIn("This is compris's doctrine of cognitive shaping", self.doc)

    def test_the_doctrine_attributes_itself_to_no_outside_project(self):
        for foreign in FOREIGN_SOURCES:
            with self.subTest(source=foreign):
                self.assertNotIn(foreign, self.doc.lower())

    def test_the_doctrine_states_the_mental_model_standard(self):
        self.assertIn(MENTAL_MODEL_STANDARD, self.doc)

    def test_every_breakdown_rule_is_accounted_for(self):
        for rule in BREAKDOWN_RULES:
            with self.subTest(rule=rule):
                self.assertIn(rule, self.doc)

    def test_the_logical_to_realized_vocabulary_is_recorded(self):
        self.assertIn("A leaf ticket is a child of an epic", self.doc)
        for mapping in ("| initiative | epic |", "| changeset | pull request |"):
            with self.subTest(mapping=mapping):
                self.assertIn(mapping, self.doc)

    def test_enforcement_is_policy_controlled_and_separate_from_judgment(self):
        self.assertIn("Shape is always judged", self.doc)
        self.assertIn(
            "Whether the judgment gates anything is the consuming project's decision",
            self.doc,
        )

    def test_mid_stream_correction_is_optional_while_planning_always_shapes(self):
        self.assertIn("Planning always aims at a shaped plan", self.doc)
        self.assertIn(
            "Correcting that prediction once implementation is under way is not"
            " required",
            self.doc,
        )
        self.assertIn("available and never automatic", self.doc)

    def test_recorded_machine_generated_evidence_is_excluded_from_judgment(self):
        self.assertIn("Recorded machine-generated evidence", self.doc)
        self.assertIn("is excluded", self.doc)
        self.assertIn("eval results", self.doc)

    def test_no_numeric_line_count_gate_is_presented_as_correctness_policy(self):
        for pattern in NUMERIC_GATE_PATTERNS:
            with self.subTest(pattern=pattern):
                self.assertIsNone(
                    re.search(pattern, self.doc, flags=re.IGNORECASE),
                    f"doctrine states a numeric size gate matching {pattern!r}",
                )

    def test_the_calibration_figures_are_marked_non_binding(self):
        for disclaimer in NON_GATE_DISCLAIMERS:
            with self.subTest(disclaimer=disclaimer):
                self.assertIn(disclaimer, self.doc)

    def test_every_consuming_skill_bundles_an_identical_doctrine(self):
        canonical = DOCTRINE.read_bytes()
        for skill in BUNDLING_SKILLS:
            bundled = REPOSITORY_ROOT / "skills" / skill / "references" / BUNDLED_NAME
            with self.subTest(skill=skill):
                self.assertTrue(
                    bundled.exists(),
                    f"{bundled} is missing; run `just sync-contracts`",
                )
                self.assertEqual(
                    canonical,
                    bundled.read_bytes(),
                    f"{bundled} drifted from {DOCTRINE}; run `just sync-contracts`",
                )

    def test_the_inline_restatement_stays_verbatim_with_the_doctrine(self):
        """`ready-ticket` restates breakdown rules inside its own `SKILL.md`,
        and nothing else binds those sentences to this document. Its forward
        eval hands the model `SKILL.md` alone, so the rules have to be present
        there; the bundled copy under `references/` is never loaded into that
        payload and so cannot carry them. Without this check, editing the
        canonical text leaves that skill stating a superseded rule with every
        suite still green.

        Three sentences are carried word for word and are bound here: the
        mental-model standard, and the two sentences of the recorded-evidence
        exclusion — the committed-artifacts sentence and its 177-line /
        4,538-line example.

        The rest of the restatement is paraphrase and cannot be bound the same
        way. `SKILL.md` says "A parent holding one child represents nothing its
        child does not already represent, and costs a level of indirection to
        say so" where the doctrine says "it costs"; it compresses "Keep an
        initiative executable as one ticket when it is already reviewable" into
        "An initiative already reviewable as one changeset stays one ticket";
        and it folds four more rules into running prose in the subsections
        below. String equality would report every one of those as drift on the
        day it was written, so it binds what is genuinely verbatim and leaves
        the paraphrase to that skill's own contract test.
        """
        skill = compact(
            (REPOSITORY_ROOT / "skills" / RESTATING_SKILL / "SKILL.md").read_text()
        )
        for sentence in RESTATED_VERBATIM:
            with self.subTest(sentence=sentence):
                self.assertIn(
                    sentence,
                    self.doc,
                    f"{DOCTRINE} no longer states this sentence, which"
                    f" skills/{RESTATING_SKILL}/SKILL.md restates verbatim;"
                    " update both together or drop it from RESTATED_VERBATIM",
                )
                self.assertIn(
                    sentence,
                    skill,
                    f"skills/{RESTATING_SKILL}/SKILL.md drifted from"
                    f" {DOCTRINE} on this sentence",
                )

    def test_the_sync_recipe_copies_the_doctrine_to_exactly_these_skills(self):
        """The failure above tells a reader to run `just sync-contracts`; that
        recipe has to refresh exactly these copies, or the advice is a dead end,
        and a skill dropped from it keeps a stale copy nothing else checks.

        `helpers.sync_block_skills` scopes the read to the block that copies
        this doctrine and states why equality rather than membership is what
        makes the check real.
        """
        self.assertEqual(sync_block_skills(f"docs/{BUNDLED_NAME}"), BUNDLING_SKILLS)

    def test_the_packaging_check_requires_the_same_bundle_set(self):
        """The third statement of this list is `validate_plugins.py`'s own, and
        it was bound to nothing: a skill added here and omitted there shipped a
        package with a dangling citation that no check reported."""
        spec = importlib.util.spec_from_file_location(
            "validate_plugins", REPOSITORY_ROOT / "scripts" / "validate_plugins.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertEqual(module.DOCTRINE_NAME, BUNDLED_NAME)
        self.assertEqual(module.DOCTRINE_BUNDLING_SKILLS, set(BUNDLING_SKILLS))

    def test_the_doctrine_carries_no_link_a_bundle_cannot_resolve(self):
        """A bundled skill ships the doctrine alone. A repository-relative link
        resolves in `docs/` and dangles everywhere the doctrine is consumed."""
        text = DOCTRINE.read_text()
        targets = re.findall(r"\]\(([^)#][^)]*)\)", text)
        targets += re.findall(r"^\[[^\]]+\]:\s*(\S+)", text, re.M)
        for target in targets:
            with self.subTest(target=target):
                self.assertTrue(
                    target.startswith(("http://", "https://")),
                    f"the doctrine links to {target}, which a bundled copy"
                    " does not ship",
                )


if __name__ == "__main__":
    unittest.main()
