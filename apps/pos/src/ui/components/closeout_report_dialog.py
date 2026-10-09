"""Readable, read-only presentation of a completed POS session."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.style import format_currency


class CloseoutReportDialog(QDialog):
    def __init__(
        self,
        *,
        opening_cash: Decimal,
        cash_sales: Decimal,
        credit_sales: Decimal,
        repayments: Decimal,
        withdrawals_total: Decimal,
        closing_cash: Decimal,
        withdrawals: Sequence[Mapping[str, object]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("closeoutReport")
        self.setWindowTitle("Սեսիայի ամփոփագիր")
        self.setModal(True)
        self.resize(860, 760)
        self.setStyleSheet("""
            QDialog#closeoutReport { background: #073d38; }
            QDialog#closeoutReport QLabel { color: #f1faf6; background: transparent;
                font-size: 14px; border: none; }
            QDialog#closeoutReport QLabel[role="muted"] { color: #a6c9be; }
            QDialog#closeoutReport QLabel[role="title"] {
                font-size: 25px; font-weight: 700; }
            QDialog#closeoutReport QLabel[role="section"] {
                font-size: 16px; font-weight: 700; }
            QDialog#closeoutReport QLabel[role="amount"] {
                font-size: 29px; font-weight: 700; }
            QDialog#closeoutReport QFrame[role="card"] { background: #104c44;
                border: 1px solid #2a675b; border-radius: 14px; }
            QDialog#closeoutReport QFrame[role="hero"] { background: #f5c451;
                border: none; border-radius: 14px; }
            QDialog#closeoutReport QFrame[role="hero"] QLabel { color: #173f3b; }
            QDialog#closeoutReport QLabel[role="difference"] {
                color: #f5c451; font-weight: 700; }
            QDialog#closeoutReport QScrollArea {
                border: none; background: transparent; }
            QDialog#closeoutReport QWidget#reportBody { background: #073d38; }
            QDialog#closeoutReport QTableWidget { background: #104c44; color: #f1faf6;
                alternate-background-color: #14554b; border: 1px solid #2a675b;
                border-radius: 10px; gridline-color: #2a675b; font-size: 13px; }
            QDialog#closeoutReport QHeaderView::section { background: #1c5d51;
                color: #bcd9cd; border: none; padding: 10px; font-weight: 600; }
            QDialog#closeoutReport QTableWidget::item { padding: 8px; }
            QDialog#closeoutReport QPushButton { background: #f5c451; color: #173f3b;
                border: none; border-radius: 10px; padding: 12px 28px;
                font-size: 15px; font-weight: 700; }
            QDialog#closeoutReport QScrollBar:vertical {
                background: #073d38; width: 8px; margin: 0; }
            QDialog#closeoutReport QScrollBar::handle:vertical {
                background: #387568; border-radius: 4px; min-height: 28px; }
            QDialog#closeoutReport QScrollBar::add-line:vertical,
            QDialog#closeoutReport QScrollBar::sub-line:vertical { height: 0; }
            QDialog#closeoutReport QScrollBar::add-page:vertical,
            QDialog#closeoutReport QScrollBar::sub-page:vertical { background: none; }
            QDialog#closeoutReport QPushButton:hover { background: #ffda78; }
            QDialog#closeoutReport QPushButton:focus { border: 2px solid #ffffff; }
        """)
        handover = cash_sales + repayments - withdrawals_total
        expected = opening_cash + handover
        difference = expected - closing_cash
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 22)
        root.setSpacing(18)
        root.addWidget(self._label("Աշխատանքային սեսիայի ամփոփագիր", "title"))
        root.addWidget(self._label("Վաճառքներ, դրամարկղ և դուրսբերումներ", "muted"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("reportBody")
        content = QVBoxLayout(body)
        content.setContentsMargins(0, 0, 8, 0)
        content.setSpacing(18)
        cards = QHBoxLayout()
        cards.setSpacing(14)
        for caption, amount, role in (
            ("Օրվա հանձնվող գումար", handover, "hero"),
            ("Ընդհանուր վաճառքներ", cash_sales + credit_sales, "card"),
        ):
            card = QFrame()
            card.setProperty("role", role)
            layout = QVBoxLayout(card)
            layout.setContentsMargins(20, 18, 20, 18)
            layout.setSpacing(10)
            layout.addWidget(self._label(caption, "muted"))
            layout.addWidget(self._label(format_currency(amount), "amount"))
            cards.addWidget(card, 1)
        content.addLayout(cards)
        breakdown = QFrame()
        breakdown.setProperty("role", "card")
        grid = QGridLayout(breakdown)
        grid.setContentsMargins(20, 18, 20, 18)
        grid.setVerticalSpacing(8)
        grid.addWidget(self._label("Դրամարկղի ամփոփում", "section"), 0, 0, 1, 2)
        rows = (
            ("Սկզբնական դրամարկղ", opening_cash),
            ("Կանխիկ վաճառքներ", cash_sales),
            ("Պարտքով վաճառքներ", credit_sales),
            ("Պարտքերի վերադարձ", repayments),
            ("Դուրսբերումներ", withdrawals_total),
            ("Ակնկալվող դրամարկղ", expected),
            ("Մնացորդ դրամարկղում", closing_cash),
            ("Տարբերություն", difference),
        )
        for row, (caption, amount) in enumerate(rows, 1):
            role = "difference" if row == len(rows) else "muted"
            grid.addWidget(self._label(caption, role), row, 0)
            value = self._label(
                format_currency(amount), role if role == "difference" else "value"
            )
            value.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            grid.addWidget(value, row, 1)
        grid.setColumnStretch(0, 1)
        content.addWidget(breakdown)
        section = QHBoxLayout()
        section.addWidget(self._label("Դուրսբերումներ", "section"))
        section.addStretch()
        section.addWidget(
            self._label(
                f"{len(withdrawals)} • {format_currency(withdrawals_total)}", "muted"
            )
        )
        content.addLayout(section)
        if withdrawals:
            table = QTableWidget(len(withdrawals), 4)
            table.setHorizontalHeaderLabels(
                ["Ամսաթիվ / ժամ", "Ստացող", "Գումար", "Նպատակ"]
            )
            table.verticalHeader().hide()
            table.verticalHeader().setDefaultSectionSize(44)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            table.setAlternatingRowColors(True)
            table.setShowGrid(False)
            table.setWordWrap(False)
            table.setMinimumHeight(190)
            table.setMaximumHeight(270)
            header = table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
            for row, withdrawal in enumerate(withdrawals):
                raw_date = str(withdrawal.get("taken_at", ""))
                try:
                    date = datetime.fromisoformat(raw_date).strftime("%d.%m.%Y  %H:%M")
                except ValueError:
                    date = raw_date
                values = [
                    date,
                    str(withdrawal.get("recipient_name", "")),
                    format_currency(Decimal(str(withdrawal.get("amount", "0")))),
                    str(withdrawal.get("reason", "")),
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setToolTip(raw_date if column == 0 else value)
                    if column == 2:
                        item.setTextAlignment(
                            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                        )
                    table.setItem(row, column, item)
            content.addWidget(table)
        else:
            content.addWidget(
                self._label("Այս սեսիայի ընթացքում դուրսբերումներ չկան։", "muted")
            )
        content.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll, 1)
        footer = QHBoxLayout()
        footer.addStretch()
        close = QPushButton("Փակել")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        root.addLayout(footer)
        screen = self.screen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(
                min(860, available.width() - 48), min(760, available.height() - 80)
            )

    @staticmethod
    def _label(text: str, role: str) -> QLabel:
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setProperty("role", role)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label
