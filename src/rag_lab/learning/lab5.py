from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..generation import ExtractiveGenerator
from ..models import Answer, SearchResult
from ..pipeline import RAGPipeline
from .checks import LabCompletion, make_check
from .datasets import LearningDataset
from .experiments import SavedLearningRun, save_learning_run
from .lab2 import SEARCH_MODES, build_retriever


SUMMARY_QUESTION = "この文書の目的、重要な数値、結論を3点以内で要約してください。"
MIN_INPUT_LENGTH = 2
MAX_INPUT_LENGTH = 500


@dataclass(frozen=True)
class Lab5Experiment:
    dataset: LearningDataset
    search_query: str
    summary_document_id: str
    qa_question: str
    search_mode: str
    top_k: int
    dimension: int
    prompt_version: str
    search_results: tuple[SearchResult, ...]
    summary_text: str
    summary_answerable: bool
    summary_source_chunk_ids: tuple[str, ...]
    qa_answer: Answer


def document_ids(dataset: LearningDataset) -> tuple[str, ...]:
    return tuple(sorted({chunk.document_id for chunk in dataset.chunks}))


def _clean_input(value: str, label: str) -> str:
    cleaned = value.strip()
    if not MIN_INPUT_LENGTH <= len(cleaned) <= MAX_INPUT_LENGTH:
        raise ValueError(
            f"{label}は{MIN_INPUT_LENGTH}文字以上"
            f"{MAX_INPUT_LENGTH}文字以下で入力してください"
        )
    return cleaned


def run_lab5_experiment(
    dataset: LearningDataset,
    *,
    search_query: str,
    summary_document_id: str,
    qa_question: str,
    prompt_path: Path,
    search_mode: str = "hybrid",
    top_k: int = 5,
    dimension: int = 384,
) -> Lab5Experiment:
    cleaned_search = _clean_input(search_query, "検索語")
    cleaned_question = _clean_input(qa_question, "質問")
    if search_mode not in SEARCH_MODES:
        raise ValueError("検索方式が不正です")
    if not 1 <= top_k <= 20:
        raise ValueError("top_kは1から20で指定してください")
    if dimension <= 0:
        raise ValueError("Embedding次元は1以上で指定してください")
    if not prompt_path.is_file():
        raise ValueError("プロンプトファイルが見つかりません")

    matching_chunks = tuple(
        chunk
        for chunk in dataset.chunks
        if chunk.document_id == summary_document_id
    )
    if not matching_chunks:
        raise ValueError("要約対象のdocument_idが見つかりません")

    retriever = build_retriever(dataset.chunks, dimension)
    search_results = tuple(
        retriever.search(cleaned_search, top_k=top_k, mode=search_mode)
    )
    summary_results = tuple(
        SearchResult(chunk=chunk, score=1.0, rank=rank, method="document")
        for rank, chunk in enumerate(matching_chunks, start=1)
    )
    prompt = prompt_path.read_text(encoding="utf-8")
    generator = ExtractiveGenerator()
    summary_text, summary_answerable = generator.generate(
        SUMMARY_QUESTION,
        summary_results,
        prompt,
    )
    pipeline = RAGPipeline(
        retriever=retriever,
        generator=generator,
        prompt_path=prompt_path,
        search_mode=search_mode,
        top_k=top_k,
    )
    qa_answer = pipeline.ask(cleaned_question)
    return Lab5Experiment(
        dataset=dataset,
        search_query=cleaned_search,
        summary_document_id=summary_document_id,
        qa_question=cleaned_question,
        search_mode=search_mode,
        top_k=top_k,
        dimension=dimension,
        prompt_version=prompt_path.name,
        search_results=search_results,
        summary_text=summary_text,
        summary_answerable=summary_answerable,
        summary_source_chunk_ids=tuple(
            result.chunk.chunk_id for result in summary_results
        ),
        qa_answer=qa_answer,
    )


def evaluate_lab5(
    experiment: Lab5Experiment,
    *,
    prediction: str,
    observation: str,
) -> LabCompletion:
    answer = experiment.qa_answer
    retrieved_ids = {result.chunk.chunk_id for result in answer.retrieved}
    citation_ids = {citation.chunk_id for citation in answer.citations}
    citation_policy_ok = (
        answer.answerable
        and bool(citation_ids)
        and citation_ids.issubset(retrieved_ids)
    ) or (not answer.answerable and not citation_ids)
    data_checks = (
        make_check(
            "search_traceable",
            bool(experiment.search_results)
            and all(
                result.chunk.chunk_id
                and result.chunk.document_id
                and result.chunk.page >= 1
                for result in experiment.search_results
            ),
            "検索結果にスコアと出典があります",
            "検索結果または出典が不足しています",
        ),
        make_check(
            "summary_traceable",
            experiment.summary_answerable
            and bool(experiment.summary_text.strip())
            and bool(experiment.summary_source_chunk_ids),
            "要約から対象文書と根拠チャンクへ戻れます",
            "要約または要約元チャンクを確認してください",
        ),
        make_check(
            "qa_citation_policy",
            bool(answer.retrieved) and citation_policy_ok,
            "QAは回答時に引用を付け、回答不能時は引用を付けません",
            "QAの検索結果、回答、引用の対応を確認してください",
        ),
    )
    learning_checks = (
        make_check(
            "prediction_recorded",
            bool(prediction.strip()),
            "3機能の出力の違いを予想しました",
            "実行前の予想が未記録です",
        ),
        make_check(
            "observation_recorded",
            bool(observation.strip()),
            "検索・要約・QAの違いを観察しました",
            "実行後の観察が未記録です",
        ),
    )
    checks = data_checks + learning_checks
    if not all(check.passed for check in data_checks):
        status = "needs_review"
    elif not all(check.passed for check in learning_checks):
        status = "in_progress"
    else:
        status = "completed"
    return LabCompletion(status=status, checks=checks)


def save_lab5_experiment(
    workspace: Path,
    experiment: Lab5Experiment,
    *,
    prediction: str,
    observation: str,
) -> SavedLearningRun:
    completion = evaluate_lab5(
        experiment,
        prediction=prediction,
        observation=observation,
    )
    answer = experiment.qa_answer
    return save_learning_run(
        workspace,
        lab_id="lab5",
        dataset_id=experiment.dataset.dataset_id,
        completion=completion,
        prediction=prediction,
        observation=observation,
        settings={
            "search_query": experiment.search_query,
            "summary_document_id": experiment.summary_document_id,
            "qa_question": experiment.qa_question,
            "search_mode": experiment.search_mode,
            "top_k": experiment.top_k,
            "embedding_model": f"hash-embedding-v1-{experiment.dimension}",
            "generator": "extractive",
            "prompt_version": experiment.prompt_version,
        },
        summary={
            "search_results": [
                {
                    "rank": result.rank,
                    "score": round(result.score, 6),
                    "chunk_id": result.chunk.chunk_id,
                    "document_id": result.chunk.document_id,
                    "page": result.chunk.page,
                }
                for result in experiment.search_results
            ],
            "summary_source_chunk_ids": list(
                experiment.summary_source_chunk_ids
            ),
            "qa_answerable": answer.answerable,
            "qa_citations": [citation.to_dict() for citation in answer.citations],
        },
    )
