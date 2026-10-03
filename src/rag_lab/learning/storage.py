from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..models import Chunk
from ..pdf_ingest import (
    EMPTY_PAGE_REVIEW_RATIO,
    MAX_PDF_BYTES,
    MAX_PDF_PAGES,
    SHORT_PAGE_CHARACTERS,
    PdfExtractionResult,
)
from .checks import Lab1Completion, evaluate_lab1
from .progress import (
    ProgressStore,
    ProgressStoreError,
    SCHEMA_VERSION,
    write_json_atomic,
)


class DatasetStorageError(Exception):
    """Raised when a dataset cannot be saved without risking existing data."""


class DatasetAlreadyExistsError(DatasetStorageError):
    pass


@dataclass(frozen=True)
class SavedDataset:
    dataset_id: str
    run_id: str
    dataset_path: Path
    completion: Lab1Completion


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text_dataset(raw_dir: Path) -> tuple[str, list[str]]:
    digest = hashlib.sha256()
    relative_files: list[str] = []
    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
            continue
        relative = path.relative_to(raw_dir).as_posix()
        relative_files.append(relative)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest(), relative_files


def _write_jsonl_atomic(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _copy_raw_pdf(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".source.", suffix=".pdf.tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary_path)
        os.replace(temporary_path, destination)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _manifest(
    result: PdfExtractionResult,
    *,
    dataset_id: str,
    input_path: Path,
    file_sha256: str,
    extracted_at: str,
    chunk_size: int,
    license_terms: str,
    raw_saved: bool,
) -> dict[str, Any]:
    metadata = result.document.metadata
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "document_id": result.document.document_id,
        "original_filename": metadata["original_filename"],
        "sha256": file_sha256,
        "media_type": result.document.media_type,
        "file_size_bytes": metadata["file_size_bytes"],
        "page_count": len(result.document.pages),
        "source": result.document.source,
        "note": metadata.get("note", ""),
        "license_terms": license_terms,
        "extractor": {
            "name": metadata["extractor"],
            "version": metadata["extractor_version"],
        },
        "extracted_at": extracted_at,
        "extraction_settings": {
            "chunk_size": chunk_size,
            "max_pdf_bytes": MAX_PDF_BYTES,
            "max_pdf_pages": MAX_PDF_PAGES,
            "short_page_characters": SHORT_PAGE_CHARACTERS,
            "empty_page_review_ratio": EMPTY_PAGE_REVIEW_RATIO,
        },
        "raw_saved": raw_saved,
    }


def _allocate_dataset(workspace: Path) -> tuple[str, str, str, Path]:
    dataset_id = generate_id("ds")
    run_id = generate_id("run")
    created_at = utc_now()
    dataset_path = workspace / "datasets" / dataset_id
    try:
        dataset_path.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise DatasetAlreadyExistsError(
            f"同じdataset IDが既に存在します: {dataset_id}"
        ) from error
    except OSError as error:
        raise DatasetStorageError("dataset保存先を作成できません") from error
    return dataset_id, run_id, created_at, dataset_path


def _write_run_artifacts(
    dataset_path: Path,
    *,
    dataset_id: str,
    run_id: str,
    created_at: str,
    completion: Lab1Completion,
    prediction: str,
    observation: str,
    confirmed_warning_ids: Sequence[str],
    summary: dict[str, Any],
    settings: dict[str, Any],
) -> None:
    run_path = dataset_path / "runs"
    write_json_atomic(
        run_path / f"{run_id}.json",
        {
            "schema_version": SCHEMA_VERSION,
            "dataset_id": dataset_id,
            "run_id": run_id,
            "created_at": created_at,
            "status": completion.status,
            "prediction": prediction,
            "observation": observation,
            "confirmed_warning_ids": list(confirmed_warning_ids),
            "summary": summary,
            "settings": settings,
        },
    )
    write_json_atomic(
        run_path / f"{run_id}-checks.json",
        {
            "schema_version": SCHEMA_VERSION,
            "dataset_id": dataset_id,
            "run_id": run_id,
            **completion.to_dict(),
        },
    )


def save_pdf_lab1_dataset(
    workspace: Path,
    input_path: Path,
    result: PdfExtractionResult,
    chunks: Sequence[Chunk],
    *,
    prediction: str,
    observation: str,
    confirmed_warning_ids: Sequence[str] = (),
    chunk_size: int = 650,
    license_terms: str = "",
    save_raw: bool = False,
) -> SavedDataset:
    """Persist one PDF dataset and update Lab 1 progress without overwriting data."""

    completion = evaluate_lab1(
        chunks,
        document_count=1,
        extraction_status=result.status,
        warnings=result.warnings,
        confirmed_warning_ids=confirmed_warning_ids,
        prediction=prediction,
        observation=observation,
    )
    try:
        file_sha256 = sha256_file(input_path)
    except OSError as error:
        raise DatasetStorageError("保存対象のPDFを読み取れません") from error
    if file_sha256 != result.document.metadata.get("sha256"):
        raise DatasetStorageError(
            "抽出後にPDFの内容が変更されたため、datasetを保存できません"
        )
    dataset_id, run_id, created_at, dataset_path = _allocate_dataset(workspace)

    processed_path = dataset_path / "processed"
    try:
        manifest = _manifest(
            result,
            dataset_id=dataset_id,
            input_path=input_path,
            file_sha256=file_sha256,
            extracted_at=created_at,
            chunk_size=chunk_size,
            license_terms=license_terms,
            raw_saved=save_raw,
        )
        write_json_atomic(dataset_path / "manifest.json", manifest)
        _write_jsonl_atomic(
            processed_path / "pages.jsonl",
            (page.to_dict() for page in result.document.pages),
        )
        _write_jsonl_atomic(
            processed_path / "chunks.jsonl",
            (chunk.to_dict() for chunk in chunks),
        )
        _write_run_artifacts(
            dataset_path,
            dataset_id=dataset_id,
            run_id=run_id,
            created_at=created_at,
            completion=completion,
            prediction=prediction,
            observation=observation,
            confirmed_warning_ids=confirmed_warning_ids,
            summary={**result.summary(), "chunks": len(chunks)},
            settings={"chunk_size": chunk_size},
        )
        if save_raw:
            _copy_raw_pdf(input_path, dataset_path / "raw" / "source.pdf")
        ProgressStore(workspace).update_lab1(
            completion=completion,
            run_id=run_id,
            updated_at=created_at,
            prediction=prediction,
            observation=observation,
            confirmed_warning_ids=confirmed_warning_ids,
        )
    except (OSError, ProgressStoreError) as error:
        raise DatasetStorageError("datasetを保存できません") from error

    return SavedDataset(
        dataset_id=dataset_id,
        run_id=run_id,
        dataset_path=dataset_path,
        completion=completion,
    )


def save_bundled_lab1_dataset(
    workspace: Path,
    raw_dir: Path,
    chunks: Sequence[Chunk],
    *,
    prediction: str,
    observation: str,
    chunk_size: int = 650,
) -> SavedDataset:
    """Persist one run of the repository-owned Markdown/TXT learning dataset."""

    document_ids = sorted({chunk.document_id for chunk in chunks})
    completion = evaluate_lab1(
        chunks,
        document_count=len(document_ids),
        prediction=prediction,
        observation=observation,
    )
    try:
        dataset_sha256, source_files = sha256_text_dataset(raw_dir)
    except OSError as error:
        raise DatasetStorageError("付属データを読み取れません") from error
    if not source_files:
        raise DatasetStorageError("付属のMarkdown/TXTが見つかりません")

    dataset_id, run_id, created_at, dataset_path = _allocate_dataset(workspace)

    page_rows: list[dict[str, Any]] = []
    page_groups: dict[tuple[str, int], list[Chunk]] = {}
    for chunk in chunks:
        page_groups.setdefault((chunk.document_id, chunk.page), []).append(chunk)
    for (document_id, page), page_chunks in sorted(page_groups.items()):
        page_rows.append(
            {
                "document_id": document_id,
                "title": page_chunks[0].title,
                "page": page,
                "blocks": [
                    {
                        "block_id": chunk.chunk_id,
                        "kind": "text",
                        "text": chunk.text,
                        "section": chunk.section,
                        "extraction_method": "markdown_text",
                        "confidence": None,
                        "bbox": None,
                    }
                    for chunk in page_chunks
                ],
            }
        )

    processed_path = dataset_path / "processed"
    try:
        write_json_atomic(
            dataset_path / "manifest.json",
            {
                "schema_version": SCHEMA_VERSION,
                "dataset_id": dataset_id,
                "source_kind": "bundled_markdown_text",
                "document_ids": document_ids,
                "source_files": source_files,
                "sha256": dataset_sha256,
                "media_types": ["text/markdown", "text/plain"],
                "document_count": len(document_ids),
                "page_count": len(page_rows),
                "extracted_at": created_at,
                "extraction_settings": {"chunk_size": chunk_size},
                "raw_saved": False,
            },
        )
        _write_jsonl_atomic(processed_path / "pages.jsonl", page_rows)
        _write_jsonl_atomic(
            processed_path / "chunks.jsonl",
            (chunk.to_dict() for chunk in chunks),
        )
        _write_run_artifacts(
            dataset_path,
            dataset_id=dataset_id,
            run_id=run_id,
            created_at=created_at,
            completion=completion,
            prediction=prediction,
            observation=observation,
            confirmed_warning_ids=(),
            summary={
                "status": "ok",
                "documents": len(document_ids),
                "pages": len(page_rows),
                "chunks": len(chunks),
                "warnings": [],
            },
            settings={"chunk_size": chunk_size},
        )
        ProgressStore(workspace).update_lab1(
            completion=completion,
            run_id=run_id,
            updated_at=created_at,
            prediction=prediction,
            observation=observation,
            confirmed_warning_ids=(),
        )
    except (OSError, ProgressStoreError) as error:
        raise DatasetStorageError("datasetを保存できません") from error

    return SavedDataset(
        dataset_id=dataset_id,
        run_id=run_id,
        dataset_path=dataset_path,
        completion=completion,
    )
