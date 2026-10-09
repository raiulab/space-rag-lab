from __future__ import annotations

from pathlib import Path

import streamlit as st

from rag_lab.learning.diagnostics import (
    FAILURE_LABELS,
    METRIC_KEYS,
    METRIC_LABELS,
    DiagnosticReportError,
    EvaluationReport,
    build_learning_report,
    compare_reports,
    hints_for_case,
    list_report_paths,
    load_evaluation_report,
    save_learning_report,
)


def _load_report(path: Path, report_dir: Path) -> EvaluationReport | None:
    try:
        return load_evaluation_report(path, report_dir)
    except DiagnosticReportError as error:
        st.error(str(error))
        return None


def _render_summary(report: EvaluationReport) -> None:
    st.subheader("評価値を確認する")
    columns = st.columns(4)
    for column, key in zip(columns, METRIC_KEYS):
        column.metric(METRIC_LABELS[key], f"{float(report.summary[key]):.2f}")
    st.caption(
        f"{int(report.summary['examples'])}問中、"
        f"{len(report.failed_cases)}問に確認すべき指標があります。"
    )


def _render_failures(report: EvaluationReport) -> None:
    st.subheader("失敗問題を診断する")
    if not report.failed_cases:
        st.success("このレポートには失敗問題がありません。")
        return

    for case in report.failed_cases:
        labels = " / ".join(FAILURE_LABELS[code] for code in case.failure_codes)
        st.write(f"- `{case.case_id}` — {labels}")

    case_options = {
        f"{case.case_id}: {case.question}": case for case in report.failed_cases
    }
    selected = st.selectbox(
        "詳しく見る失敗問題",
        options=list(case_options),
        key="diagnostic_case",
    )
    case = case_options[selected]
    st.markdown(f"**質問:** {case.question}")
    st.write(
        "期待: "
        f"{'回答可能' if case.expected_answerable else '回答不能'} / "
        "実際: "
        f"{'回答可能' if case.predicted_answerable else '回答不能'}"
    )
    level_labels = {
        "1. 観察ポイント": 1,
        "2. 原因の切り分け": 2,
        "3. 次の操作": 3,
    }
    selected_level = st.radio(
        "ヒント段階",
        options=list(level_labels),
        horizontal=True,
        key="diagnostic_hint_level",
    )
    for hint in hints_for_case(case, level_labels[selected_level]):
        st.info(hint)


def _render_comparison(
    baseline: EvaluationReport,
    paths: tuple[Path, ...],
    report_dir: Path,
) -> EvaluationReport | None:
    st.subheader("変更前後を比較する")
    candidates = [path for path in paths if path.name != baseline.name]
    if not candidates:
        st.info(
            "比較用レポートがまだありません。次のように条件を1つだけ変えて作成します。"
        )
        st.code(
            "rag-lab evaluate --mode dense --report reports/dense.json\n"
            "rag-lab evaluate --mode hybrid --report reports/hybrid.json"
        )
        return None

    selected_name = st.selectbox(
        "比較レポート",
        options=[path.name for path in candidates],
        key="diagnostic_candidate",
    )
    candidate_path = next(path for path in candidates if path.name == selected_name)
    candidate = _load_report(candidate_path, report_dir)
    if candidate is None:
        return None
    try:
        comparison = compare_reports(baseline, candidate)
    except DiagnosticReportError as error:
        st.warning(str(error))
        return None

    columns = st.columns(4)
    for column, key in zip(columns, METRIC_KEYS):
        delta = comparison.metric_deltas[key]
        column.metric(
            METRIC_LABELS[key],
            f"{float(candidate.summary[key]):.2f}",
            delta=f"{delta:+.2f}",
        )
    resolved = "、".join(comparison.resolved_case_ids) or "なし"
    new_failures = "、".join(comparison.new_failure_case_ids) or "なし"
    st.write(f"改善した問題: {resolved}")
    if comparison.new_failure_case_ids:
        st.warning(f"新たな失敗: {new_failures}")
    else:
        st.write("新たな失敗: なし")
    return candidate


def _render_learning_report(
    workspace: Path,
    baseline: EvaluationReport,
    candidate: EvaluationReport | None,
) -> None:
    st.subheader("学習レポートを残す")
    observation = st.text_area(
        "診断から分かったこと",
        placeholder="どの工程に問題があり、どの証拠からそう考えたかを書きます。",
        key="diagnostic_observation",
    )
    next_action = st.text_area(
        "次に1つだけ試すこと",
        placeholder="例: 検索方式だけをhybridからBM25へ変えて同じ10問を再評価する。",
        key="diagnostic_next_action",
    )
    st.caption("APIキー、認証情報、個人情報、非公開文書の本文は記入しません。")
    content = build_learning_report(
        baseline,
        candidate=candidate,
        observation=observation,
        next_action=next_action,
    )
    st.download_button(
        "Markdownをダウンロード",
        data=content,
        file_name="rag_evaluation_learning_report.md",
        mime="text/markdown",
        disabled=not observation.strip() or not next_action.strip(),
    )
    if st.button(
        "ローカル学習記録へ保存",
        type="primary",
        disabled=not observation.strip() or not next_action.strip(),
        key="save_diagnostic_report",
    ):
        try:
            path = save_learning_report(workspace, content)
        except DiagnosticReportError as error:
            st.error(str(error))
            return
        st.success(f"学習レポートを保存しました: {path}")


def render_diagnostics(workspace: Path, report_dir: Path) -> None:
    st.header("診断・比較: 評価結果から次の実験を決める")
    st.markdown(
        "**学習目標:** 評価値の平均だけで判断せず、失敗問題を工程別に分類し、"
        "変更を1つに絞って改善と副作用を比較する。"
    )
    paths = list_report_paths(report_dir)
    if not paths:
        st.info("評価レポートがありません。まず `rag-lab all` を実行してください。")
        st.code("rag-lab all")
        return

    selected_name = st.selectbox(
        "基準レポート",
        options=[path.name for path in paths],
        key="diagnostic_baseline",
    )
    selected_path = next(path for path in paths if path.name == selected_name)
    baseline = _load_report(selected_path, report_dir)
    if baseline is None:
        return

    _render_summary(baseline)
    _render_failures(baseline)
    candidate = _render_comparison(baseline, paths, report_dir)
    _render_learning_report(workspace, baseline, candidate)
