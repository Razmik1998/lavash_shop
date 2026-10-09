"""Admin shell: sidebar navigation, header, and stacked content area."""

from __future__ import annotations

from functools import partial

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from models import User
from services import (
    EmployeeService,
    KitchenService,
    OnlineOrderService,
    ProductService,
    SalesHistoryService,
)
from services.reports import ReportsService
from services.sync import SyncService
from services.waste import WasteService
from ui.cash_withdrawals_window import CashWithdrawalsWindow
from ui.analytics_window import AnalyticsWindow
from ui.components import (
    NavButton,
    NavScrollArea,
    PageTitle,
    QuitButton,
    StatusBadge,
    confirm,
)
from ui.credit_customers_window import CreditCustomersWindow
from ui.employees_window import EmployeesWindow
from ui.kitchen_window import KitchenWindow
from ui.online_selling_window import OnlineSellingWindow
from ui.pos_sessions_window import PosSessionMonitoringService, PosSessionsWindow
from ui.products_window import ProductsWindow, WebSyncService
from ui.purchases_window import PurchaseService, PurchasesWindow
from ui.recommendations_window import RecommendationsWindow
from ui.reports_window import ReportsWindow
from ui.sale_unlock_keys_window import SaleUnlockKeysWindow
from ui.sales_history_window import SalesHistoryWindow
from ui.style import configure_page_layout
from ui.supplier_report_window import SupplierReportWindow
from ui.suppliers_window import SupplierService, SuppliersWindow
from ui.systems_window import SystemsWindow
from ui.waste_window import WasteWindow

_PRODUCTS_LABEL = "Ապրանքներ"
_POS_SESSIONS_LABEL = "POS սեսիաներ"
_SALES_HISTORY_LABEL = "Վաճառքի պատմություն"
_CREDIT_CUSTOMERS_LABEL = "Պարտքով հաճախորդներ"
_BARBECUE_SALES_LABEL = "Խորովածի վաճառք"
_SUPPLIERS_LABEL = "Մատակարարներ"
_PURCHASES_LABEL = "Գնումներ"
_SUPPLIER_REPORT_LABEL = "Մատակարարների հաշվետվություն"
_EMPLOYEES_LABEL = "Աշխատակիցներ"
_SALE_UNLOCK_KEYS_LABEL = "POS բացման բանալիներ"
_ONLINE_SELLING_LABEL = "Օնլայն վաճառք"
_RECOMMENDATIONS_LABEL = "Գնման առաջարկներ"
_ANALYTICS_LABEL = "Վաճառքի վերլուծություն"
_KITCHEN_LABEL = "Խոհանոց"
_WASTE_LABEL = "Դուրսգրում · Отход"


def _placeholder_page(title: str) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout()
    configure_page_layout(layout)
    label = QLabel(f"{title} — շուտով")
    label.setObjectName("pageTitle")
    layout.addWidget(label)
    page.setLayout(layout)
    return page


