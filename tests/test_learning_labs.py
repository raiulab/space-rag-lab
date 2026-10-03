from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from rag_lab.learning.datasets import (
    LearningDatasetError,
    bundled_dataset,
    list_saved_datasets,
    load_saved_dataset,
)
from rag_lab.learning.lab1 import prepare_bundled_data, save_prepared_bundled
from rag_lab.learning.lab2 import (
    evaluate_lab2,
    run_lab2_experiment,
    save_lab2_experiment,
)


ROOT = Path(__file__).parents[1]
RAW_DIR = ROOT / "data" / "raw"
GOLD_PATH = ROOT / "data" / "evaluation" / "gold.jsonl"


class LearningDatasetTests(unittest.TestCase):
    def test_saved_lab1_dataset_can_be_loaded_without_source_paths(self) -> None:
        prepared = prepare_bundled_data(RAW_DIR)
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / ".rag_lab"
            saved = save_prepared_bundled(
                workspace,
                prepared,
                prediction="20チャンクと予想",
                observation="出典を保持した",
            )

            options = list_saved_datasets(workspace)
            loaded = load_saved_dataset(workspace, saved.dataset_id)

        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].dataset_id, saved.dataset_id)
        self.assertEqual(len(loaded.chunks), 20)
        self.assertEqual(loaded.source_kind, "bundled_markdown_text")

    def test_unsafe_dataset_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(LearningDatasetError, "不正"):
                load_saved_dataset(Path(directory), "../outside")


class Lab2LearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = bundled_dataset(RAW_DIR)

    def test_three_search_modes_and_benchmark_are_comparable(self) -> None:
        experiment = run_lab2_experiment(
            self.dataset,
            query="火星の砂嵐で太陽電池出力は何%まで低下しましたか？",
            top_k=5,
            dimension=384,
            gold_path=GOLD_PATH,
        )

        self.assertEqual(set(experiment.results), {"dense", "bm25", "hybrid"})
        self.assertTrue(all(len(rows) == 5 for rows in experiment.results.values()))
        self.assertEqual(experiment.benchmark_questions, 8)
        self.assertTrue(all(rate >= 0.8 for rate in experiment.hit_rates.values()))
        self.assertEqual(experiment.results["bm25"][0].chunk.document_id, "mars_power_2026")

    def test_completion_requires_prediction_and_observation(self) -> None:
        experiment = run_lab2_experiment(
            self.dataset,
            query="太陽電池出力",
            top_k=3,
            dimension=64,
        )

        incomplete = evaluate_lab2(experiment, prediction="", observation="")
        complete = evaluate_lab2(
            experiment,
            prediction="BM25が上位になると予想",
            observation="BM25は完全一致語を上位にした",
        )

        self.assertEqual(incomplete.status, "in_progress")
        self.assertEqual(complete.status, "completed")

    def test_saved_run_contains_metrics_but_not_chunk_text_or_secret(self) -> None:
        experiment = run_lab2_experiment(
            self.dataset,
            query="太陽電池出力",
            top_k=3,
            dimension=64,
            gold_path=GOLD_PATH,
        )
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / ".rag_lab"
            with mock.patch.dict(
                os.environ, {"AWS_SECRET_ACCESS_KEY": "do-not-persist"}
            ):
                saved = save_lab2_experiment(
                    workspace,
                    experiment,
                    prediction="hybridを予想",
                    observation="順位差を確認した",
                )
            value = json.loads(saved.path.read_text(encoding="utf-8"))
            saved_text = saved.path.read_text(encoding="utf-8")
            progress = json.loads(
                (workspace / "progress.json").read_text(encoding="utf-8")
            )

        self.assertEqual(value["lab_id"], "lab2")
        self.assertEqual(value["status"], "completed")
        self.assertIn("hit_rates", value["summary"])
        self.assertNotIn(self.dataset.chunks[0].text, saved_text)
        self.assertNotIn("do-not-persist", saved_text)
        self.assertEqual(progress["labs"]["lab2"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
