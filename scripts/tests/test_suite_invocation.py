"""Every module in this suite must import under the module-path invocation.

`just test-plugins` runs this suite by discovery, which puts `scripts/tests`
on `sys.path` and makes a bare `from helpers import ...` resolve for free. The
module-path form does not: `python3 -m unittest scripts.tests.test_x` puts the
repository root on `sys.path` instead, so a module relying on discovery's
implicit path errors with `ModuleNotFoundError: No module named 'helpers'`
before a single assertion runs.

Ticket bodies name that form as required pre-merge verification, so a module
that only imports under discovery makes recorded evidence unreproducible for
the next reader. Each module carries the `__file__`-relative `sys.path` shim
already used across `review-suite/scripts/tests/`; this test is what keeps a
new module from being added without one.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = TESTS_DIR.parents[1]


def _dotted_names() -> list[str]:
    return sorted(f"scripts.tests.{path.stem}" for path in TESTS_DIR.glob("test_*.py"))


class ModulePathInvocationTests(unittest.TestCase):
    def test_the_suite_is_non_empty(self) -> None:
        # A glob that silently matched nothing would make every other
        # assertion here vacuous.
        self.assertGreater(len(_dotted_names()), 1)

    def test_every_module_imports_from_the_repository_root(self) -> None:
        # PYTHONPATH is stripped so an ambient entry cannot supply the path
        # the module is supposed to establish for itself.
        environment = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        for dotted in _dotted_names():
            with self.subTest(module=dotted):
                result = subprocess.run(
                    [sys.executable, "-c", f"import {dotted}"],
                    cwd=REPOSITORY_ROOT,
                    env=environment,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"`python3 -m unittest {dotted}` cannot import "
                    f"{dotted.rsplit('.', 1)[1]}.py:\n{result.stderr}",
                )


if __name__ == "__main__":
    unittest.main()
