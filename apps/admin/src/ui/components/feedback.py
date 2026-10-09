"""One place for user-facing message boxes, so wording and buttons match."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QVBoxLayout, QWidget

from ui.components.buttons import AppButton
from ui.components.inputs import TextArea
from ui.components.layouts import DialogButtonBar


def confirm(parent: QWidget, title: str, message: str) -> bool:
    return (
        QMessageBox.question(parent, title, message) == QMessageBox.StandardButton.Yes
    )


def warn(parent: QWidget, message: str, title: str = "Սխալ") -> None:
    QMessageBox.warning(parent, title, message)


def inform(parent: QWidget, message: str, title: str = "Տեղեկություն") -> None:
    QMessageBox.information(parent, title, message)


def report_error(parent: QWidget, message: str, title: str = "Սխալ") -> None:
    QMessageBox.critical(parent, title, message)


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
        layout.addWidget(
            DialogButtonBar(
                [
                    AppButton(cancel_text, variant="danger", on_click=self.reject),
                    AppButton(
                        confirm_text,
                        variant=confirm_variant,
                        on_click=self._accept_if_valid,
                    ),
                ]
            )
        )

    def _accept_if_valid(self) -> None:
        if self._text.value():
            self.accept()

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
    """Ask the user for a short, required block of free-form text (e.g. a
    reject reason). Returns ``None`` if the dialog was cancelled or the
    field was left empty."""
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
