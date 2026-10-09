from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import streamlit as st

from rag_lab.learning.datasets import LearningDatasetError
from rag_lab.learning.experiments import LearningRunError
from rag_lab.learning.lab4 import (
    Lab4Experiment,
    run_lab4_experiment,
    save_lab4_experiment,
)
from rag_lab.ui.lab2 import dataset_options, load_dataset


PROMPT_PATH = Path("prompts/answer_v2_grounded.txt")
PROVIDER_LABELS = {
    "オフライン模擬API": "simulated",
    "Amazon Bedrock（実API）": "bedrock",
}
SCENARIO_LABELS = {
    "成功": "success",
    "スロットリング": "throttling",
    "タイムアウト": "timeout",
    "不正なモデルID": "invalid_model",
}


def _render_answer(label: str, answer) -> None:
    st.markdown(f"#### {label}")
    if answer.answerable:
        st.success(answer.text)
    else:
        st.info(answer.text)
    if answer.citations:
        st.write("引用:")
        for citation in answer.citations:
            st.write(
                f"- `{citation.chunk_id}` — {citation.title} / page {citation.page}"
            )
    else:
        st.write("回答不能判定のため引用はありません。")


def _render_results(experiment: Lab4Experiment) -> None:
    call = experiment.external_call
    st.subheader("抽出式と外部APIの境界を観察する")
    columns = st.columns(4)
    columns[0].metric("外部呼び出し", "成功" if call.status == "success" else "失敗")
    columns[1].metric("入力文字数", call.input_chars)
    columns[2].metric("出力文字数", call.output_chars)
    columns[3].metric("応答時間", f"{call.latency_ms:.2f} ms")

    baseline_tab, external_tab, evidence_tab = st.tabs(
        ("抽出式ベースライン", "外部API", "送信対象の根拠")
    )
    with baseline_tab:
        _render_answer("APIキー不要の回答", experiment.baseline_answer)
    with external_tab:
        if call.answer is not None:
            _render_answer("外部APIの回答", call.answer)
        else:
            st.warning(call.safe_message)
            st.write(f"失敗分類: `{call.failure_type}`")
            st.caption(
                "例外メッセージや認証情報は画面と学習記録へ保存しません。"
            )
    with evidence_tab:
        st.caption(
            "実APIでは、質問、下記チャンク本文、プロンプトがAWSへ送信されます。"
        )
        for result in experiment.baseline_answer.retrieved:
            with st.expander(
                f"#{result.rank} {result.chunk.title} / "
                f"page {result.chunk.page} / {result.chunk.chunk_id}"
            ):
                st.code(result.chunk.text)

    predicted_success = experiment.expected_external_success
    actual_success = call.status == "success"
    if predicted_success != actual_success:
        st.warning(
            "実行前の成否予想と結果が異なります。"
            "環境、認証、モデルID、リージョン、制限を切り分けてください。"
        )


def _render_save_form(
    workspace: Path,
    experiment: Lab4Experiment,
    prediction: str,
) -> None:
    st.subheader("観察を記録する")
    observation = st.text_area(
        "Lab 4 実行後の観察",
        placeholder=(
            "抽出式と外部APIの違い、応答時間、送信量、"
            "または失敗分類から分かったことを書きます。"
        ),
        key="lab4_observation",
    )
    if st.button(
        "Lab 4の学習記録を保存",
        type="primary",
        disabled=not observation.strip(),
        key="save_lab4",
    ):
        try:
            saved = save_lab4_experiment(
                workspace,
                experiment,
                prediction=prediction,
                observation=observation,
            )
        except LearningRunError as error:
            st.error(str(error))
            return
        if saved.completion.completed:
            st.success(f"Lab 4を完了しました。run ID: {saved.run_id}")
        else:
            st.warning(
                f"状態は {saved.completion.status} です。"
                "成否予想、失敗分類、観察内容を確認してください。"
            )
        for check in saved.completion.checks:
            mark = "✅" if check.passed else "⬜"
            st.write(f"{mark} {check.message}")


