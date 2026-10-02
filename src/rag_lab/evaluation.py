from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

from .pipeline import RAGPipeline
from .text import normalize_text


def load_gold(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _keyword_recall(answer: str, keywords: list[str]) -> float:
    if not keywords:
        return 1.0
    normalized = normalize_text(answer).casefold()
    matched = sum(
        normalize_text(keyword).casefold() in normalized for keyword in keywords
    )
    return matched / len(keywords)


def evaluate_pipeline(pipeline: RAGPipeline, gold_path: Path) -> dict[str, Any]:
    """Run a small, transparent RAG evaluation suite.

    The metrics deliberately avoid an LLM judge so that the first evaluation is
    repeatable and free. Learners can add semantic similarity or judge-based
    scoring after they understand what each baseline metric measures.
    """

    examples = load_gold(gold_path)
    if not examples:
        raise ValueError("gold dataset is empty")

    details: list[dict[str, Any]] = []
    for example in examples:
        answer = pipeline.ask(example["question"])
        expected_documents = set(example.get("expected_document_ids", []))
        retrieved_documents = {
            result.chunk.document_id for result in answer.retrieved
        }
        cited_documents = {citation.document_id for citation in answer.citations}
        expected_answerable = bool(example.get("answerable", True))

        retrieval_hit = (
            bool(expected_documents & retrieved_documents)
            if expected_documents
            else not expected_answerable
        )
        citation_hit = (
            bool(expected_documents & cited_documents)
            if expected_answerable and expected_documents
            else not answer.citations
        )
        keyword_recall = _keyword_recall(
            answer.text, example.get("answer_keywords", [])
        )
        refusal_correct = answer.answerable == expected_answerable

        details.append(
            {
                "id": example.get("id", ""),
                "question": example["question"],
                "expected_answerable": expected_answerable,
                "predicted_answerable": answer.answerable,
                "retrieval_hit": retrieval_hit,
                "citation_hit": citation_hit,
                "keyword_recall": round(keyword_recall, 4),
                "refusal_correct": refusal_correct,
                "answer": answer.text,
                "citations": [citation.to_dict() for citation in answer.citations],
                "retrieved_document_ids": [
                    result.chunk.document_id for result in answer.retrieved
                ],
            }
        )

    summary = {
        "examples": len(details),
        "retrieval_hit_rate": round(mean(item["retrieval_hit"] for item in details), 4),
        "citation_hit_rate": round(mean(item["citation_hit"] for item in details), 4),
        "keyword_recall": round(mean(item["keyword_recall"] for item in details), 4),
        "answerability_accuracy": round(
            mean(item["refusal_correct"] for item in details), 4
        ),
    }
    return {"summary": summary, "details": details}


def write_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
