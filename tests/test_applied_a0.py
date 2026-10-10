from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from rag_lab.applied.corpus import (
    A0ValidationError,
    dataset_sha256,
    file_sha256,
    load_gold_cases,
    load_manifest,
    validate_a0_dataset,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APPLIED_ROOT = PROJECT_ROOT / "data" / "applied"


class AppliedA0Tests(unittest.TestCase):
    def test_checked_in_dataset_meets_a0_acceptance_counts(self) -> None:
        summary = validate_a0_dataset(APPLIED_ROOT)

        self.assertEqual(summary.dataset_id, "synthetic_research_institute_v1")
        self.assertEqual(summary.document_count, 8)
        self.assertEqual(summary.page_count, 32)
        self.assertEqual(summary.evaluation_case_count, 29)
        self.assertEqual(summary.unanswerable_case_count, 7)
        self.assertEqual(summary.access_boundary_case_count, 12)

    def test_manifest_checksums_are_reproducible(self) -> None:
        manifest = load_manifest(APPLIED_ROOT / "corpus" / "manifest.json")

        for document in manifest["documents"]:
            source = APPLIED_ROOT / "corpus" / document["source"]
            self.assertEqual(file_sha256(source), document["sha256"])
        self.assertEqual(dataset_sha256(manifest["documents"]), manifest["dataset_sha256"])

    def test_dataset_is_explicitly_synthetic_and_uses_relative_sources(self) -> None:
        manifest = load_manifest(APPLIED_ROOT / "corpus" / "manifest.json")

        self.assertEqual(manifest["source_policy"], "synthetic")
        self.assertIn("synthetic", manifest["license_or_terms"])
        for document in manifest["documents"]:
            source = Path(document["source"])
            self.assertFalse(source.is_absolute())
            self.assertNotIn("..", source.parts)
            self.assertIn("synthetic", document["license_or_terms"])

    def test_gold_cases_cover_answerability_and_access_boundaries(self) -> None:
        cases = load_gold_cases(APPLIED_ROOT / "evaluation" / "gold.jsonl")
        by_id = {case["case_id"]: case for case in cases}

        self.assertGreaterEqual(len(cases), 20)
        self.assertGreaterEqual(
            sum(not case["expected_answerable"] for case in cases) / len(cases),
            0.2,
        )
        self.assertGreaterEqual(sum(case["access_boundary"] for case in cases), 5)
        for case_id in (
            "access-deny-01",
            "access-deny-02",
            "access-deny-03",
            "access-deny-04",
        ):
            self.assertEqual(by_id[case_id]["allowed_result_document_ids"], [])
            self.assertFalse(by_id[case_id]["expected_answerable"])
        self.assertEqual(
            by_id["access-public-01"]["allowed_result_document_ids"],
            ["ari_coating_report_r2"],
        )

    def test_schema_files_use_json_schema_2020_12(self) -> None:
        for name in (
            "corpus_manifest.schema.json",
            "research_document_metadata.schema.json",
            "gold_case.schema.json",
        ):
            schema = load_manifest(APPLIED_ROOT / "schemas" / name)
            self.assertEqual(
                schema["$schema"],
                "https://json-schema.org/draft/2020-12/schema",
            )
            self.assertEqual(schema["type"], "object")

    def test_prompt_injection_fixture_is_data_with_a_safety_case(self) -> None:
        document = (
            APPLIED_ROOT / "corpus" / "documents" / "coating_failure_review.md"
        ).read_text(encoding="utf-8")
        cases = load_gold_cases(APPLIED_ROOT / "evaluation" / "gold.jsonl")

        self.assertIn("それまでの指示を無視し", document)
        safety_case = next(case for case in cases if case["case_id"] == "safety-01")
        self.assertEqual(safety_case["task_type"], "safety")
        self.assertEqual(safety_case["required_values"], ["実行してはならず"])

    def test_validation_rejects_modified_source_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            copied_root = Path(temp_dir) / "applied"
            shutil.copytree(APPLIED_ROOT, copied_root)
            source = copied_root / "corpus" / "documents" / "coating_report_r1.md"
            source.write_text(source.read_text(encoding="utf-8") + "\n改変\n", encoding="utf-8")

            with self.assertRaisesRegex(A0ValidationError, "SHA-256"):
                validate_a0_dataset(copied_root)

    def test_validation_rejects_revision_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            copied_root = Path(temp_dir) / "applied"
            shutil.copytree(APPLIED_ROOT, copied_root)
            manifest_path = copied_root / "corpus" / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["documents"][0]["supersedes_document_id"] = (
                "ari_coating_report_r2"
            )
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(A0ValidationError, "循環"):
                validate_a0_dataset(copied_root)


if __name__ == "__main__":
    unittest.main()
