"""Independent POS design tokens and centralized widget defaults."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QLayout,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTableView,
    QTableWidget,
)

_APP_STYLESHEET = """
QWidget#loginPage {
    background: #173f3b;
}
QWidget#loginPage QFrame {
    background: transparent;
    border: 0;
}
QWidget#sessionPage, QWidget#homePage, QWidget#checkoutPage {
    background: #eef3f8;
}
QWidget#loginPage QLabel#brandMark {
    color: #f5c451;
    font-size: 46px;
    font-weight: 700;
}
QWidget#loginPage QLabel#brandKicker,
QWidget#loginPage QLabel#loginEyebrow {
    color: #f5c451;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}
QWidget#loginPage QLabel#brandTitle {
    color: #ffffff;
    font-size: 30px;
    font-weight: 700;
}
QWidget#loginPage QLabel#brandSubtitle {
    color: #bdd4ca;
    font-size: 14px;
}
QWidget#loginPage QLabel#brandFooter {
    color: #7fa99b;
    font-size: 11px;
    font-weight: 700;
}
QWidget#loginPage QFrame#loginCard QLabel { color: #ffffff; }
QWidget#loginPage QLabel#loginTitle {
    color: #f5c451;
    font-size: 28px;
    font-weight: 700;
}
QWidget#loginPage QLabel#loginSubtitle {
    color: #bdd4ca;
    font-size: 13px;
    padding-bottom: 10px;
}
QWidget#loginPage QLabel#securityNote {
    color: #83918a;
    font-size: 12px;
}
QLabel#pageTitle { color: #182330; font-size: 24px; font-weight: 700; }
QLabel#pageSubtitle { color: #7a8794; }
QLineEdit, QDoubleSpinBox, QComboBox {
    min-height: 36px; padding: 5px 10px; border: 1px solid #cbd3dc;
    border-radius: 6px; background: #ffffff;
}

