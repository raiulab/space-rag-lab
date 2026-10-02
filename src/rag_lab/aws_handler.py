from __future__ import annotations

import base64
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from .generation import make_generator
from .pipeline import RAGPipeline
from .retrieval import Retriever


@lru_cache(maxsize=1)
def _pipeline() -> RAGPipeline:
    task_root = Path(__file__).resolve().parents[2]
    return RAGPipeline(
        Retriever.from_path(
            Path(os.environ.get("RAG_INDEX_PATH", task_root / "data/index/index.jsonl"))
        ),
        make_generator(os.environ.get("RAG_LAB_GENERATOR", "bedrock")),
        Path(
            os.environ.get(
                "RAG_PROMPT_PATH", task_root / "prompts/answer_v2_grounded.txt"
            )
        ),
        search_mode=os.environ.get("RAG_SEARCH_MODE", "hybrid"),
        top_k=int(os.environ.get("RAG_TOP_K", "5")),
    )


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json; charset=utf-8"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    del context
    try:
        raw_body = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            raw_body = base64.b64decode(raw_body).decode("utf-8")
        body = json.loads(raw_body)
        question = str(body.get("question", "")).strip()
        if len(question) < 2:
            return _response(400, {"error": "question は2文字以上で指定してください"})
        return _response(200, _pipeline().ask(question).to_dict())
    except (json.JSONDecodeError, TypeError):
        return _response(400, {"error": "JSON形式のbodyを指定してください"})
    except Exception as exc:  # Lambda logging is handled by the platform
        return _response(500, {"error": type(exc).__name__, "message": str(exc)})
