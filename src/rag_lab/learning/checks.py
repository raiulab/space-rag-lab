from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Sequence

from ..models import Chunk
from ..pdf_ingest import PdfStatus, PdfWarning


ProgressStatus = Literal["not_started", "in_progress", "needs_review", "completed"]


@dataclass(frozen=True)
class Lab1Check:
    code: str
    passed: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Lab1Completion:
    status: ProgressStatus
    checks: tuple[Lab1Check, ...]

    @property
    def completed(self) -> bool:
        return self.status == "completed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "completed": self.completed,
            "checks": [check.to_dict() for check in self.checks],
        }


def warning_id(warning: PdfWarning) -> str:
    location = f"p{warning.page}" if warning.page is not None else "document"
    return f"{warning.code}:{location}"


def _check(code: str, passed: bool, success: str, failure: str) -> Lab1Check:
    return Lab1Check(code=code, passed=passed, message=success if passed else failure)


def evaluate_lab1(
    chunks: Sequence[Chunk],
    *,
    document_count: int,
    extraction_status: PdfStatus = "ok",
    warnings: Sequence[PdfWarning] = (),
    confirmed_warning_ids: Sequence[str] = (),
    prediction: str = "",
    observation: str = "",
) -> Lab1Completion:
    """Evaluate Lab 1 evidence instead of completing it from a button click."""

    confirmed = set(confirmed_warning_ids)
    warning_ids = {warning_id(warning) for warning in warnings}
    warning_reviewed = not warning_ids or bool(warning_ids & confirmed)

    data_checks = (
        _check(
            "documents_present",
            document_count >= 1,
            "1件以上の文書を処理しました",
            "処理済み文書がありません",
        ),
        _check(
            "chunks_present",
            len(chunks) >= 1,
            "1件以上のチャンクを生成しました",
            "チャンクが生成されていません",
        ),
        _check(
            "document_ids_present",
            bool(chunks) and all(chunk.document_id.strip() for chunk in chunks),
            "全チャンクにdocument_idがあります",
            "document_idがないチャンクがあります",
        ),
        _check(
            "pages_valid",
            bool(chunks) and all(chunk.page >= 1 for chunk in chunks),
            "全チャンクのpageが1以上です",
            "pageが不正なチャンクがあります",
        ),
        _check(
            "sections_present",
            bool(chunks) and all(chunk.section.strip() for chunk in chunks),
            "全チャンクにsectionがあります",
            "sectionがないチャンクがあります",
        ),
        _check(
            "sources_present",
            bool(chunks) and all(chunk.source.strip() for chunk in chunks),
            "全チャンクにsourceがあります",
            "sourceがないチャンクがあります",
        ),
        _check(
            "traceable",
            bool(chunks)
            and all(chunk.chunk_id.strip() and chunk.page >= 1 for chunk in chunks),
            "チャンクから元文書とページへ追跡できます",
            "元文書またはページへ追跡できないチャンクがあります",
        ),
    )
    learning_checks = (
        _check(
            "prediction_recorded",
            bool(prediction.strip()),
            "実行前の予想を記録しました",
            "実行前の予想が未記録です",
        ),
        _check(
            "observation_recorded",
            bool(observation.strip()),
            "実行後の観察を記録しました",
            "実行後の観察が未記録です",
        ),
        _check(
            "warning_reviewed",
            warning_reviewed,
            "警告なし、または警告を1件以上確認しました",
            "警告を1件以上確認してください",
        ),
        _check(
            "ocr_not_required",
            extraction_status != "OCR_REQUIRED",
            "文字レイヤーを抽出できました",
            "文字を抽出できないためOCRが必要です",
        ),
    )
    checks = data_checks + learning_checks

    if extraction_status == "OCR_REQUIRED" or not all(
        check.passed for check in data_checks
    ):
        status: ProgressStatus = "needs_review"
    elif not warning_reviewed:
        status = "needs_review"
    elif not all(check.passed for check in learning_checks[:2]):
        status = "in_progress"
    else:
        status = "completed"
    return Lab1Completion(status=status, checks=checks)
