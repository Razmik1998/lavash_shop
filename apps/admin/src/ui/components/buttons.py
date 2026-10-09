"""Every button used by the Admin UI.

No screen may instantiate ``QPushButton`` directly. If a needed button does
not exist here, add a subclass with its semantic variant and reuse it.

Variants map to the ``QPushButton[variant="..."]`` rules in ``ui.style``:

===========  ======  ==========================================
variant      colour  meaning
===========  ======  ==========================================
primary      blue    the main action of a screen
secondary    white   neutral / supporting action
success      green   accept, save, confirm, finish
warning      yellow  edit, reopen, anything mutating live data
danger       red     delete, cancel, archive, close
ghost        flat    low-emphasis inline action
===========  ======  ==========================================
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QPushButton, QWidget

BUTTON_VARIANTS = ("primary", "secondary", "success", "warning", "danger", "ghost")


class AppButton(QPushButton):
    """Base class for every button; applies the shared style contract."""

    variant = "secondary"
    label = ""

    def __init__(
        self,
        text: str | None = None,
        *,
        on_click: Callable[[], object] | None = None,
        variant: str | None = None,
        icon: str | None = None,
        enabled: bool = True,
        tooltip: str | None = None,
        compact: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        caption = text if text is not None else self.label
        super().__init__(f"{icon}  {caption}" if icon else caption, parent)
        chosen = variant or self.variant
        if chosen not in BUTTON_VARIANTS:
            raise ValueError(f"Unknown button variant: {chosen}")
        self.setObjectName("actionButton")
        self.setProperty("variant", chosen)
        self.setMinimumHeight(30 if compact else 36)
        if tooltip:
            self.setToolTip(tooltip)
        if not enabled:
            self.setEnabled(False)
        if on_click is not None:
            self.clicked.connect(lambda: on_click())
        self._repolish()

    def set_variant(self, variant: str) -> None:
        if variant not in BUTTON_VARIANTS:
            raise ValueError(f"Unknown button variant: {variant}")
        self.setProperty("variant", variant)
        self._repolish()

    def _repolish(self) -> None:
        style = self.style()
        style.unpolish(self)
        style.polish(self)


class PrimaryButton(AppButton):
    variant = "primary"


class SecondaryButton(AppButton):
    variant = "secondary"


class GhostButton(AppButton):
    variant = "ghost"


class BackButton(GhostButton):
    label = "← Վերադառնալ"


class SaveButton(AppButton):
    variant = "success"
    label = "Պահպանել"


class AcceptButton(AppButton):
    variant = "success"
    label = "Հաստատել"


class ConfirmButton(AppButton):
    variant = "success"
    label = "Ավարտել"


class PaymentButton(AppButton):
    variant = "success"
    label = "Գրանցել վճարում"


class AddButton(AppButton):
    variant = "primary"
    label = "Ավելացնել"

    def __init__(self, text: str | None = None, **kwargs: object) -> None:
        super().__init__(text, icon="+", **kwargs)  # type: ignore[arg-type]


class EditButton(AppButton):
    variant = "warning"
    label = "Խմբագրել"


class DeleteButton(AppButton):
    variant = "danger"
    label = "Ջնջել"


class ArchiveButton(AppButton):
    variant = "danger"
    label = "Արխիվացնել"


class RestoreButton(AppButton):
    variant = "secondary"
    label = "Վերականգնել"


class CancelButton(AppButton):
    variant = "danger"
    label = "Չեղարկել"


class CloseButton(AppButton):
    variant = "danger"
    label = "Փակել"


class QuitButton(AppButton):
    """Exits the application (open-door icon, yellow = leaves live work)."""

    variant = "warning"
    label = "Դուրս գալ"

    def __init__(self, text: str | None = None, **kwargs: object) -> None:
        kwargs.setdefault("tooltip", "Փակել հավելվածը")
        super().__init__(text, icon="\U0001f6aa", **kwargs)  # type: ignore[arg-type]


def _action_icon(path: str) -> QIcon:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        'viewBox="0 0 24 24" fill="none" stroke="#526170" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        f"{path}</svg>"
    )
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    return QIcon(pixmap)


class SearchButton(AppButton):
    variant = "secondary"
    label = "Որոնել"

    def __init__(self, text: str | None = None, **kwargs: object) -> None:
        super().__init__(text, **kwargs)  # type: ignore[arg-type]
        self.setIcon(
            _action_icon('<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>')
        )
        self.setIconSize(QSize(18, 18))


class RefreshButton(AppButton):
    variant = "secondary"
    label = "Թարմացնել"

    def __init__(self, text: str | None = None, **kwargs: object) -> None:
        super().__init__(text, **kwargs)  # type: ignore[arg-type]
        self.setIcon(
            _action_icon(
                '<path d="M20 7v5h-5M4 17v-5h5"/>'
                '<path d="M6 7a7 7 0 0 1 12-1l2 3'
                'M18 17a7 7 0 0 1-12 1l-2-3"/>'
            )
        )
        self.setIconSize(QSize(18, 18))


class DetailsButton(AppButton):
    variant = "secondary"
    label = "Մանրամասներ"


class SyncButton(AppButton):
    variant = "secondary"
    label = "Համաժամեցնել կայքի հետ"


class TabButton(QPushButton):
    """A single tab in a ``TabBar`` (see ``layouts.py``); styled by
    ``QPushButton#tabButton``. Not a sidebar ``NavButton`` — tabs switch
    an in-page ``QStackedWidget``, not the app's top-level pages."""

    def __init__(
        self,
        text: str,
        *,
        on_click: Callable[[], object] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("tabButton")
        self.setCheckable(True)
        self.setMinimumHeight(34)
        if on_click is not None:
            self.clicked.connect(lambda: on_click())

    def set_active(self, active: bool) -> None:
        self.setChecked(active)
        self.setProperty("active", "true" if active else "false")
        style = self.style()
        style.unpolish(self)
        style.polish(self)


class NavButton(QPushButton):
    """Sidebar navigation entry; styled by ``QPushButton#navButton``."""

    def __init__(
        self,
        text: str,
        *,
        on_click: Callable[[], object] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("navButton")
        self.setCheckable(True)
        self.setMinimumHeight(38)
        if on_click is not None:
            self.clicked.connect(lambda: on_click())

    def set_active(self, active: bool) -> None:
        self.setProperty("active", "true" if active else "false")
        style = self.style()
        style.unpolish(self)
        style.polish(self)
