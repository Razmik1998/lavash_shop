import logging
import sys
import threading

from PySide6.QtWidgets import QWidget

from logging_setup import configure_logging
from ui.workers import run_in_background


def test_background_failure_reaches_ui_and_both_log_files(qtbot, monkeypatch, tmp_path):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    original_hook, original_thread_hook = sys.excepthook, threading.excepthook
    try:
        configure_logging()
        configure_logging()  # Repeated setup must not duplicate records.
        owner = QWidget()
        qtbot.addWidget(owner)
        failures = []

        def fail():
            raise RuntimeError("report database failed")

        run_in_background(owner, fail, lambda result: None, failures.append)
        qtbot.waitUntil(lambda: len(failures) == 1)
        for name in ("app.log", "error.log"):
            content = (tmp_path / name).read_text()
            assert content.count("background operation failed owner=QWidget") == 1
            assert "Traceback (most recent call last)" in content
            assert "RuntimeError: report database failed" in content
        assert str(tmp_path) in (tmp_path / "app.log").read_text()
    finally:
        for handler in list(root.handlers):
            if handler not in original_handlers:
                root.removeHandler(handler)
                handler.close()
        for handler in original_handlers:
            if handler not in root.handlers:
                root.addHandler(handler)
        root.setLevel(original_level)
        sys.excepthook, threading.excepthook = original_hook, original_thread_hook
