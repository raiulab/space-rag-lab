from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import streamlit as st

from rag_lab.learning.checks import warning_id
from rag_lab.learning.lab1 import (
    PreparedBundledLab1,
    PreparedPdfLab1,
    prepare_bundled_data,
    prepare_pdf_upload,
    save_prepared_bundled,
    save_prepared_pdf,
)
from rag_lab.learning.progress import ProgressStore, ProgressStoreError
from rag_lab.learning.storage import DatasetStorageError
from rag_lab.pdf_ingest import PdfIngestError
from rag_lab.ui.lab2 import render_lab2
from rag_lab.ui.lab3 import render_lab3
from rag_lab.ui.diagnostics import render_diagnostics
from rag_lab.ui.lab4 import render_lab4
from rag_lab.ui.lab5 import render_lab5


WORKSPACE = Path(".rag_lab")
REPORT_DIR = Path("reports")
LAB_NAMES = (
    "技術文書・報告書の収集と加工",
    "Embedding生成とベクトル検索",
    "RAGパイプライン設計・実装",
    "LLM API連携",
    "検索・要約・質問応答",
    "回答精度の評価・改善",
    "プロンプト設計",
    "AWS実行環境",
)


def _progress_status(lab_id: str) -> str:
    try:
        progress = ProgressStore(WORKSPACE).load()
        return progress.get("labs", {}).get(lab_id, {}).get("status", "not_started")
    except ProgressStoreError:
        return "needs_review"


def render_lab_catalog() -> None:
    st.subheader("8つのLab")
    for number, name in enumerate(LAB_NAMES, start=1):
        lab_id = f"lab{number}"
        if number in {1, 2, 3, 4, 5}:
            status = _progress_status(lab_id)
            availability = (
                "オフライン模擬対応・Bedrock任意"
                if number == 4
                else "オフライン対応"
            )
            st.markdown(
                f"**Lab {number} — {name}**　`{status}`　{availability}"
            )
        else:
            st.markdown(f"Lab {number} — {name}　`準備中`")
    st.markdown("**診断・比較 — Milestone 3**　`利用可能`　オフライン対応")


def render_environment() -> None:
    st.subheader("環境チェック")
    python_ok = (3, 10) <= sys.version_info[:2] <= (3, 12)
    pdf_ok = importlib.util.find_spec("pypdf") is not None
    first, second, third = st.columns(3)
    first.metric("Python", f"{sys.version_info.major}.{sys.version_info.minor}")
    second.metric("PDF抽出", "利用可能" if pdf_ok else "追加導入が必要")
    third.metric("外部API", "任意（既定は不要）")
    if not python_ok:
        st.warning("この教材の検証済みPythonは3.10〜3.12です。")
    if not pdf_ok:
        st.info("PDFを使うには `python -m pip install -e '.[pdf]'` を実行します。")


def _render_prepared(prepared: PreparedPdfLab1) -> None:
    result = prepared.extraction
    st.subheader("抽出結果を観察する")
    first, second, third, fourth = st.columns(4)
    first.metric("文書", 1)
    second.metric("ページ", len(result.document.pages))
    third.metric("チャンク", len(prepared.chunks))
    fourth.metric("状態", result.status)

    if result.warnings:
        st.warning("警告を確認し、元PDFと抽出結果を比較してください。")
        for warning in result.warnings:
            page = f"（ページ{warning.page}）" if warning.page else ""
            st.write(f"- `{warning_id(warning)}` {warning.message}{page}")

    page_number = st.selectbox(
        "比較するページ",
        options=[page.page for page in result.document.pages],
        key="selected_pdf_page",
    )
    selected = result.document.pages[page_number - 1]
    pdf_column, text_column = st.columns(2)
    with pdf_column:
        st.caption("元PDF")
        try:
            st.pdf(prepared.file_bytes, height=600)
        except Exception:
            st.info(
                "PDFビューアーを利用できません。"
                "`.[ui,pdf]`を確認してください。"
            )
    with text_column:
        st.caption(f"ページ{page_number}の抽出テキスト")
        extracted = "\n\n".join(block.text for block in selected.blocks)
        st.text_area(
            "抽出テキスト",
            value=extracted or "（文字を抽出できませんでした）",
            height=300,
            disabled=True,
            label_visibility="collapsed",
        )

    with st.expander("生成チャンクを確認"):
        for chunk in prepared.chunks:
            st.markdown(
                f"**{chunk.chunk_id}** — page {chunk.page} / {chunk.section} / "
                f"{chunk.source}"
            )
            st.code(chunk.text)


