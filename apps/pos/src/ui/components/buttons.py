"""Every button used by the POS UI.

No screen may instantiate ``QPushButton`` directly. If a needed button does
not exist here, add a subclass with its semantic variant and reuse it.

Variants map to the ``QPushButton[variant="..."]`` rules in ``ui.style``:
primary (blue, main action), secondary (neutral), success (green: accept,
save, finish), warning (yellow: edit / mutate live data), danger (red:
delete, cancel, close), ghost (low emphasis).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
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
        icon: str | QIcon | None = None,
        enabled: bool = True,
        tooltip: str | None = None,
        compact: bool = False,
        min_height: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        caption = text if text is not None else self.label
        super().__init__(
            f"{icon}  {caption}" if isinstance(icon, str) else caption, parent
        )
        if isinstance(icon, QIcon):
            self.setIcon(icon)
            self.setIconSize(QSize(20, 20))
        chosen = variant or self.variant
        if chosen not in BUTTON_VARIANTS:
            raise ValueError(f"Unknown button variant: {chosen}")
        self.setObjectName("actionButton")
        self.setProperty("variant", chosen)
        height = min_height if min_height is not None else (32 if compact else 38)
        self.setMinimumHeight(height)
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


class SaveButton(AppButton):
    variant = "success"
    label = "Պահպանել"


class PaymentButton(AppButton):
    variant = "success"
    label = "Վճարել"


class AcceptButton(AppButton):
    variant = "success"
    label = "Հաստատել"


class ConfirmButton(AppButton):
    variant = "success"
    label = "Ավարտել"


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


class SearchButton(AppButton):
    variant = "secondary"
    label = "Որոնել"


class RefreshButton(AppButton):
    variant = "secondary"
    label = "Թարմացնել"


class DetailsButton(AppButton):
    variant = "secondary"
    label = "Մանրամասներ"
