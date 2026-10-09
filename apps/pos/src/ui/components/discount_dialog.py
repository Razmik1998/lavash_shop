from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ui.components.buttons import CancelButton, GhostButton, SaveButton
from ui.components.inputs import MoneyField
from ui.components.panels import ErrorLabel
from ui.style import format_currency

_SLIDER_STEPS = 1000


class DiscountDialog(QDialog):
    """Pick a unit price between the product minimum and its selling price.

    The dialog opens on ``current_price`` (the selling price by default) and
    only accepts values inside ``[minimum_price, original_price]``.
    """

    _STYLE = """
    QDialog#discountDialog { background: #ffffff; }
    QLabel#discountTitle { font-size: 18px; font-weight: 700; color: #111827; }
    QLabel#discountRange {
        background: #eff6ff; color: #1d4ed8; border-radius: 10px;
        padding: 6px 12px; font-weight: 600;
    }
    QFrame#discountSummary {
        background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 12px;
    }
    QLabel#discountNewPrice { font-size: 26px; font-weight: 800; color: #15803d; }
    QLabel#discountCaption { color: #6b7280; }
    QSlider::groove:horizontal { height: 8px; background: #e5e7eb; border-radius: 4px; }
    QSlider::sub-page:horizontal { background: #2563eb; border-radius: 4px; }
    QSlider::handle:horizontal {
        width: 22px; height: 22px; margin: -8px 0; border-radius: 11px;
        background: #ffffff; border: 3px solid #2563eb;
    }
    """

    def __init__(
        self,
        product_name: str,
        original_price: Decimal,
        minimum_price: Decimal,
        current_price: Decimal | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("discountDialog")
        self.setWindowTitle("Զեղչ")
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setStyleSheet(self._STYLE)
        self._original = original_price
        self._minimum = min(minimum_price, original_price)
        self._selected = self._clamp(
            original_price if current_price is None else current_price
        )
        self._syncing = False

        title = QLabel(product_name)
        title.setObjectName("discountTitle")
        title.setWordWrap(True)
        range_label = QLabel(
            f"Թույլատրելի տիրույթ՝ {format_currency(self._minimum)} – "
            f"{format_currency(self._original)}"
        )
        range_label.setObjectName("discountRange")

        self._price_field = MoneyField("Նոր գին", on_changed=self._on_text_changed)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, _SLIDER_STEPS)
        self._slider.setEnabled(self._original > self._minimum)
        self._slider.valueChanged.connect(self._on_slider_changed)

        min_button = GhostButton("Նվազագույն", on_click=lambda: self._set_price(self._minimum))
        max_button = GhostButton("Սկզբնական գին", on_click=lambda: self._set_price(self._original))
        presets = QHBoxLayout()
        presets.addWidget(min_button)
        presets.addStretch()
        presets.addWidget(max_button)

        self._new_price = QLabel()
        self._new_price.setObjectName("discountNewPrice")
        self._savings = QLabel()
        self._savings.setObjectName("discountCaption")
        summary = QFrame()
        summary.setObjectName("discountSummary")
        summary_layout = QVBoxLayout(summary)
        caption = QLabel("Վաճառքի գին")
        caption.setObjectName("discountCaption")
        summary_layout.addWidget(caption)
        summary_layout.addWidget(self._new_price)
        summary_layout.addWidget(self._savings)

        self._error = ErrorLabel()
        self._save = SaveButton("Կիրառել", on_click=self._accept_if_valid)
        cancel = CancelButton("Չեղարկել", on_click=self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(self._save)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(range_label, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._price_field)
        layout.addWidget(self._slider)
        layout.addLayout(presets)
        layout.addWidget(summary)
        layout.addWidget(self._error)
        layout.addLayout(buttons)

        self._set_price(self._selected)

    def price(self) -> Decimal:
        return self._selected

    def _clamp(self, value: Decimal) -> Decimal:
        return max(self._minimum, min(self._original, value))

    def _price_to_slider(self, price: Decimal) -> int:
        span = self._original - self._minimum
        if span <= 0:
            return _SLIDER_STEPS
        return int(((price - self._minimum) / span * _SLIDER_STEPS).to_integral_value(ROUND_HALF_UP))

    def _slider_to_price(self, value: int) -> Decimal:
        span = self._original - self._minimum
        raw = self._minimum + span * Decimal(value) / Decimal(_SLIDER_STEPS)
        return raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP) if span >= _SLIDER_STEPS else raw.quantize(Decimal("0.01"))

    def _set_price(self, price: Decimal) -> None:
        self._selected = self._clamp(price)
        self._refresh(update_text=True, update_slider=True)

    def _on_slider_changed(self, value: int) -> None:
        if self._syncing:
            return
        self._selected = self._clamp(self._slider_to_price(value))
        self._refresh(update_text=True, update_slider=False)

    def _on_text_changed(self) -> None:
        if self._syncing:
            return
        value = self._price_field.decimal_value()
        in_range = value is not None and self._minimum <= value <= self._original
        if in_range and value is not None:
            self._selected = value
            self._refresh(update_text=False, update_slider=True)
        else:
            self._save.setEnabled(False)
            self._error.setText(
                f"Գինը պետք է լինի {format_currency(self._minimum)} և "
                f"{format_currency(self._original)} միջակայքում։"
            )

    def _refresh(self, *, update_text: bool, update_slider: bool) -> None:
        self._syncing = True
        try:
            if update_text:
                self._price_field.setText(f"{self._selected:f}")
            if update_slider:
                self._slider.setValue(self._price_to_slider(self._selected))
        finally:
            self._syncing = False
        discount = self._original - self._selected
        percent = (
            (discount / self._original * 100).quantize(Decimal("0.1"))
            if self._original > 0
            else Decimal("0")
        )
        self._new_price.setText(format_currency(self._selected))
        self._savings.setText(
            f"Զեղչ՝ {format_currency(discount)} ({percent}%)" if discount > 0 else "Առանց զեղչի"
        )
        self._error.setText("")
        self._save.setEnabled(True)

    def _accept_if_valid(self) -> None:
        if self._save.isEnabled():
            self.accept()