def render_lab4(workspace: Path) -> None:
    st.header("Lab 4: 任意LLM API連携")
    st.markdown(
        "**学習目標:** 検索と生成を分離したまま外部LLMへ接続し、"
        "送信データ、応答時間、課金、認証、失敗処理を説明する。"
    )
    st.info(
        "既定の模擬APIはネットワーク、AWS認証情報、料金を使いません。"
        "先に成功・失敗経路を安全に練習できます。"
    )

    options = dataset_options(workspace)
    selected = st.selectbox(
        "Lab 4で使うデータセット",
        options=list(options),
        key="lab4_dataset",
    )
    question = st.text_input(
        "質問",
        value="火星の砂嵐で太陽電池出力は何%まで低下しましたか？",
        max_chars=500,
        key="lab4_question",
    )
    expected_label = st.radio(
        "外部API呼び出しは成功すると予想しますか？",
        options=("成功する", "安全に失敗する"),
        horizontal=True,
        key="lab4_expected",
    )
    columns = st.columns(3)
    search_mode = columns[0].selectbox(
        "検索方式",
        options=("dense", "bm25", "hybrid"),
        index=2,
        key="lab4_mode",
    )
    top_k = columns[1].slider("top-k", 1, 10, 5, key="lab4_top_k")
    dimension = columns[2].selectbox(
        "Embedding次元",
        options=(64, 128, 384),
        index=2,
        key="lab4_dimension",
    )

    provider_label = st.radio(
        "外部API経路",
        options=tuple(PROVIDER_LABELS),
        horizontal=True,
        key="lab4_provider",
    )
    provider = PROVIDER_LABELS[provider_label]
    scenario = "success"
    region = "ap-northeast-1"
    model_id = ""
    cost_confirmed = True
    data_confirmed = True
    aws_extra_available = importlib.util.find_spec("boto3") is not None

    if provider == "simulated":
        scenario_label = st.selectbox(
            "模擬する結果",
            options=tuple(SCENARIO_LABELS),
            key="lab4_scenario",
        )
        scenario = SCENARIO_LABELS[scenario_label]
        st.caption("模擬APIは取得チャンクを外部へ送信しません。")
    else:
        st.warning(
            "Bedrock実行では料金が発生する可能性があり、質問、"
            "検索されたチャンク本文、プロンプトがAWSへ送信されます。"
        )
        if not aws_extra_available:
            st.error("`python -m pip install -e '.[aws]'` を先に実行してください。")
        region = st.text_input(
            "AWSリージョン",
            value=os.environ.get("AWS_REGION", "ap-northeast-1"),
            key="lab4_region",
        )
        model_id = st.text_input(
            "BedrockモデルIDまたは推論プロファイルID",
            value=os.environ.get("BEDROCK_MODEL_ID", ""),
            max_chars=512,
            key="lab4_model_id",
            help="モデルIDは設定値です。アクセスキーや秘密鍵は入力しません。",
        )
        st.caption(
            "認証にはAWS SDKの標準認証チェーンを使います。"
            "この画面はアクセスキーを入力・表示・保存しません。"
        )
        cost_confirmed = st.checkbox(
            "料金が発生する可能性を理解しました",
            key="lab4_cost_confirmed",
        )
        data_confirmed = st.checkbox(
            "選択した文書をAWSへ送信できることを確認しました",
            key="lab4_data_confirmed",
        )

    prediction = st.text_area(
        "Lab 4 実行前の予想",
        placeholder=(
            "成功・失敗の予想、抽出式との違い、"
            "時間や送信文字数の見込みを書きます。"
        ),
        key="lab4_prediction",
    )
    live_ready = (
        provider != "bedrock"
        or (
            aws_extra_available
            and bool(model_id.strip())
            and bool(region.strip())
            and cost_confirmed
            and data_confirmed
        )
    )
    if st.button(
        "抽出式と外部APIを比較する",
        disabled=(
            not question.strip()
            or not prediction.strip()
            or not live_ready
        ),
        key="run_lab4",
    ):
        try:
            dataset = load_dataset(workspace, options[selected])
            st.session_state["lab4_experiment"] = run_lab4_experiment(
                dataset,
                question=question,
                expected_external_success=expected_label == "成功する",
                prompt_path=PROMPT_PATH,
                provider=provider,
                simulation_scenario=scenario,
                model_id=model_id,
                region=region,
                search_mode=search_mode,
                top_k=top_k,
                dimension=dimension,
            )
            st.session_state["lab4_prepared_prediction"] = prediction
        except (LearningDatasetError, OSError, ValueError) as error:
            st.error(str(error))

    experiment = st.session_state.get("lab4_experiment")
    if isinstance(experiment, Lab4Experiment):
        _render_results(experiment)
        _render_save_form(
            workspace,
            experiment,
            st.session_state.get("lab4_prepared_prediction", prediction),
        )