def _save_form(prepared: PreparedPdfLab1, prediction: str) -> None:
    st.subheader("観察を記録して完了条件を確認する")
    observation = st.text_area(
        "実行後の観察",
        placeholder="予想との差、ページ情報、文章の切れ方を書きます。",
        key="pdf_observation",
    )
    warning_options = [warning_id(item) for item in prepared.extraction.warnings]
    confirmed = st.multiselect(
        "確認済みの警告",
        options=warning_options,
        help="警告がある場合は、元PDFと比較して確認したものを選びます。",
    )
    license_terms = st.text_input(
        "利用条件・ライセンス（任意）",
        placeholder="自作、CC BY 4.0、社内利用許可済み、など",
    )
    save_raw = st.checkbox(
        "再現用にPDF原本も保存する",
        value=False,
        help=(
            "未選択なら原本は保存せず、"
            "抽出ページとチャンクだけを保存します。"
        ),
    )
    if st.button("学習記録を保存", type="primary", disabled=not observation.strip()):
        try:
            saved = save_prepared_pdf(
                WORKSPACE,
                prepared,
                prediction=prediction,
                observation=observation,
                confirmed_warning_ids=tuple(confirmed),
                license_terms=license_terms,
                save_raw=save_raw,
            )
        except DatasetStorageError as error:
            st.error(str(error))
            return

        if saved.completion.completed:
            st.success(f"Lab 1を完了しました。保存先: {saved.dataset_path}")
        else:
            st.warning(
                f"状態は {saved.completion.status} です。"
                "未達の条件を確認してください。"
            )
        for check in saved.completion.checks:
            mark = "✅" if check.passed else "⬜"
            st.write(f"{mark} {check.message}")


def render_pdf_lab() -> None:
    st.markdown(
        "文字レイヤー付きPDFを1件選び、"
        "ページ別抽出とチャンクの出典を確認します。"
    )
    uploaded = st.file_uploader("PDFを選択", type=["pdf"], accept_multiple_files=False)
    document_id = st.text_input("document_id", placeholder="my_report")
    title = st.text_input("title", placeholder="技術報告書の表示名")
    source = st.text_input("source（任意）", placeholder="資料名または出典URL")
    classification = st.text_input("classification", value="user_provided")
    note = st.text_area("メモ（任意）")
    chunk_size = st.slider("チャンクサイズ", 100, 1200, 650, step=50)
    prediction = st.text_area(
        "実行前の予想",
        placeholder=(
            "ページ数やチャンク数、文章が切れそうな場所を予想します。"
        ),
        key="pdf_prediction",
    )

    can_extract = uploaded is not None and bool(document_id.strip()) and bool(
        prediction.strip()
    )
    if st.button("PDFを抽出してチャンクを作る", disabled=not can_extract):
        try:
            st.session_state["prepared_pdf"] = prepare_pdf_upload(
                uploaded.getvalue(),
                uploaded.name,
                document_id=document_id,
                title=title or None,
                source=source or None,
                classification=classification,
                note=note,
                chunk_size=chunk_size,
            )
            st.session_state["prepared_prediction"] = prediction
        except PdfIngestError as error:
            st.error(str(error))

    prepared = st.session_state.get("prepared_pdf")
    if isinstance(prepared, PreparedPdfLab1):
        _render_prepared(prepared)
        _save_form(
            prepared,
            st.session_state.get("prepared_prediction", prediction),
        )


def _render_bundled_result(prepared: PreparedBundledLab1) -> None:
    st.subheader("加工結果を観察する")
    first, second, third = st.columns(3)
    first.metric("文書", prepared.document_count)
    second.metric("ページ", prepared.page_count)
    third.metric("チャンク", len(prepared.chunks))
    with st.expander("先頭のチャンクを確認", expanded=True):
        for chunk in prepared.chunks[:5]:
            st.markdown(
                f"**{chunk.chunk_id}** — page {chunk.page} / {chunk.section} / "
                f"{chunk.source}"
            )
            st.code(chunk.text)


