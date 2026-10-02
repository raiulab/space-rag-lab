from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Iterable

from .models import Chunk
from .text import tokenize


class HashEmbeddingModel:
    """A deterministic, offline embedding baseline.

    It is intentionally simple: tokens are hashed into a fixed-size dense vector.
    This teaches the indexing and vector-search mechanics without an API key. Lab 2
    asks learners to replace it with a semantic multilingual embedding model.
    """

    def __init__(self, dimension: int = 384) -> None:
        if dimension < 16:
            raise ValueError("dimension must be at least 16")
        self.dimension = dimension
        self.model_id = f"hash-embedding-v1-{dimension}"

    def embed(self, text: str) -> list[float]:
        counts = Counter(tokenize(text))
        vector = [0.0] * self.dimension
        for token, count in counts.items():
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimension
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += sign * (1.0 + math.log(count))
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector

    def embed_many(self, texts: Iterable[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have equal dimensions")
    return sum(a * b for a, b in zip(left, right))


def build_index(
    chunks: Iterable[Chunk],
    output_path: Path,
    model: HashEmbeddingModel | None = None,
) -> int:
    embedding_model = model or HashEmbeddingModel()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            record = {
                "schema_version": 1,
                "embedding_model": embedding_model.model_id,
                "chunk": chunk.to_dict(),
                "embedding": embedding_model.embed(chunk.text),
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def load_index(path: Path) -> list[tuple[Chunk, list[float]]]:
    rows: list[tuple[Chunk, list[float]]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            rows.append((Chunk.from_dict(record["chunk"]), record["embedding"]))
    return rows
