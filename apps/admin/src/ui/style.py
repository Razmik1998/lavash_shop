"""Admin design tokens and centralized widget defaults."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

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
QWidget {
    background: #f4f6f8;
    color: #182330;
    font-size: 14px;
}

QLabel {
    background: transparent;
}

QLabel#pageTitle {
    font-size: 24px;
    font-weight: 700;
    color: #182330;
}

QLabel#pageSubtitle {
    color: #7a8794;
}

QFrame#panel {
    background: #ffffff;
    border: 1px solid #e1e6eb;
    border-radius: 10px;
}

QFrame#panel QWidget#formField,
QFrame#panel QLabel {
    background: transparent;
}

QScrollArea#cardScroll,
QWidget#cardScrollBody {
    background: transparent;
}

QFrame#panel[urgent="true"] {
    border-left: 4px solid #d64545;
}

QLabel#cardTitle {
    font-size: 17px;
    font-weight: 700;
    color: #182330;
}

QLabel#cardHighlight {
    font-size: 22px;
    font-weight: 700;
    color: #1f6feb;
}

QLabel#metricCaption {
    font-size: 12px;
    color: #7a8794;
}

QLabel#metricValue {
    font-size: 14px;
    font-weight: 600;
    color: #182330;
}

QLabel#cardNote {
    font-size: 12px;
    color: #2f855a;
}

QLabel#sectionHeading {
    font-size: 16px;
    font-weight: 700;
    color: #182330;
}

QLabel#fieldLabel {
    font-size: 13px;
    font-weight: 600;
    color: #344150;
}

QLabel#fieldHint {
    font-size: 12px;
    color: #7a8794;
}

QGroupBox#filterBar {
    background: #ffffff;
    border: 1px solid #e1e6eb;
    border-radius: 12px;
    margin-top: 12px;
    padding-top: 10px;
}

QGroupBox#filterBar::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    background: #ffffff;
    color: #52606d;
    font-weight: 700;
}

QFrame#statCard {
    background: #ffffff;
    border: 1px solid #e1e6eb;
    border-left: 5px solid #94a3b8;
    border-radius: 12px;
}
QFrame#statCard[clickable="true"] { border-bottom: 3px solid #dbeafe; }
QFrame#statCard[clickable="true"]:hover {
    background: #f8fbff;
    border-top-color: #bfdbfe;
    border-right-color: #bfdbfe;
    border-bottom-color: #93c5fd;
}
QFrame#statCard[clickable="true"]:focus {
    border-top-color: #60a5fa;
    border-right-color: #60a5fa;
}

QFrame#statCard[tone="success"] { border-left-color: #0f9b83; }
QFrame#statCard[tone="info"] { border-left-color: #3b82f6; }
QFrame#statCard[tone="primary"] { border-left-color: #1d4ed8; }
QFrame#statCard[tone="warning"] { border-left-color: #e0a030; }
QFrame#statCard[tone="danger"] { border-left-color: #d9534f; }

QFrame#statCard QLabel { background: transparent; border: none; }

QFrame#statCard QLabel#statLabel {
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
}

QFrame#analyticsComparison,
QFrame#analyticsTablePanel,
QFrame#barChart {
    background: #ffffff;
    border: 1px solid #e1e6eb;
    border-radius: 12px;
}

QFrame#analyticsComparison {
    border-left: 4px solid #2563eb;
}

QFrame#barChart {
    min-height: 198px;
}

QFrame#barChart QLabel#sectionHeading,
QFrame#analyticsTablePanel QLabel#sectionHeading,
QFrame#analyticsComparison QLabel#sectionHeading {
    font-size: 14px;
}

QWidget#barChartPlot {
    background: transparent;
}

QLabel#analyticsEmptyState {
    padding: 12px;
    border: 1px dashed #cbd3dc;
    border-radius: 8px;
    color: #52606d;
    background: #f8fafb;
}

QLabel#analyticsInsight {
    padding: 10px 14px;
    border-radius: 8px;
    color: #52606d;
    background: #eaf1ff;
}

QFrame#divider {
    background: #e1e6eb;
    border: none;
}

QPlainTextEdit {
    border: 1px solid #cbd3dc;
    border-radius: 6px;
    padding: 6px 8px;
    background: #ffffff;
}

QPlainTextEdit:focus {
    border: 2px solid #2563eb;
}

QLineEdit,
QComboBox,
QDoubleSpinBox {
    min-height: 36px;
    border: 1px solid #cbd3dc;
    border-radius: 6px;
    padding: 5px 10px;
    background: #ffffff;
}

QLineEdit:focus,
QComboBox:focus,
QDoubleSpinBox:focus {
    border: 2px solid #2563eb;
}

QPushButton,
QPushButton#actionButton {
    color: #000000;
    min-height: 36px;
    border: 1px solid #cbd3dc;
    border-radius: 6px;
    padding: 5px 14px;
    background: #ffffff;
    font-weight: 600;
}

QPushButton:hover,
QPushButton#actionButton:hover {
    background: #eaf1ff;
    border-color: #2563eb;
}

QPushButton#actionButton[variant="primary"] {
    color: #ffffff;
    background: #2563eb;
    border-color: #2563eb;
}

QPushButton#actionButton[variant="primary"]:hover,
QPushButton#actionButton[variant="primary"]:pressed {
    color: #ffffff;
    background: #1749b8;
    border-color: #1749b8;
}

QPushButton#actionButton[variant="secondary"]:hover,
QPushButton#actionButton[variant="secondary"]:pressed {
    color: #000000;
    background: #dbe8ff;
    border-color: #2563eb;
}

QPushButton#actionButton[variant="success"] {
    color: #ffffff;
    background: #0f9f8c;
    border-color: #0f9f8c;
}

QPushButton#actionButton[variant="success"]:hover,
QPushButton#actionButton[variant="success"]:pressed {
    color: #ffffff;
    background: #087765;
    border-color: #087765;
}

QPushButton#actionButton[variant="warning"] {
    color: #3d2a05;
    background: #f2b32c;
    border-color: #f2b32c;
}

QPushButton#actionButton[variant="warning"]:hover,
QPushButton#actionButton[variant="warning"]:pressed {
    color: #3d2a05;
    background: #d99a13;
    border-color: #d99a13;
}

QPushButton#actionButton[variant="ghost"] {
    color: #2563eb;
    background: transparent;
    border-color: transparent;
}

QPushButton#actionButton[variant="ghost"]:hover,
QPushButton#actionButton[variant="ghost"]:pressed {
    background: #eaf1ff;
    border-color: #2563eb;
}

QPushButton#actionButton[variant="danger"] {
    color: #ffffff;
    background: #c24145;
    border-color: #c24145;
}

QPushButton#actionButton[variant="danger"]:hover,
QPushButton#actionButton[variant="danger"]:pressed {
    color: #ffffff;
    background: #982f34;
    border-color: #982f34;
}

QPushButton:disabled,
QPushButton#actionButton:disabled,
QPushButton#actionButton[variant="primary"]:disabled,
QPushButton#actionButton[variant="success"]:disabled,
QPushButton#actionButton[variant="warning"]:disabled,
QPushButton#actionButton[variant="ghost"]:disabled,
QPushButton#actionButton[variant="danger"]:disabled {
    color: #87909a;
    background: #eef0f2;
    border-color: #d8dde3;
}

QFrame#sidebar {
    background: #13283b;
    border: 0;
}

QScrollArea#navScroll, QWidget#navScrollBody {
    background: transparent;
    border: 0;
}

QScrollArea#navScroll QScrollBar:vertical {
    width: 6px;
    margin: 2px 0;
    background: transparent;
}

QScrollArea#navScroll QScrollBar::handle:vertical {
    min-height: 28px;
    border-radius: 3px;
    background: #3a4f66;
}

QScrollArea#navScroll QScrollBar::handle:vertical:hover {
    background: #5b7592;
}

QScrollArea#navScroll QScrollBar:horizontal {
    height: 6px;
    margin: 0 2px;
    background: transparent;
}

QScrollArea#navScroll QScrollBar::handle:horizontal {
    min-width: 28px;
    border-radius: 3px;
    background: #3a4f66;
}

QScrollArea#navScroll QScrollBar::handle:horizontal:hover {
    background: #5b7592;
}

QScrollArea#navScroll QScrollBar::add-line:vertical,
QScrollArea#navScroll QScrollBar::sub-line:vertical,
QScrollArea#navScroll QScrollBar::add-page:vertical,
QScrollArea#navScroll QScrollBar::sub-page:vertical {
    height: 0;
    background: transparent;
}

QScrollArea#navScroll QScrollBar::add-line:horizontal,
QScrollArea#navScroll QScrollBar::sub-line:horizontal,
QScrollArea#navScroll QScrollBar::add-page:horizontal,
QScrollArea#navScroll QScrollBar::sub-page:horizontal {
    width: 0;
    background: transparent;
}

QLabel#brand {
    color: #f7c948;
    font-size: 26px;
    font-weight: 800;
}

QLabel#brandCaption {
    color: #a9c2d8;
    font-size: 12px;
}

QFrame#userPanel {
    background: #20435d;
    border: 1px solid #35647f;
    border-radius: 10px;
}

QLabel#userCaption {
    color: #9fc0d4;
    font-size: 11px;
}

QLabel#userName {
    color: #ffffff;
    font-size: 15px;
    font-weight: 700;
}

QWidget#content {
    background: #eef3f7;
}

QWidget#header {
    background: #ffffff;
    border-bottom: 1px solid #e1e6eb;
}

QPushButton#navGroupButton {
    color: #dce5ef;
    text-align: left;
    font-weight: 600;
    border: 0;
    border-radius: 6px;
    padding: 10px 8px;
    background: transparent;
}

QPushButton#navGroupButton:hover,
QPushButton#navGroupButton:checked {
    color: #ffffff;
    background: #223143;
}

QWidget#navGroupBody {
    background: transparent;
}

QPushButton#navButton {
    color: #dce5ef;
    text-align: left;
    border: 0;
    border-radius: 6px;
    padding: 10px 12px;
    background: transparent;
}

QPushButton#navButton:hover,
QPushButton#navButton[active="true"] {
    color: #ffffff;
    background: #223143;
    border-left: 3px solid #2563eb;
}

QPushButton#navButton[active="true"] {
    background: #2563eb;
}

QPushButton#tabButton {
    color: #526170;
    background: transparent;
    border: 0;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    padding: 6px 4px;
    margin-right: 6px;
}

QPushButton#tabButton:hover {
    color: #2563eb;
}

QPushButton#tabButton[active="true"] {
    color: #182330;
    border-bottom: 2px solid #2563eb;
}

QFrame#notificationBanner {
    background: #eaf1ff;
    border: 1px solid #2563eb;
    border-radius: 8px;
}

QFrame#notificationBanner[tone="warning"] {
    background: #fff4df;
    border-color: #d99a13;
}

QFrame#notificationBanner[tone="danger"] {
    background: #fbe9ea;
    border-color: #c24145;
}

QFrame#summaryBanner {
    background: #eaf2ff;
    border: 1px solid #c8dcff;
    border-left: 4px solid #2563eb;
    border-radius: 12px;
}

QLabel#summaryBannerIcon {
    background: #d5e5ff;
    color: #1746a2;
    border-radius: 18px;
    min-width: 36px;
    max-width: 36px;
    min-height: 36px;
    max-height: 36px;
    font-size: 18px;
    font-weight: 700;
}

QLabel#summaryBannerTitle {
    color: #344c70;
    font-size: 14px;
    font-weight: 600;
}

QLabel#summaryBannerValue {
    color: #1746a2;
    font-size: 21px;
    font-weight: 700;
}

QTableView,
QTableWidget {
    background: #ffffff;
    border: 1px solid #e1e6eb;
    border-radius: 10px;
    gridline-color: transparent;
    alternate-background-color: #f8fafb;
    selection-background-color: #dbe8ff;
    selection-color: #182330;
}

QListWidget {
    background: #ffffff;
    border: 1px solid #e1e6eb;
    border-radius: 10px;
    padding: 6px;
}

QListWidget::item {
    padding: 10px 12px;
    border-radius: 6px;
}

QListWidget::item:hover {
    background: #f0f5ff;
}

QListWidget::item:selected {
    color: #182330;
    background: #dbe8ff;
}

QHeaderView::section {
    background: #f4f6f8;
    border: 0;
    border-bottom: 1px solid #e1e6eb;
    padding: 10px 8px;
    font-weight: 700;
    color: #526170;
}

QLabel#statusBadge {
    padding: 5px 10px;
    border-radius: 10px;
    background: #e8f4f1;
    color: #0f806f;
    font-weight: 600;
}

QLabel#statusBadge[tone="warning"] {
    background: #fff4df;
    color: #9a620b;
}

QLabel#statusBadge[tone="danger"] {
    background: #fbe9ea;
    color: #a93439;
}

QLabel#statusBadge[tone="info"] {
    background: #e8f0ff;
    color: #1d4ed8;
}

QLabel#statusBadge[tone="success"] {
    background: #e8f4f1;
    color: #087765;
}

QFrame#profileHeader {
    background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 #1d4ed8, stop: 1 #0f806f);
    border: 0;
    border-radius: 16px;
}

QFrame#profileHeader QLabel {
    background: transparent;
    color: #ffffff;
}

QLabel#profileAvatar {
    background: rgba(255, 255, 255, 0.18);
    border: 2px solid rgba(255, 255, 255, 0.45);
    border-radius: 32px;
    min-width: 64px;
    max-width: 64px;
    min-height: 64px;
    max-height: 64px;
    font-size: 26px;
    font-weight: 700;
}

QLabel#profileName {
    font-size: 26px;
    font-weight: 700;
}

QLabel#profileDetail {
    color: rgba(255, 255, 255, 0.82);
    font-size: 14px;
}

QFrame#profileHeader QLabel#statusBadge {
    background: rgba(255, 255, 255, 0.2);
    color: #ffffff;
}

QFrame#navCard {
    background: #ffffff;
    border: 1px solid #e1e6eb;
    border-radius: 14px;
}

QFrame#navCard:hover,
QFrame#navCard:focus {
    background: #f5f9ff;
    border-color: #2563eb;
}

QFrame#navCard QLabel {
    background: transparent;
}

QLabel#navCardIcon {
    background: #e8f0ff;
    border-radius: 24px;
    min-width: 48px;
    max-width: 48px;
    min-height: 48px;
    max-height: 48px;
    font-size: 22px;
}

QLabel#navCardIcon[tone="success"] {
    background: #e6f5f1;
}

QLabel#navCardTitle {
    font-size: 17px;
    font-weight: 700;
    color: #182330;
}

QLabel#navCardText {
    color: #52606d;
}

QLabel#navCardArrow {
    font-size: 28px;
    color: #9aa5b1;
}

QLabel#errorLabel {
    color: #c24145;
}

QLabel#statValue {
    color: #182330;
    font-size: 28px;
    font-weight: 700;
}

QLabel#statValue[tone="success"] {
    color: #087765;
}

QLabel#statValue[tone="info"] {
    color: #2563eb;
}

QLabel#statValue[tone="primary"] {
    color: #1d4ed8;
}

QLabel#statValue[tone="warning"] {
    color: #b7791f;
}

QLabel#statValue[tone="danger"] {
    color: #c24145;
}

QLabel#statLabel,
QLabel#statDetail {
    color: #52606d;
}

QScrollBar:vertical {
    width: 10px;
    margin: 4px 0;
    background: transparent;
}

QScrollBar::handle:vertical {
    min-height: 28px;
    border-radius: 5px;
    background: #cbd3dc;
}

QWidget#loginPage {
    background: #0c3a33;
    color: #ffffff;
}

QWidget#loginPage QFrame#brandPanel,
QWidget#loginPage QFrame#loginCard,
QWidget#loginPage QFrame#loginShell {
    border-radius: 12px;
}

QWidget#loginPage QFrame#brandPanel {
    background: #0c3a33;
    border: 1px solid #186055;
}

QWidget#loginPage QFrame#loginCard {
    background: #114e45;
    border: 1px solid #186055;
}

QWidget#loginPage QFrame#loginShell {
    background: transparent;
    border: none;
}

QWidget#loginPage QLabel#brandMark {
    color: #ffcc00;
    font-size: 46px;
    font-weight: 700;
}

QWidget#loginPage QLabel#brandKicker,
QWidget#loginPage QLabel#loginEyebrow {
    color: #ffcc00;
    font-size: 11px;
    font-weight: 700;
}

QWidget#loginPage QLabel#brandTitle {
    color: #ffffff;
    font-size: 30px;
    font-weight: 700;
}

QWidget#loginPage QLabel#brandSubtitle,
QWidget#loginPage QLabel#loginSubtitle {
    color: #a0c4be;
}

QWidget#loginPage QLabel#brandFooter,
QWidget#loginPage QLabel#securityNote {
    color: #7fa99b;
    font-size: 11px;
    font-weight: 600;
}

QWidget#loginPage QLabel#loginTitle {
    color: #ffffff;
    font-size: 28px;
    font-weight: 700;
}

QWidget#loginPage QLineEdit {
    min-height: 40px;
    padding: 5px 12px;
    border-color: #1b6b5e;
    border-radius: 8px;
    background: #186055;
    color: #ffffff;
}

QWidget#loginPage QLineEdit:focus {
    border: 2px solid #ffcc00;
}

QWidget#loginPage QPushButton[variant="primary"] {
    min-height: 46px;
    color: #0c3a33;
    background: #ffcc00;
    border-color: #ffcc00;
    font-size: 15px;
}

QWidget#loginPage QPushButton[variant="primary"]:hover {
    color: #0c3a33;
    background: #e6b800;
    border-color: #e6b800;
}

QWidget#loginPage QLabel#errorLabel {
    color: #ff8b85;
}
"""


