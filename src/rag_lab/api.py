from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .generation import make_generator
from .pipeline import RAGPipeline
from .retrieval import Retriever


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)


@lru_cache(maxsize=1)
def get_pipeline() -> RAGPipeline:
    return RAGPipeline(
        retriever=Retriever.from_path(
            Path(os.environ.get("RAG_INDEX_PATH", "data/index/index.jsonl"))
        ),
        generator=make_generator(os.environ.get("RAG_LAB_GENERATOR", "extractive")),
        prompt_path=Path(
            os.environ.get("RAG_PROMPT_PATH", "prompts/answer_v2_grounded.txt")
        ),
        search_mode=os.environ.get("RAG_SEARCH_MODE", "hybrid"),
        top_k=int(os.environ.get("RAG_TOP_K", "5")),
    )


app = FastAPI(title="Space RAG Lab API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask")
def ask(request: AskRequest) -> dict[str, object]:
    return get_pipeline().ask(request.question).to_dict()
