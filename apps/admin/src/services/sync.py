"""`SyncService`: the Qt-signal surface `ui/online_selling_window.py` (and
any other screen that cares about online-order sync state) is coded
against.

The signal surface defines the exact signals the UI
connects to, per this task's brief:

  - `new_online_order(object)` -- payload: `schemas.online_orders.OnlineOrderRow`,
    the newly received pending order. Drives the Online Selling page's
    notification banner and a Pending-tab reload.
  - `order_confirmed(object)` -- payload: `uuid.UUID`, the local
    `OnlineOrder.id` that just transitioned to CONFIRMED (whether
    confirmed from this UI or observed via the WebSocket event stream).
    Drives a list/detail reload.
  - `order_rejected(object)` -- payload: `uuid.UUID`, same shape as
    `order_confirmed` but for REJECTED.
  - `connection_changed(object)` -- payload: `bool`, `True` once the
    WebSocket connection is established/re-established, `False` on
    disconnect. Drives a connection-status indicator.
  - `synchronization_completed(object)` -- payload: `int`, the number of
    events processed by the most recent HTTP-recovery catch-up
    (`OrderSyncClient.fetch_missed_events`). Emitted once per completed
    catch-up pass, including a pass that processed zero events.

Never `object`-typed as "anything goes" in practice -- each signal's
payload type is fixed above; `implementer`/`python-network-engineer`
should emit exactly that shape, not a raw dict/ORM row.

TODO(implementer / python-network-engineer): construct this with a
`networking.order_sync_client.OrderSyncClient`, an `OnlineOrderService`
(services/online_orders.py), and an `OrderSyncStateRepository` (per
admin-architecture.md §5), and implement `start()`/`stop()` to run the
receive loop on a background `QThread` via `ui/workers.run_in_background`
-- never blocking the Qt event loop, never importing
`websocket`/`requests`/`json` directly in this module (that stays behind
`OrderSyncClient`, per admin-architecture.md §9). Every event must be
persisted and committed locally *before* `OrderSyncClient.acknowledge`
is called (commit-then-ack, admin-architecture.md §7/§9/§10) -- that
ordering belongs in this class's event-handling method, not in the UI.
`main.py` wiring: construct alongside `start_background_server(...)`,
call `start()` after the `ONLINE` `PosSession` bootstrap, and call
`stop()` from the same `aboutToQuit` handler that shuts down the TCP
server.
"""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, Signal

from exceptions import SyncError
from models import DEFAULT_DEVICE_ID
from networking.order_sync_client import OrderSyncClient
from repositories.online_order import OnlineOrderRepository
from schemas.order_sync_events import OrderEventType, OrderSyncEvent
from services.online_orders import OnlineOrderService

logger = logging.getLogger(__name__)


class SyncService(QObject):
    """Qt-signal surface only. No socket/HTTP/JSON import here -- see
    module docstring and `.claude/rules/desktop.md`/`ui-components.md`'s
    "UI/service layer never touches sockets directly" boundary."""

    new_online_order = Signal(object)
    order_confirmed = Signal(object)
    order_rejected = Signal(object)
    connection_changed = Signal(object)
    synchronization_completed = Signal(object)

    def __init__(
        self,
        client: OrderSyncClient,
        order_service: OnlineOrderService,
        order_repository: OnlineOrderRepository,
        device_id: str = DEFAULT_DEVICE_ID,
    ) -> None:
        super().__init__()
        self._client = client
        self._order_service = order_service
        self._order_repository = order_repository
        self._device_id = device_id
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Return the latest connection state for newly opened screens."""
        return self._connected

    def start(self) -> None:
        """Begins the background receive loop. TODO(implementer): see
        module docstring."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="order-sync", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Stops the background receive loop and disconnects the
        transport; called from `main.py`'s `aboutToQuit` handler. Must be
        safe to call even if `start()` was never called or already
        stopped. TODO(implementer): see module docstring."""
        self._stop_event.set()
        self._connected = False
        self.connection_changed.emit(False)
        self._client.disconnect()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=0.5)

    def process_event(self, event: OrderSyncEvent) -> None:
        """Persist an event and advance the cursor before acknowledging it."""
        detail = self._client.fetch_order_detail(event.order_id)
        order = self._order_repository.save_snapshot(detail)
        if event.event_type is OrderEventType.ORDER_CONFIRMED:
            self._order_service.retry_conversion(order.id)
            self.order_confirmed.emit(order.id)
        elif event.event_type is OrderEventType.ORDER_REJECTED:
            self.order_rejected.emit(order.id)
        else:
            self.new_online_order.emit(self._order_service.get_order_row(order.id))
        self._order_repository.save_sync_state(self._device_id, event.event_id)
        self._client.acknowledge(event.order_id, self._device_id, event.event_id)
        self._order_repository.mark_acknowledged(detail.order_id)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._client.connect()
                if self._stop_event.is_set():
                    break
                self._client.send_connect_handshake(self._last_event_id())
                if self._stop_event.is_set():
                    break
                self._connected = True
                self.connection_changed.emit(True)
                recovered = self._client.fetch_missed_events(self._last_event_id())
                for event in recovered:
                    if self._stop_event.is_set():
                        break
                    self.process_event(event)
                self.synchronization_completed.emit(len(recovered))
                self._receive_events()
            except SyncError as exc:
                logger.warning("order_sync op=loop outcome=retry error=%s", exc)
                self._connected = False
                self.connection_changed.emit(False)
                self._client.disconnect()
                self._stop_event.wait(1.0)
            except Exception:
                logger.exception("order_sync op=loop outcome=unexpected_error")
                self._connected = False
                self.connection_changed.emit(False)
                self._client.disconnect()
                self._stop_event.wait(1.0)
        self._client.disconnect()

    def _receive_events(self) -> None:
        while not self._stop_event.is_set():
            event = self._client.receive_event(timeout=1.0)
            if event is not None:
                self.process_event(event)

    def _last_event_id(self) -> int | None:
        state = self._order_repository.get_sync_state(self._device_id)
        return None if state is None else state.last_event_id
