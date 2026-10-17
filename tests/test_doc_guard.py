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
                "docs/research/general/2026-09-08-access.md": (
                    "# Access\n\nObserved: 2026-09-08\nScope: general\nStatus: snapshot\n"
                    "\n[Docs](../../README.md#research)\n[Remote](https://invalid.example/doc)\n"
                ),
                ".code-review-graph/wiki/Anything.md": "# Ignored\n",
            }
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("PASS (3 Markdown files)", result.stdout)

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

    def test_versioned_design_copy_requires_authoritative_issue(self) -> None:
        name = "docs/design/liquidity-v0.2.3.md"
        result = self.run_guard(
            {
                name: "# Liquidity\n\n[Specification](https://github.com/proletariat64/dogopencli/issues/76)\n"
            }
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        for body in (
            "# Liquidity\n",
            "# Liquidity\n\n```text\nhttps://github.com/proletariat64/dogopencli/issues/76\n```\n",
            "# Liquidity\n\nhttps://github.com/another/repository/issues/76\n",
        ):
            with self.subTest(body=body):
                result = self.run_guard({name: body})
                self.assertEqual(result.returncode, 1)
                self.assertIn("authoritative GitHub issue", result.stdout)

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

    def test_research_requires_matching_date_scope_and_status(self) -> None:
        cases = (
            (
                "2026-02-30-access.md",
                "Observed: 2026-02-30\nScope: general\nStatus: snapshot\n",
            ),
            (
                "2026-09-08-access.md",
                "Observed: 2026-09-09\nScope: general\nStatus: snapshot\n",
            ),
            (
                "2026-09-08-access.md",
                "Observed: 2026-09-08\nScope: payment\nStatus: snapshot\n",
            ),
            ("2026-09-08-access.md", "Observed: 2026-09-08\nScope: general\n"),
        )
        for name, metadata in cases:
            with self.subTest(name=name, metadata=metadata):
                result = self.run_guard(
                    {f"docs/research/general/{name}": "# Research\n\n" + metadata}
                )
                self.assertNotEqual(result.returncode, 0)

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
            }
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("PASS (1 Markdown files)", result.stdout)

    def test_duplicate_adr_numbers_fail(self) -> None:
        result = self.run_guard(
            {
                "docs/adr/0001-first.md": "# First\n",
                "docs/adr/0001-second.md": "# Second\n",
            }
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate ADR number 0001", result.stdout)


if __name__ == "__main__":
    unittest.main()
