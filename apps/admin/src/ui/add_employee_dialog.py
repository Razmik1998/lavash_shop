"""'Ավելացնել աշխատակից' (Add employee) dialog."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
)


class AddEmployeeDialog(QDialog):
    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.setWindowTitle("Ավելացնել աշխատակից")

        self.username_edit = QLineEdit()
        self.full_name_edit = QLineEdit()
        self.temp_password_edit = QLineEdit()
        self.temp_password_edit.setEchoMode(QLineEdit.EchoMode.Password)

        form = QFormLayout()
        form.addRow("Օգտանուն:", self.username_edit)
        form.addRow("Անուն ազգանուն:", self.full_name_edit)
        form.addRow("Ժամանակավոր գաղտնաբառ:", self.temp_password_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def values(self) -> tuple[str, str, str]:
        return (
            self.username_edit.text().strip(),
            self.full_name_edit.text().strip(),
            self.temp_password_edit.text(),
        )
