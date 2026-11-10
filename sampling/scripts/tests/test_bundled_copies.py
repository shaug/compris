"""Both standalone executors ship the canonical policy and run its guards."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
from sampling_helpers import ROOT  # noqa: E402

BUNDLING_SKILLS = ("implement-ticket", "plan-implementation")


class BundledSamplingCoreTests(unittest.TestCase):
    def test_every_consumer_bundles_the_exact_canonical_policy(self):
        canonical = ROOT / "sampling/core.py"
        for skill in BUNDLING_SKILLS:
            bundled = ROOT / "skills" / skill / "scripts/evals/sampling_core.py"
            with self.subTest(skill=skill):
                self.assertTrue(
                    bundled.exists(), f"{bundled} missing; run just sync-contracts"
                )
                self.assertEqual(
                    canonical.read_bytes(),
                    bundled.read_bytes(),
                    f"{bundled} drifted; run just sync-contracts",
                )

    def test_the_sync_recipe_copies_into_exactly_the_two_skill_distributions(self):
        recipe = (ROOT / "justfile").read_text()
        blocks = [
            skills
            for skills, body in re.findall(
                r"@for skill in (.+?); do(.*?)\n  done", recipe, re.S
            )
            if "cp sampling/core.py" in body
        ]
        self.assertEqual(
            len(blocks), 1, msg="expected exactly one sampling/core.py sync block"
        )
        self.assertEqual(
            tuple(blocks[0].split()),
            BUNDLING_SKILLS,
            msg="sampling/core.py sync block must name its two distributions",
        )

    def test_local_and_ci_test_commands_include_the_sampling_suite(self):
        for path in ("justfile", ".github/workflows/ci.yml"):
            text = (ROOT / path).read_text()
            loops = re.findall(r"for tests in ([^;]+); do", text)
            with self.subTest(path=path):
                self.assertTrue(
                    any("sampling/scripts/tests" in loop.split() for loop in loops)
                )


if __name__ == "__main__":
    unittest.main()
