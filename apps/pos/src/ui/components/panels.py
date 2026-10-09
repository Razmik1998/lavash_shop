"""Surfaces, headings and status widgets shared by the POS UI."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class Panel(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")


class IconLabel(QLabel):
    """A compact visual marker paired with a normal text label."""

    def __init__(
        self,
        icon: str,
        text: str,
        object_name: str = "iconLabel",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(f"{icon}  {text}", parent)
        self.setObjectName(object_name)
        self._icon = icon

    def set_text(self, text: str) -> None:
        self.setText(f"{self._icon}  {text}")


class PageTitle(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("pageTitle")


class PageSubtitle(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("pageSubtitle")
        self.setWordWrap(True)


class PageHeader(QWidget):
    def __init__(
        self, title: str, subtitle: str = "", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(2)
        layout.addWidget(PageTitle(title))
        if subtitle:
            layout.addWidget(PageSubtitle(subtitle))


class ErrorLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("errorLabel")
        self.setWordWrap(True)


class ChangeDueLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("changeDue")
        self.setAlignment(Qt.AlignmentFlag.AlignRight)


class StatusBadge(QLabel):
    """Preserves the caller's status text while adding a visible marker."""

    def __init__(
        self, text: str, tone: str = "info", parent: QWidget | None = None
    ) -> None:
        super().__init__(f"●  {text}", parent)
        self.setObjectName("statusBadge")
        self.setProperty("tone", tone)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_status(self, text: str, tone: str = "info") -> None:
        self.setText(f"●  {text}")
        self.setProperty("tone", tone)
        style = self.style()
        style.unpolish(self)
        style.polish(self)


class DebtorCard(QFrame):
    """Payment-type card: shows cash/credit state and hosts the change action."""

    def __init__(
        self,
        action: QWidget,
        secondary_action: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("debtorCard")
        self._caption = QLabel("ՎՃԱՐՄԱՆ ՏԵՍԱԿ")
        self._caption.setObjectName("debtorCaption")
        self._name = QLabel()
        self._name.setObjectName("debtorName")
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self._caption)
        text.addWidget(self._name)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 10, 8)
        layout.setSpacing(16)
        layout.addLayout(text, 1)
        layout.addWidget(action)
        if secondary_action is not None:
            layout.addWidget(secondary_action)

    def set_state(self, credit: bool, name: str | None) -> None:
        if credit:
            self._caption.setText("ՎԱՃԱՌՎԱԾ Է ՊԱՐՏՔՈՎ · ՊԱՐՏԱՊԱՆ")
            self._name.setText(f"👤  {name or '…'}")
        else:
            self._caption.setText("ՎՃԱՐՄԱՆ ՏԵՍԱԿ")
            self._name.setText("💵  Կանխիկ")
        self.setProperty("credit", credit)
        self.style().unpolish(self)
        self.style().polish(self)
