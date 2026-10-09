"""Persistent controls for the online integration."""

from PySide6.QtCore import QObject, QSettings, QTimer, Signal

from networking.order_sync_client import DjangoOrderSyncClient
from networking.web_sync_client import WebSyncClient
from services.sync import SyncService


class SystemsService(QObject):
    changed = Signal()

    def __init__(
        self,
        sync: SyncService | None,
        orders: DjangoOrderSyncClient | None,
        products: WebSyncClient | None,
        preferences: QSettings | None = None,
    ) -> None:
        super().__init__()
        self._sync = sync
        self._orders = orders
        self._products = products
        self._preferences = preferences or QSettings("FishShop", "Admin")
        self.enabled = self._preferences.value(
            "systems/online_enabled", True, type=bool
        )
        self.configured = (
            sync is not None and orders is not None and products is not None
        )
        self._apply_transport()
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.start)
        if sync is not None:
            sync.connection_changed.connect(self._connection_changed)

    @property
    def connected(self) -> bool:
        return self.enabled and self._sync is not None and self._sync.is_connected

    def _connection_changed(self, connected: object) -> None:
        self.changed.emit()

    def _apply_transport(self) -> None:
        if self._orders is not None:
            self._orders.set_enabled(self.enabled)
        if self._products is not None:
            self._products.enabled = self.enabled

    def start(self) -> None:
        if self.enabled and self._sync is not None:
            self._sync.start()
            self._timer.start()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self._preferences.setValue("systems/online_enabled", enabled)
        self._apply_transport()
        if enabled:
            self.start()
        else:
            self._timer.stop()
            if self._sync is not None:
                self._sync.stop()
        self.changed.emit()
