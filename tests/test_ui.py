import importlib.util
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


if __name__ == "__main__":
    unittest.main()
