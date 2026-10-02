import tempfile
import unittest
from pathlib import Path

from rag_lab.embeddings import HashEmbeddingModel
from rag_lab.generation import ExtractiveGenerator
from rag_lab.models import Chunk
from rag_lab.pipeline import RAGPipeline
from rag_lab.retrieval import Retriever


def make_row(chunk_id: str, document_id: str, text: str):
    chunk = Chunk(
        chunk_id=chunk_id,
        document_id=document_id,
        title=document_id,
        page=1,
        section="本文",
        text=text,
    )
    return chunk, HashEmbeddingModel(64).embed(text)


class RetrievalPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            make_row(
                "mars:1", "mars", "砂嵐で太陽電池の出力は32 %まで低下した。"
            ),
            make_row("moon:1", "moon", "月面装置の最高温度は78 ℃だった。"),
        ]

    def test_bm25_ranks_matching_document_first(self) -> None:
        results = Retriever(self.rows).bm25_search("太陽電池の出力", top_k=2)
        self.assertEqual(results[0].chunk.document_id, "mars")
        self.assertGreater(results[0].score, results[1].score)

    def test_pipeline_answers_and_cites(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prompt = Path(directory) / "prompt.txt"
            prompt.write_text("{context}\n{question}", encoding="utf-8")
            pipeline = RAGPipeline(
                Retriever(self.rows), ExtractiveGenerator(), prompt, search_mode="hybrid"
            )
            answer = pipeline.ask("太陽電池の出力は何%まで低下しましたか？")

        self.assertTrue(answer.answerable)
        self.assertIn("32 %", answer.text)
        self.assertEqual(answer.citations[0].document_id, "mars")

    def test_pipeline_refuses_when_no_evidence_tokens_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            prompt = Path(directory) / "prompt.txt"
            prompt.write_text("{context}\n{question}", encoding="utf-8")
            pipeline = RAGPipeline(
                Retriever(self.rows), ExtractiveGenerator(), prompt, search_mode="bm25"
            )
            answer = pipeline.ask("penguin feather count")

        self.assertFalse(answer.answerable)
        self.assertEqual(answer.citations, [])


if __name__ == "__main__":
    unittest.main()
