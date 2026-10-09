import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from rag_lab.ui.launcher import launch_ui


HAS_STREAMLIT = importlib.util.find_spec("streamlit") is not None
APP_PATH = Path(__file__).parents[1] / "src" / "rag_lab" / "ui" / "app.py"


class UiLauncherTests(unittest.TestCase):
    def test_launcher_uses_fixed_local_address_and_disables_telemetry(self) -> None:
        application = mock.Mock()
        streamlit = mock.Mock()
        streamlit.App.return_value = application

        with mock.patch("rag_lab.ui.launcher.load_streamlit", return_value=streamlit):
            launch_ui()

        launched_path = Path(streamlit.App.call_args.args[0])
        self.assertEqual(launched_path, APP_PATH.resolve())
        application.run.assert_called_once_with(
            config={
                "server.address": "127.0.0.1",
                "server.headless": True,
                "browser.gatherUsageStats": False,
                "client.showErrorDetails": "none",
                "client.toolbarMode": "viewer",
                "logger.hideWelcomeMessage": True,
            }
        )

    def test_launcher_exits_cleanly_on_keyboard_interrupt(self) -> None:
        application = mock.Mock()
        application.run.side_effect = KeyboardInterrupt
        streamlit = mock.Mock()
        streamlit.App.return_value = application

        with mock.patch("rag_lab.ui.launcher.load_streamlit", return_value=streamlit):
            launch_ui()


