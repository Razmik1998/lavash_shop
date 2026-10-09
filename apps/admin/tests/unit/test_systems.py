from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QSettings

from exceptions import SyncConnectionError
from networking.order_sync_client import DjangoOrderSyncClient
from networking.web_sync_client import WebSyncClient, WebSyncError
from services.systems import SystemsService


def test_disabled_transports_make_no_requests():
    orders = DjangoOrderSyncClient("https://example.com", "secret")
    products = WebSyncClient("https://example.com", "secret")
    orders.set_enabled(False)
    products.enabled = False
    with patch("networking.order_sync_client.websocket.create_connection") as dial:
        with pytest.raises(SyncConnectionError):
            orders.connect()
        dial.assert_not_called()
    with patch("requests.get") as get, patch("requests.post") as post:
        with pytest.raises(SyncConnectionError):
            orders.fetch_missed_events(None)
        with pytest.raises(WebSyncError):
            products.sync_products([])
        get.assert_not_called()
        post.assert_not_called()


def test_switch_persists_and_restarts(qtbot, tmp_path):
    preferences = QSettings(str(tmp_path / "systems.ini"), QSettings.Format.IniFormat)
    sync = Mock()
    orders = Mock()
    products = Mock()
    service = SystemsService(sync, orders, products, preferences)
    service.set_enabled(False)
    sync.stop.assert_called_once()
    orders.set_enabled.assert_called_with(False)
    assert products.enabled is False
    restored = SystemsService(sync, orders, products, preferences)
    assert restored.enabled is False
    restored.start()
    sync.start.assert_not_called()
    restored.set_enabled(True)
    sync.start.assert_called_once()
    assert products.enabled is True
    restored._timer.stop()
