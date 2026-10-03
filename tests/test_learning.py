import importlib.util
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from rag_lab.learning.checks import Lab1Completion, evaluate_lab1, warning_id
from rag_lab.learning.progress import ProgressStore, write_json_atomic
from rag_lab.learning.storage import (
    DatasetAlreadyExistsError,
    save_pdf_lab1_dataset,
)
from rag_lab.models import Chunk
from rag_lab.pdf_ingest import PdfWarning, extract_pdf
from rag_lab.source_documents import chunk_source_document


HAS_PYPDF = importlib.util.find_spec("pypdf") is not None
FIXTURE = Path(__file__).parent / "fixtures" / "lab1_text_sample.pdf"


def sample_chunk() -> Chunk:
    return Chunk(
        chunk_id="demo:p1:001",
        document_id="demo",
        title="Demo",
        page=1,
        section="本文",
        text="Evidence",
        source="demo.pdf",
    )


class Lab1CompletionTests(unittest.TestCase):
    def test_complete_requires_learning_records_and_warning_review(self) -> None:
        result = evaluate_lab1(
            [sample_chunk()],
            document_count=1,
            warnings=(),
            prediction="2チャンクになると予想した",
            observation="実際に1チャンクだった",
        )
        self.assertTrue(result.completed)
        self.assertTrue(all(check.passed for check in result.checks))

    def test_missing_observation_stays_in_progress(self) -> None:
        result = evaluate_lab1(
            [sample_chunk()],
            document_count=1,
            prediction="1チャンクと予想",
        )
        self.assertEqual(result.status, "in_progress")

    def test_missing_provenance_needs_review(self) -> None:
        incomplete = replace(sample_chunk(), source="")
        result = evaluate_lab1(
            [incomplete],
            document_count=1,
            prediction="予想",
            observation="観察",
        )
        self.assertEqual(result.status, "needs_review")
        failed = {check.code for check in result.checks if not check.passed}
        self.assertIn("sources_present", failed)

    def test_ocr_required_cannot_complete(self) -> None:
        result = evaluate_lab1(
            [sample_chunk()],
            document_count=1,
            extraction_status="OCR_REQUIRED",
            prediction="予想",
            observation="観察",
        )
        self.assertEqual(result.status, "needs_review")
        self.assertFalse(result.completed)

    def test_warning_must_be_confirmed(self) -> None:
        warning = PdfWarning(code="EMPTY_PAGE", page=3, message="empty")
        unconfirmed = evaluate_lab1(
            [sample_chunk()],
            document_count=1,
            warnings=[warning],
            prediction="予想",
            observation="観察",
        )
        confirmed = evaluate_lab1(
            [sample_chunk()],
            document_count=1,
            warnings=[warning],
            confirmed_warning_ids=[warning_id(warning)],
            prediction="予想",
            observation="観察",
        )

        self.assertEqual(unconfirmed.status, "needs_review")
        self.assertEqual(confirmed.status, "completed")