@unittest.skipUnless(HAS_STREAMLIT, "UI extra is not installed")
class StreamlitAppTests(unittest.TestCase):
    def test_initial_screen_renders_without_exception(self) -> None:
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(APP_PATH)).run(timeout=10)

        self.assertEqual(app.exception, [])
        self.assertEqual(app.title[0].value, "Space RAG Lab")
        self.assertIn("Lab 1", app.header[0].value)
        self.assertGreaterEqual(len(app.radio), 1)

    def test_bundled_dataset_path_runs_in_ui(self) -> None:
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(APP_PATH)).run(timeout=10)
        app.radio[0].set_value("付属Markdown/TXT").run(timeout=10)
        app.text_area[0].set_value("4文書程度になると予想").run(timeout=10)
        app.button[0].click().run(timeout=10)

        self.assertEqual(app.exception, [])
        self.assertEqual(
            [metric.value for metric in app.metric[-3:]], ["4", "12", "20"]
        )

    def test_lab2_compares_three_retrieval_modes(self) -> None:
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(APP_PATH)).run(timeout=10)
        app.selectbox[0].set_value("Lab 2: Embeddingと検索比較").run(timeout=10)
        app.text_area[0].set_value("BM25が1位になると予想").run(timeout=10)
        app.button[0].click().run(timeout=10)

        self.assertEqual(app.exception, [])
        self.assertIn("Lab 2", app.header[0].value)
        metric_labels = [metric.label for metric in app.metric]
        self.assertIn("dense Hit@5", metric_labels)
        self.assertIn("bm25 Hit@5", metric_labels)
        self.assertIn("hybrid Hit@5", metric_labels)

    def test_lab3_shows_answer_retrieval_and_citations(self) -> None:
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(APP_PATH)).run(timeout=10)
        app.selectbox[0].set_value("Lab 3: RAGパイプライン").run(timeout=10)
        app.text_area[0].set_value("火星文書から32%と答える").run(timeout=10)
        app.button[0].click().run(timeout=10)

        self.assertEqual(app.exception, [])
        self.assertIn("Lab 3", app.header[0].value)
        metric_labels = [metric.label for metric in app.metric]
        self.assertIn("取得チャンク", metric_labels)
        self.assertIn("回答可能判定", metric_labels)
        rendered_text = "\n".join(item.value for item in app.success)
        self.assertIn("32 %", rendered_text)

    def test_lab5_separates_search_summary_and_qa(self) -> None:
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(APP_PATH)).run(timeout=10)
        app.selectbox[0].set_value("Lab 5: 検索・要約・質問応答").run(timeout=10)
        app.text_area[0].set_value(
            "検索は候補、要約は文書、QAは回答を返す"
        ).run(timeout=10)
        app.button[0].click().run(timeout=10)

        self.assertEqual(app.exception, [])
        self.assertIn("Lab 5", app.header[0].value)
        metric_labels = [metric.label for metric in app.metric]
        self.assertIn("検索結果", metric_labels)
        self.assertIn("要約元", metric_labels)
        self.assertIn("QA引用", metric_labels)
        rendered_text = "\n".join(item.value for item in app.success)
        self.assertIn("6時間", rendered_text)

    def test_lab6_compares_one_change_on_the_same_questions(self) -> None:
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(APP_PATH)).run(timeout=10)
        app.selectbox[0].set_value("Lab 6: 回答精度の評価・改善").run(
            timeout=10
        )
        app.text_area[0].set_value("次元を下げると必須語再現率が下がる").run(
            timeout=10
        )
        app.text_area[1].set_value("ハッシュ衝突が増え根拠文が変わる").run(
            timeout=10
        )
        app.button[0].click().run(timeout=15)

        self.assertEqual(app.exception, [])
        self.assertIn("Lab 6", app.header[0].value)
        metric_labels = [metric.label for metric in app.metric]
        self.assertIn("検索ヒット率", metric_labels)
        self.assertIn("必須語再現率", metric_labels)
        rendered_code = "\n".join(item.value for item in app.code)
        self.assertIn("europa-01", rendered_code)

    def test_lab4_runs_offline_simulated_api_without_credentials(self) -> None:
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(APP_PATH)).run(timeout=10)
        app.selectbox[0].set_value("Lab 4: 任意LLM API連携").run(timeout=10)
        app.text_area[0].set_value(
            "模擬APIは成功し抽出式と同じ根拠を使う"
        ).run(timeout=10)
        app.button[0].click().run(timeout=10)

        self.assertEqual(app.exception, [])
        self.assertIn("Lab 4", app.header[0].value)
        metric_labels = [metric.label for metric in app.metric]
        self.assertIn("外部呼び出し", metric_labels)
        self.assertIn("入力文字数", metric_labels)
        self.assertIn("応答時間", metric_labels)
        rendered_text = "\n".join(item.value for item in app.success)
        self.assertIn("32 %", rendered_text)

    def test_lab4_bedrock_requires_cost_and_data_confirmation(self) -> None:
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file(str(APP_PATH)).run(timeout=10)
        app.selectbox[0].set_value("Lab 4: 任意LLM API連携").run(timeout=10)
        app.radio[1].set_value("Amazon Bedrock（実API）").run(timeout=10)
        app.text_input[2].set_value("example-model-id").run(timeout=10)
        app.text_area[0].set_value("実APIは成功すると予想").run(timeout=10)

        self.assertTrue(app.button[0].disabled)
        app.checkbox[0].set_value(True).run(timeout=10)
        self.assertTrue(app.button[0].disabled)
        app.checkbox[1].set_value(True).run(timeout=10)
        if app.error:
            self.assertIn(".[aws]", "\n".join(item.value for item in app.error))
            self.assertTrue(app.button[0].disabled)
        else:
            self.assertFalse(app.button[0].disabled)
        self.assertEqual(app.exception, [])

    def test_diagnostics_explains_how_to_create_first_report(self) -> None:
        from streamlit.testing.v1 import AppTest

        original = Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as directory:
                os.chdir(directory)
                app = AppTest.from_file(str(APP_PATH)).run(timeout=10)
                app.selectbox[0].set_value(
                    "診断・比較: 評価結果と次の実験"
                ).run(timeout=10)
        finally:
            os.chdir(original)

        self.assertEqual(app.exception, [])
        self.assertIn("診断・比較", app.header[0].value)
        rendered_info = "\n".join(item.value for item in app.info)
        self.assertIn("rag-lab all", rendered_info)

    def test_diagnostics_shows_failures_and_saves_learning_report(self) -> None:
        from streamlit.testing.v1 import AppTest

        report = {
            "summary": {
                "examples": 1,
                "retrieval_hit_rate": 1.0,
                "citation_hit_rate": 1.0,
                "keyword_recall": 0.5,
                "answerability_accuracy": 1.0,
            },
            "details": [
                {
                    "id": "sample-01",
                    "question": "必要な数値を答えましたか？",
                    "expected_answerable": True,
                    "predicted_answerable": True,
                    "retrieval_hit": True,
                    "citation_hit": True,
                    "keyword_recall": 0.5,
                    "refusal_correct": True,
                    "answer": "学習記録へ保存しない本文",
                }
            ],
        }
        original = Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                report_dir = root / "reports"
                report_dir.mkdir()
                (report_dir / "evaluation.json").write_text(
                    json.dumps(report, ensure_ascii=False), encoding="utf-8"
                )
                os.chdir(root)
                app = AppTest.from_file(str(APP_PATH)).run(timeout=10)
                app.selectbox[0].set_value(
                    "診断・比較: 評価結果と次の実験"
                ).run(timeout=10)
                app.text_area[0].set_value("回答内容の問題だと分かった").run(
                    timeout=10
                )
                app.text_area[1].set_value("チャンク境界だけを変更する").run(
                    timeout=10
                )
                app.button[-1].click().run(timeout=10)
                saved = list((root / ".rag_lab" / "reports").glob("*.md"))
                saved_text = saved[0].read_text(encoding="utf-8")
        finally:
            os.chdir(original)

        self.assertEqual(app.exception, [])
        self.assertIn("検索ヒット率", [metric.label for metric in app.metric])
        self.assertIn("sample-01", "\n".join(item.value for item in app.markdown))
        self.assertEqual(len(saved), 1)
        self.assertNotIn("学習記録へ保存しない本文", saved_text)


if __name__ == "__main__":
    unittest.main()
