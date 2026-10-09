"""Scoped presentation and vector icons for the product catalogue."""

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

PRODUCTS_STYLE = """
QWidget#productsPage { background: #f4f7fb; }
QFrame#productSection { background: white; border: 1px solid #dce5ef;
    border-radius: 14px; }
QFrame#productSection QLabel { background: transparent; border: none; }
QTabWidget#productTabs { background: transparent; }
QTabWidget#productTabs::pane { border: none; background: transparent; }
QTabWidget#productTabs QTabBar { background: #f4f7fb; border: none; }
QTabWidget#productTabs QTabBar::tab { padding: 12px 18px; margin: 0 8px 12px 0;
    background: white; color: #526477; border: 1px solid #dce5ef;
    border-radius: 9px; font-weight: 600; }
QTabWidget#productTabs QTabBar::tab:selected { background: #eaf2ff;
    color: #1d4ed8; border: 1px solid #a9c8fb; }
QTabWidget#productTabs QTabBar::tab:hover:!selected { background: #eef3f9; }
QTableView#productTable { background: white; alternate-background-color: #f8fafc;
    border: 1px solid #e2e8f0; border-radius: 8px; gridline-color: #edf2f7;
    selection-background-color: #e6efff; selection-color: #163c78; }
QTableView#productTable QHeaderView { background: #f1f5f9; }
QTableView#productTable QHeaderView::section { background: #f1f5f9;
    color: #526477; border: none; border-bottom: 1px solid #e2e8f0;
    padding: 12px 10px; font-weight: 600; }
QTableView#productTable::item { padding: 7px 10px; border: none; }
QLabel#catalogueSubtitle, QLabel#catalogueHint { color: #738399;
    font-size: 13px; background: transparent; }
"""

_ICON_PATHS = {
    "sale": '<path d="M3 3h2l2 12h11l3-9H6M9 20h.01M17 20h.01"/>',
    "barbecue": (
        '<path d="M12 3c1 5 6 6 6 11a6 6 0 0 1-12 0'
        'c0-3 2-5 3-7 0 3 1 4 2 4 2-2 2-5 1-8Z"/>'
    ),
    "own": '<path d="m3 7 9-4 9 4v10l-9 4-9-4ZM3 7l9 4 9-4M12 11v10"/>',
    "search": '<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
    "refresh": (
        '<path d="M20 7v5h-5M4 17v-5h5M5 8a8 8 0 0 1 13-3'
        'l2 3M4 16l2 3a8 8 0 0 0 13-3"/>'
    ),
    "edit": '<path d="m15 4 5 5M4 20l4-1L20 7a2 2 0 0 0-3-3L5 16Z"/>',
}


def catalogue_icon(name: str, color: str = "#526477") -> QIcon:
    """Render a crisp, font-independent outline icon."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        f"{_ICON_PATHS[name]}</svg>"
    )
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    return QIcon(pixmap)
