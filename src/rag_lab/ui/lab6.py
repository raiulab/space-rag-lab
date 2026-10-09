from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import streamlit as st

from rag_lab.learning.datasets import LearningDatasetError, bundled_dataset
from rag_lab.learning.diagnostics import METRIC_KEYS, METRIC_LABELS, hints_for_case
from rag_lab.learning.experiments import LearningRunError
from rag_lab.learning.lab6 import (
    Lab6Configuration,
    Lab6Experiment,
    run_lab6_experiment,
    save_lab6_experiment,
)


RAW_DIR = Path("data/raw")
GOLD_PATH = Path("data/evaluation/gold.jsonl")
PROMPT_PATH = Path("prompts/answer_v2_grounded.txt")
PARAMETER_LABELS = {
    "search_mode": "検索方式",
    "top_k": "top-k",
    "dimension": "Embedding次元",
}


def _candidate_configuration(
    baseline: Lab6Configuration,
    changed_parameter: str,
) -> Lab6Configuration:
    if changed_parameter == "search_mode":
        value = st.selectbox(
            "変更後の検索方式",
            options=("dense", "bm25"),
            key="lab6_candidate_mode",
        )
    elif changed_parameter == "top_k":
        value = st.selectbox(
            "変更後のtop-k",
            options=(1, 3, 10),
            index=1,
            key="lab6_candidate_top_k",
        )
    else:
        value = st.selectbox(
            "変更後のEmbedding次元",
            options=(64, 128),
            key="lab6_candidate_dimension",
        )
    return replace(baseline, **{changed_parameter: value})


def _format_configuration(configuration: Lab6Configuration) -> str:
    return (
        f"search_mode={configuration.search_mode}, "
        f"top_k={configuration.top_k}, dimension={configuration.dimension}"
    )


def _render_metrics(experiment: Lab6Experiment) -> None:
    st.subheader("変更前後の評価値")
    for key in METRIC_KEYS:
        baseline = float(experiment.baseline_report.summary[key])
        candidate = float(experiment.candidate_report.summary[key])
        st.metric(
            METRIC_LABELS[key],
            f"{candidate:.1%}",
            delta=f"{candidate - baseline:+.1%}",
            help=f"変更前: {baseline:.1%}",
        )
    st.caption(
        f"同じ{experiment.baseline_report.summary['examples']}問を使用。"
        "矢印は変更後から変更前を引いた差です。"
    )


def _case_label(case_id: str, experiment: Lab6Experiment) -> str:
    cases = {case.case_id: case for case in experiment.candidate_report.cases}
    case = cases[case_id]
    return f"{case.case_id}: {case.question}"


def _render_failures(experiment: Lab6Experiment) -> None:
    comparison = experiment.comparison
    first, second = st.columns(2)
    first.write("改善した問題ID")
    first.code(", ".join(comparison.resolved_case_ids) or "なし")
    second.write("新たに失敗した問題ID")
    second.code(", ".join(comparison.new_failure_case_ids) or "なし")

    failed = experiment.candidate_report.failed_cases
    if not failed:
        st.success("変更後に失敗判定された問題はありません。")
        return
    st.subheader("変更後の失敗例")
    selected_id = st.selectbox(
        "観察する失敗例",
        options=[case.case_id for case in failed],
        format_func=lambda case_id: _case_label(case_id, experiment),
        key="lab6_failed_case",
    )
    selected = next(case for case in failed if case.case_id == selected_id)
    st.write("失敗分類: " + ", ".join(selected.failure_codes))
    level = st.radio(
        "ヒントの深さ",
        options=(1, 2, 3),
        horizontal=True,
        format_func=lambda value: {
            1: "観察ポイント",
            2: "原因の切り分け",
            3: "次の操作",
        }[value],
        key="lab6_hint_level",
    )
    for hint in hints_for_case(selected, level):
        st.info(hint)


