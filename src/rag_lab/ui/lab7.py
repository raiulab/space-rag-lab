from __future__ import annotations

from pathlib import Path

import streamlit as st

from rag_lab.learning.experiments import LearningRunError
from rag_lab.learning.lab7 import (
    Lab7Experiment,
    PromptAnalysis,
    run_lab7_experiment,
    save_lab7_experiment,
)


PROMPT_V1_PATH = Path("prompts/answer_v1.txt")
PROMPT_V2_PATH = Path("prompts/answer_v2_grounded.txt")
JSON_SUFFIX = """

7. 出力はJSONオブジェクトのみにする。
8. 必須キーはanswer（文字列）、answerable（真偽値）、citations（chunk_id文字列の配列）とする。
9. 回答不能の場合はanswerを固定応答、answerableをfalse、citationsを空配列にする。
""".strip()
DEFAULT_JSONL = """{"answer":"根拠に基づく回答","answerable":true,"citations":["sample:p1:001"]}
{"answer":"提供された文書では確認できません。","answerable":false,"citations":[]}"""


def _load_prompt(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ValueError(f"{path.name}を読み取れません") from error


def _render_analysis(label: str, analysis: PromptAnalysis) -> None:
    st.markdown(f"**{label}** — {analysis.character_count}文字")
    for check in analysis.checks:
        mark = "✅" if check.passed else "⬜"
        st.write(f"{mark} {check.message}")


def _render_results(experiment: Lab7Experiment) -> None:
    st.subheader("プロンプト契約の比較")
    columns = st.columns(3)
    with columns[0]:
        _render_analysis("v1", experiment.prompt_v1_analysis)
    with columns[1]:
        _render_analysis("v2", experiment.prompt_v2_analysis)
    with columns[2]:
        _render_analysis("v3案", experiment.draft_analysis)

    metrics = experiment.json_metrics
    first, second, third = st.columns(3)
    first.metric("JSONL出力例", metrics.examples)
    second.metric("構文エラー", metrics.syntax_errors)
    third.metric("schemaエラー", metrics.schema_errors)
    st.metric("JSON契約エラー率", f"{metrics.error_rate:.1%}")

    with st.expander("文書内命令を含む展開プロンプトを確認"):
        st.caption(
            "fixture内の「指示を無視」は実行せず、"
            "外部LLMに渡すときの文字列として表示します。"
        )
        st.code(experiment.rendered_preview)


def _render_save_form(
    workspace: Path,
    experiment: Lab7Experiment,
    *,
    prediction: str,
    change_reason: str,
    targeted_failure: str,
) -> None:
    observation = st.text_area(
        "Lab 7 実行後の観察",
        placeholder=(
            "v1、v2、v3案で増えた契約と、"
            "JSON出力例のエラー率を書きます。"
        ),
        key="lab7_observation",
    )
    if st.button(
        "v3案とLab 7学習記録を保存",
        type="primary",
        disabled=not observation.strip(),
        key="save_lab7",
    ):
        try:
            saved = save_lab7_experiment(
                workspace,
                experiment,
                prediction=prediction,
                change_reason=change_reason,
                targeted_failure=targeted_failure,
                observation=observation,
            )
        except (LearningRunError, OSError) as error:
            st.error(str(error))
            return
        if saved.run.completion.completed:
            st.success(
                f"Lab 7を完了しました。"
                f"v3案の保存先: {saved.prompt_path}"
            )
        else:
            st.warning(
                f"状態は {saved.run.completion.status} です。"
                "未達のプロンプト契約を確認してください。"
            )
        for check in saved.run.completion.checks:
            mark = "✅" if check.passed else "⬜"
            st.write(f"{mark} {check.message}")


def render_lab7(workspace: Path) -> None:
    st.header("Lab 7: プロンプト設計")
    st.markdown(
        "**学習目標:** プロンプトを版管理し、変更理由、"
        "対象の失敗、出力契約の検査結果を1セットで説明する。"
    )
    st.info(
        "この基礎経路はオフラインの構造検査です。"
        "ルールの有無は確認できますが、LLMが実際に守るかは"
        "同じ評価セットで別途測定が必要です。"
    )
    try:
        prompt_v1 = _load_prompt(PROMPT_V1_PATH)
        prompt_v2 = _load_prompt(PROMPT_V2_PATH)
    except ValueError as error:
        st.error(str(error))
        return

    tabs = st.tabs(("v1を読む", "v2を読む"))
    tabs[0].code(prompt_v1)
    tabs[1].code(prompt_v2)

    st.subheader("新しいv3案を作る")
    draft = st.text_area(
        "v3プロンプ案",
        value=f"{prompt_v2}\n\n{JSON_SUFFIX}",
        height=480,
        max_chars=20_000,
        key="lab7_draft",
        help=(
            "既存のv1/v2は上書きしません。"
            "保存時は.rag_lab/prompts/の新規ファイルになります。"
        ),
    )
    jsonl_outputs = st.text_area(
        "JSONL出力例（1行1 JSON）",
        value=DEFAULT_JSONL,
        height=150,
        max_chars=100_000,
        key="lab7_jsonl_outputs",
    )
    targeted_failure = st.text_input(
        "対象とする失敗",
        value="回答形式が一定せず後続処理でJSON解析に失敗する",
        max_chars=500,
        key="lab7_targeted_failure",
    )
    change_reason = st.text_area(
        "プロンプ変更理由",
        placeholder="どの契約をなぜ追加するか書きます。",
        max_chars=2_000,
        key="lab7_change_reason",
    )
    prediction = st.text_area(
        "実行前の予想",
        placeholder="v3案の構造検査とJSONエラー率を予想します。",
        max_chars=2_000,
        key="lab7_prediction",
    )
    if st.button(
        "v1・v2・v3案とJSON出力例を検査",
        disabled=not all(
            value.strip()
            for value in (draft, jsonl_outputs, targeted_failure, change_reason, prediction)
        ),
        key="run_lab7",
    ):
        try:
            st.session_state["lab7_experiment"] = run_lab7_experiment(
                prompt_v1_path=PROMPT_V1_PATH,
                prompt_v2_path=PROMPT_V2_PATH,
                draft_text=draft,
                jsonl_outputs=jsonl_outputs,
            )
            st.session_state["lab7_prediction_used"] = prediction
            st.session_state["lab7_change_reason_used"] = change_reason
            st.session_state["lab7_targeted_failure_used"] = targeted_failure
        except (OSError, ValueError) as error:
            st.error(str(error))

    experiment = st.session_state.get("lab7_experiment")
    if isinstance(experiment, Lab7Experiment):
        _render_results(experiment)
        _render_save_form(
            workspace,
            experiment,
            prediction=st.session_state.get("lab7_prediction_used", prediction),
            change_reason=st.session_state.get(
                "lab7_change_reason_used", change_reason
            ),
            targeted_failure=st.session_state.get(
                "lab7_targeted_failure_used", targeted_failure
            ),
        )
