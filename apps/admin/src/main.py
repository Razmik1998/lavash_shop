"""Admin application entrypoint."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from config import load_settings
from repositories.cash_withdrawal import CashWithdrawalRepository
from db import create_session_factory
from logging_setup import configure_logging, mask_database_url
from models import User
from networking.order_sync_client import DjangoOrderSyncClient
from networking.server import start_background_server
from networking.web_sync_client import WebSyncClient
from repositories.reports import ReportsRepository
from repositories.waste import WasteRepository
from repository import (
    CustomerRepository,
    KitchenRepository,
    OnlineOrderRepository,
    PosSessionRepository,
    ProductRepository,
    PurchaseRepository,
    SaleRepository,
    SupplierRepository,
    UserRepository,
)
from services import (
    AuthService,
    EmployeeService,
    KitchenService,
    OnlineOrderService,
    PosSessionService,
    ProductService,
    PurchaseService,
    SalesService,
    SupplierService,
    SyncService,
    WebSyncService,
)
from services.analytics import AnalyticsService
from services.reports import ReportsService
from services.systems import SystemsService
from services.waste import WasteService
from ui.login_window import LoginWindow
from ui.main_window import AdminMainWindow
from ui.style import apply_admin_style

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
        "starting admin app database_url=%s admin_lan_port=%s business_timezone=%s",
        mask_database_url(settings.database_url),
        settings.admin_lan_port,
        settings.business_timezone,
    )
    session_factory = create_session_factory(settings)
    user_repository = UserRepository(session_factory)
    product_repository = ProductRepository(session_factory)
    pos_session_repository = PosSessionRepository(session_factory)
    sale_repository = SaleRepository(session_factory)
    customer_repository = CustomerRepository(session_factory)
    supplier_repository = SupplierRepository(session_factory)
    purchase_repository = PurchaseRepository(session_factory)
    auth_service = AuthService(user_repository)
    employee_service = EmployeeService(user_repository)
    product_service = ProductService(product_repository)
    supplier_service = SupplierService(supplier_repository)
    purchase_service = PurchaseService(purchase_repository, product_repository)
    cash_repository = CashWithdrawalRepository(session_factory)
    pos_session_service = PosSessionService(
        pos_session_repository,
        user_repository,
        sale_repository,
        customer_repository,
        cash_repository,
    )
    sales_service = SalesService(
        sale_repository,
        pos_session_repository,
        product_repository,
        settings.business_timezone,
        customer_repository,
    )
    analytics_service = AnalyticsService(sale_repository, settings.business_timezone)
    web_sync_client = None
    order_sync_client = None
    web_sync_service: WebSyncService | None = None
    online_order_repository = OnlineOrderRepository(session_factory)
    kitchen_repository = KitchenRepository(session_factory)
    kitchen_service = KitchenService(kitchen_repository)
    waste_service = WasteService(WasteRepository(session_factory))
    online_order_service = OnlineOrderService(online_order_repository)
    sync_service: SyncService | None = None
    if settings.web_sync_url and settings.web_sync_api_key:
        web_sync_client = WebSyncClient(
            settings.web_sync_url, settings.web_sync_api_key
        )
        web_sync_service = WebSyncService(product_service, web_sync_client)
        order_sync_client = DjangoOrderSyncClient(
            settings.web_sync_url, settings.web_sync_api_key
        )
        sync_service = SyncService(
            order_sync_client,
            online_order_service,
            online_order_repository,
        )

    tcp_server = start_background_server(
        "0.0.0.0",
        settings.admin_lan_port,
        auth_service,
        pos_session_service,
        sales_service,
        product_service,
    )

    app = QApplication(sys.argv)
    apply_admin_style(app)
    systems_service = SystemsService(sync_service, order_sync_client, web_sync_client)

    def _shutdown_tcp_server() -> None:
        if sync_service is not None:
            sync_service.stop()
        tcp_server.shutdown()
        tcp_server.server_close()

    app.aboutToQuit.connect(_shutdown_tcp_server)

    windows: list[object] = []

    def on_login_success(admin_user: User) -> None:
        main_window = AdminMainWindow(
            employee_service,
            admin_user,
            product_service,
            pos_session_service,
            sales_service,
            supplier_service,
            purchase_service,
            settings.business_timezone,
            web_sync_service,
            online_order_service,
            sync_service,
            analytics_service,
            kitchen_service,
            waste_service,
            ReportsService(
                ReportsRepository(session_factory), settings.business_timezone
            ),
            systems_service=systems_service,
            cash_repository=cash_repository,
        )
        main_window.showFullScreen()
        windows.append(main_window)
        login_window.close()

    login_window = LoginWindow(auth_service, on_login_success)
    login_window.resize(320, 160)
    login_window.show()
    windows.append(login_window)

    systems_service.start()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
