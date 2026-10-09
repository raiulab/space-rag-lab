from __future__ import annotations

from pathlib import Path

import streamlit as st

from rag_lab.learning.datasets import LearningDatasetError
from rag_lab.learning.experiments import LearningRunError
from rag_lab.learning.lab5 import (
    Lab5Experiment,
    document_ids,
    run_lab5_experiment,
    save_lab5_experiment,
)
from rag_lab.ui.lab2 import dataset_options, load_dataset


PROMPT_PATH = Path("prompts/answer_v2_grounded.txt")


def _render_results(experiment: Lab5Experiment) -> None:
    st.subheader("3機能の出力を比べる")
    tabs = st.tabs(("検索", "要約", "質問応答"))

    with tabs[0]:
        st.caption(
            "検索は、質問へ直接答えるのではなく、候補チャンク、順位、"
            "スコア、出典を返します。"
        )
        for result in experiment.search_results:
            with st.expander(
                f"#{result.rank} {result.chunk.title} / "
                f"page {result.chunk.page} / {result.chunk.chunk_id}"
            ):
                st.caption(
                    f"method={result.method} / score={result.score:.6f} / "
                    f"section={result.chunk.section}"
                )
                st.code(result.chunk.text)

    with tabs[1]:
        st.caption(
            "要約は、選択した1文書を対象に、目的・数値・結論を短くします。"
        )
        st.write(f"対象document_id: `{experiment.summary_document_id}`")
        if experiment.summary_answerable:
            st.success(experiment.summary_text)
        else:
            st.warning(experiment.summary_text)
        st.write("要約元チャンク:")
        for chunk_id in experiment.summary_source_chunk_ids:
            st.write(f"- `{chunk_id}`")

    with tabs[2]:
        answer = experiment.qa_answer
        st.caption(
            "質問応答は、特定の問いに対して回答可能性を判定し、"
            "回答と引用を返します。"
        )
        if answer.answerable:
            st.success(answer.text)
        else:
            st.info(answer.text)
        if answer.citations:
            for citation in answer.citations:
                st.write(
                    f"- `{citation.chunk_id}` — "
                    f"{citation.title} / page {citation.page}"
                )
        else:
            st.write("回答不能判定のため引用はありません。")

    columns = st.columns(3)
    columns[0].metric("検索結果", len(experiment.search_results))
    columns[1].metric("要約元", len(experiment.summary_source_chunk_ids))
    columns[2].metric("QA引用", len(experiment.qa_answer.citations))


def _render_save_form(
    workspace: Path,
    experiment: Lab5Experiment,
    prediction: str,
) -> None:
    st.subheader("観察を記録する")
    observation = st.text_area(
        "Lab 5 実行後の観察",
        placeholder=(
            "検索・要約・QAで、入力、出力、根拠の示し方が"
            "どう違ったかを書きます。"
        ),
        key="lab5_observation",
    )
    if st.button(
        "Lab 5の学習記録を保存",
        type="primary",
        disabled=not observation.strip(),
        key="save_lab5",
    ):
        try:
            saved = save_lab5_experiment(
                workspace,
                experiment,
                prediction=prediction,
                observation=observation,
            )
        except LearningRunError as error:
            st.error(str(error))
            return
        if saved.completion.completed:
            st.success(f"Lab 5を完了しました。run ID: {saved.run_id}")
        else:
            st.warning(
                f"状態は {saved.completion.status} です。"
                "3機能の出力と根拠を確認してください。"
            )
        for check in saved.completion.checks:
            mark = "✅" if check.passed else "⬜"
            st.write(f"{mark} {check.message}")


def render_lab5(workspace: Path) -> None:
    st.header("Lab 5: 検索・要約・質問応答")
    st.markdown(
        "**学習目標:** 検索、文書要約、質問応答を同じ処理として扱わず、"
        "それぞれの入力、出力、根拠、評価観点を説明する。"
    )
    options = dataset_options(workspace)
    selected = st.selectbox(
        "Lab 5で使うデータセット",
        options=list(options),
        key="lab5_dataset",
    )
    try:
        dataset = load_dataset(workspace, options[selected])
    except (LearningDatasetError, OSError, ValueError) as error:
        st.error(str(error))
        return

    search_query = st.text_input(
        "検索語",
        value="低電力時の安全モード",
        max_chars=500,
        key="lab5_search_query",
    )
    ids = document_ids(dataset)
    default_document = ids.index("mars_power_2026") if "mars_power_2026" in ids else 0
    summary_document_id = st.selectbox(
        "要約するdocument_id",
        options=ids,
        index=default_document,
        key="lab5_document_id",
    )
    qa_question = st.text_input(
        "質問応答で使う質問",
        value="蓄電池の設計目標との差は何時間ですか？",
        max_chars=500,
        key="lab5_qa_question",
    )
    columns = st.columns(3)
    search_mode = columns[0].selectbox(
        "検索方式",
        options=("dense", "bm25", "hybrid"),
        index=2,
        key="lab5_mode",
    )
    top_k = columns[1].slider("top-k", 1, 10, 5, key="lab5_top_k")
    dimension = columns[2].selectbox(
        "Embedding次元",
        options=(64, 128, 384),
        index=2,
        key="lab5_dimension",
    )
    prediction = st.text_area(
        "Lab 5 実行前の予想",
        placeholder=(
            "検索は何を返し、要約とQAはどのように異なると予想しますか？"
        ),
        key="lab5_prediction",
    )
    st.caption(
        "質問・予想・観察・出典IDは`.rag_lab/`へ保存できます。"
        "生成文とチャンク本文は学習記録へ複製しません。"
    )
    if st.button(
        "検索・要約・QAを実行",
        disabled=(
            not search_query.strip()
            or not qa_question.strip()
            or not prediction.strip()
        ),
        key="run_lab5",
    ):
        try:
            st.session_state["lab5_experiment"] = run_lab5_experiment(
                dataset,
                search_query=search_query,
                summary_document_id=summary_document_id,
                qa_question=qa_question,
                prompt_path=PROMPT_PATH,
                search_mode=search_mode,
                top_k=top_k,
                dimension=dimension,
            )
            st.session_state["lab5_prepared_prediction"] = prediction
        except (OSError, ValueError) as error:
            st.error(str(error))

    experiment = st.session_state.get("lab5_experiment")
    if isinstance(experiment, Lab5Experiment):
        _render_results(experiment)
        _render_save_form(
            workspace,
            experiment,
            st.session_state.get("lab5_prepared_prediction", prediction),
        )
