from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Sequence

from .models import SearchResult
from .text import split_sentences, tokenize


DEFAULT_REFUSAL = "提供された文書では確認できません。"


def render_grounded_prompt(
    question: str,
    results: Sequence[SearchResult],
    prompt_template: str,
) -> str:
    """Render the exact prompt sent to an external generator."""

    context_parts = []
    for result in results:
        context_parts.append(
            f"[chunk_id={result.chunk.chunk_id} title={result.chunk.title} "
            f"page={result.chunk.page}]\n{result.chunk.text}"
        )
    return prompt_template.format(
        question=question,
        context="\n\n".join(context_parts),
    )


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

    def __init__(
        self,
        model_id: str | None = None,
        region: str | None = None,
        *,
        client: Any | None = None,
        read_timeout_seconds: int = 30,
        max_attempts: int = 2,
    ) -> None:
        self.model_id = model_id or os.environ.get("BEDROCK_MODEL_ID", "")
        if not self.model_id:
            raise RuntimeError("BEDROCK_MODEL_ID is required for the Bedrock generator")
        if read_timeout_seconds <= 0 or max_attempts <= 0:
            raise ValueError("timeout and retry limits must be positive")
        self.region = region or os.environ.get("AWS_REGION", "ap-northeast-1")
        self.read_timeout_seconds = read_timeout_seconds
        self.max_attempts = max_attempts
        if client is not None:
            self.client = client
            return
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - optional integration
            raise RuntimeError("Install the AWS extra: pip install -e '.[aws]'") from exc
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=self.region,
            config=Config(
                connect_timeout=5,
                read_timeout=read_timeout_seconds,
                retries={"max_attempts": max_attempts, "mode": "standard"},
            ),
        )

    def generate(
        self,
        question: str,
        results: Sequence[SearchResult],
        prompt_template: str,
    ) -> tuple[str, bool]:  # pragma: no cover - requires AWS credentials
        prompt = render_grounded_prompt(question, results, prompt_template)
        response = self.client.converse(
            modelId=self.model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"temperature": 0.0, "maxTokens": 800},
        )
        try:
            text = response["output"]["message"]["content"][0]["text"].strip()
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise RuntimeError("Bedrock returned an unsupported response format") from exc
        if not text:
            raise RuntimeError("Bedrock returned an empty response")
        answerable = DEFAULT_REFUSAL not in text
        return text, answerable


def make_generator(name: str) -> Generator:
    if name == "extractive":
        return ExtractiveGenerator()
    if name == "bedrock":
        return BedrockGenerator()
    raise ValueError(f"unknown generator: {name}")
