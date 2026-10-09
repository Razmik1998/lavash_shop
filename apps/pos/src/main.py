"""POS application entrypoint."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from config import load_settings
from logging_setup import configure_logging
from models import User
from networking.local_connection import LocalConnection
from networking.protocol import SessionPayload
from printing import ReceiptSettings, ThermalPrinterService
from services import (
    AuthService,
    CustomerService,
    PosSessionService,
    ProductService,
    SaleService,
)
from ui.home_window import HomeWindow
from ui.login_window import LoginWindow
from ui.session_window import SessionWindow
from ui.style import apply_pos_style

_ADMIN_UNAVAILABLE_MESSAGE = "Ադմինիստրատոր հասանելի չէ։"

logger = logging.getLogger(__name__)


def main() -> int:
    configure_logging()
    try:
        return _run()
    except Exception:
        logger.critical("startup failed", exc_info=True)
        raise


def _run() -> int:
    settings = load_settings()
    logger.info(
        "starting pos app admin_host=%s admin_port=%s terminal_id=%s printer_name=%s "
        "store_name=%s receipt_paper_width_mm=%s receipt_directory=%s",
        settings.admin_host,
        settings.admin_port,
        settings.terminal_id,
        settings.printer_name,
        settings.store_name,
        settings.receipt_paper_width_mm,
        settings.receipt_directory,
    )
    connection = LocalConnection(settings.admin_host, settings.admin_port)

    app = QApplication.instance() or QApplication(sys.argv)
    apply_pos_style(app)

    if not connection.is_available():
        logger.error(
            "admin_host=%s admin_port=%s outcome=unavailable",
            settings.admin_host,
            settings.admin_port,
        )
        QMessageBox.critical(None, "Սխալ", _ADMIN_UNAVAILABLE_MESSAGE)
        return 1

    auth_service = AuthService(connection)
    session_service = PosSessionService(connection)
    product_service = ProductService(connection)
    sale_service = SaleService(connection)
    customer_service = CustomerService(connection)
    printer_service = ThermalPrinterService(
        ReceiptSettings(
            store_name=settings.store_name,
            phone_numbers=settings.store_phone_numbers,
            address=settings.store_address,
            paper_width_mm=settings.receipt_paper_width_mm,
            receipt_directory=settings.receipt_directory,
            chars_per_line=settings.receipt_chars_per_line,
            cut_paper=settings.receipt_cut,
            online_order_url=settings.online_order_url,
            language=settings.receipt_language,
        ),
        settings.printer_name or "XP-80C",
        enabled=settings.printer_enabled,
    )
    windows: list[object] = []
    active_session_id: list[str] = []

    def show_session_window(employee: User) -> None:
        session_window = SessionWindow(
            session_service,
            employee,
            settings.terminal_id,
            auth_service.reconnect,
        )
        session_window.session_started.connect(
            lambda session: on_session_started(employee, session_window, session)
        )
        session_window.showFullScreen()
        windows.append(session_window)

    def on_session_started(
        employee: User, session_window: SessionWindow, session: SessionPayload
    ) -> None:
        active_session_id.clear()
        active_session_id.append(session.id)
        home_window = HomeWindow(
            employee,
            session_service,
            session,
            product_service,
            sale_service,
            customer_service,
            printer_service,
            session_window._opening_cash,
            auth_service.reconnect,
        )
        home_window.session_closed.connect(
            lambda: on_session_closed(employee, home_window)
        )
        home_window.showFullScreen()
        windows.append(home_window)
        session_window.close()

    def on_session_closed(employee: User, home_window: HomeWindow) -> None:
        active_session_id.clear()
        # The session ended (explicit close) but the employee remains
        # authenticated in this running process — return to the
        # session page rather than forcing a full re-login.
        home_window.close()
        show_session_window(employee)

    def on_login_success(employee: User) -> None:
        show_session_window(employee)
        login_window.close()

    def cleanup() -> None:
        if active_session_id:
            try:
                session_service.disconnect(active_session_id[0])
            except Exception:
                pass

    app.aboutToQuit.connect(cleanup)

    login_window = LoginWindow(auth_service, on_login_success)
    login_window.resize(920, 560)
    login_window.setMinimumSize(760, 480)
    login_window.show()
    windows.append(login_window)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
