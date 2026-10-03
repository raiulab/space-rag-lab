import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

from rag_lab.cli import main
from rag_lab.pdf_ingest import PdfValidationError, extract_pdf, validate_document_id
from rag_lab.source_documents import chunk_source_document


HAS_PYPDF = importlib.util.find_spec("pypdf") is not None
FIXTURE = Path(__file__).parent / "fixtures" / "lab1_text_sample.pdf"


class PdfEarlyValidationTests(unittest.TestCase):
    def test_document_id_rejects_path_characters(self) -> None:
        with self.assertRaisesRegex(PdfValidationError, "document_id"):
            validate_document_id("../unsafe")

    def test_non_pdf_signature_is_rejected_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "not-really.pdf"
            path.write_bytes(b"plain text")
            with self.assertRaisesRegex(PdfValidationError, "シグネチャ"):
                extract_pdf(path, document_id="invalid")

    def test_size_limit_is_checked_before_parsing(self) -> None:
        with self.assertRaisesRegex(PdfValidationError, "サイズ上限"):
            extract_pdf(FIXTURE, document_id="too_large", max_bytes=10)


@unittest.skipUnless(HAS_PYPDF, "PDF extra is not installed")
class PdfIngestTests(unittest.TestCase):
    def test_extracts_multiple_pages_unicode_and_warnings(self) -> None:
        result = extract_pdf(
            FIXTURE,
            document_id="lab1_pdf",
            title="PDF取り込み試験",
            source="synthetic fixture",
            classification="synthetic",
            note="unit test",
        )

        self.assertEqual(result.status, "needs_review")
        self.assertEqual([page.page for page in result.document.pages], [1, 2, 3])
        self.assertIn("Mars Power System", result.document.pages[0].blocks[0].text)
        self.assertIn("temperature 78°C", result.document.pages[1].blocks[0].text)
        self.assertEqual(result.document.pages[2].blocks, [])
        self.assertEqual(result.document.metadata["classification"], "synthetic")
        self.assertEqual(result.document.metadata["note"], "unit test")
        codes = {(warning.code, warning.page) for warning in result.warnings}
        self.assertIn(("EMPTY_PAGE", 3), codes)
        self.assertIn(("SHORT_PAGE", 3), codes)
        self.assertIn(("HIGH_EMPTY_PAGE_RATIO", None), codes)

    def test_chunks_are_deterministic_and_keep_page_numbers(self) -> None:
        first = extract_pdf(FIXTURE, document_id="stable")
        second = extract_pdf(FIXTURE, document_id="stable")

        first_chunks = chunk_source_document(first.document, chunk_size=60)
        second_chunks = chunk_source_document(second.document, chunk_size=60)

        self.assertEqual(first_chunks, second_chunks)
        self.assertEqual({chunk.page for chunk in first_chunks}, {1, 2})
        self.assertTrue(all(chunk.source == FIXTURE.name for chunk in first_chunks))
        self.assertTrue(
            all(chunk.metadata["extraction_method"] == "pypdf" for chunk in first_chunks)
        )

    def test_page_limit_is_rejected(self) -> None:
        with self.assertRaisesRegex(PdfValidationError, "ページ数上限"):
            extract_pdf(FIXTURE, document_id="too_many", max_pages=2)

    def test_encrypted_pdf_is_rejected(self) -> None:
        from pypdf import PdfReader, PdfWriter

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "encrypted.pdf"
            writer = PdfWriter()
            writer.append_pages_from_reader(PdfReader(str(FIXTURE)))
            writer.encrypt("secret")
            with path.open("wb") as handle:
                writer.write(handle)

            with self.assertRaisesRegex(PdfValidationError, "暗号化"):
                extract_pdf(path, document_id="encrypted")

    def test_corrupt_pdf_has_safe_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.pdf"
            path.write_bytes(b"%PDF-this-is-not-a-valid-document")
            with self.assertRaisesRegex(PdfValidationError, "解析できません"):
                extract_pdf(path, document_id="broken")

    def test_blank_document_is_marked_ocr_required(self) -> None:
        from pypdf import PdfWriter

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "blank.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            with path.open("wb") as handle:
                writer.write(handle)

            result = extract_pdf(path, document_id="blank")

        self.assertEqual(result.status, "OCR_REQUIRED")
        self.assertEqual(result.empty_page_count, 1)
        self.assertIn("OCR_REQUIRED", [warning.code for warning in result.warnings])

    def test_cli_writes_chunks_and_prints_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "chunks.jsonl"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                main(
                    [
                        "ingest-pdf",
                        str(FIXTURE),
                        "--document-id",
                        "cli_pdf",
                        "--title",
                        "CLI PDF",
                        "--output",
                        str(output),
                    ]
                )

            summary = json.loads(stdout.getvalue())
            rows = [json.loads(line) for line in output.read_text().splitlines()]

        self.assertEqual(summary["status"], "needs_review")
        self.assertEqual(summary["pages"], 3)
        self.assertEqual(summary["chunks"], len(rows))
        self.assertEqual({row["page"] for row in rows}, {1, 2})
        self.assertTrue(all(row["document_id"] == "cli_pdf" for row in rows))


if __name__ == "__main__":
    unittest.main()
