from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..generation import ExtractiveGenerator
from ..models import Answer
from ..pipeline import RAGPipeline
from .checks import LabCompletion, make_check
from .datasets import LearningDataset
from .experiments import SavedLearningRun, save_learning_run
from .lab2 import SEARCH_MODES, build_retriever


@dataclass(frozen=True)
class Lab3Experiment:
    dataset: LearningDataset
    question: str
    expected_answerable: bool
    search_mode: str
    top_k: int
    dimension: int
    prompt_version: str
    answer: Answer


def run_lab3_experiment(
    dataset: LearningDataset,
    *,
    question: str,
    expected_answerable: bool,
    prompt_path: Path,
    search_mode: str = "hybrid",
    top_k: int = 5,
    dimension: int = 384,
) -> Lab3Experiment:
    cleaned_question = question.strip()
    if not cleaned_question:
        raise ValueError("質問を入力してください")
    if search_mode not in SEARCH_MODES:
        raise ValueError("検索方式が不正です")
    if not 1 <= top_k <= 20:
        raise ValueError("top_kは1から20で指定してください")
    if not prompt_path.is_file():
        raise ValueError("プロンプトファイルが見つかりません")

    pipeline = RAGPipeline(
        retriever=build_retriever(dataset.chunks, dimension),
        generator=ExtractiveGenerator(),
        prompt_path=prompt_path,
        search_mode=search_mode,
        top_k=top_k,
    )
    answer = pipeline.ask(cleaned_question)
    return Lab3Experiment(
        dataset=dataset,
        question=cleaned_question,
        expected_answerable=expected_answerable,
        search_mode=search_mode,
        top_k=top_k,
        dimension=dimension,
        prompt_version=prompt_path.name,
        answer=answer,
    )


def evaluate_lab3(
    experiment: Lab3Experiment,
    *,
    prediction: str,
    observation: str,
) -> LabCompletion:
    answer = experiment.answer
    retrieved_ids = {result.chunk.chunk_id for result in answer.retrieved}
    citation_ids = {citation.chunk_id for citation in answer.citations}
    citation_policy_ok = (
        answer.answerable
        and bool(citation_ids)
        and citation_ids.issubset(retrieved_ids)
    ) or (not answer.answerable and not citation_ids)
    data_checks = (
        make_check(
            "retrieval_completed",
            bool(answer.retrieved),
            "質問に対する検索結果を取得しました",
            "検索結果がありません",
        ),
        make_check(
            "retrieval_traceable",
            bool(answer.retrieved)
            and all(
                result.chunk.document_id
                and result.chunk.chunk_id
                and result.chunk.page >= 1
                for result in answer.retrieved
            ),
            "検索結果から元文書とページへ戻れます",
            "検索結果の出典情報が不足しています",
        ),
        make_check(
            "citation_policy",
            citation_policy_ok,
            "回答には検索結果の引用があり、"
            "回答不能時は引用を付けていません",
            "回答と引用の対応を確認してください",
        ),
        make_check(
            "answerability_matches_prediction",
            answer.answerable == experiment.expected_answerable,
            "回答可能性の予想と実際が一致しました",
            "回答可能性の予想と実際が異なります。"
            "根拠を確認してください",
        ),
    )
    learning_checks = (
        make_check(
            "prediction_recorded",
            bool(prediction.strip()),
            "検索結果と回答の予想を記録しました",
            "実行前の予想が未記録です",
        ),
        make_check(
            "observation_recorded",
            bool(observation.strip()),
            "検索・回答・引用の関係を観察しました",
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


def save_lab3_experiment(
    workspace: Path,
    experiment: Lab3Experiment,
    *,
    prediction: str,
    observation: str,
) -> SavedLearningRun:
    completion = evaluate_lab3(
        experiment,
        prediction=prediction,
        observation=observation,
    )
    answer = experiment.answer
    return save_learning_run(
        workspace,
        lab_id="lab3",
        dataset_id=experiment.dataset.dataset_id,
        completion=completion,
        prediction=prediction,
        observation=observation,
        settings={
            "question": experiment.question,
            "expected_answerable": experiment.expected_answerable,
            "search_mode": experiment.search_mode,
            "top_k": experiment.top_k,
            "embedding_model": f"hash-embedding-v1-{experiment.dimension}",
            "generator": "extractive",
            "prompt_version": experiment.prompt_version,
        },
        summary={
            "predicted_answerable": answer.answerable,
            "citations": [citation.to_dict() for citation in answer.citations],
            "retrieved": [
                {
                    "rank": result.rank,
                    "score": round(result.score, 6),
                    "chunk_id": result.chunk.chunk_id,
                    "document_id": result.chunk.document_id,
                    "page": result.chunk.page,
                }
                for result in answer.retrieved
            ],
        },
    )
