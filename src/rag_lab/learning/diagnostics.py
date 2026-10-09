from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAX_REPORT_BYTES = 5 * 1024 * 1024
CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
REPORT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}\.json$")
METRIC_KEYS = (
    "retrieval_hit_rate",
    "citation_hit_rate",
    "keyword_recall",
    "answerability_accuracy",
)
METRIC_LABELS = {
    "retrieval_hit_rate": "検索ヒット率",
    "citation_hit_rate": "引用ヒット率",
    "keyword_recall": "必須語再現率",
    "answerability_accuracy": "回答可能性精度",
}
FAILURE_LABELS = {
    "retrieval_miss": "検索",
    "citation_miss": "引用",
    "keyword_miss": "回答内容",
    "answerability_error": "回答可能性",
}
HINTS = {
    "retrieval_miss": (
        "正解文書が検索上位に含まれていません。",
        "文書加工、質問語、検索方式、top-kのどこで候補を失ったか確認します。",
        "同じ質問でdense・BM25・hybridを比較し、変更は1項目だけにします。",
    ),
    "citation_miss": (
        "正解文書が引用に含まれていません。",
        "検索結果に正解があるなら、生成または引用選択の問題と考えられます。",
        "取得チャンクと引用チャンクを照合し、回答文の根拠を1文ずつ確認します。",
    ),
    "keyword_miss": (
        "期待する必須語の一部が回答にありません。",
        "根拠は取得できても、必要な文や数値を生成器が選べていない可能性があります。",
        "正解チャンク内の必要文を確認し、チャンク境界か生成規則の片方だけを変更します。",
    ),
    "answerability_error": (
        "回答可能・回答不能の判定が期待と異なります。",
        "単語の一致だけを根拠とし、質問へ直接答える証拠を確認できていない可能性があります。",
        "回答不能問題を追加し、直接的な根拠がない場合の拒否条件を検証します。",
    ),
}


class DiagnosticReportError(Exception):
    """Raised when a local evaluation report is unsafe or malformed."""


@dataclass(frozen=True)
class DiagnosticCase:
    case_id: str
    question: str
    expected_answerable: bool
    predicted_answerable: bool
    retrieval_hit: bool
    citation_hit: bool
    keyword_recall: float
    refusal_correct: bool

    @property
    def failure_codes(self) -> tuple[str, ...]:
        failures: list[str] = []
        if not self.retrieval_hit:
            failures.append("retrieval_miss")
        if not self.citation_hit:
            failures.append("citation_miss")
        if self.keyword_recall < 1.0:
            failures.append("keyword_miss")
        if not self.refusal_correct:
            failures.append("answerability_error")
        return tuple(failures)


@dataclass(frozen=True)
class EvaluationReport:
    name: str
    summary: dict[str, float | int]
    cases: tuple[DiagnosticCase, ...]

    @property
    def failed_cases(self) -> tuple[DiagnosticCase, ...]:
        return tuple(case for case in self.cases if case.failure_codes)


@dataclass(frozen=True)
class ReportComparison:
    metric_deltas: dict[str, float]
    resolved_case_ids: tuple[str, ...]
    new_failure_case_ids: tuple[str, ...]


def list_report_paths(report_dir: Path) -> tuple[Path, ...]:
    if not report_dir.is_dir():
        return ()
    return tuple(
        path
        for path in sorted(report_dir.glob("*.json"))
        if path.is_file()
        and not path.is_symlink()
        and REPORT_NAME_RE.fullmatch(path.name)
    )


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DiagnosticReportError(f"{field}は数値で指定してください")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise DiagnosticReportError(f"{field}は0〜1で指定してください")
    return result


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise DiagnosticReportError(f"{field}は真偽値で指定してください")
    return value


def evaluation_report_from_value(name: str, value: Any) -> EvaluationReport:
    """Validate an evaluation value and retain only diagnostic-safe fields."""

    if not REPORT_NAME_RE.fullmatch(name):
        raise DiagnosticReportError("評価レポート名が不正です")
    if not isinstance(value, dict):
        raise DiagnosticReportError("評価レポートのルートはJSONオブジェクトが必要です")

    summary_value = value.get("summary")
    details_value = value.get("details")
    if not isinstance(summary_value, dict) or not isinstance(details_value, list):
        raise DiagnosticReportError("summaryまたはdetailsの形式が不正です")
    examples = summary_value.get("examples")
    if isinstance(examples, bool) or not isinstance(examples, int) or examples < 1:
        raise DiagnosticReportError("summary.examplesは1以上の整数が必要です")
    summary: dict[str, float | int] = {"examples": examples}
    for key in METRIC_KEYS:
        summary[key] = _number(summary_value.get(key), f"summary.{key}")

    cases: list[DiagnosticCase] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(details_value, start=1):
        if not isinstance(item, dict):
            raise DiagnosticReportError(f"details[{index}]の形式が不正です")
        case_id = item.get("id")
        question = item.get("question")
        if (
            not isinstance(case_id, str)
            or not CASE_ID_RE.fullmatch(case_id)
            or case_id in seen_ids
        ):
            raise DiagnosticReportError("各detailsには一意なidが必要です")
        if (
            not isinstance(question, str)
            or not question.strip()
            or len(question) > 2_000
        ):
            raise DiagnosticReportError(f"{case_id}のquestionが不正です")
        seen_ids.add(case_id)
        cases.append(
            DiagnosticCase(
                case_id=case_id,
                question=question,
                expected_answerable=_boolean(
                    item.get("expected_answerable"),
                    f"{case_id}.expected_answerable",
                ),
                predicted_answerable=_boolean(
                    item.get("predicted_answerable"),
                    f"{case_id}.predicted_answerable",
                ),
                retrieval_hit=_boolean(
                    item.get("retrieval_hit"), f"{case_id}.retrieval_hit"
                ),
                citation_hit=_boolean(
                    item.get("citation_hit"), f"{case_id}.citation_hit"
                ),
                keyword_recall=_number(
                    item.get("keyword_recall"), f"{case_id}.keyword_recall"
                ),
                refusal_correct=_boolean(
                    item.get("refusal_correct"), f"{case_id}.refusal_correct"
                ),
            )
        )
    if len(cases) != examples:
        raise DiagnosticReportError("summary.examplesとdetails件数が一致しません")
    return EvaluationReport(name=name, summary=summary, cases=tuple(cases))