def apply_admin_style(app: QApplication) -> None:
    app.setStyleSheet(_APP_STYLESHEET)


def configure_page_layout(layout: QLayout) -> None:
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)


def configure_action_button(button: QPushButton) -> None:
    button.setMinimumHeight(36)
    button.setObjectName("actionButton")
    button.setProperty("variant", "secondary")


def _format_display_number(value: Decimal) -> str:
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if rounded.is_zero():
        rounded = abs(rounded)
    text = format(rounded, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{Decimal(text or '0'):,}".replace(",", "'")


def format_currency(value: Decimal) -> str:
    """Format currency rounded to at most two decimal places."""
    return f"{_format_display_number(value)} ֏"


def format_quantity(value: Decimal | int | None) -> str:
    """Format a number rounded to at most two decimal places."""
    if value is None:
        return ""
    return _format_display_number(Decimal(value))


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
ATTENTION_ROW_BACKGROUND = "#f8d3d5"


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
    table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(True)
    table.setWordWrap(False)
    table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setMinimumSectionSize(MIN_COLUMN_WIDTH)
    header.setStretchLastSection(False)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    _ColumnFitter(table)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.verticalHeader().setVisible(False)
    table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    table.customContextMenuRequested.connect(
        lambda position: _show_table_copy_menu(table, position)
    )
    copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, table)
    copy_shortcut.activated.connect(lambda: copy_table_selection(table))
