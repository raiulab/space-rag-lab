from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rag_lab.learning.diagnostics import (
    DiagnosticReportError,
    build_learning_report,
    compare_reports,
    hints_for_case,
    load_evaluation_report,
    save_learning_report,
)


def _report_value(*, candidate: bool = False) -> dict:
    second_failed = candidate
    return {
        "summary": {
            "examples": 2,
            "retrieval_hit_rate": 0.5 if candidate else 1.0,
            "citation_hit_rate": 1.0,
            "keyword_recall": 1.0 if candidate else 0.75,
            "answerability_accuracy": 1.0,
        },
        "details": [
            {
                "id": "case-a",
                "question": "必要な語を含む回答ですか？",
                "expected_answerable": True,
                "predicted_answerable": True,
                "retrieval_hit": True,
                "citation_hit": True,
                "keyword_recall": 1.0 if candidate else 0.5,
                "refusal_correct": True,
                "answer": "保存対象にしない回答本文",
            },
            {
                "id": "case-b",
                "question": "正解文書を検索できましたか？",
                "expected_answerable": True,
                "predicted_answerable": True,
                "retrieval_hit": not second_failed,
                "citation_hit": True,
                "keyword_recall": 1.0,
                "refusal_correct": True,
                "answer": "別の保存対象にしない回答本文",
            },
        ],
    }


class DiagnosticReportTests(unittest.TestCase):
    def _write(self, directory: Path, name: str, value: dict) -> Path:
        path = directory / name
        path.write_text(
            json.dumps(value, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def test_load_report_classifies_failed_case_and_provides_hints(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory) / "reports"
            report_dir.mkdir()
            path = self._write(report_dir, "baseline.json", _report_value())

            report = load_evaluation_report(path, report_dir)

        self.assertEqual(report.summary["examples"], 2)
        self.assertEqual(len(report.failed_cases), 1)
        self.assertEqual(report.failed_cases[0].failure_codes, ("keyword_miss",))
        self.assertIn("必要な文や数値", hints_for_case(report.failed_cases[0], 2)[0])

    def test_comparison_shows_improvements_and_regressions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory) / "reports"
            report_dir.mkdir()
            baseline = load_evaluation_report(
                self._write(report_dir, "baseline.json", _report_value()),
                report_dir,
            )
            candidate = load_evaluation_report(
                self._write(
                    report_dir,
                    "candidate.json",
                    _report_value(candidate=True),
                ),
                report_dir,
            )

            comparison = compare_reports(baseline, candidate)

        self.assertEqual(comparison.resolved_case_ids, ("case-a",))
        self.assertEqual(comparison.new_failure_case_ids, ("case-b",))
        self.assertEqual(comparison.metric_deltas["retrieval_hit_rate"], -0.5)
        self.assertEqual(comparison.metric_deltas["keyword_recall"], 0.25)

    def test_report_outside_reports_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_dir = root / "reports"
            report_dir.mkdir()
            outside = self._write(root, "outside.json", _report_value())

            with self.assertRaisesRegex(DiagnosticReportError, "reports直下"):
                load_evaluation_report(outside, report_dir)

    def test_unsafe_report_filename_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory) / "reports"
            report_dir.mkdir()
            path = self._write(report_dir, "unsafe name.json", _report_value())

            with self.assertRaisesRegex(DiagnosticReportError, "reports直下"):
                load_evaluation_report(path, report_dir)

    def test_unsafe_case_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory) / "reports"
            report_dir.mkdir()
            value = _report_value()
            value["details"][0]["id"] = "unsafe|markdown"
            path = self._write(report_dir, "unsafe.json", value)

            with self.assertRaisesRegex(DiagnosticReportError, "一意なid"):
                load_evaluation_report(path, report_dir)

    def test_learning_report_omits_answers_and_saves_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_dir = root / "reports"
            report_dir.mkdir()
            baseline = load_evaluation_report(
                self._write(report_dir, "baseline.json", _report_value()),
                report_dir,
            )
            content = build_learning_report(
                baseline,
                candidate=None,
                observation="生成工程を確認する",
                next_action="チャンクサイズだけを変更する",
            )
            path = save_learning_report(root / ".rag_lab", content)
            saved = path.read_text(encoding="utf-8")

        self.assertIn("case-a", saved)
        self.assertIn("生成工程を確認する", saved)
        self.assertNotIn("保存対象にしない回答本文", saved)
        self.assertEqual(path.suffix, ".md")

    def test_comparison_rejects_different_question_sets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory) / "reports"
            report_dir.mkdir()
            baseline = load_evaluation_report(
                self._write(report_dir, "baseline.json", _report_value()),
                report_dir,
            )
            changed = _report_value(candidate=True)
            changed["details"][1]["id"] = "different-case"
            candidate = load_evaluation_report(
                self._write(report_dir, "candidate.json", changed),
                report_dir,
            )

            with self.assertRaisesRegex(DiagnosticReportError, "問題ID"):
                compare_reports(baseline, candidate)


if __name__ == "__main__":
    unittest.main()
