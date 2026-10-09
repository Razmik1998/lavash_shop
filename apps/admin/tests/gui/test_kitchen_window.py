from threading import Event, get_ident
from types import SimpleNamespace

from ui.kitchen_window import KitchenWindow


class KitchenService:
    def list_exports(self):
        return []

    def list_productions(self):
        return []


class Catalog:
    def __init__(self):
        self.release = Event()
        self.thread_id = None
        self.error = None

    def list_products(self):
        self.thread_id = get_ident()
        self.release.wait(2)
        if self.error:
            raise self.error
        return []


def make_window(qtbot):
    catalog = Catalog()
    window = KitchenWindow(KitchenService(), catalog, SimpleNamespace(id=1))
    qtbot.addWidget(window)
    window.resize(1200, 900)
    window.show()
    qtbot.waitUntil(lambda: not getattr(window, "_background_threads", []))
    return window, catalog


def test_return_form_is_visible_and_back_restores_navigation(qtbot):
    window, catalog = make_window(qtbot)
    window._tabs._select(1)
    window._produce.click()
    qtbot.waitUntil(lambda: catalog.thread_id is not None)
    assert catalog.thread_id != get_ident()
    assert window._page_header.isVisible()
    assert window._stack.currentIndex() == 1
    catalog.release.set()
    qtbot.waitUntil(lambda: window._in_inline_page)
    assert window._stack.currentIndex() == 0
    assert window._export_stack.currentWidget() is window._production_page
    assert window._production_page.isVisible()
    window._production_page._back.click()
    assert window._stack.currentIndex() == 1
    assert window._tabs.isVisible() and window._tabs.isEnabled()
    assert window._produce.isEnabled()
    qtbot.waitUntil(lambda: not window._background_threads)


def test_catalog_error_leaves_navigation_and_create_buttons_usable(qtbot, monkeypatch):
    window, catalog = make_window(qtbot)
    errors = []
    monkeypatch.setattr(window, "_failed", errors.append)
    catalog.error = RuntimeError("Catalog unavailable")
    window._new.click()
    catalog.release.set()
    qtbot.waitUntil(lambda: bool(errors))
    assert not window._in_inline_page
    assert window._tabs.isVisible() and window._tabs.isEnabled()
    assert window._new.isEnabled() and window._produce.isEnabled()
    catalog.error = None
    window._new.click()
    qtbot.waitUntil(lambda: window._in_inline_page)
    assert window._export_stack.currentWidget() is window._export_editor
    window._export_editor._back.click()
    qtbot.waitUntil(lambda: not window._background_threads)
