from __future__ import annotations

import ast
import unittest
from pathlib import Path

import helpers  # noqa: F401
from cli import COMMAND_MUTATION_CLASSES, build_parser


def _gh_chokepoint_errors(filename: str, source: str) -> list[str]:
    commands: list[str | None] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, (ast.List, ast.Tuple)) or not node.elts:
            continue
        first = node.elts[0]
        if not isinstance(first, ast.Constant) or first.value != "gh":
            continue
        second = node.elts[1] if len(node.elts) > 1 else None
        commands.append(second.value if isinstance(second, ast.Constant) else None)

    if filename == "github.py":
        if "stack" in commands:
            return ["github.py may not contain literal gh stack argv"]
        return []
    if filename == "gh_stack.py":
        if not commands:
            return ["gh_stack.py must contain its literal gh stack boundary"]
        if any(command != "stack" for command in commands):
            return ["gh_stack.py may contain only literal gh stack argv"]
        return []
    if commands:
        return [f"{filename} may not contain literal gh argv"]
    return []


class CliSafetyTests(unittest.TestCase):
    def test_every_operation_has_one_mutation_class(self) -> None:
        parser = build_parser()
        help_text = parser.format_help()
        self.assertEqual(17, len(COMMAND_MUTATION_CLASSES))
        for command, mutation_class in COMMAND_MUTATION_CLASSES.items():
            self.assertIn(command, help_text)
            self.assertIn(f"[{mutation_class}]", help_text)

    def test_status_class_covers_authorized_native_state_refresh(self) -> None:
        self.assertEqual("local-mutating", COMMAND_MUTATION_CLASSES["status"])

    def test_issue_30_all_remote_mutations_default_to_dry_run(self) -> None:
        parser = build_parser()
        for argv in (
            ("pr-create",),
            ("push-chain",),
            ("propagate", "--source", "feature/test", "--index", "1"),
            ("merge-propagate", "--source", "feature/test", "--index", "1"),
            (
                "recover-suffix",
                "--source",
                "feature/test",
                "--base",
                "main",
                "--from-index",
                "2",
                "--successor-source",
                "feature/test-corrected",
                "--successor-sha",
                "a" * 40,
            ),
        ):
            args = parser.parse_args(argv)
            self.assertEqual("remote-mutating", args.mutation_class)
            self.assertTrue(args.dry_run)

    def test_issue_30_uses_file_messages_and_never_hard_resets(self) -> None:
        scripts = Path(__file__).resolve().parents[1]
        implementation = "\n".join(
            path.read_text()
            for path in scripts.glob("*.py")
            if path.name
            not in {"metadata.py", "rehydrate.py", "status.py", "validate.py"}
        )
        self.assertNotIn('"commit", "-m"', implementation)
        self.assertNotIn('"--body",', implementation)
        self.assertNotIn('"reset", "--hard"', implementation)

    def test_issue_163_stack_and_non_stack_gh_calls_have_separate_chokepoints(
        self,
    ) -> None:
        scripts = Path(__file__).resolve().parents[1]
        for path in scripts.glob("*.py"):
            source = path.read_text()
            self.assertEqual([], _gh_chokepoint_errors(path.name, source), path.name)

    def test_issue_163_stack_chokepoint_rejects_non_stack_gh_argv(self) -> None:
        errors = _gh_chokepoint_errors("gh_stack.py", 'runner(["gh", "pr", "view"])')

        self.assertEqual(["gh_stack.py may contain only literal gh stack argv"], errors)

    def test_database_compare_spelling_is_standardized(self) -> None:
        scripts = Path(__file__).resolve().parents[1]
        disallowed = "db" + "compare"
        for path in scripts.rglob("*.py"):
            self.assertNotIn(disallowed, path.name, str(path))
            self.assertNotIn(disallowed, path.read_text(), str(path))


if __name__ == "__main__":
    unittest.main()
