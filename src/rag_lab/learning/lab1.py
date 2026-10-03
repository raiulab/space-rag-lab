from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..ingest import collect_chunks
from ..models import Chunk
from ..pdf_ingest import (
    MAX_PDF_BYTES,
    PdfExtractionResult,
    PdfValidationError,
    extract_pdf,
    sanitize_display_filename,
)
from ..source_documents import chunk_source_document
from .storage import (
    SavedDataset,
    save_bundled_lab1_dataset,
    save_pdf_lab1_dataset,
)


@dataclass(frozen=True)
class PreparedPdfLab1:
    filename: str
    file_bytes: bytes
    extraction: PdfExtractionResult
    chunks: tuple[Chunk, ...]
    chunk_size: int


@dataclass(frozen=True)
class PreparedBundledLab1:
    raw_dir: Path
    chunks: tuple[Chunk, ...]
    document_count: int
    page_count: int
    chunk_size: int


def safe_display_filename(filename: str) -> str:
    """Keep an upload name for display without ever using it as a save path."""

    return sanitize_display_filename(filename)


def prepare_pdf_upload(
    file_bytes: bytes,
    filename: str,
    *,
    document_id: str,
    title: str | None = None,
    source: str | None = None,
    classification: str = "user_provided",
    note: str = "",
    chunk_size: int = 650,
) -> PreparedPdfLab1:
    """Validate and extract uploaded bytes in an isolated temporary directory."""

    if len(file_bytes) > MAX_PDF_BYTES:
        raise PdfValidationError(
            f"PDFがサイズ上限を超えています: {len(file_bytes)} bytes / "
            f"{MAX_PDF_BYTES} bytes"
        )
    display_filename = safe_display_filename(filename)
    with tempfile.TemporaryDirectory(prefix="rag-lab-pdf-") as directory:
        temporary_pdf = Path(directory) / "source.pdf"
        temporary_pdf.write_bytes(file_bytes)
        extraction = extract_pdf(
            temporary_pdf,
            document_id=document_id,
            title=title,
            source=source,
            classification=classification,
            note=note,
            original_filename=display_filename,
        )
    chunks = tuple(chunk_source_document(extraction.document, chunk_size=chunk_size))
    return PreparedPdfLab1(
        filename=display_filename,
        file_bytes=file_bytes,
        extraction=extraction,
        chunks=chunks,
        chunk_size=chunk_size,
    )


def save_prepared_pdf(
    workspace: Path,
    prepared: PreparedPdfLab1,
    *,
    prediction: str,
    observation: str,
    confirmed_warning_ids: tuple[str, ...] = (),
    license_terms: str = "",
    save_raw: bool = False,
) -> SavedDataset:
    """Save a prepared upload, reconstructing only a fixed-name temporary file."""

    with tempfile.TemporaryDirectory(prefix="rag-lab-pdf-") as directory:
        temporary_pdf = Path(directory) / "source.pdf"
        temporary_pdf.write_bytes(prepared.file_bytes)
        return save_pdf_lab1_dataset(
            workspace,
            temporary_pdf,
            prepared.extraction,
            prepared.chunks,
            prediction=prediction,
            observation=observation,
            confirmed_warning_ids=confirmed_warning_ids,
            chunk_size=prepared.chunk_size,
            license_terms=license_terms,
            save_raw=save_raw,
        )


def prepare_bundled_data(
    raw_dir: Path = Path("data/raw"), chunk_size: int = 650
) -> PreparedBundledLab1:
    try:
        chunks = tuple(collect_chunks(raw_dir, chunk_size=chunk_size))
    except (OSError, UnicodeError) as error:
        raise ValueError("付属文書を読み取れません") from error
    if not chunks:
        raise ValueError(f"付属文書が見つかりません: {raw_dir}")
    return PreparedBundledLab1(
        raw_dir=raw_dir,
        chunks=chunks,
        document_count=len({chunk.document_id for chunk in chunks}),
        page_count=len({(chunk.document_id, chunk.page) for chunk in chunks}),
        chunk_size=chunk_size,
    )


def save_prepared_bundled(
    workspace: Path,
    prepared: PreparedBundledLab1,
    *,
    prediction: str,
    observation: str,
) -> SavedDataset:
    return save_bundled_lab1_dataset(
        workspace,
        prepared.raw_dir,
        prepared.chunks,
        prediction=prediction,
        observation=observation,
        chunk_size=prepared.chunk_size,
    )
