"""Small, consistent vector icons for POS actions."""

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS = {
    "cart": (
        '<path d="M3 3h2l2 12h11l3-9H6"/><circle cx="9" cy="20" r="1"/><ci'
        'rcle cx="18" cy="20" r="1"/>'
    ),
    "history": '<path d="M3 11a9 9 0 1 1 2 7M3 4v7h7m2-4v5l3 2"/>',
    "customers": (
        '<circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3m2'
        '-16a3 3 0 0 1 0 6m2 4a5 5 0 0 1 2 4v2"/>'
    ),
    "cash": (
        '<rect x="2" y="5" width="20" height="14" rx="2"/><circle cx="12" '
        'cy="12" r="3"/><path d="M5 12h1m12 0h1"/>'
    ),
    "close": '<path d="m6 6 12 12M6 18 18 6"/>',
    "check": '<path d="m4 12 5 5L20 6"/>',
    "discount": '<path d="m3 3 9 0 9 9-9 9-9-9Z"/><circle cx="8" cy="8" r="1"/>',
    "print": '<path d="M6 9V3h12v6M6 17H3V9h18v8h-3M6 14h12v7H6Z"/>',
    "note": '<path d="M5 3h14v18H5Zm4 5h6m-6 4h6m-6 4h4"/>',
}


def pos_icon(name: str, color: str = "#d6efe9") -> QIcon:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        f"{_PATHS[name]}</svg>"
    )
    icon = QIcon()
    for size in (20, 40):
        pixmap = QPixmap(QSize(size, size))
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        QSvgRenderer(QByteArray(svg.encode())).render(painter)
        painter.end()
        icon.addPixmap(pixmap)
    return icon
