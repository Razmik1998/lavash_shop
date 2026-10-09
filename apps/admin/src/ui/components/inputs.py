"""Input components: every field a screen needs, already styled.

These wrap the Qt widgets so placeholder text, parsing and error wording
stay identical across screens.
"""

from __future__ import annotations

import calendar
from collections.abc import Callable, Sequence
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import cast

from PySide6.QtCore import QDate, QRegularExpression, QTimer
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)


class TextField(QLineEdit):
    def __init__(
        self,
        placeholder: str = "",
        *,
        text: str = "",
        password: bool = False,
        on_submit: Callable[[], object] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        if placeholder:
            self.setPlaceholderText(placeholder)
        if password:
            self.setEchoMode(QLineEdit.EchoMode.Password)
        if on_submit is not None:
            self.returnPressed.connect(lambda: on_submit())

    def value(self) -> str:
        return self.text().strip()


class SearchField(TextField):
    def __init__(
        self,
        placeholder: str = "Որոնել",
        *,
        on_submit: Callable[[], object] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(placeholder, on_submit=on_submit, parent=parent)


class AmountField(TextField):
    """A numeric field that parses to ``Decimal`` or ``None``."""

    def __init__(
        self,
        placeholder: str = "",
        *,
        text: str = "",
        on_edited: Callable[[], object] | None = None,
        on_changed: Callable[[], object] | None = None,
        digits_only: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(placeholder, text=text, parent=parent)
        if digits_only:
            self.setValidator(
                QRegularExpressionValidator(QRegularExpression(r"\d*\.?\d*"), self)
            )
        if on_edited is not None:
            self.editingFinished.connect(lambda: on_edited())
        if on_changed is not None:
            # textEdited fires for user typing only, so programmatic setText
            # from linked fields never re-triggers it.
            self.textEdited.connect(lambda _text: on_changed())

    def decimal_value(self) -> Decimal | None:
        raw = self.text().strip()
        if not raw:
            return None
        try:
            return Decimal(raw)
        except InvalidOperation:
            return None


class MoneyField(AmountField):
    def __init__(self, placeholder: str = "Գումար", **kwargs: object) -> None:
        super().__init__(placeholder, **kwargs)  # type: ignore[arg-type]


class QuantityField(AmountField):
    def __init__(self, placeholder: str = "Քանակ", **kwargs: object) -> None:
        super().__init__(placeholder, **kwargs)  # type: ignore[arg-type]


class TextArea(QPlainTextEdit):
    """A multi-line text field, e.g. for a reject reason or free-form
    note. Use ``TextField``/``SearchField`` for single-line input."""

    def __init__(
        self,
        placeholder: str = "",
        *,
        text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        if placeholder:
            self.setPlaceholderText(placeholder)
        self.setMinimumHeight(90)

    def value(self) -> str:
        return self.toPlainText().strip()


class QuantityDialog(QDialog):
    """Ask for a quantity while showing the product's unit."""

    def __init__(
        self,
        unit_label: str,
        *,
        product_name: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Մուտքագրել քանակ")
        self._quantity = QuantityField(text="1")
        product_field = QLineEdit(product_name)
        product_field.setReadOnly(True)

        form = QFormLayout()
        form.addRow("Ապրանք", product_field)
        form.addRow(f"Քանակ ({unit_label})", self._quantity)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        QTimer.singleShot(0, self._focus_quantity)

    def _focus_quantity(self) -> None:
        self._quantity.setFocus()
        self._quantity.selectAll()

    def _accept_if_valid(self) -> None:
        quantity = self._quantity.decimal_value()
        if quantity is not None and quantity > 0:
            self.accept()

    def quantity(self) -> Decimal | None:
        return self._quantity.decimal_value()


class SelectField(QComboBox):
    def __init__(
        self,
        options: Sequence[tuple[str, object]] = (),
        *,
        on_change: Callable[[], object] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        for label, value in options:
            self.addItem(label, value)
        if on_change is not None:
            self.currentIndexChanged.connect(lambda _index: on_change())

    def set_options(self, options: Sequence[tuple[str, object]]) -> None:
        self.clear()
        for label, value in options:
            self.addItem(label, value)


class DateField(QDateEdit):
    def __init__(
        self,
        *,
        on_change: Callable[[], object] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(QDate.currentDate(), parent)
        self.setCalendarPopup(True)
        if on_change is not None:
            self.dateChanged.connect(lambda _value: on_change())

    def date_value(self) -> date:
        return cast(date, self.date().toPython())


class StatusChecks(QWidget):
    """Two reusable checkboxes for inclusive status filtering."""

    def __init__(
        self,
        *,
        on_change: Callable[[], object] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._active = QCheckBox("Ակտիվ")
        self._closed = QCheckBox("Փակված")
        self._active.setChecked(True)
        self._closed.setChecked(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._active)
        layout.addWidget(self._closed)
        if on_change is not None:
            self._active.toggled.connect(lambda _checked: on_change())
            self._closed.toggled.connect(lambda _checked: on_change())

    def selected(self) -> set[str]:
        statuses: set[str] = set()
        if self._active.isChecked():
            statuses.add("active")
        if self._closed.isChecked():
            statuses.add("closed")
        return statuses


class DatePeriodFilter(QWidget):
    """Reusable quick-period and custom date-range selector."""

    def __init__(
        self,
        *,
        on_change: Callable[[], object] | None = None,
        business_timezone: str | None = None,
        periods: Sequence[tuple[str, str]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._business_timezone = business_timezone
        self._period = SelectField(
            periods
            if periods is not None
            else [
                ("Ամբողջ պատմություն", "all"),
                ("Այսօր", "today"),
                ("Երեկ", "yesterday"),
                ("Վաղը", "tomorrow"),
                ("Այս շաբաթ", "week"),
                ("Այս ամիս", "month"),
                ("Վերջին 2 ամիս", "2_months"),
                ("Վերջին 3 ամիս", "3_months"),
                ("Այս տարի", "year"),
                ("Վերջին 1 տարի", "12_months"),
                ("Անհատական միջակայք", "custom"),
            ],
            on_change=self._period_changed,
        )
        self._from_date = DateField(on_change=on_change)
        self._to_date = DateField(on_change=on_change)
        self._on_change = on_change
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._period)
        layout.addWidget(self._from_date)
        layout.addWidget(self._to_date)
        self._period_changed(notify=False)

    def set_period(self, period: str, *, notify: bool = True) -> None:
        """Select a named period, e.g. ``today`` or ``all``."""
        index = self._period.findData(period)
        if index < 0:
            raise ValueError(f"Unknown date period: {period}")
        if self._period.currentIndex() == index:
            return
        self._period.blockSignals(True)
        self._period.setCurrentIndex(index)
        self._period.blockSignals(False)
        self._period_changed(notify=notify)

    def _period_changed(self, *, notify: bool = True) -> None:
        custom = self._period.currentData() == "custom"
        self._from_date.setEnabled(custom)
        self._to_date.setEnabled(custom)
        if not custom:
            from_value, to_value = self.values()
            if from_value is not None and to_value is not None:
                self._from_date.blockSignals(True)
                self._to_date.blockSignals(True)
                self._from_date.setDate(QDate(from_value.date()))
                self._to_date.setDate(QDate((to_value - timedelta(days=1)).date()))
                self._from_date.blockSignals(False)
                self._to_date.blockSignals(False)
        if notify and self._on_change is not None:
            self._on_change()

    def values(self) -> tuple[datetime | None, datetime | None]:
        period = self._period.currentData()
        if period == "all":
            return None, None
        if self._business_timezone:
            from zoneinfo import ZoneInfo

            today = datetime.now(ZoneInfo(self._business_timezone)).date()
        else:
            today = date.today()
        end = today + timedelta(days=1)
        if period == "today":
            start = today
        elif period == "tomorrow":
            start = today + timedelta(days=1)
            end = start + timedelta(days=1)
        elif period == "yesterday":
            start = today - timedelta(days=1)
            end = today
        elif period == "custom":
            start = self._from_date.date_value()
            end = self._to_date.date_value() + timedelta(days=1)
        elif period == "7_days":
            start = today - timedelta(days=6)
        elif period == "week":
            start = today - timedelta(days=today.weekday())
        elif period == "month":
            start = today.replace(day=1)
        elif period == "year":
            start = date(today.year, 1, 1)
        else:
            months = {
                "1_month": 1,
                "2_months": 2,
                "3_months": 3,
                "6_months": 6,
                "12_months": 12,
            }[period]
            month_index = today.year * 12 + today.month - 1 - months
            year, month = divmod(month_index, 12)
            month += 1
            day = min(today.day, calendar.monthrange(year, month)[1])
            start = date(year, month, day)
        return datetime.combine(start, time.min), datetime.combine(end, time.min)
