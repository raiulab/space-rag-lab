from __future__ import annotations

import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReleaseReadinessTests(unittest.TestCase):
    def test_public_project_files_exist(self) -> None:
        required = (
            "LICENSE",
            "CHANGELOG.md",
            "CONTRIBUTING.md",
            "SECURITY.md",
            "THIRD_PARTY_NOTICES.md",
            ".github/workflows/ci.yml",
            "docs/releases/v0.1.0.md",
        )

        missing = [path for path in required if not (PROJECT_ROOT / path).is_file()]

        self.assertEqual(missing, [])

    def test_package_and_module_versions_match_release(self) -> None:
        pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        package_init = (PROJECT_ROOT / "src/rag_lab/__init__.py").read_text(
            encoding="utf-8"
        )

        project_version = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)
        module_version = re.search(r'^__version__ = "([^"]+)"$', package_init, re.MULTILINE)

        self.assertIsNotNone(project_version)
        self.assertIsNotNone(module_version)
        self.assertEqual(project_version.group(1), "0.1.0")
        self.assertEqual(module_version.group(1), project_version.group(1))
        self.assertIn(
            'Repository = "https://github.com/raiulab/space-rag-lab"',
            pyproject,
        )

    def test_ci_covers_supported_python_versions_and_offline_evaluation(self) -> None:
        workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

        for version in ("3.10", "3.11", "3.12"):
            self.assertIn(f'"{version}"', workflow)
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn("rag-lab all", workflow)

    def test_private_and_generated_paths_are_ignored(self) -> None:
        ignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

        for entry in (
            ".venv/",
            ".rag_lab/",
            ".env",
            "build/",
            "dist/",
            "data/index/*.jsonl",
        ):
            self.assertIn(entry, ignore)


if __name__ == "__main__":
    unittest.main()
