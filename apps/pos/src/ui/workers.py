"""QThread workers so DB calls never block the Qt event loop
(skills/desktop/threading.md).

Uses a QThread subclass overriding run() directly, rather than the
moveToThread()+quit() worker-object pattern: the thread naturally
finishes as soon as run() returns, with no separate quit() request
needed and no window where the thread object can be destroyed while
still winding down."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Signal


class _CallableThread(QThread):
    succeeded = Signal(object)
    failed = Signal(object)

    def __init__(self, fn: Callable[[], object], parent: QObject) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            result = self._fn()
        except Exception as exc:  # noqa: BLE001 - surfaced to UI via signal
            self.failed.emit(exc)
            return
        self.succeeded.emit(result)


def run_in_background[T](
    owner: QObject,
    fn: Callable[[], T],
    on_success: Callable[[T], None],
    on_failure: Callable[[Exception], None],
) -> None:
    """Runs `fn` on a worker thread; `on_success`/`on_failure` are invoked
    back on the calling (UI) thread via queued signal delivery."""
    thread = _CallableThread(fn, owner)

    if not hasattr(owner, "_background_threads"):
        owner._background_threads = []  # type: ignore[attr-defined]
    threads: list[QThread] = owner._background_threads  # type: ignore[attr-defined]
    threads.append(thread)

    def _cleanup() -> None:
        if thread in threads:
            threads.remove(thread)

    thread.succeeded.connect(on_success)
    thread.failed.connect(on_failure)
    thread.finished.connect(_cleanup)
    thread.finished.connect(thread.deleteLater)

    thread.start()


def wait_for_pending_threads(owner: QObject, timeout_ms: int = 2000) -> None:
    """Blocks (bounded) until every background thread started for `owner`
    has finished. Call from the owning widget's closeEvent — this is the
    one place a bounded QThread.wait() from the UI thread is acceptable,
    since the work is already done or nearly done by the time a widget
    closes (skills/desktop/threading.md)."""
    for thread in list(getattr(owner, "_background_threads", [])):
        thread.wait(timeout_ms)
