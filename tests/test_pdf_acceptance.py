from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

from rag_lab.pdf_acceptance import (
    PdfAcceptanceError,
    inspect_public_pdf,
    render_acceptance_markdown,
    suggested_inspection_pages,
    write_acceptance_report,
)
from rag_lab.cli import main


HAS_PYPDF = importlib.util.find_spec("pypdf") is not None
FIXTURE = Path(__file__).parent / "fixtures" / "lab1_text_sample.pdf"


@unittest.skipUnless(HAS_PYPDF, "PDF extra is not installed")
class PdfAcceptanceTests(unittest.TestCase):
    def _inspect(self, **overrides: object):
        arguments = {
            "document_id": "public_sample",
            "title": "Public sample",
            "source_url": "https://example.test/sample.pdf",
            "catalog_url": "https://example.test/catalog",
            "distribution": "Public",
            "license_terms": "Repository-owned fixture",
            "inspected_pages": (1, 2, 3),
            "decision": "accepted_with_limitations",
            "observation": "代表ページを比較し、空白ページを確認した。",
            "generated_at": "2026-10-03T00:00:00+00:00",
        }
        arguments.update(overrides)
        return inspect_public_pdf(FIXTURE, **arguments)

    def test_suggested_pages_are_unique_for_short_documents(self) -> None:
        self.assertEqual(suggested_inspection_pages(1), (1,))
        self.assertEqual(suggested_inspection_pages(2), (1, 2))
        self.assertEqual(suggested_inspection_pages(17), (1, 9, 17))

    def test_acceptance_requires_ok_extraction_and_visual_checks(self) -> None:
        report = self._inspect()

        self.assertEqual(report.status, "needs_review")
        self.assertEqual(report.required_pages, (1, 2, 3))
        self.assertTrue(report.provenance_complete)
        self.assertEqual(report.chunks, 2)
        failed = {check.check_id for check in report.checks if not check.passed}
        self.assertEqual(failed, {"text_extraction"})

    def test_missing_visual_page_is_recorded_as_incomplete(self) -> None:
        report = self._inspect(inspected_pages=(1, 3), decision="accepted")

        failed = {check.check_id for check in report.checks if not check.passed}
        self.assertIn("visual_pages_confirmed", failed)
        self.assertEqual(report.status, "needs_review")

    def test_ok_pdf_can_pass_with_documented_limitations(self) -> None:
        from pypdf import PdfReader, PdfWriter

        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "two-pages.pdf"
            reader = PdfReader(str(FIXTURE))
            writer = PdfWriter()
            writer.add_page(reader.pages[0])
            writer.add_page(reader.pages[1])
            with input_path.open("wb") as handle:
                writer.write(handle)

            report = inspect_public_pdf(
                input_path,
                document_id="public_sample",
                title="Public sample",
                source_url="https://example.test/sample.pdf",
                catalog_url="https://example.test/catalog",
                distribution="Public",
                license_terms="Repository-owned fixture",
                inspected_pages=(1, 2),
                decision="accepted_with_limitations",
                observation="先頭と末尾を比較した。",
                generated_at="2026-10-03T00:00:00+00:00",
            )

        self.assertEqual(report.status, "passed_with_limitations")
        self.assertTrue(all(check.passed for check in report.checks))

    def test_report_contains_metrics_but_not_absolute_input_path(self) -> None:
        report = self._inspect()
        markdown = render_acceptance_markdown(report)

        self.assertIn("SHA-256", markdown)
        self.assertIn("ページ数: 3", markdown)
        self.assertIn("チャンク数: 2", markdown)
        self.assertNotIn(str(FIXTURE.resolve()), markdown)
        self.assertNotIn("火星気象観測ステーション", markdown)

    def test_report_is_never_overwritten(self) -> None:
        report = self._inspect()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "acceptance.md"
            write_acceptance_report(report, output)
            original = output.read_text(encoding="utf-8")

            with self.assertRaisesRegex(
                PdfAcceptanceError, "上書きしません"
            ):
                write_acceptance_report(report, output)

            self.assertEqual(output.read_text(encoding="utf-8"), original)

    def test_cli_writes_reviewed_markdown_report(self) -> None:
        from pypdf import PdfReader, PdfWriter

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "two-pages.pdf"
            output = root / "acceptance.md"
            reader = PdfReader(str(FIXTURE))
            writer = PdfWriter()
            writer.add_page(reader.pages[0])
            writer.add_page(reader.pages[1])
            with input_path.open("wb") as handle:
                writer.write(handle)

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                main(
                    [
                        "accept-pdf",
                        str(input_path),
                        "--document-id",
                        "public_sample",
                        "--title",
                        "Public sample",
                        "--source-url",
                        "https://example.test/sample.pdf",
                        "--catalog-url",
                        "https://example.test/catalog",
                        "--distribution",
                        "Public",
                        "--license-terms",
                        "Repository-owned fixture",
                        "--inspected-page",
                        "1",
                        "--inspected-page",
                        "2",
                        "--decision",
                        "accepted",
                        "--observation",
                        "代表ページを確認した。",
                        "--report",
                        str(output),
                    ]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["status"], "passed")
            self.assertEqual(payload["pages"], 2)
            self.assertTrue(output.is_file())

    def test_out_of_range_inspection_page_is_rejected(self) -> None:
        with self.assertRaisesRegex(PdfAcceptanceError, "範囲外"):
            self._inspect(inspected_pages=(1, 2, 99))


if __name__ == "__main__":
    unittest.main()