class AdminMainWindow(QMainWindow):
    def __init__(
        self,
        employee_service: EmployeeService,
        admin_user: User,
        product_service: ProductService | None = None,
        pos_session_service: PosSessionMonitoringService | None = None,
        sales_history_service: SalesHistoryService | None = None,
        supplier_service: SupplierService | None = None,
        purchase_service: PurchaseService | None = None,
        business_timezone: str = "Asia/Yerevan",
        web_sync_service: WebSyncService | None = None,
        online_order_service: OnlineOrderService | None = None,
        sync_service: SyncService | None = None,
        analytics_service: object | None = None,
        kitchen_service: KitchenService | None = None,
        waste_service: WasteService | None = None,
        reports_service: ReportsService | None = None,
        systems_service: object | None = None,
        cash_repository=None,
    ) -> None:
        super().__init__()
        self.setWindowTitle(f"Ադմինիստրատոր — {admin_user.full_name}")

        self._pages = QStackedWidget()
        self._page_labels = [
            _PRODUCTS_LABEL,
            _SUPPLIERS_LABEL,
            _PURCHASES_LABEL,
            _SUPPLIER_REPORT_LABEL,
            _EMPLOYEES_LABEL,
            _POS_SESSIONS_LABEL,
            _SALES_HISTORY_LABEL,
            _CREDIT_CUSTOMERS_LABEL,
            _BARBECUE_SALES_LABEL,
            _SALE_UNLOCK_KEYS_LABEL,
            _ONLINE_SELLING_LABEL,
            _RECOMMENDATIONS_LABEL,
            _ANALYTICS_LABEL,
            _KITCHEN_LABEL,
            _WASTE_LABEL,
            "Բիզնեսի հաշվետվություն",
            "Համակարգեր",
            "Դրամարկղի դուրսբերումներ",
        ]
        if product_service is None:
            self._pages.addWidget(_placeholder_page(_PRODUCTS_LABEL))
        else:
            self._pages.addWidget(
                ProductsWindow(product_service, web_sync_service=web_sync_service)
            )
        if supplier_service is None:
            self._pages.addWidget(_placeholder_page(_SUPPLIERS_LABEL))
        else:
            self._pages.addWidget(
                SuppliersWindow(
                    supplier_service,
                    purchase_service,
                    product_service,
                )
            )
        if purchase_service is None:
            self._pages.addWidget(_placeholder_page(_PURCHASES_LABEL))
        else:
            self._pages.addWidget(
                PurchasesWindow(
                    purchase_service,
                    supplier_service,
                    product_service,
                    business_timezone=business_timezone,
                )
            )
        if purchase_service is None or supplier_service is None:
            self._pages.addWidget(_placeholder_page(_SUPPLIER_REPORT_LABEL))
        else:
            self._pages.addWidget(
                SupplierReportWindow(purchase_service, supplier_service)
            )
        self._pages.addWidget(EmployeesWindow(employee_service, admin_user))
        if pos_session_service is None:
            self._pages.addWidget(_placeholder_page(_POS_SESSIONS_LABEL))
        else:
            sessions_window = PosSessionsWindow(
                pos_session_service, sales_history_service
            )
            self._pages.addWidget(sessions_window)
        if sales_history_service is None:
            self._pages.addWidget(_placeholder_page(_SALES_HISTORY_LABEL))
        else:
            self._pages.addWidget(
                SalesHistoryWindow(sales_history_service, actor_user_id=admin_user.id)
            )
        if sales_history_service is None:
            self._pages.addWidget(_placeholder_page(_CREDIT_CUSTOMERS_LABEL))
        else:
            self._pages.addWidget(CreditCustomersWindow(sales_history_service))
        if sales_history_service is None:
            self._pages.addWidget(_placeholder_page(_BARBECUE_SALES_LABEL))
        else:
            self._pages.addWidget(
                SalesHistoryWindow(
                    sales_history_service,
                    barbecue_only=True,
                    actor_user_id=admin_user.id,
                )
            )
        if sales_history_service is None:
            self._pages.addWidget(_placeholder_page(_SALE_UNLOCK_KEYS_LABEL))
        else:
            self._pages.addWidget(
                SaleUnlockKeysWindow(sales_history_service, admin_user)
            )
        if online_order_service is None:
            self._pages.addWidget(_placeholder_page(_ONLINE_SELLING_LABEL))
        else:
            self._pages.addWidget(
                OnlineSellingWindow(online_order_service, sync_service)
            )
        if purchase_service is None:
            self._pages.addWidget(_placeholder_page(_RECOMMENDATIONS_LABEL))
        else:
            self._pages.addWidget(RecommendationsWindow(purchase_service))
        if analytics_service is None:
            self._pages.addWidget(_placeholder_page(_ANALYTICS_LABEL))
        else:
            self._pages.addWidget(AnalyticsWindow(analytics_service))
        if kitchen_service is None or product_service is None:
            self._pages.addWidget(_placeholder_page(_KITCHEN_LABEL))
        else:
            self._pages.addWidget(
                KitchenWindow(kitchen_service, product_service, admin_user)
            )
        if waste_service is None or product_service is None:
            self._pages.addWidget(_placeholder_page(_WASTE_LABEL))
        else:
            self._pages.addWidget(
                WasteWindow(
                    waste_service, product_service, admin_user, business_timezone
                )
            )
        self._pages.addWidget(
            ReportsWindow(reports_service)
            if reports_service is not None
            else _placeholder_page("Բիզնեսի հաշվետվություն")
        )
        self._pages.addWidget(SystemsWindow(systems_service))
        self._pages.addWidget(
            CashWithdrawalsWindow(cash_repository)
            if cash_repository
            else _placeholder_page("Դրամարկղի դուրսբերումներ")
        )
        self._build_shell(admin_user)
        self._pages.setCurrentIndex(0)

    def _build_shell(self, admin_user: User) -> None:
        shell = QWidget()
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(228)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 20, 16, 20)
        sidebar_layout.setSpacing(6)
        brand = QLabel("Market")
        brand.setObjectName("brand")
        sidebar_layout.addWidget(brand)
        brand_caption = QLabel("Վաճառքի կառավարում")
        brand_caption.setObjectName("brandCaption")
        sidebar_layout.addWidget(brand_caption)
        sidebar_layout.addSpacing(18)

        navigation_groups = [
            ("Ապրանքներ և խոհանոց", [0, 13, 14]),
            ("Գնումներ և մատակարարներ", [1, 2, 3, 11]),
            ("Վաճառք", [5, 6, 7, 8, 10, 12]),
            ("Հաշվետվություններ", [15]),
            ("Կառավարում", [4, 9, 16, 17]),
        ]
        self._nav_scroll = nav_scroll = NavScrollArea()
        buttons_by_index: dict[int, NavButton] = {}
        self._nav_groups: list[tuple[QPushButton, QWidget]] = []
        self._page_groups: dict[int, int] = {}
        self._nav_animations: list[QPropertyAnimation] = []
        for group_index, (title, page_indices) in enumerate(navigation_groups):
            toggle = QPushButton()
            toggle.setObjectName("navGroupButton")
            toggle.setCheckable(True)
            toggle.setMinimumHeight(38)
            toggle.setAccessibleName(title)
            toggle.setToolTip(title)
            nav_scroll.body.addWidget(toggle)
            children = QWidget()
            children.setObjectName("navGroupBody")
            children_layout = QVBoxLayout(children)
            children_layout.setContentsMargins(10, 0, 0, 0)
            children_layout.setSpacing(4)
            for index in page_indices:
                label = self._page_labels[index]
                button = NavButton(label, on_click=partial(self._select_page, index))
                button.set_active(index == 0)
                button.setChecked(index == 0)
                button.setToolTip(label)
                children_layout.addWidget(button)
                buttons_by_index[index] = button
                self._page_groups[index] = group_index
            nav_scroll.body.addWidget(children)
            self._nav_groups.append((toggle, children))
            toggle.toggled.connect(partial(self._toggle_nav_group, group_index))
            toggle.setText(f"▸  {title}")
            children.setMaximumHeight(0)
            children.hide()
            animation = QPropertyAnimation(children, b"maximumHeight", self)
            animation.setDuration(240)
            animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
            animation.finished.connect(partial(self._finish_nav_animation, group_index))
            self._nav_animations.append(animation)
        self._nav_buttons = [buttons_by_index[i] for i in range(len(self._page_labels))]
        self._nav_groups[0][0].setChecked(True)
        nav_scroll.body.addStretch()
        sidebar_layout.addWidget(nav_scroll, stretch=1)
        user_panel = QFrame()
        user_panel.setObjectName("userPanel")
        user_layout = QVBoxLayout(user_panel)
        user_layout.setContentsMargins(12, 10, 12, 10)
        user_layout.setSpacing(2)
        user_caption = QLabel("Մուտք գործած օգտատեր")
        user_caption.setObjectName("userCaption")
        user_label = QLabel(admin_user.full_name)
        user_label.setObjectName("userName")
        user_layout.addWidget(user_caption)
        user_layout.addWidget(user_label)
        sidebar_layout.addWidget(user_panel)
        sidebar_layout.addWidget(QuitButton(on_click=self._quit))

        content = QWidget()
        content.setObjectName("content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 18, 24, 0)
        header_layout = QHBoxLayout()
        header = QFrame()
        header.setObjectName("header")
        header.setLayout(header_layout)
        self._header_title = PageTitle(_PRODUCTS_LABEL)
        header_layout.addWidget(self._header_title)
        header_layout.addStretch()
        connection_badge = StatusBadge("Համակարգը հասանելի է")
        header_layout.addWidget(connection_badge)
        content_layout.addWidget(header)
        content_layout.addWidget(self._pages, stretch=1)

        shell_layout.addWidget(sidebar)
        shell_layout.addWidget(content, stretch=1)
        self.setCentralWidget(shell)

    def _quit(self) -> None:
        if confirm(self, "Դուրս գալ", "Փակե՞լ հավելվածը։"):
            self.close()

    def _toggle_nav_group(self, group_index: int, expanded: bool) -> None:
        toggle, children = self._nav_groups[group_index]
        title = toggle.accessibleName()
        toggle.setText(f"{'▾' if expanded else '▸'}  {title}")
        animation = self._nav_animations[group_index]
        animation.stop()
        target_height = children.layout().sizeHint().height() if expanded else 0
        if self.isVisible():
            current_height = children.height() if children.isVisible() else 0
            children.setMaximumHeight(current_height)
            children.show()
            animation.setStartValue(current_height)
            animation.setEndValue(target_height)
            animation.start()
        else:
            children.setMaximumHeight(target_height)
            children.setVisible(expanded)
        if expanded:
            for other_index, (other_toggle, _) in enumerate(self._nav_groups):
                if other_index != group_index:
                    other_toggle.setChecked(False)

    def _finish_nav_animation(self, group_index: int) -> None:
        toggle, children = self._nav_groups[group_index]
        if not toggle.isChecked():
            children.hide()
        elif self._page_groups[self._pages.currentIndex()] == group_index:
            self._nav_scroll.reveal(self._nav_buttons[self._pages.currentIndex()])

    def _select_page(self, index: int) -> None:
        self._pages.setCurrentIndex(index)
        self._header_title.setText(self._page_labels[index])
        self._nav_groups[self._page_groups[index]][0].setChecked(True)
        for button_index, button in enumerate(self._nav_buttons):
            button.set_active(button_index == index)
            button.setChecked(button_index == index)
        # Wait for expanded/collapsed layouts before scrolling to the selection.
        QTimer.singleShot(0, partial(self._nav_scroll.reveal, self._nav_buttons[index]))