def _save_bundled_form(
    prepared: PreparedBundledLab1, prediction: str
) -> None:
    st.subheader("観察を記録して完了条件を確認する")
    observation = st.text_area(
        "実行後の観察",
        placeholder="予想との差、ページ情報、文章の切れ方を書きます。",
        key="bundled_observation",
    )
    if st.button(
        "付属データの学習記録を保存",
        type="primary",
        disabled=not observation.strip(),
    ):
        try:
            saved = save_prepared_bundled(
                WORKSPACE,
                prepared,
                prediction=prediction,
                observation=observation,
            )
        except DatasetStorageError as error:
            st.error(str(error))
            return
        if saved.completion.completed:
            st.success(f"Lab 1を完了しました。保存先: {saved.dataset_path}")
        else:
            st.warning(f"状態は {saved.completion.status} です。")
        for check in saved.completion.checks:
            mark = "✅" if check.passed else "⬜"
            st.write(f"{mark} {check.message}")


def render_bundled_lab() -> None:
    st.markdown(
        "付属の架空Markdown/TXTを使い、front matter、ページ、節、"
        "チャンクの関係を確認します。"
    )
    chunk_size = st.slider(
        "チャンクサイズ", 100, 1200, 650, step=50, key="bundled_chunk_size"
    )
    prediction = st.text_area(
        "実行前の予想",
        placeholder="文書数、ページ数、チャンク数を予想します。",
        key="bundled_prediction",
    )
    if st.button(
        "付属データを加工する",
        disabled=not prediction.strip(),
    ):
        try:
            st.session_state["prepared_bundled"] = prepare_bundled_data(
                chunk_size=chunk_size
            )
            st.session_state["bundled_prepared_prediction"] = prediction
        except ValueError as error:
            st.error(str(error))

    prepared = st.session_state.get("prepared_bundled")
    if isinstance(prepared, PreparedBundledLab1):
        _render_bundled_result(prepared)
        _save_bundled_form(
            prepared,
            st.session_state.get("bundled_prepared_prediction", prediction),
        )


def render_guidance() -> None:
    with st.expander("自己実装とコーディングAIの使い分け"):
        st.markdown(
            """
            **自己実装:** `pdf_ingest.py`と`source_documents.py`を読み、警告値や
            チャンクサイズを1つだけ変更してテストします。

            **AI協働:** 対象関数、期待する振る舞い、必須テストを
            小さな依頼文にします。APIキー、AWS認証情報、非公開PDFの本文は
            渡しません。差分とテスト結果は必ず自分で確認します。
            """
        )


def render_lab1() -> None:
    st.header("Lab 1: 技術文書・報告書の収集と加工")
    st.markdown(
        "**学習目標:** 文書を検索単位へ分けても、"
        "文書ID・ページ・節・出典を失わない。"
    )
    source_type = st.radio(
        "データソース",
        ("自分のPDF", "付属Markdown/TXT"),
        horizontal=True,
    )
    if source_type == "自分のPDF":
        render_pdf_lab()
    else:
        render_bundled_lab()
    render_guidance()


def main() -> None:
    st.set_page_config(page_title="Space RAG Lab", page_icon="🛰️", layout="wide")
    st.title("Space RAG Lab")
    st.caption("ローカル中心で進めるRAG学習ナビゲーション")
    render_lab_catalog()
    render_environment()
    st.divider()
    selected_lab = st.selectbox(
        "学習するLab",
        options=(
            "Lab 1: 文書の収集と加工",
            "Lab 2: Embeddingと検索比較",
            "Lab 3: RAGパイプライン",
            "Lab 4: 任意LLM API連携",
            "Lab 5: 検索・要約・質問応答",
            "診断・比較: 評価結果と次の実験",
        ),
        key="selected_lab",
    )
    if selected_lab.startswith("Lab 1"):
        render_lab1()
    elif selected_lab.startswith("Lab 2"):
        render_lab2(WORKSPACE)
    elif selected_lab.startswith("Lab 3"):
        render_lab3(WORKSPACE)
    elif selected_lab.startswith("Lab 4"):
        render_lab4(WORKSPACE)
    elif selected_lab.startswith("Lab 5"):
        render_lab5(WORKSPACE)
    else:
        render_diagnostics(WORKSPACE, REPORT_DIR)


main()
