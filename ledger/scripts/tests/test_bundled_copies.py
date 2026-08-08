"""Verify each skill's bundled `ledger_core.py` matches the canonical source.

Mirrors `review-suite/scripts/tests/test_bundled_contracts.py`'s drift check
for the same reason: `just sync-contracts` refreshes every copy, but nothing
else catches a copy that has silently fallen behind `ledger/core.py`.
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CANONICAL = REPOSITORY_ROOT / "ledger" / "core.py"
BUNDLING_SKILLS = ("implement-epic", "carve-changesets", "babysit-pr")


class BundledLedgerCoreTests(unittest.TestCase):
    def test_every_skill_bundles_an_identical_ledger_core(self) -> None:
        canonical_bytes = CANONICAL.read_bytes()
        for skill in BUNDLING_SKILLS:
            bundled = REPOSITORY_ROOT / "skills" / skill / "scripts" / "ledger_core.py"
            with self.subTest(skill=skill):
                self.assertTrue(
                    bundled.exists(), f"{bundled} is missing; run `just sync-contracts`"
                )
                self.assertEqual(
                    canonical_bytes,
                    bundled.read_bytes(),
                    f"{bundled} drifted from {CANONICAL}; run `just sync-contracts`",
                )


if __name__ == "__main__":
    unittest.main()