class ProgressStoreTests(unittest.TestCase):
    def test_missing_progress_defaults_to_not_started(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            progress = ProgressStore(Path(directory) / ".rag_lab").load()

        self.assertEqual(progress["schema_version"], 1)
        self.assertEqual(progress["labs"]["lab1"]["status"], "not_started")

    def test_update_preserves_existing_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / ".rag_lab"
            write_json_atomic(
                workspace / "progress.json",
                {
                    "schema_version": 1,
                    "display_preference": "compact",
                    "labs": {"lab1": {"learner_note": "keep me"}},
                },
            )
            completion = Lab1Completion(status="in_progress", checks=())
            updated = ProgressStore(workspace).update_lab1(
                completion=completion,
                run_id="run_safe",
                updated_at="2026-10-03T00:00:00Z",
                prediction="予想",
                observation="",
                confirmed_warning_ids=(),
            )

        self.assertEqual(updated["schema_version"], 1)
        self.assertEqual(updated["display_preference"], "compact")
        self.assertEqual(updated["labs"]["lab1"]["learner_note"], "keep me")
        self.assertEqual(updated["labs"]["lab1"]["status"], "in_progress")


@unittest.skipUnless(HAS_PYPDF, "PDF extra is not installed")
class DatasetStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.extraction = extract_pdf(FIXTURE, document_id="stored_pdf")
        self.chunks = chunk_source_document(self.extraction.document)
        self.confirmed = [warning_id(self.extraction.warnings[0])]

    def _save(self, workspace: Path, *, save_raw: bool = False):
        return save_pdf_lab1_dataset(
            workspace,
            FIXTURE,
            self.extraction,
            self.chunks,
            prediction="2チャンクと予想した",
            observation="2ページから2チャンク生成された",
            confirmed_warning_ids=self.confirmed,
            license_terms="self-created fixture",
            save_raw=save_raw,
        )

    def test_dataset_files_and_progress_are_saved_without_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / ".rag_lab"
            with mock.patch.dict(
                os.environ, {"AWS_SECRET_ACCESS_KEY": "do-not-save-this"}
            ):
                saved = self._save(workspace)
            manifest_path = saved.dataset_path / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            pages = (saved.dataset_path / "processed" / "pages.jsonl").read_text(
                encoding="utf-8"
            )
            chunks = (saved.dataset_path / "processed" / "chunks.jsonl").read_text(
                encoding="utf-8"
            )
            all_saved_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in workspace.rglob("*.json*")
            )

            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["dataset_id"], saved.dataset_id)
            self.assertRegex(saved.dataset_id, r"^ds_[0-9a-f]{16}$")
            self.assertRegex(saved.run_id, r"^run_[0-9a-f]{16}$")
            self.assertEqual(len(manifest["sha256"]), 64)
            self.assertFalse(manifest["raw_saved"])
            self.assertFalse((saved.dataset_path / "raw").exists())
            self.assertEqual(len(pages.splitlines()), 3)
            self.assertEqual(len(chunks.splitlines()), 2)
            self.assertNotIn(str(FIXTURE.resolve()), all_saved_text)
            self.assertNotIn("do-not-save-this", all_saved_text)
            self.assertEqual(saved.completion.status, "completed")

            progress = json.loads(
                (workspace / "progress.json").read_text(encoding="utf-8")
            )
            self.assertEqual(progress["labs"]["lab1"]["status"], "completed")
            self.assertEqual(progress["labs"]["lab1"]["last_run_id"], saved.run_id)

    def test_raw_pdf_is_saved_only_when_explicitly_requested(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            saved = self._save(Path(directory) / ".rag_lab", save_raw=True)
            raw_path = saved.dataset_path / "raw" / "source.pdf"
            manifest = json.loads(
                (saved.dataset_path / "manifest.json").read_text(encoding="utf-8")
            )

            self.assertTrue(raw_path.is_file())
            self.assertEqual(raw_path.read_bytes(), FIXTURE.read_bytes())
            self.assertTrue(manifest["raw_saved"])

    def test_existing_dataset_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / ".rag_lab"
            with mock.patch(
                "rag_lab.learning.storage.generate_id",
                side_effect=["ds_fixed", "run_first", "ds_fixed", "run_second"],
            ):
                first = self._save(workspace)
                original_manifest = (first.dataset_path / "manifest.json").read_bytes()
                with self.assertRaises(DatasetAlreadyExistsError):
                    self._save(workspace)

            self.assertEqual(
                (first.dataset_path / "manifest.json").read_bytes(), original_manifest
            )

    def test_pdf_changed_after_extraction_is_not_saved(self) -> None:
        from rag_lab.learning.storage import DatasetStorageError

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            changed_pdf = root / "changed.pdf"
            changed_pdf.write_bytes(FIXTURE.read_bytes())
            extraction = extract_pdf(changed_pdf, document_id="changed")
            chunks = chunk_source_document(extraction.document)
            changed_pdf.write_bytes(changed_pdf.read_bytes() + b"changed")

            with self.assertRaisesRegex(DatasetStorageError, "変更された"):
                save_pdf_lab1_dataset(
                    root / ".rag_lab",
                    changed_pdf,
                    extraction,
                    chunks,
                    prediction="予想",
                    observation="観察",
                )

            self.assertFalse((root / ".rag_lab").exists())


if __name__ == "__main__":
    unittest.main()
