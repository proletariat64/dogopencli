"""Exercise the documentation guard through its public command-line interface."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "doc_guard.py"


class DocGuardTests(unittest.TestCase):
    def run_guard(self, files: dict[str, str]) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), "--root", str(root)],
                capture_output=True,
                text=True,
                check=False,
            )
            after = {
                path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, files, "guard must not modify or create files")
            return result

    def test_valid_docs_and_examples_pass_offline(self) -> None:
        result = self.run_guard(
            {
                "README.md": "# Project\n\n[Docs](docs/README.md)\n",
                "docs/README.md": "# Docs\n\n```md\n# Example\n[Missing](missing.md)\n```\n",
                "docs/agents/access.md": (
                    "# Access\n\n[Docs](../README.md)\n"
                    "[Remote](https://invalid.example/doc)\n"
                ),
                ".code-review-graph/wiki/Anything.md": "# Ignored\n",
                "tools/leaf-dev/README.md": "# Leaf development\n\n[Interfaces](interfaces.md)\n",
                "tools/leaf-dev/interfaces.md": "# Interfaces\n",
            }
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("PASS (5 Markdown files)", result.stdout)

    def test_standalone_leaf_readme_keeps_prose_and_link_checks(self) -> None:
        name = "leaf_packages/liquidity/reference.banks/README.md"
        result = self.run_guard(
            {
                name: "# Banks\n\n[Manifest](leaf.json)\n",
                name.replace("README.md", "leaf.json"): "{}",
            }
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        broken = self.run_guard({name: "# Banks\n\n[Missing](missing.json)\n"})
        self.assertEqual(broken.returncode, 1)
        self.assertIn("broken local link", broken.stdout)
        invalid = self.run_guard({name.replace("README.md", "notes.md"): "# Notes\n"})
        self.assertEqual(invalid.returncode, 1)
        self.assertIn("invalid documentation", invalid.stdout)

    def test_invalid_names_and_locations_fail(self) -> None:
        for name in (
            "notes.md",
            "docs/report.md",
            "docs/agents/Bad_Name.md",
            "docs/spec/payment.md",
            "docs/design/payment.md",
            "docs/design/payment-v01.2.3.md",
            "docs/research/genernal/2026-09-08-access.md",
        ):
            with self.subTest(name=name):
                result = self.run_guard({name: "# Test\n"})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid documentation", result.stdout)

    def test_process_and_version_archives_are_not_active_documentation(self) -> None:
        for name in (
            "CHANGELOG.md",
            "docs/design/liquidity-v0.2.3.md",
            "docs/adr/0001-first.md",
            "docs/research/general/2026-09-08-access.md",
        ):
            with self.subTest(name=name):
                result = self.run_guard({name: "# Obsolete process\n"})
                self.assertEqual(result.returncode, 1)
                self.assertIn("invalid documentation", result.stdout)

    def test_inline_code_title_and_link_examples_pass(self) -> None:
        result = self.run_guard(
            {"README.md": "# `Project`\n\nExample: `[Link](missing.md)`\n[Self]( )\n"}
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_malformed_link_reports_error_without_crashing(self) -> None:
        result = self.run_guard(
            {"README.md": "# Project\n\n[Link](https://[invalid)\n"}
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("malformed link", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_missing_title_duplicate_title_and_missing_newline_fail(self) -> None:
        for content in ("## Not a title\n", "# One\n# Two\n", "# Missing newline"):
            with self.subTest(content=content):
                self.assertNotEqual(
                    self.run_guard({"README.md": content}).returncode, 0
                )

    def test_broken_and_escaping_links_fail(self) -> None:
        for target in ("missing.md", "../outside.md", "/etc/passwd"):
            with self.subTest(target=target):
                result = self.run_guard(
                    {"README.md": f"# Project\n\n[Link]({target})\n"}
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("local link", result.stdout)

    def test_private_tmp_directory_is_skipped(self) -> None:
        result = self.run_guard(
            {
                "README.md": "# Project\n",
                "tmp/private/notes.md": "not a documentation file\n",
                "aidb/private/notes.md": "private dataset, not documentation\n",
                "duckdog-data/notes.md": "private dataset, not documentation\n",
            }
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("PASS (1 Markdown files)", result.stdout)


if __name__ == "__main__":
    unittest.main()
