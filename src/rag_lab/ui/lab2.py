from __future__ import annotations

from pathlib import Path

import streamlit as st

from rag_lab.learning.datasets import (
    LearningDatasetError,
    bundled_dataset,
    list_saved_datasets,
    load_saved_dataset,
)
from rag_lab.learning.experiments import LearningRunError
from rag_lab.learning.lab2 import (
    Lab2Experiment,
    run_lab2_experiment,
    save_lab2_experiment,
)


RAW_DIR = Path("data/raw")
GOLD_PATH = Path("data/evaluation/gold.jsonl")


def dataset_options(workspace: Path) -> dict[str, str]:
    options = {"付属の宇宙技術レポート（評価質問あり）": "bundled"}
    for item in list_saved_datasets(workspace):
        label = f"{item.label} / {item.chunk_count} chunks / {item.dataset_id}"
        options[label] = item.dataset_id
    return options


def load_dataset(workspace: Path, dataset_id: str):
    if dataset_id == "bundled":
        return bundled_dataset(RAW_DIR)
    return load_saved_dataset(workspace, dataset_id)


def _render_results(experiment: Lab2Experiment) -> None:
    st.subheader("同じ質問で検索方式を比較する")
    first, second, third = st.columns(3)
    first.metric("チャンク", len(experiment.dataset.chunks))
    second.metric("top-k", experiment.top_k)
    third.metric("Embedding次元", experiment.dimension)

    if experiment.hit_rates:
        st.caption(
            f"付属ゴールドデータの回答可能な"
            f"{experiment.benchmark_questions}問でHit@{experiment.top_k}を計算"
        )
        columns = st.columns(3)
        for column, mode in zip(columns, ("dense", "bm25", "hybrid")):
            column.metric(f"{mode} Hit@{experiment.top_k}", experiment.hit_rates[mode])
    else:
        st.info(
            "この実データには正解文書IDがないため、"
            "自動Hit率は計算しません。"
            "元資料と検索結果を目視で評価してください。"
        )

    st.info(
        "dense・BM25・hybridはスコアの尺度が異なるため、"
        "方式をまたいでスコア値そのものを大小比較しません。"
        "順位と本文を比べます。"
    )
    tabs = st.tabs(["dense", "BM25", "hybrid"])
    for tab, mode in zip(tabs, ("dense", "bm25", "hybrid")):
        with tab:
            for result in experiment.results[mode]:
                st.markdown(
                    f"**#{result.rank} {result.chunk.title}** — "
                    f"page {result.chunk.page} / `{result.chunk.chunk_id}`"
                )
                st.caption(
                    f"score={result.score:.6f} / section={result.chunk.section}"
                )
                st.code(result.chunk.text)


def _render_save_form(
    workspace: Path,
    experiment: Lab2Experiment,
    prediction: str,
) -> None:
    st.subheader("観察を記録する")
    observation = st.text_area(
        "Lab 2 実行後の観察",
        placeholder=(
            "完全一致語に強い方式、意味が近い語を拾った方式、"
            "順位融合の変化を書きます。"
        ),
        key="lab2_observation",
    )
    if st.button(
        "Lab 2の学習記録を保存",
        type="primary",
        disabled=not observation.strip(),
    ):
        try:
            saved = save_lab2_experiment(
                workspace,
                experiment,
                prediction=prediction,
                observation=observation,
            )
        except LearningRunError as error:
            st.error(str(error))
            return
        if saved.completion.completed:
            st.success(f"Lab 2を完了しました。run ID: {saved.run_id}")
        else:
            st.warning(f"状態は {saved.completion.status} です。")
        for check in saved.completion.checks:
            mark = "✅" if check.passed else "⬜"
            st.write(f"{mark} {check.message}")


def render_lab2(workspace: Path) -> None:
    st.header("Lab 2: Embedding生成とベクトル検索")
    st.markdown(
        "**学習目標:** dense、BM25、hybridの違いを、"
        "同じデータ・質問・top-kで比較して説明する。"
    )
    options = dataset_options(workspace)
    selected = st.selectbox(
        "Lab 2で使うデータセット",
        options=list(options),
        key="lab2_dataset",
    )
    query = st.text_input(
        "検索質問",
        value="火星の砂嵐で太陽電池出力は何%まで低下しましたか？",
        key="lab2_query",
    )
    first, second = st.columns(2)
    top_k = first.slider("top-k", 1, 10, 5, key="lab2_top_k")
    dimension = second.selectbox(
        "HashEmbeddingの次元",
        options=(64, 128, 384),
        index=2,
        key="lab2_dimension",
    )
    prediction = st.text_area(
        "Lab 2 実行前の予想",
        placeholder="どの方式が、どの文書を1位にすると予想しますか？",
        key="lab2_prediction",
    )
    if st.button(
        "3方式を比較する",
        disabled=not query.strip() or not prediction.strip(),
        key="run_lab2",
    ):
        try:
            dataset = load_dataset(workspace, options[selected])
            st.session_state["lab2_experiment"] = run_lab2_experiment(
                dataset,
                query=query,
                top_k=top_k,
                dimension=dimension,
                gold_path=GOLD_PATH if dataset.dataset_id == "bundled" else None,
            )
            st.session_state["lab2_prepared_prediction"] = prediction
        except (LearningDatasetError, OSError, ValueError) as error:
            st.error(str(error))

    experiment = st.session_state.get("lab2_experiment")
    if isinstance(experiment, Lab2Experiment):
        _render_results(experiment)
        _render_save_form(
            workspace,
            experiment,
            st.session_state.get("lab2_prepared_prediction", prediction),
        )
