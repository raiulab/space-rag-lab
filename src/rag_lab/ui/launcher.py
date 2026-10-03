from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any


class UiDependencyError(Exception):
    pass


def load_streamlit() -> Any:
    try:
        return importlib.import_module("streamlit")
    except ImportError as error:
        raise UiDependencyError(
            "UI機能が未導入です。"
            "python -m pip install -e '.[ui,pdf]' を実行してください"
        ) from error


def launch_ui() -> None:
    """Launch the fixed UI script on localhost with telemetry disabled."""

    streamlit = load_streamlit()
    app_path = Path(__file__).with_name("app.py").resolve()
    application = streamlit.App(str(app_path))
    try:
        application.run(
            config={
                "server.address": "127.0.0.1",
                "server.headless": True,
                "browser.gatherUsageStats": False,
                "client.showErrorDetails": "none",
                "client.toolbarMode": "viewer",
                "logger.hideWelcomeMessage": True,
            }
        )
    except KeyboardInterrupt:
        return
