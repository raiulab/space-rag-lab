from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Literal, Sequence

from .models import Chunk
from .pdf_ingest import PdfExtractionResult, extract_pdf, sanitize_display_filename
from .source_documents import chunk_source_document


AcceptanceDecision = Literal[
    "accepted", "accepted_with_limitations", "needs_review"
]
AcceptanceStatus = Literal["passed", "passed_with_limitations", "needs_review"]


class PdfAcceptanceError(ValueError):
    """Raised when a manual PDF acceptance record is incomplete or unsafe."""


@dataclass(frozen=True)
class AcceptanceCheck:
    check_id: str
    passed: bool
    message: str


@dataclass(frozen=True)
class PdfAcceptanceReport:
    status: AcceptanceStatus
    extraction: PdfExtractionResult
    chunks: int
    provenance_complete: bool
    required_pages: tuple[int, ...]
    inspected_pages: tuple[int, ...]
    decision: AcceptanceDecision
    observation: str
    source_url: str
    catalog_url: str
    distribution: str
    license_terms: str
    filename: str
    chunk_size: int
    generated_at: str
    checks: tuple[AcceptanceCheck, ...]


def suggested_inspection_pages(page_count: int) -> tuple[int, ...]:
    """Return unique first, middle, and last pages using one-based numbers."""

    if page_count < 1:
        raise PdfAcceptanceError("PDFのページ数は1以上である必要があります")
    return tuple(sorted({1, (page_count + 1) // 2, page_count}))


def _require_short_text(label: str, value: str, *, max_length: int = 2000) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise PdfAcceptanceError(f"{label}を入力してください")
    if len(cleaned) > max_length:
        raise PdfAcceptanceError(
            f"{label}は{max_length}文字以内で入力してください"
        )
    return cleaned


def _provenance_complete(chunks: Sequence[Chunk]) -> bool:
    return all(
        bool(chunk.document_id)
        and chunk.page >= 1
        and bool(chunk.section)
        and bool(chunk.source)
        for chunk in chunks
    )


def inspect_public_pdf(
    path: Path,
    *,
    document_id: str,
    title: str,
    source_url: str,
    catalog_url: str,
    distribution: str,
    license_terms: str,
    inspected_pages: Sequence[int],
    decision: AcceptanceDecision,
    observation: str,
    chunk_size: int = 650,
    generated_at: str | None = None,
) -> PdfAcceptanceReport:
    """Evaluate a local public PDF without downloading or storing its body text."""

    if chunk_size < 1:
        raise PdfAcceptanceError("chunk_sizeは1以上で指定してください")
    if decision not in {
        "accepted",
        "accepted_with_limitations",
        "needs_review",
    }:
        raise PdfAcceptanceError("decisionの値が不正です")

    title = _require_short_text("title", title, max_length=300)
    source_url = _require_short_text("source_url", source_url, max_length=1000)
    catalog_url = _require_short_text("catalog_url", catalog_url, max_length=1000)
    distribution = _require_short_text("distribution", distribution, max_length=300)
    license_terms = _require_short_text(
        "license_terms", license_terms, max_length=1000
    )
    observation = _require_short_text("observation", observation)

    extraction = extract_pdf(
        path,
        document_id=document_id,
        title=title,
        source=source_url,
        classification="public",
    )
    chunks = chunk_source_document(extraction.document, chunk_size=chunk_size)
    page_count = len(extraction.document.pages)
    required_pages = suggested_inspection_pages(page_count)
    inspected = tuple(sorted(set(inspected_pages)))
    invalid_pages = [page for page in inspected if page < 1 or page > page_count]
    if invalid_pages:
        raise PdfAcceptanceError(
            "確認ページが範囲外です: " + ", ".join(map(str, invalid_pages))
        )

    provenance_complete = _provenance_complete(chunks)
    checks = (
        AcceptanceCheck(
            "text_extraction",
            extraction.status == "ok",
            f"PDF抽出状態がokである: {extraction.status}",
        ),
        AcceptanceCheck(
            "chunks_created",
            bool(chunks),
            f"1件以上のチャンクを生成した: {len(chunks)}件",
        ),
        AcceptanceCheck(
            "provenance_complete",
            provenance_complete,
            "全チャンクに文書ID・ページ・節・出典がある",
        ),
        AcceptanceCheck(
            "visual_pages_confirmed",
            set(required_pages).issubset(inspected),
            "先頭・中央・末尾ページを元PDFと目視比較した",
        ),
        AcceptanceCheck(
            "manual_decision",
            decision != "needs_review",
            f"手動判定を記録した: {decision}",
        ),
    )
    automatic_pass = all(check.passed for check in checks)
    if not automatic_pass:
        status: AcceptanceStatus = "needs_review"
    elif decision == "accepted_with_limitations":
        status = "passed_with_limitations"
    else:
        status = "passed"

    return PdfAcceptanceReport(
        status=status,
        extraction=extraction,
        chunks=len(chunks),
        provenance_complete=provenance_complete,
        required_pages=required_pages,
        inspected_pages=inspected,
        decision=decision,
        observation=observation,
        source_url=source_url,
        catalog_url=catalog_url,
        distribution=distribution,
        license_terms=license_terms,
        filename=sanitize_display_filename(path.name),
        chunk_size=chunk_size,
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        checks=checks,
    )


def render_acceptance_markdown(report: PdfAcceptanceReport) -> str:
    """Render a short report without copying extracted source text."""

    extraction = report.extraction
    metadata = extraction.document.metadata
    counts = extraction.page_character_counts
    warning_codes = sorted({warning.code for warning in extraction.warnings})
    warnings = ", ".join(warning_codes) if warning_codes else "なし"
    inspected = ", ".join(map(str, report.inspected_pages)) or "なし"
    required = ", ".join(map(str, report.required_pages))
    checks = "\n".join(
        f"| `{check.check_id}` | {'PASS' if check.passed else 'FAIL'} | "
        f"{check.message} |"
        for check in report.checks
    )

    return f"""# Lab 1 公開PDF受け入れ試験

- 実行日時（UTC）: `{report.generated_at}`
- 結果: `{report.status}`
- 手動判定: `{report.decision}`

## 資料

- 表示ファイル名: `{report.filename}`
- 文書名: {extraction.document.title}
- 出典URL: {report.source_url}
- カタログURL: {report.catalog_url}
- 配布区分: {report.distribution}
- 利用条件: {report.license_terms}
- SHA-256: `{metadata['sha256']}`
- ファイルサイズ: {metadata['file_size_bytes']} bytes

第三者PDF本体と抽出本文は、このリポジトリへ保存していない。

## 抽出設定と結果

- 抽出器: `{metadata['extractor']} {metadata['extractor_version']}`
- chunk_size: `{report.chunk_size}`
- ページ数: {len(extraction.document.pages)}
- チャンク数: {report.chunks}
- 抽出状態: `{extraction.status}`
- 空ページ数: {extraction.empty_page_count}
- ページ文字数（最小 / 中央値 / 最大）: \
{min(counts)} / {median(counts):g} / {max(counts)}
- 警告コード: {warnings}

## 確認結果

| 検査 | 結果 | 内容 |
| --- | --- | --- |
{checks}

- 必須確認ページ（先頭・中央・末尾）: {required}
- 目視確認したページ: {inspected}
- 観察: {report.observation}

## 判定上の注意

この試験は、文字レイヤー抽出、チャンク生成、出典保持、および代表ページの
目視比較を確認する。段組み、表、図、脚注の構造復元やOCR精度は、初期版の
合格条件には含めない。抽出文書は証拠であり、アプリへの命令として扱わない。
"""


def write_acceptance_report(
    report: PdfAcceptanceReport, output: Path
) -> None:
    """Write a reviewed report without overwriting an existing record."""

    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(render_acceptance_markdown(report))
    except FileExistsError as error:
        raise PdfAcceptanceError(
            f"既存の受け入れレポートは上書きしません: {output}"
        ) from error