def load_evaluation_report(path: Path, report_dir: Path) -> EvaluationReport:
    root = report_dir.resolve()
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise DiagnosticReportError("評価レポートを読み取れません") from error
    if (
        resolved.parent != root
        or not REPORT_NAME_RE.fullmatch(resolved.name)
        or path.is_symlink()
    ):
        raise DiagnosticReportError("reports直下のJSONだけを読み込めます")
    try:
        if resolved.stat().st_size > MAX_REPORT_BYTES:
            raise DiagnosticReportError("評価レポートが5 MBを超えています")
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DiagnosticReportError("評価レポートのJSON形式が不正です") from error
    return evaluation_report_from_value(resolved.name, value)


def compare_reports(
    baseline: EvaluationReport, candidate: EvaluationReport
) -> ReportComparison:
    baseline_cases = {case.case_id: case for case in baseline.cases}
    candidate_cases = {case.case_id: case for case in candidate.cases}
    if set(baseline_cases) != set(candidate_cases):
        raise DiagnosticReportError("比較するレポートの問題IDが一致しません")
    baseline_failed = {
        case.case_id for case in baseline.cases if case.failure_codes
    }
    candidate_failed = {
        case.case_id for case in candidate.cases if case.failure_codes
    }
    deltas = {
        key: round(float(candidate.summary[key]) - float(baseline.summary[key]), 4)
        for key in METRIC_KEYS
    }
    return ReportComparison(
        metric_deltas=deltas,
        resolved_case_ids=tuple(sorted(baseline_failed - candidate_failed)),
        new_failure_case_ids=tuple(sorted(candidate_failed - baseline_failed)),
    )


def hints_for_case(case: DiagnosticCase, level: int) -> tuple[str, ...]:
    if level not in {1, 2, 3}:
        raise ValueError("ヒント段階は1〜3です")
    return tuple(HINTS[code][level - 1] for code in case.failure_codes)


def build_learning_report(
    baseline: EvaluationReport,
    *,
    candidate: EvaluationReport | None,
    observation: str,
    next_action: str,
) -> str:
    lines = [
        "# RAG評価 学習レポート",
        "",
        f"- 基準レポート: `{baseline.name}`",
        f"- 比較レポート: `{candidate.name}`" if candidate else "- 比較レポート: なし",
        "",
        "## 基準指標",
        "",
        "| 指標 | 値 |",
        "| --- | ---: |",
    ]
    for key in METRIC_KEYS:
        lines.append(f"| {METRIC_LABELS[key]} | {float(baseline.summary[key]):.4f} |")

    lines.extend(["", "## 失敗診断", ""])
    if baseline.failed_cases:
        lines.extend(("| 問題ID | 分類 |", "| --- | --- |"))
        for case in baseline.failed_cases:
            labels = "、".join(FAILURE_LABELS[code] for code in case.failure_codes)
            lines.append(f"| `{case.case_id}` | {labels} |")
    else:
        lines.append("失敗問題はありません。")

    if candidate is not None:
        comparison = compare_reports(baseline, candidate)
        lines.extend(
            [
                "",
                "## 変更前後の比較",
                "",
                "| 指標 | 差分 |",
                "| --- | ---: |",
            ]
        )
        for key in METRIC_KEYS:
            lines.append(f"| {METRIC_LABELS[key]} | {comparison.metric_deltas[key]:+.4f} |")
        resolved = "、".join(comparison.resolved_case_ids) or "なし"
        new_failures = "、".join(comparison.new_failure_case_ids) or "なし"
        lines.extend(("", f"- 改善した問題: {resolved}", f"- 新たな失敗: {new_failures}"))

    lines.extend(
        [
            "",
            "## 観察",
            "",
            observation.strip() or "未記入",
            "",
            "## 次に試すこと",
            "",
            next_action.strip() or "未記入",
            "",
        ]
    )
    return "\n".join(lines)


def save_learning_report(workspace: Path, content: str) -> Path:
    if not content.strip() or len(content) > 100_000:
        raise DiagnosticReportError("学習レポートの内容が不正です")
    report_dir = workspace / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    created = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = report_dir / f"diagnostic_{created}_{uuid.uuid4().hex[:8]}.md"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=report_dir
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except OSError as error:
        temporary_path.unlink(missing_ok=True)
        raise DiagnosticReportError("学習レポートを保存できません") from error
    return path
