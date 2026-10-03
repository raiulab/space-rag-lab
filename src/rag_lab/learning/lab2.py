from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Sequence

from ..embeddings import HashEmbeddingModel
from ..evaluation import load_gold
from ..models import Chunk, SearchResult
from ..retrieval import Retriever
from .checks import LabCompletion, make_check
from .datasets import LearningDataset
from .experiments import SavedLearningRun, save_learning_run


SEARCH_MODES = ("dense", "bm25", "hybrid")


@dataclass(frozen=True)
class Lab2Experiment:
    dataset: LearningDataset
    query: str
    top_k: int
    dimension: int
    results: dict[str, tuple[SearchResult, ...]]
    hit_rates: dict[str, float]
    benchmark_questions: int


def _retriever(chunks: Sequence[Chunk], dimension: int) -> Retriever:
    model = HashEmbeddingModel(dimension)
    rows = [(chunk, model.embed(chunk.text)) for chunk in chunks]
    return Retriever(rows, model)


def _benchmark(
    retriever: Retriever,
    gold_path: Path | None,
    *,
    top_k: int,
) -> tuple[dict[str, float], int]:
    if gold_path is None:
        return {}, 0
    examples = [
        example
        for example in load_gold(gold_path)
        if example.get("expected_document_ids")
    ]
    if not examples:
        return {}, 0
    rates: dict[str, float] = {}
    for mode in SEARCH_MODES:
        hits = []
        for example in examples:
            expected = set(example["expected_document_ids"])
            results = retriever.search(example["question"], top_k=top_k, mode=mode)
            retrieved = {result.chunk.document_id for result in results}
            hits.append(bool(expected & retrieved))
        rates[mode] = round(mean(hits), 4)
    return rates, len(examples)


def run_lab2_experiment(
    dataset: LearningDataset,
    *,
    query: str,
    top_k: int = 5,
    dimension: int = 384,
    gold_path: Path | None = None,
) -> Lab2Experiment:
    cleaned_query = query.strip()
    if not cleaned_query:
        raise ValueError("検索質問を入力してください")
    if not 1 <= top_k <= 20:
        raise ValueError("top_kは1から20で指定してください")
    retriever = _retriever(dataset.chunks, dimension)
    results = {
        mode: tuple(retriever.search(cleaned_query, top_k=top_k, mode=mode))
        for mode in SEARCH_MODES
    }
    hit_rates, question_count = _benchmark(
        retriever,
        gold_path,
        top_k=top_k,
    )
    return Lab2Experiment(
        dataset=dataset,
        query=cleaned_query,
        top_k=top_k,
        dimension=dimension,
        results=results,
        hit_rates=hit_rates,
        benchmark_questions=question_count,
    )


def evaluate_lab2(
    experiment: Lab2Experiment,
    *,
    prediction: str,
    observation: str,
) -> LabCompletion:
    result_rows = [
        result for mode in SEARCH_MODES for result in experiment.results.get(mode, ())
    ]
    benchmark_ok = not experiment.hit_rates or max(experiment.hit_rates.values()) >= 0.8
    data_checks = (
        make_check(
            "three_modes_compared",
            all(experiment.results.get(mode) for mode in SEARCH_MODES),
            "dense・BM25・hybridを同じ条件で比較しました",
            "3方式すべての検索結果が必要です",
        ),
        make_check(
            "provenance_present",
            bool(result_rows)
            and all(
                result.chunk.document_id
                and result.chunk.chunk_id
                and result.chunk.page >= 1
                for result in result_rows
            ),
            "検索結果から文書・ページ・チャンクへ戻れます",
            "検索結果の出典情報が不足しています",
        ),
        make_check(
            "benchmark_target",
            benchmark_ok,
            "代表質問の検索ヒット率80%以上を確認しました",
            "検索ヒット率が80%未満です。top-kや方式を観察してください",
        ),
    )
    learning_checks = (
        make_check(
            "prediction_recorded",
            bool(prediction.strip()),
            "実行前の予想を記録しました",
            "実行前の予想が未記録です",
        ),
        make_check(
            "observation_recorded",
            bool(observation.strip()),
            "検索方式の違いを観察しました",
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


def save_lab2_experiment(
    workspace: Path,
    experiment: Lab2Experiment,
    *,
    prediction: str,
    observation: str,
) -> SavedLearningRun:
    completion = evaluate_lab2(
        experiment,
        prediction=prediction,
        observation=observation,
    )
    result_summary: dict[str, Any] = {}
    for mode, results in experiment.results.items():
        result_summary[mode] = [
            {
                "rank": result.rank,
                "score": round(result.score, 6),
                "chunk_id": result.chunk.chunk_id,
                "document_id": result.chunk.document_id,
                "page": result.chunk.page,
            }
            for result in results
        ]
    return save_learning_run(
        workspace,
        lab_id="lab2",
        dataset_id=experiment.dataset.dataset_id,
        completion=completion,
        prediction=prediction,
        observation=observation,
        settings={
            "query": experiment.query,
            "top_k": experiment.top_k,
            "embedding_model": f"hash-embedding-v1-{experiment.dimension}",
            "modes": list(SEARCH_MODES),
        },
        summary={
            "benchmark_questions": experiment.benchmark_questions,
            "hit_rates": experiment.hit_rates,
            "results": result_summary,
        },
    )