QListWidget {
    background: #ffffff;
    border: 1px solid #e1e6eb;
    border-radius: 10px;
    padding: 6px;
}
QListWidget::item { padding: 12px; border-radius: 6px; }
QListWidget::item:hover { background: #f0f5ff; }
QListWidget::item:selected { color: #182330; background: #dbe8ff; }
QWidget#loginPage QLineEdit,
QWidget#loginPage QDoubleSpinBox,
QWidget#loginPage QComboBox {
    min-height: 40px; padding: 5px 12px; border-color: #7fa99b;
    border-radius: 7px; background: #173f3b; color: #ffffff;
}
QLineEdit:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 2px solid #2563eb;
}
QWidget#loginPage QLineEdit:focus,
QWidget#loginPage QDoubleSpinBox:focus,
QWidget#loginPage QComboBox:focus {
    border-color: #f5c451;
}
QPushButton, QPushButton#actionButton {
    color: #000000;
    min-height: 38px; padding: 5px 14px; border: 1px solid #cbd3dc;
    border-radius: 6px; background: #ffffff; font-weight: 600;
}
QPushButton:hover, QPushButton#actionButton:hover {
    background: #eaf1ff; border-color: #2563eb;
}
QPushButton[variant="primary"] {
    color: #ffffff; background: #2563eb; border-color: #2563eb;
    min-height: 44px; font-size: 15px;
}
QPushButton[variant="primary"]:hover {
    color: #ffffff; background: #1749b8; border-color: #1749b8;
}
QPushButton[variant="primary"]:pressed {
    color: #ffffff; background: #123b96; border-color: #123b96;
}
QWidget#loginPage QPushButton#actionButton[variant="primary"] {
    color: #173f3b; background: #f5c451; border-color: #f5c451;
    min-height: 46px; font-size: 15px;
}
QWidget#loginPage QPushButton#actionButton[variant="primary"]:hover {
    color: #173f3b; background: #f8d77a; border-color: #f8d77a;
}
QWidget#loginPage QPushButton#actionButton[variant="primary"]:pressed {
    color: #173f3b; background: #dfaa2f; border-color: #dfaa2f;
}
QPushButton[variant="secondary"]:hover,
QPushButton[variant="secondary"]:pressed {
    color: #000000; background: #dbe8ff; border-color: #2563eb;
}
QPushButton[variant="success"] {
    color: #ffffff; background: #0f9f8c; border-color: #0f9f8c;
}
QPushButton[variant="success"]:hover,
QPushButton[variant="success"]:pressed {
    color: #ffffff; background: #087765; border-color: #087765;
}
QPushButton[variant="danger"] {
    color: #ffffff; background: #c24145; border-color: #c24145;
}
QPushButton[variant="danger"]:hover,
QPushButton[variant="danger"]:pressed {
    color: #ffffff; background: #982f34; border-color: #982f34;
}
QPushButton[variant="warning"] {
    color: #3d2a05; background: #f2b32c; border-color: #f2b32c;
}
QPushButton[variant="warning"]:hover,
QPushButton[variant="warning"]:pressed {
    color: #3d2a05; background: #d99a13; border-color: #d99a13;
}
QPushButton[variant="ghost"] {
    color: #2563eb; background: transparent; border-color: transparent;
}
QPushButton[variant="ghost"]:hover,
QPushButton[variant="ghost"]:pressed {
    background: #eaf1ff; border-color: #2563eb;
}
QPushButton:disabled { color: #87909a; background: #eef0f2; border-color: #d8dde3; }
QFrame#panel { background: #ffffff; border: 1px solid #e1e6eb; border-radius: 10px; }
QFrame#softPanel {
    background: #f8fafc; border: 1px solid #e1e6eb; border-radius: 12px;
}
QLabel#sectionTitle { color: #182330; font-size: 17px; font-weight: 700; }
QLabel#iconLabel { color: #2563eb; font-size: 15px; font-weight: 700; }
QLabel#sessionMeta { color: #52606d; font-size: 13px; }
QLabel#statusLabel {
    padding: 7px 12px; border-radius: 8px; background: #eef4ff;
    color: #2454a6; font-weight: 600;
}
QLabel#statusLabel[tone="success"] { background: #e5f7f3; color: #0f806f; }
QLabel#statusLabel[tone="danger"] { background: #fbe9ea; color: #a93439; }
QLabel#statusLabel[tone="warning"] { background: #fff4df; color: #9a620b; }
QLabel#cartTotal {
    color: #182330;
    font-size: 22px;
    font-weight: 700;
}
QLabel#screenTitle {
    color: #182330;
    font-size: 26px;
    font-weight: 700;
}
QLabel#screenSubtitle { color: #7a8794; }
QTableView, QTableWidget {
    background: #ffffff; border: 1px solid #e1e6eb; border-radius: 10px;
    gridline-color: #edf0f3; alternate-background-color: #fbfcfd;
    selection-background-color: #dbe8ff; selection-color: #182330;
}
QHeaderView::section {
    background: #f4f6f8; border: 0; border-bottom: 1px solid #e1e6eb;
    padding: 10px 8px; font-weight: 700; color: #526170;
}
QLabel#statusBadge {
    padding: 5px 10px; border-radius: 10px; background: #e8f4f1;
    color: #0f806f; font-weight: 600;
}
QLabel#statusBadge[tone="danger"] { background: #fbe9ea; color: #a93439; }
QLabel#statusBadge[tone="warning"] { background: #fff4df; color: #9a620b; }
QLabel#errorLabel { color: #c24145; }
"""

POS_THEME_QSS = """
QMainWindow, QDialog, QWidget#loginPage, QWidget#sessionPage,
QWidget#homePage, QWidget#checkoutPage, QWidget#root_view {
    background-color: #0c3a33;
    color: #ffffff;
    font-family: 'Segoe UI', system-ui, Arial, sans-serif;
    font-size: 13px;
}
QFrame#brandPanel, QFrame#loginCard, QFrame#loginShell,
QFrame#panel, QFrame#softPanel, QFrame#card_container,
QFrame#header_bar, QFrame#top_header, QFrame#top_status_bar,
QFrame#idle_central_card, QFrame#info_row {
    background-color: #114e45;
    border: 1px solid #186055;
    border-radius: 12px;
}
QFrame#loginShell { border: none; }
QFrame#brandPanel, QFrame#header_bar, QFrame#top_header {
    background-color: #0c3a33;
    border-color: #186055;
}
QFrame#top_status_bar {
    background-color: #0c3a33;
    border: none;
    border-bottom: 1px solid #186055;
    border-radius: 0;
}
QFrame#status_pill {
    background-color: #186055;
    border: 1px solid #1b6b5e;
    border-radius: 6px;
}
QFrame#idle_central_card {
    background-color: #114e45;
    border: 1px solid #186055;
    border-radius: 12px;
}
QFrame#info_row {
    background-color: #186055;
    border: none;
    border-radius: 8px;
}
QLabel#status_text_white {
    color: #ffffff;
    font-size: 13px;
    font-weight: 600;
}
QWidget#sessionPage QLabel#status_text_white {
    color: #ffffff;
}
QLabel#status_text_muted {
    color: #a0c4be;
    font-size: 12px;
}
QLabel#idle_title {
    color: #ffffff;
    font-size: 20px;
    font-weight: bold;
}
QPushButton#start_work_button {
    background-color: #ffcc00;
    color: #0c3a33;
    font-weight: bold;
    font-size: 15px;
    border: none;
    border-radius: 8px;
    min-height: 46px;
}
QPushButton#start_work_button:hover { background-color: #e6b800; }
QPushButton#start_work_button:pressed { background-color: #cca300; }
QLabel#brandMark, QLabel#brandKicker, QLabel#loginEyebrow,
QLabel#loginTitle, QLabel#screenTitle {
    color: #ffcc00;
}
QLabel#brandTitle, QLabel#loginTitle, QLabel#screenTitle,
QLabel#welcome_label {
    font-weight: bold;
}
QLabel#screenTitle, QLabel#welcome_label { color: #ffffff; }
QLabel#brandSubtitle, QLabel#brandFooter, QLabel#loginSubtitle,
QLabel#securityNote, QLabel#pageSubtitle, QLabel#sessionMeta,
QLabel#checkout_header_subtitle, QLabel#statusLabel {
    color: #a0c4be;
}
QLabel#sectionTitle, QLabel#iconLabel { color: #ffffff; }
QLabel#cartTotal { color: #ffcc00; }
QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #186055;
    border: 1px solid #1b6b5e;
    border-radius: 8px;
    padding: 8px 12px;
    color: #ffffff;
    selection-background-color: #ffcc00;
    selection-color: #0c3a33;
}
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QComboBox:focus {
    border: 2px solid #ffcc00;
}
QPushButton, QPushButton#actionButton {
    background-color: #186055;
    color: #ffffff;
    border: 1px solid #1b6b5e;
    border-radius: 8px;
    padding: 8px 14px;
    min-height: 38px;
    font-weight: 600;
}
QPushButton:hover, QPushButton#actionButton:hover {
    background-color: #1b6b5e;
}
QPushButton[variant="primary"], QPushButton#primary_button {
    background-color: #ffcc00;
    color: #0c3a33;
    border: none;
    font-weight: bold;
}
QPushButton[variant="primary"]:hover, QPushButton#primary_button:hover {
    background-color: #e6b800;
}
QPushButton[variant="success"] {
    background-color: #ffcc00;
    color: #0c3a33;
    border-color: #ffcc00;
}
QPushButton[variant="success"]:hover {
    background-color: #e6b800;
    border-color: #e6b800;
}
QPushButton#actionButton[variant="success"] {
    background-color: #35d399;
    color: #063b2c;
    border: 1px solid #83f0c3;
    border-radius: 12px;
    padding: 12px 18px;
    font-size: 14px;
    font-weight: bold;
}
QPushButton#actionButton[variant="success"]:hover {
    background-color: #55e5ae;
    border-color: #b0f8d9;
}
QPushButton#actionButton[variant="success"]:pressed {
    background-color: #1fb981;
    border-color: #1fb981;
}
QPushButton#actionButton[variant="warning"] {
    background-color: #ffcc00;
    color: #0c3a33;
    border: 1px solid #ffe16b;
    border-radius: 12px;
    padding: 12px 18px;
    font-size: 14px;
    font-weight: bold;
}
QPushButton#actionButton[variant="warning"]:hover {
    background-color: #ffda3e;
    border-color: #fff0a6;
}
QPushButton#actionButton[variant="warning"]:pressed {
    background-color: #e6b800;
    border-color: #d8ad00;
}
QPushButton#actionButton[variant="warning"]:focus {
    border: 2px solid #fff4bc;
}
QPushButton#actionButton[variant="danger"] {
    background-color: #df4655;
    color: #ffffff;
    border: 1px solid #ff8590;
    border-radius: 12px;
    padding: 12px 18px;
    font-size: 14px;
    font-weight: bold;
}
QPushButton#actionButton[variant="danger"]:hover {
    background-color: #f45c6a;
    border-color: #ffb2b9;
}
QPushButton#actionButton[variant="danger"]:pressed {
    background-color: #c93646;
    border-color: #c93646;
}
QPushButton#actionButton:disabled {
    background-color: #24564f;
    color: #86a8a1;
    border-color: #24564f;
}
QPushButton#actionButton[variant="warning"]:disabled {
    background-color: #24564f;
    color: #86a8a1;
    border-color: #24564f;
}
QPushButton:disabled {
    background-color: #24564f;
    color: #86a8a1;
    border-color: #24564f;
}
QTableWidget, QTableView {
    background-color: #114e45;
    alternate-background-color: #14564c;
    gridline-color: #186055;
    border: 1px solid #186055;
    border-radius: 8px;
    color: #ffffff;
    selection-background-color: #186055;
    selection-color: #ffcc00;
}
QHeaderView::section {
    background-color: #114e45;
    color: #ffffff;
    font-weight: bold;
    padding: 8px;
    border: none;
    border-bottom: 1px solid #1b6b5e;
}
QTableCornerButton::section {
    background-color: #186055;
    border: none;
}
QTabWidget::pane {
    border: none;
    background-color: transparent;
}
QTabBar::tab {
    background-color: #186055;
    color: #a0c4be;
    padding: 8px 18px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 4px;
    font-weight: 500;
}
QTabBar::tab:selected {
    background-color: #114e45;
    color: #ffffff;
    border-bottom: 2px solid #ffcc00;
    font-weight: bold;
}
QListWidget, QDialogButtonBox {
    background-color: #114e45;
    color: #ffffff;
}
QLabel#statusBadge, QLabel#statusLabel {
    background-color: #186055;
    border-radius: 8px;
    padding: 7px 12px;
}
QLabel#errorLabel { color: #ff8b85; }
QFrame#top_header {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #114e45, stop:1 #0f433c);
    border: 1px solid #1f7a6b;
    border-radius: 12px;
}
QFrame#top_header QPushButton,
QFrame#top_header QPushButton#actionButton {
    min-height: 22px; padding: 2px 8px; border-radius: 8px;
    font-size: 12px;
}
QFrame#top_header QPushButton#actionButton[variant="danger"],
QFrame#top_header QPushButton#actionButton[variant="warning"] {
    min-height: 22px; padding: 2px 8px; border-radius: 8px;
    font-size: 12px;
}
QFrame#top_header QPushButton[variant="secondary"] {
    background-color: transparent; border: 1px solid #2c8a79;
    color: #d6efe9;
}
QFrame#top_header QPushButton[variant="secondary"]:hover {
    background-color: #1f7a6b; color: #ffffff;
}
QFrame#top_header QPushButton[variant="danger"] {
    background-color: #7a2f35; border: 1px solid #a64a52;
}
QFrame#top_header QPushButton[variant="danger"]:hover {
    background-color: #96383f;
}
QFrame#top_header QPushButton[current="true"],
QFrame#top_header QPushButton[current="true"]:disabled {
    background-color: #ffcc00; color: #0c3a33; border: 1px solid #ffcc00;
    font-weight: bold;
}
QFrame#debtorCard {
    background-color: #114e45; border: 1px solid #2c8a79; border-radius: 14px;
    min-width: 420px;
}
QFrame#debtorCard[credit="true"] {
    background-color: #3a3410; border: 2px solid #ffcc00;
}
QLabel#debtorCaption {
    color: #a0c4be; font-size: 11px; font-weight: bold; letter-spacing: 1px;
    background: transparent;
}
QFrame#debtorCard[credit="true"] QLabel#debtorCaption { color: #ffcc00; }
QLabel#debtorName {
    color: #ffffff; font-size: 22px; font-weight: bold; background: transparent;
}
QFrame#debtorCard QPushButton {
    background-color: #ffcc00; color: #0c3a33; border: none; border-radius: 12px;
    padding: 8px 18px; font-weight: bold;
}
QFrame#debtorCard QPushButton[variant="success"] {
    background-color: #2fbf71; color: #062b21;
}
QFrame#debtorCard QPushButton[variant="success"]:hover { background-color: #45d98a; }
QFrame#debtorCard QPushButton:hover { background-color: #ffd93d; }
QFrame#debtorCard QPushButton:disabled { background-color: #6b6420; color: #2a2a2a; }
QFrame#top_header QLabel#status_text_white { font-size: 11px; }
QFrame#top_header QLabel#welcome_label {
    color: #ffcc00; font-size: 12px; font-weight: bold;
}
QFrame#top_header QLabel#checkout_header_title {
    font-size: 17px; letter-spacing: 0.5px;
}
"""

POS_THEME_QSS += """
QDialog#cashWithdrawalDialog QLabel { color: #d6efe9; }
QDialog#cashWithdrawalDialog QLabel#screenTitle { color: #ffcc00; font-size: 24px; }
QDialog#cashWithdrawalDialog QLabel#screenSubtitle { color: #a0c4be; }
QDialog#cashWithdrawalDialog QLabel#errorLabel { color: #ff8b85; }
QPlainTextEdit { background: #186055; color: #ffffff; border: 1px solid #28695c;
    border-radius: 8px; padding: 10px; selection-background-color: #267969; }
QPlainTextEdit:focus { border: 2px solid #ffcc00; }
QComboBox QAbstractItemView { background: #114e45; color: #ffffff;
    selection-background-color: #267969; selection-color: #ffffff; }
QLabel#screenSubtitle { color: #a0c4be; }
QScrollBar:vertical { background: #10473f; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #337f70; border-radius: 5px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""

_APP_STYLESHEET += POS_THEME_QSS


def apply_pos_style(app: QApplication) -> None:
    app.setStyleSheet(_APP_STYLESHEET)


def configure_page_layout(layout: QLayout) -> None:
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)


def configure_action_button(button: QPushButton, variant: str = "secondary") -> None:
    button.setObjectName("actionButton")
    button.setProperty("variant", variant)
    button.setMinimumHeight(38)
    button.style().unpolish(button)
    button.style().polish(button)


def format_quantity(value: Decimal | str | int | None) -> str:
    """Format a number without insignificant trailing decimal zeroes."""
    if value is None or value == "":
        return ""
    try:
        number = Decimal(value)
    except InvalidOperation:
        return str(value)
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{Decimal(text or '0'):,}".replace(",", "'")


def format_currency(value: Decimal | str | int | None) -> str:
    """Format an amount in dram without insignificant trailing zeroes."""
    text = format_quantity(value)
    return f"{text} ֏" if text else ""


def copy_table_selection(table: QTableView | QTableWidget) -> None:
    """Copy selected table cells to the clipboard as tab-separated text."""
    model = table.model()
    selection_model = table.selectionModel()
    if model is None or selection_model is None:
        return
    selected_indexes = selection_model.selectedIndexes()
    if not selected_indexes:
        return
    rows = sorted({index.row() for index in selected_indexes})
    columns = sorted({index.column() for index in selected_indexes})
    text = "\n".join(
        "\t".join(
            str(model.data(model.index(row, column), Qt.ItemDataRole.DisplayRole) or "")
            for column in columns
        )
        for row in rows
    )
    QApplication.clipboard().setText(text)


def _show_table_copy_menu(table: QTableView | QTableWidget, position: QPoint) -> None:
    menu = QMenu(table)
    copy_action = menu.addAction("Պատճենել")
    copy_action.setEnabled(bool(table.selectionModel().selectedIndexes()))
    copy_action.triggered.connect(lambda: copy_table_selection(table))
    menu.exec(table.viewport().mapToGlobal(position))


MIN_COLUMN_WIDTH = 80


class _ColumnFitter(QObject):
    """Stretches columns to fill the table width; scrolls when content is wider."""

    def __init__(self, table: QTableView) -> None:
        super().__init__(table)
        self._table = table
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.fit)
        table.viewport().installEventFilter(self)
        model = table.model()
        if model is not None:
            for signal in (
                model.modelReset,
                model.layoutChanged,
                model.rowsInserted,
                model.rowsRemoved,
                model.columnsInserted,
                model.columnsRemoved,
                model.dataChanged,
                model.headerDataChanged,
            ):
                signal.connect(lambda *_args: self._timer.start())

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Resize:
            self._timer.start()
        return False

    def fit(self) -> None:
        header = self._table.horizontalHeader()
        columns = [c for c in range(header.count()) if not header.isSectionHidden(c)]
        # A table whose sizing was customised explicitly keeps its own modes.
        if not columns or any(
            header.sectionResizeMode(c) != QHeaderView.ResizeMode.Interactive
            for c in columns
        ):
            return
        widths = [
            max(
                MIN_COLUMN_WIDTH,
                self._table.sizeHintForColumn(c),
                header.sectionSizeHint(c),
            )
            for c in columns
        ]
        extra = self._table.viewport().width() - sum(widths)
        if extra > 0:
            share, remainder = divmod(extra, len(columns))
            widths = [width + share for width in widths]
            widths[-1] += remainder
        for column, width in zip(columns, widths, strict=True):
            header.resizeSection(column, width)


def configure_table_view(table: QTableView | QTableWidget) -> None:
    table.setAlternatingRowColors(True)
    table.setWordWrap(False)
    table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    if isinstance(table, QTableView):
        table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setMinimumSectionSize(MIN_COLUMN_WIDTH)
    header.setStretchLastSection(False)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    _ColumnFitter(table)
    table.verticalHeader().setVisible(False)
    table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    table.customContextMenuRequested.connect(
        lambda position: _show_table_copy_menu(table, position)
    )
    copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, table)
    copy_shortcut.activated.connect(lambda: copy_table_selection(table))