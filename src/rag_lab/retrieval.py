from __future__ import annotations

import math
from collections import Counter, defaultdict
from pathlib import Path

from .embeddings import HashEmbeddingModel, cosine_similarity, load_index
from .models import Chunk, SearchResult
from .text import tokenize


class Retriever:
    def __init__(
        self,
        rows: list[tuple[Chunk, list[float]]],
        embedding_model: HashEmbeddingModel | None = None,
    ) -> None:
        if not rows:
            raise ValueError("index is empty")
        self.rows = rows
        self.embedding_model = embedding_model or HashEmbeddingModel(len(rows[0][1]))
        self.doc_tokens = [tokenize(chunk.text) for chunk, _ in rows]
        self.doc_lengths = [len(tokens) for tokens in self.doc_tokens]
        self.avg_doc_length = sum(self.doc_lengths) / len(self.doc_lengths)
        self.document_frequency: Counter[str] = Counter()
        for tokens in self.doc_tokens:
            self.document_frequency.update(set(tokens))

    @classmethod
    def from_path(cls, path: Path) -> "Retriever":
        return cls(load_index(path))

    def dense_search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        query_vector = self.embedding_model.embed(query)
        scored = [
            (chunk, cosine_similarity(query_vector, embedding))
            for chunk, embedding in self.rows
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return [
            SearchResult(chunk=chunk, score=score, rank=rank, method="dense")
            for rank, (chunk, score) in enumerate(scored[:top_k], start=1)
        ]

    def bm25_search(
        self,
        query: str,
        top_k: int = 5,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> list[SearchResult]:
        query_tokens = tokenize(query)
        total_documents = len(self.rows)
        scored: list[tuple[Chunk, float]] = []
        for row_index, ((chunk, _), tokens) in enumerate(zip(self.rows, self.doc_tokens)):
            frequencies = Counter(tokens)
            length = self.doc_lengths[row_index]
            score = 0.0
            for token in query_tokens:
                df = self.document_frequency.get(token, 0)
                if not df:
                    continue
                idf = math.log(1.0 + (total_documents - df + 0.5) / (df + 0.5))
                tf = frequencies.get(token, 0)
                numerator = tf * (k1 + 1.0)
                denominator = tf + k1 * (1.0 - b + b * length / self.avg_doc_length)
                if denominator:
                    score += idf * numerator / denominator
            scored.append((chunk, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return [
            SearchResult(chunk=chunk, score=score, rank=rank, method="bm25")
            for rank, (chunk, score) in enumerate(scored[:top_k], start=1)
        ]

    def hybrid_search(
        self, query: str, top_k: int = 5, candidate_k: int = 20
    ) -> list[SearchResult]:
        dense = self.dense_search(query, min(candidate_k, len(self.rows)))
        bm25 = self.bm25_search(query, min(candidate_k, len(self.rows)))
        fused: defaultdict[str, float] = defaultdict(float)
        chunks: dict[str, Chunk] = {}
        rrf_constant = 60.0
        for result in dense + bm25:
            fused[result.chunk.chunk_id] += 1.0 / (rrf_constant + result.rank)
            chunks[result.chunk.chunk_id] = result.chunk
        ranked = sorted(fused.items(), key=lambda item: item[1], reverse=True)
        return [
            SearchResult(
                chunk=chunks[chunk_id],
                score=score,
                rank=rank,
                method="hybrid_rrf",
            )
            for rank, (chunk_id, score) in enumerate(ranked[:top_k], start=1)
        ]

    def search(self, query: str, top_k: int = 5, mode: str = "hybrid") -> list[SearchResult]:
        if mode == "dense":
            return self.dense_search(query, top_k)
        if mode == "bm25":
            return self.bm25_search(query, top_k)
        if mode == "hybrid":
            return self.hybrid_search(query, top_k)
        raise ValueError(f"unknown search mode: {mode}")
