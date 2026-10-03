from __future__ import annotations

from pathlib import Path

import streamlit as st

from rag_lab.learning.datasets import LearningDatasetError
from rag_lab.learning.experiments import LearningRunError
from rag_lab.learning.lab3 import (
    Lab3Experiment,
    run_lab3_experiment,
    save_lab3_experiment,
)
from rag_lab.ui.lab2 import dataset_options, load_dataset


PROMPT_PATH = Path("prompts/answer_v2_grounded.txt")


def _render_answer(experiment: Lab3Experiment) -> None:
    answer = experiment.answer
    st.subheader("RAGの各段階を観察する")
    columns = st.columns(4)
    columns[0].metric("検索方式", experiment.search_mode)
    columns[1].metric("取得チャンク", len(answer.retrieved))
    columns[2].metric("回答可能判定", "可能" if answer.answerable else "不能")
    columns[3].metric("引用", len(answer.citations))

    st.markdown("#### 1. 検索された根拠")
    for result in answer.retrieved:
        with st.expander(
            f"#{result.rank} {result.chunk.title} / "
            f"page {result.chunk.page} / {result.chunk.chunk_id}"
        ):
            st.caption(
                f"method={result.method} / score={result.score:.6f} / "
                f"section={result.chunk.section}"
            )
            st.code(result.chunk.text)

    st.markdown("#### 2. 抽出式生成器の回答")
    if answer.answerable:
        st.success(answer.text)
    else:
        st.info(answer.text)

    st.markdown("#### 3. 引用から根拠へ戻る")
    if answer.citations:
        for citation in answer.citations:
            st.write(
                f"- `{citation.chunk_id}` — {citation.title} / page {citation.page}"
            )
    else:
        st.write("回答不能判定のため引用はありません。")

    if answer.answerable != experiment.expected_answerable:
        st.warning(
            "実行前の回答可能性予想と結果が異なります。"
            "検索結果に質問へ直接答える根拠があるか確認してください。"
        )


def _render_save_form(
    workspace: Path,
    experiment: Lab3Experiment,
    prediction: str,
) -> None:
    st.subheader("観察を記録する")
    observation = st.text_area(
        "Lab 3 実行後の観察",
        placeholder=(
            "回答は検索根拠だけから作られたか、引用先へ戻れるか、"
            "回答不能判定は妥当かを書きます。"
        ),
        key="lab3_observation",
    )
    if st.button(
        "Lab 3の学習記録を保存",
        type="primary",
        disabled=not observation.strip(),
    ):
        try:
            saved = save_lab3_experiment(
                workspace,
                experiment,
                prediction=prediction,
                observation=observation,
            )
        except LearningRunError as error:
            st.error(str(error))
            return
        if saved.completion.completed:
            st.success(f"Lab 3を完了しました。run ID: {saved.run_id}")
        else:
            st.warning(
                f"状態は {saved.completion.status} です。"
                "失敗を隠さず、検索根拠と回答可能性を見直してください。"
            )
        for check in saved.completion.checks:
            mark = "✅" if check.passed else "⬜"
            st.write(f"{mark} {check.message}")


def render_lab3(workspace: Path) -> None:
    st.header("Lab 3: RAGパイプライン設計・実装")
    st.markdown(
        "**学習目標:** 質問、検索、生成、引用、"
        "回答不能判定を分けて観察し、"
        "回答から根拠チャンクへ戻れることを確認する。"
    )
    options = dataset_options(workspace)
    selected = st.selectbox(
        "Lab 3で使うデータセット",
        options=list(options),
        key="lab3_dataset",
    )
    question = st.text_input(
        "質問",
        value="火星の砂嵐で太陽電池出力は何%まで低下しましたか？",
        key="lab3_question",
    )
    expected_label = st.radio(
        "文書の根拠だけで回答できると予想しますか？",
        options=("回答可能", "回答不能"),
        horizontal=True,
        key="lab3_expected",
    )
    columns = st.columns(3)
    search_mode = columns[0].selectbox(
        "検索方式",
        options=("dense", "bm25", "hybrid"),
        index=2,
        key="lab3_mode",
    )
    top_k = columns[1].slider("top-k", 1, 10, 5, key="lab3_top_k")
    dimension = columns[2].selectbox(
        "Embedding次元",
        options=(64, 128, 384),
        index=2,
        key="lab3_dimension",
    )
    prediction = st.text_area(
        "Lab 3 実行前の予想",
        placeholder=(
            "どの根拠が検索され、回答と引用がどうなるか予想します。"
        ),
        key="lab3_prediction",
    )
    if st.button(
        "RAGパイプラインを実行",
        disabled=not question.strip() or not prediction.strip(),
        key="run_lab3",
    ):
        try:
            dataset = load_dataset(workspace, options[selected])
            st.session_state["lab3_experiment"] = run_lab3_experiment(
                dataset,
                question=question,
                expected_answerable=expected_label == "回答可能",
                prompt_path=PROMPT_PATH,
                search_mode=search_mode,
                top_k=top_k,
                dimension=dimension,
            )
            st.session_state["lab3_prepared_prediction"] = prediction
        except (LearningDatasetError, OSError, ValueError) as error:
            st.error(str(error))

    experiment = st.session_state.get("lab3_experiment")
    if isinstance(experiment, Lab3Experiment):
        _render_answer(experiment)
        _render_save_form(
            workspace,
            experiment,
            st.session_state.get("lab3_prepared_prediction", prediction),
        )
