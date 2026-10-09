"""One place for user-facing message boxes, so wording and buttons match."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QVBoxLayout, QWidget

from ui.components.buttons import AppButton
from ui.components.inputs import TextArea
from ui.components.layouts import DialogButtonBar


def _show_message(
    parent: QWidget,
    title: str,
    message: str,
    icon: QMessageBox.Icon,
) -> None:
    dialog = QMessageBox(icon, title, message, parent=parent)
    dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
    dialog.setDefaultButton(QMessageBox.StandardButton.Ok)
    dialog.setEscapeButton(QMessageBox.StandardButton.Ok)
    dialog.exec()


def confirm(parent: QWidget, title: str, message: str) -> bool:
    return (
        QMessageBox.question(parent, title, message)
        == QMessageBox.StandardButton.Yes
    )


def choose_unsaved_action(parent: QWidget) -> str:
    dialog = QMessageBox(
        QMessageBox.Icon.Warning,
        "Չպահպանված փոփոխություններ",
        "Պետք է պահպանել կամ հեռացնել փոփոխությունները։",
        parent=parent,
    )
    save = dialog.addButton("Պահպանել", QMessageBox.ButtonRole.AcceptRole)
    discard = dialog.addButton("Հեռացնել փոփոխությունները", QMessageBox.ButtonRole.DestructiveRole)
    dialog.addButton("Չեղարկել", QMessageBox.ButtonRole.RejectRole)
    dialog.exec()
    if dialog.clickedButton() is save:
        return "save"
    if dialog.clickedButton() is discard:
        return "discard"
    return "cancel"


def warn(parent: QWidget, message: str, title: str = "Սխալ") -> None:
    _show_message(parent, title, message, QMessageBox.Icon.Warning)


def inform(parent: QWidget, message: str, title: str = "Տեղեկություն") -> None:
    _show_message(parent, title, message, QMessageBox.Icon.Information)


def report_error(parent: QWidget, message: str, title: str = "Սխալ") -> None:
    _show_message(parent, title, message, QMessageBox.Icon.Critical)


class _TextPromptDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        title: str,
        message: str,
        *,
        placeholder: str,
        confirm_text: str,
        confirm_variant: str,
        cancel_text: str,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(360)
        self._text = TextArea(placeholder)
        layout = QVBoxLayout(self)
        label = QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(self._text)
        self._confirm_button = AppButton(
            confirm_text,
            variant=confirm_variant,
            on_click=self.accept,
            enabled=False,
        )
        self._text.textChanged.connect(self._update_confirm_state)
        layout.addWidget(
            DialogButtonBar(
                [
                    AppButton(cancel_text, variant="danger", on_click=self.reject),
                    self._confirm_button,
                ]
            )
        )

    def _update_confirm_state(self) -> None:
        self._confirm_button.setEnabled(bool(self._text.value()))

    def value(self) -> str:
        return self._text.value()


def prompt_text(
    parent: QWidget,
    title: str,
    message: str,
    *,
    placeholder: str = "",
    confirm_text: str = "Հաստատել",
    confirm_variant: str = "primary",
    cancel_text: str = "Չեղարկել",
) -> str | None:
    """Prompt for required free-form text and return None on dismissal."""
    dialog = _TextPromptDialog(
        parent,
        title,
        message,
        placeholder=placeholder,
        confirm_text=confirm_text,
        confirm_variant=confirm_variant,
        cancel_text=cancel_text,
    )
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.value()
    return None