def _render_save_form(
    workspace: Path,
    experiment: Lab6Experiment,
    *,
    prediction: str,
    hypothesis: str,
) -> None:
    st.subheader("考察を記録する")
    observation = st.text_area(
        "指標と失敗例の観察",
        placeholder="どの指標が変わり、どの問題が改善または維持されたか。",
        key="lab6_observation",
    )
    regression_note = st.text_area(
        "悪化例の有無と考察",
        placeholder="悪化例がない場合も、「なし」と判断した根拠を書きます。",
        key="lab6_regression_note",
    )
    next_action = st.text_area(
        "次に試す1項目",
        placeholder="今回とは別の条件を1つ選びます。",
        key="lab6_next_action",
    )
    can_save = all(
        value.strip() for value in (observation, regression_note, next_action)
    )
    if st.button(
        "Lab 6の学習記録を保存",
        type="primary",
        disabled=not can_save,
        key="save_lab6",
    ):
        try:
            saved = save_lab6_experiment(
                workspace,
                experiment,
                prediction=prediction,
                hypothesis=hypothesis,
                observation=observation,
                regression_note=regression_note,
                next_action=next_action,
            )
        except LearningRunError as error:
            st.error(str(error))
            return
        if saved.completion.completed:
            st.success(f"Lab 6を完了しました。run ID: {saved.run_id}")
        else:
            st.warning(f"状態は {saved.completion.status} です。")
        for check in saved.completion.checks:
            mark = "✅" if check.passed else "⬜"
            st.write(f"{mark} {check.message}")


def render_lab6(workspace: Path) -> None:
    st.header("Lab 6: 回答精度の評価・改善")
    st.markdown(
        "**学習目標:** 同じ問題セットで変更前後を比較し、"
        "改善と副作用を数字と失敗例で説明する。"
    )
    st.info(
        "この自動評価は、正解データ付きの付属データ10問"
        "（うち回答不能2問）を使います。外部APIは呼びません。"
    )
    try:
        dataset = bundled_dataset(RAW_DIR)
    except (LearningDatasetError, OSError, ValueError) as error:
        st.error(str(error))
        return

    baseline = Lab6Configuration()
    st.write(f"変更前（固定）: `{_format_configuration(baseline)}`")
    changed_parameter = st.selectbox(
        "変更する条件（1項目だけ）",
        options=("dimension", "search_mode", "top_k"),
        format_func=lambda value: PARAMETER_LABELS[value],
        key="lab6_changed_parameter",
    )
    candidate = _candidate_configuration(baseline, changed_parameter)
    st.write(f"変更後: `{_format_configuration(candidate)}`")
    prediction = st.text_area(
        "実行前の予想",
        placeholder="どの指標や失敗問題がどう変わると予想しますか？",
        key="lab6_prediction",
    )
    hypothesis = st.text_area(
        "1つの変更仮説",
        placeholder="なぜその1項目を変えると改善すると考えますか？",
        key="lab6_hypothesis",
    )
    if st.button(
        "変更前後を同じ10問で評価",
        disabled=not prediction.strip() or not hypothesis.strip(),
        key="run_lab6",
    ):
        try:
            st.session_state["lab6_experiment"] = run_lab6_experiment(
                dataset,
                baseline_configuration=baseline,
                candidate_configuration=candidate,
                changed_parameter=changed_parameter,
                gold_path=GOLD_PATH,
                prompt_path=PROMPT_PATH,
            )
            st.session_state["lab6_prediction_used"] = prediction
            st.session_state["lab6_hypothesis_used"] = hypothesis
        except (OSError, ValueError) as error:
            st.error(str(error))

    experiment = st.session_state.get("lab6_experiment")
    if isinstance(experiment, Lab6Experiment):
        _render_metrics(experiment)
        _render_failures(experiment)
        _render_save_form(
            workspace,
            experiment,
            prediction=st.session_state.get("lab6_prediction_used", prediction),
            hypothesis=st.session_state.get("lab6_hypothesis_used", hypothesis),
        )
