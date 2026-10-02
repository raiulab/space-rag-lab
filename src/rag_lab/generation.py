from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Sequence

from .models import SearchResult
from .text import split_sentences, tokenize


DEFAULT_REFUSAL = "提供された文書では確認できません。"


class Generator(ABC):
    @abstractmethod
    def generate(
        self,
        question: str,
        results: Sequence[SearchResult],
        prompt_template: str,
    ) -> tuple[str, bool]:
        raise NotImplementedError


class ExtractiveGenerator(Generator):
    """Offline baseline that extracts evidence sentences instead of calling an LLM."""

    def generate(
        self,
        question: str,
        results: Sequence[SearchResult],
        prompt_template: str,
    ) -> tuple[str, bool]:
        del prompt_template
        query_tokens = set(tokenize(question))
        candidates: list[tuple[float, str, SearchResult]] = []
        for result in results:
            for sentence in split_sentences(result.chunk.text):
                sentence_tokens = set(tokenize(sentence))
                overlap = len(query_tokens & sentence_tokens)
                if overlap:
                    score = overlap / max(len(query_tokens), 1) + 1.0 / (10 + result.rank)
                    candidates.append((score, sentence, result))
        if not candidates:
            return DEFAULT_REFUSAL, False
        candidates.sort(key=lambda item: item[0], reverse=True)
        selected: list[str] = []
        seen: set[str] = set()
        for _, sentence, _ in candidates:
            if sentence not in seen:
                selected.append(sentence)
                seen.add(sentence)
            if len(selected) == 2:
                break
        return " ".join(selected), True


class BedrockGenerator(Generator):
    """Optional Amazon Bedrock Converse API adapter used in Lab 4 and Lab 8."""

    def __init__(self, model_id: str | None = None, region: str | None = None) -> None:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - optional integration
            raise RuntimeError("Install the AWS extra: pip install -e '.[aws]'") from exc
        self.model_id = model_id or os.environ.get("BEDROCK_MODEL_ID", "")
        if not self.model_id:
            raise RuntimeError("BEDROCK_MODEL_ID is required for the Bedrock generator")
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=region or os.environ.get("AWS_REGION", "ap-northeast-1"),
        )

    def generate(
        self,
        question: str,
        results: Sequence[SearchResult],
        prompt_template: str,
    ) -> tuple[str, bool]:  # pragma: no cover - requires AWS credentials
        context_parts = []
        for result in results:
            context_parts.append(
                f"[chunk_id={result.chunk.chunk_id} title={result.chunk.title} "
                f"page={result.chunk.page}]\n{result.chunk.text}"
            )
        prompt = prompt_template.format(
            question=question,
            context="\n\n".join(context_parts),
        )
        response = self.client.converse(
            modelId=self.model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"temperature": 0.0, "maxTokens": 800},
        )
        text = response["output"]["message"]["content"][0]["text"].strip()
        answerable = DEFAULT_REFUSAL not in text
        return text, answerable


def make_generator(name: str) -> Generator:
    if name == "extractive":
        return ExtractiveGenerator()
    if name == "bedrock":
        return BedrockGenerator()
    raise ValueError(f"unknown generator: {name}")
