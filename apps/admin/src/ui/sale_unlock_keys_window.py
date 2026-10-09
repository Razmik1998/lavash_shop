"""Admin-only management screen for hashed POS document unlock keys."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget

from models import SaleUnlockKey, User
from schemas import SaleKeyHistoryRow
from services import SalesService
from ui.components import (
    AddButton,
    DataTable,
    DatePeriodFilter,
    EditButton,
    FilterBar,
    GhostButton,
    PageTitle,
    TextField,
    report_error,
    warn,
)
from ui.style import configure_page_layout, format_currency, format_quantity
from ui.workers import run_in_background, wait_for_pending_threads

ARMENIA_TIMEZONE = ZoneInfo("Asia/Yerevan")

_AUDIT_LABELS = {
    "created": "Ստեղծված",
    "DOCUMENT_UNLOCKED": "Փաստաթուղթը բացվել է",
    "DOCUMENT_EDIT_STARTED": "Խմբագրումը սկսվել է",
    "DOCUMENT_RECONFIRMED": "Փաստաթուղթը վերահաստատվել է",
    "DOCUMENT_CANCELLED": "Փաստաթուղթը չեղարկվել է",
    "PAYMENT_TYPE_CHANGED": "Վճարման ձևը փոխվել է",
}

_VALUE_LABELS = {
    "total": "Ընդհանուր",
    "revision": "Վերանայում",
    "product_name": "Ապրանք",
    "product_sku": "Կոդ",
    "quantity": "Քանակ",
    "unit_price": "Գին",
    "line_total": "Գումար",
    "payment": "Վճարում",
    "customer": "Պարտապան",
}

_PAYMENT_LABELS = {"cash": "Կանխիկ", "credit": "Պարտքով"}


def _audit_label(event_type: str) -> str:
    return _AUDIT_LABELS.get(event_type, event_type)


def _format_change(value: dict[str, object] | None) -> str:
    if not value:
        return "-"
    parts: list[str] = []
    for key, raw in value.items():
        if key == "authorization_key_id":
            continue
        label = _VALUE_LABELS.get(key, key)
        if key in {"total", "unit_price", "line_total"}:
            try:
                rendered = format_currency(Decimal(str(raw)))
            except (InvalidOperation, ValueError):
                rendered = str(raw)
        elif key == "quantity":
            try:
                rendered = format_quantity(Decimal(str(raw)))
            except (InvalidOperation, ValueError):
                rendered = str(raw)
        elif key == "payment":
            rendered = _PAYMENT_LABELS.get(str(raw), str(raw))
        elif key == "items" and isinstance(raw, list):
            rendered_items = []
            for item in raw:
                if isinstance(item, dict):
                    name = item.get("product_name") or item.get("product_sku", "Ապրանք")
                    quantity = item.get("quantity", "-")
                    rendered_items.append(f"{name} × {quantity}")
            rendered = "; ".join(rendered_items) or "-"
        else:
            rendered = str(raw)
        parts.append(f"{label}: {rendered}")
    return "; ".join(parts) or "-"


class SaleUnlockKeysWindow(QWidget):
    def __init__(self, service: SalesService, admin_user: User) -> None:
        super().__init__()
        self._service = service
        self._admin_user = admin_user
        self._name = TextField("Բանալիի անվանում")
        self._value = TextField("Գաղտնի բանալի", password=True)
        self._keys: list[SaleUnlockKey] = []
        self._selected_key: SaleUnlockKey | None = None
        self._stack = QStackedWidget()
        self._list_page = self._build_list_page()
        self._history_page = self._build_history_page()
        self._stack.addWidget(self._list_page)
        self._stack.addWidget(self._history_page)
        layout = QVBoxLayout(self)
        configure_page_layout(layout)
        layout.addWidget(self._stack)
        self._reload()

    def _build_list_page(self) -> QWidget:
        page = QWidget()
        self._table = DataTable(
            ["Անվանում", "Ակտիվ", "Ստեղծված"],
            on_double_click=self._open_selected_history,
            on_selection_changed=self._selection_changed,
        )
        add = AddButton("Ստեղծել բանալի", on_click=self._create)
        self._toggle = EditButton(
            "Միացնել/անջատել", on_click=self._toggle_selected, enabled=False
        )
        form = QHBoxLayout()
        form.addWidget(self._name)
        form.addWidget(self._value)
        form.addWidget(add)
        form.addWidget(self._toggle)
        layout = QVBoxLayout(page)
        configure_page_layout(layout)
        layout.addWidget(PageTitle("POS բացման բանալիներ"))
        layout.addLayout(form)
        layout.addWidget(self._table, stretch=1)
        return page

    def _build_history_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        header = QHBoxLayout()
        header.addWidget(GhostButton("← Վերադառնալ", on_click=self._show_key_list))
        self._history_title = PageTitle("Բանալիի պատմություն")
        header.addWidget(self._history_title)
        header.addStretch()
        layout.addLayout(header)
        self._history_period = DatePeriodFilter(on_change=self._reload_key_history)
        layout.addWidget(
            FilterBar([("Ժամանակահատված", self._history_period)], title="Զտիչներ")
        )
        self._history_table = DataTable(
            [
                "Փաստաթուղթ",
                "POS տերմինալ",
                "Սեսիա",
                "Գործողություն",
                "Փոփոխությունը կատարող",
                "Նախորդ արժեք",
                "Նոր արժեք",
                "Ամսաթիվ",
            ]
        )
        self._history_empty = PageTitle("")
        layout.addWidget(self._history_empty)
        layout.addWidget(self._history_table, stretch=1)
        return page

    def _reload(self) -> None:
        run_in_background(
            self, self._service.list_unlock_keys, self._loaded, self._failed
        )

    def _loaded(self, keys: list[SaleUnlockKey]) -> None:
        self._keys = keys
        self._table.set_rows(
            [key.name, "Այո" if key.is_active else "Ոչ", str(key.created_at)]
            for key in keys
        )

    def _selection_changed(self) -> None:
        self._toggle.setEnabled(self._table.selected_row() >= 0)

    def _open_selected_history(self) -> None:
        row = self._table.selected_row()
        if 0 <= row < len(self._keys):
            self._selected_key = self._keys[row]
            self._history_title.setText(
                f"Բանալիի պատմություն՝ {self._selected_key.name}"
            )
            self._stack.setCurrentWidget(self._history_page)
            self._reload_key_history()

    def _show_key_list(self) -> None:
        self._stack.setCurrentWidget(self._list_page)

    def _reload_key_history(self) -> None:
        if self._selected_key is None:
            return
        from_value, to_value = self._history_period.values()
        from_datetime = (
            from_value.replace(tzinfo=ARMENIA_TIMEZONE) if from_value else None
        )
        to_datetime = to_value.replace(tzinfo=ARMENIA_TIMEZONE) if to_value else None
        run_in_background(
            self,
            lambda: self._service.list_key_history(
                self._selected_key.id, from_datetime, to_datetime
            ),
            self._history_loaded,
            self._failed,
        )

    def _history_loaded(self, rows: list[SaleKeyHistoryRow]) -> None:
        self._history_empty.setText(
            "Պատմություն չի գտնվել ընտրված ժամանակահատվածում։" if not rows else ""
        )
        self._history_table.set_rows(
            [
                str(row.sale_id),
                row.terminal_id,
                str(row.session_id),
                _audit_label(row.event_type),
                row.actor_name,
                _format_change(row.old_value),
                _format_change(row.new_value),
                row.created_at.astimezone(ARMENIA_TIMEZONE).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            ]
            for row in rows
        )

    def _toggle_selected(self) -> None:
        row = self._table.selected_row()
        if 0 <= row < len(self._keys):
            key = self._keys[row]
            run_in_background(
                self,
                lambda: self._service.set_unlock_key_active(key.id, not key.is_active),
                lambda _result: self._reload(),
                self._failed,
            )

    def _create(self) -> None:
        name, value = self._name.value(), self._value.value()
        if not name or not value:
            warn(self, "Բանալիի անվանումը և գաղտնի բանալին պարտադիր են։")
            return
        run_in_background(
            self,
            lambda: self._service.create_unlock_key(name, value, self._admin_user.id),
            lambda _key: (self._name.clear(), self._value.clear(), self._reload()),
            self._failed,
        )

    def _failed(self, error: Exception) -> None:
        report_error(self, str(error))

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        wait_for_pending_threads(self)
        super().closeEvent(event)
