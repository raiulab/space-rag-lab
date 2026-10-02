from __future__ import annotations

from pathlib import Path

from .generation import Generator
from .models import Answer, Citation
from .retrieval import Retriever


class RAGPipeline:
    def __init__(
        self,
        retriever: Retriever,
        generator: Generator,
        prompt_path: Path,
        search_mode: str = "hybrid",
        top_k: int = 5,
    ) -> None:
        self.retriever = retriever
        self.generator = generator
        self.prompt_path = prompt_path
        self.search_mode = search_mode
        self.top_k = top_k

    def ask(self, question: str) -> Answer:
        results = self.retriever.search(question, top_k=self.top_k, mode=self.search_mode)
        prompt = self.prompt_path.read_text(encoding="utf-8")
        text, answerable = self.generator.generate(question, results, prompt)
        citations = []
        if answerable:
            citations = [
                Citation(
                    chunk_id=result.chunk.chunk_id,
                    document_id=result.chunk.document_id,
                    title=result.chunk.title,
                    page=result.chunk.page,
                )
                for result in results[:3]
            ]
        return Answer(
            question=question,
            text=text,
            citations=citations,
            answerable=answerable,
            retrieved=results,
        )
