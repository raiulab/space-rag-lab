from __future__ import annotations

from pathlib import Path

import streamlit as st

from rag_lab.learning.datasets import LearningDatasetError, bundled_dataset
from rag_lab.learning.experiments import LearningRunError
from rag_lab.learning.lab8 import (
    InfrastructureReadinessError,
    Lab8Experiment,
    run_lab8_readiness,
    save_lab8_experiment,
)


RAW_DIR = Path("data/raw")
TEMPLATE_PATH = Path("infra/template.yaml")
PROMPT_PATH = Path("prompts/answer_v2_grounded.txt")


def _render_results(experiment: Lab8Experiment) -> None:
    st.subheader("ローカルスモークテスト")
    first, second, third = st.columns(3)
    first.metric("HTTP status", experiment.smoke_status_code)
    second.metric("回答可能判定", "yes" if experiment.smoke_answerable else "no")
    third.metric("引用", len(experiment.smoke_citation_ids))
    st.caption(
        "抽出式生成器と付属データでLambda相当の"
        "HTTP入出力をローカル実行しました。AWSには接続していません。"
    )
    for citation_id in experiment.smoke_citation_ids:
        st.write(f"- `{citation_id}`")

    st.subheader("SAMテンプレートの点検")
    for finding in experiment.findings:
        if finding.status == "passed":
            st.success(f"{finding.category} / {finding.code}: {finding.message}")
        else:
            st.warning(f"{finding.category} / {finding.code}: {finding.message}")


def _render_save_form(
    workspace: Path,
    experiment: Lab8Experiment,
    prediction: str,
) -> None:
    st.subheader("デプロイ前の計画を記録する")
    review_options = list(experiment.review_finding_codes)
    acknowledged = st.multiselect(
        "確認した要対応項目",
        options=review_options,
        help="実AWSでの対応完了ではなく、デプロイ前の課題として理解した項目を選びます。",
        key="lab8_acknowledged",
    )
    iam_plan = st.text_area(
        "IAMの最小権限化計画",
        placeholder="BedrockのResourceを利用モデルのARNへ絞る、など。",
        max_chars=2_000,
        key="lab8_iam_plan",
    )
    cost_plan = st.text_area(
        "料金監視と停止条件",
        placeholder="予算通知の閾値、同時実行上限、実習を止める条件。",
        max_chars=2_000,
        key="lab8_cost_plan",
    )
    cleanup_plan = st.text_area(
        "実習後の削除手順",
        placeholder="SAMスタック、ログ、パッケージ用S3、予算通知を確認する。",
        max_chars=2_000,
        key="lab8_cleanup_plan",
    )
    observation = st.text_area(
        "Lab 8 ローカル確認の観察",
        placeholder="通過項目と、AWS公開前に必要な修正を書きます。",
        max_chars=2_000,
        key="lab8_observation",
    )
    can_save = all(
        value.strip() for value in (iam_plan, cost_plan, cleanup_plan, observation)
    ) and set(review_options).issubset(acknowledged)
    if st.button(
        "Lab 8のローカル準備記録を保存",
        type="primary",
        disabled=not can_save,
        key="save_lab8",
    ):
        try:
            saved = save_lab8_experiment(
                workspace,
                experiment,
                prediction=prediction,
                observation=observation,
                iam_plan=iam_plan,
                cost_plan=cost_plan,
                cleanup_plan=cleanup_plan,
                acknowledged_finding_codes=tuple(acknowledged),
            )
        except LearningRunError as error:
            st.error(str(error))
            return
        if saved.completion.completed:
            st.success(
                "Lab 8のローカルデプロイ前準備を完了しました。"
                "AWSへの実デプロイはまだ実行していません。"
            )
        else:
            st.warning(f"状態は {saved.completion.status} です。")
        for check in saved.completion.checks:
            mark = "✅" if check.passed else "⬜"
            st.write(f"{mark} {check.message}")


def render_lab8(workspace: Path) -> None:
    st.header("Lab 8: AWS実行環境")
    st.markdown(
        "**学習目標:** AWSへデプロイする前に、"
        "入出力、IAM、ログ、料金上限、後片付けを説明できる。"
    )
    st.warning(
        "この画面はAWSコマンドを実行せず、認証情報も読みません。"
        "完了表示はローカルのデプロイ前準備であり、"
        "AWSへの配置済みを意味しません。"
    )
    st.code(
        "HTTP API -> Lambda -> RAG pipeline -> Extractive / Bedrock\n"
        "                     |-> CloudWatch Logs / X-Ray"
    )
    st.markdown(
        "実AWSでの任意実習は `infra/README.md` の手順を使います。"
        "このUIから任意コマンドや`sam deploy`は実行できません。"
    )
    try:
        dataset = bundled_dataset(RAW_DIR)
    except (LearningDatasetError, OSError, ValueError) as error:
        st.error(str(error))
        return

    prediction = st.text_area(
        "実行前の予想",
        placeholder="どの設定が通過し、どこが要対応になると予想しますか？",
        max_chars=2_000,
        key="lab8_prediction",
    )
    if st.button(
        "SAMテンプレートとローカルLambda入出力を確認",
        disabled=not prediction.strip(),
        key="run_lab8",
    ):
        try:
            st.session_state["lab8_experiment"] = run_lab8_readiness(
                dataset,
                template_path=TEMPLATE_PATH,
                prompt_path=PROMPT_PATH,
            )
            st.session_state["lab8_prediction_used"] = prediction
        except InfrastructureReadinessError as error:
            st.error(str(error))

    experiment = st.session_state.get("lab8_experiment")
    if isinstance(experiment, Lab8Experiment):
        _render_results(experiment)
        _render_save_form(
            workspace,
            experiment,
            st.session_state.get("lab8_prediction_used", prediction),
        )
