import unittest
from pathlib import Path

from rag_lab.evaluation import _keyword_recall, evaluate_pipeline
from rag_lab.generation import ExtractiveGenerator
from rag_lab.ingest import collect_chunks
from rag_lab.embeddings import HashEmbeddingModel
from rag_lab.pipeline import RAGPipeline
from rag_lab.retrieval import Retriever


ROOT = Path(__file__).resolve().parents[1]


class EvaluationTests(unittest.TestCase):
    def test_keyword_recall_normalizes_temperature_symbol(self) -> None:
        self.assertEqual(_keyword_recall("最高温度は78 °C", ["78 ℃"]), 1.0)

    def test_training_dataset_retrieves_all_expected_documents(self) -> None:
        chunks = collect_chunks(ROOT / "data/raw")
        model = HashEmbeddingModel(64)
        rows = [(chunk, model.embed(chunk.text)) for chunk in chunks]
        pipeline = RAGPipeline(
            Retriever(rows, model),
            ExtractiveGenerator(),
            ROOT / "prompts/answer_v2_grounded.txt",
            search_mode="hybrid",
            top_k=5,
        )
        report = evaluate_pipeline(pipeline, ROOT / "data/evaluation/gold.jsonl")
        self.assertEqual(report["summary"]["retrieval_hit_rate"], 1.0)
        self.assertGreaterEqual(report["summary"]["answerability_accuracy"], 0.8)


if __name__ == "__main__":
    unittest.main()
