from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from .source_documents import ContentBlock, SourceDocument, SourcePage
from .text import normalize_text


PDF_MEDIA_TYPE = "application/pdf"
MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_PDF_PAGES = 200
SHORT_PAGE_CHARACTERS = 20
EMPTY_PAGE_REVIEW_RATIO = 0.20
PDF_SIGNATURE = b"%PDF-"
DOCUMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

PdfStatus = Literal["ok", "needs_review", "OCR_REQUIRED"]


class PdfIngestError(Exception):
    """Base exception with a learner-safe message for PDF ingestion."""


class PdfDependencyError(PdfIngestError):
    pass


class PdfValidationError(PdfIngestError):
    pass


@dataclass(frozen=True)
class PdfWarning:
    code: str
    message: str
    page: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PdfExtractionResult:
    document: SourceDocument
    status: PdfStatus
    page_character_counts: tuple[int, ...]
    warnings: tuple[PdfWarning, ...]

    @property
    def empty_page_count(self) -> int:
        return sum(count == 0 for count in self.page_character_counts)

    def summary(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "document_id": self.document.document_id,
            "pages": len(self.document.pages),
            "empty_pages": self.empty_page_count,
            "page_character_counts": list(self.page_character_counts),
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


def validate_document_id(document_id: str) -> None:
    if not DOCUMENT_ID_RE.fullmatch(document_id):
        raise PdfValidationError(
            "document_id は英数字で始め、英数字・ハイフン・"
            "アンダースコアの64文字以内で指定してください"
        )


def _load_pypdf() -> Any:
    try:
        import pypdf
    except ImportError as error:
        raise PdfDependencyError(
            "PDF機能が未導入です。"
            "python -m pip install -e '.[pdf]' を実行してください"
        ) from error
    return pypdf


def _validate_pdf_file(path: Path, max_bytes: int) -> int:
    if not path.is_file():
        raise PdfValidationError(f"PDFファイルが見つかりません: {path}")
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            signature = handle.read(len(PDF_SIGNATURE))
    except OSError as error:
        raise PdfValidationError("PDFファイルを読み取れません") from error
    if size > max_bytes:
        raise PdfValidationError(
            f"PDFがサイズ上限を超えています: {size} bytes / {max_bytes} bytes"
        )
    if signature != PDF_SIGNATURE:
        raise PdfValidationError("PDFシグネチャを確認できません")
    return size


def _open_reader(path: Path, pypdf: Any) -> Any:
    reader_logger = logging.getLogger("pypdf._reader")
    was_disabled = reader_logger.disabled
    try:
        reader_logger.disabled = True
        reader = pypdf.PdfReader(str(path), strict=False)
        if reader.is_encrypted:
            raise PdfValidationError("暗号化PDFには対応していません")
        return reader
    except PdfValidationError:
        raise
    except Exception as error:
        raise PdfValidationError(
            "PDFを解析できません。破損していないか確認してください"
        ) from error
    finally:
        reader_logger.disabled = was_disabled


def extract_pdf(
    path: Path,
    *,
    document_id: str,
    title: str | None = None,
    source: str | None = None,
    classification: str = "user_provided",
    note: str = "",
    max_bytes: int = MAX_PDF_BYTES,
    max_pages: int = MAX_PDF_PAGES,
) -> PdfExtractionResult:
    """Extract an unencrypted text-layer PDF into the common source model."""

    validate_document_id(document_id)
    file_size = _validate_pdf_file(path, max_bytes)
    pypdf = _load_pypdf()
    reader = _open_reader(path, pypdf)

    page_count = len(reader.pages)
    if page_count > max_pages:
        raise PdfValidationError(
            f"PDFがページ数上限を超えています: {page_count} pages / {max_pages} pages"
        )
    if page_count == 0:
        raise PdfValidationError("PDFにページがありません")

    pages: list[SourcePage] = []
    counts: list[int] = []
    warnings: list[PdfWarning] = []
    try:
        for page_number, pdf_page in enumerate(reader.pages, start=1):
            text = normalize_text(pdf_page.extract_text() or "")
            character_count = len(text.replace(" ", "").replace("\n", ""))
            counts.append(character_count)

            blocks: list[ContentBlock] = []
            if text:
                blocks.append(
                    ContentBlock(
                        block_id=f"{document_id}:p{page_number}:b001",
                        kind="text",
                        text=text,
                        section="本文",
                        extraction_method="pypdf",
                    )
                )
            pages.append(SourcePage(page=page_number, blocks=blocks))

            if character_count == 0:
                warnings.append(
                    PdfWarning(
                        code="EMPTY_PAGE",
                        page=page_number,
                        message="このページから文字を抽出できませんでした",
                    )
                )
            if character_count < SHORT_PAGE_CHARACTERS:
                warnings.append(
                    PdfWarning(
                        code="SHORT_PAGE",
                        page=page_number,
                        message=(
                            f"抽出文字数が{SHORT_PAGE_CHARACTERS}文字未満です"
                        ),
                    )
                )
    except Exception as error:
        raise PdfValidationError("PDFのテキスト抽出に失敗しました") from error

    empty_pages = sum(count == 0 for count in counts)
    if empty_pages == page_count:
        status: PdfStatus = "OCR_REQUIRED"
        warnings.append(
            PdfWarning(
                code="OCR_REQUIRED",
                message=(
                    "文書全体から文字を抽出できませんでした。"
                    "スキャンPDFのOCRは後続機能です"
                ),
            )
        )
    elif empty_pages / page_count >= EMPTY_PAGE_REVIEW_RATIO:
        status = "needs_review"
        warnings.append(
            PdfWarning(
                code="HIGH_EMPTY_PAGE_RATIO",
                message=(
                    "空ページ率が20%以上です。抽出結果を確認してください"
                ),
            )
        )
    else:
        status = "ok"

    metadata: dict[str, Any] = {
        "classification": classification,
        "original_filename": path.name,
        "file_size_bytes": file_size,
        "page_count": page_count,
        "extractor": "pypdf",
        "extractor_version": pypdf.__version__,
    }
    if note:
        metadata["note"] = note

    document = SourceDocument(
        document_id=document_id,
        title=title or path.stem,
        source=source or path.name,
        media_type=PDF_MEDIA_TYPE,
        metadata=metadata,
        pages=pages,
    )
    return PdfExtractionResult(
        document=document,
        status=status,
        page_character_counts=tuple(counts),
        warnings=tuple(warnings),
    )


class PdfSourceAdapter:
    """Adapter for local, unencrypted PDFs with a text layer."""

    def supports(self, media_type: str, filename: str) -> bool:
        return media_type == PDF_MEDIA_TYPE and filename.lower().endswith(".pdf")

    def extract(self, path: Path, **metadata: Any) -> SourceDocument:
        return extract_pdf(path, **metadata).document
