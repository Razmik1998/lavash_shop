"""Login screen (Armenian UI), employee-role-only."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from exceptions import AuthenticationError
from models import User
from services import AuthService
from ui.components import ErrorLabel, PrimaryButton, TextField
from ui.style import configure_page_layout
from ui.workers import run_in_background, wait_for_pending_threads


class LoginWindow(QWidget):
    def __init__(
        self,
        auth_service: AuthService,
        on_success: Callable[[User], None],
    ) -> None:
        super().__init__()
        self._auth_service = auth_service
        self._on_success = on_success

        self.setWindowTitle("Աշխատակցի մուտք")
        self.setObjectName("loginPage")

        self._username_edit = TextField("Օգտանուն")
        self._password_edit = TextField(
            "Գաղտնաբառ", password=True, on_submit=self._handle_login
        )
        self._error_label = ErrorLabel()
        self._login_button = PrimaryButton("Մուտք", on_click=self._handle_login)

        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 0)
        form.setVerticalSpacing(14)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.addRow("Օգտանուն", self._username_edit)
        form.addRow("Գաղտնաբառ", self._password_edit)

        brand_panel = QFrame()
        brand_panel.setObjectName("brandPanel")
        brand_layout = QVBoxLayout(brand_panel)
        brand_layout.setContentsMargins(36, 36, 36, 36)
        brand_layout.setSpacing(10)
        brand_mark = QLabel("M")
        brand_mark.setObjectName("brandMark")
        brand_kicker = QLabel("POS TERMINAL  /  01")
        brand_kicker.setObjectName("brandKicker")
        brand_title = QLabel("Վաճառքը\nսկսվում է այստեղ")
        brand_title.setObjectName("brandTitle")
        brand_subtitle = QLabel(
            "Մուտք գործեք աշխատակցի հաշվով՝ հերթափոխը շարունակելու համար։"
        )
        brand_subtitle.setObjectName("brandSubtitle")
        brand_layout.addWidget(brand_mark)
        brand_layout.addSpacing(28)
        brand_layout.addWidget(brand_kicker)
        brand_layout.addWidget(brand_title)
        brand_layout.addWidget(brand_subtitle)
        brand_layout.addStretch()
        brand_footer = QLabel("ԱՐԱԳ  •  ՊԱՐԶ  •  ՀՈՒՍԱԼԻ")
        brand_footer.setObjectName("brandFooter")
        brand_layout.addWidget(brand_footer)

        login_card = QFrame()
        login_card.setObjectName("loginCard")
        card_layout = QVBoxLayout(login_card)
        card_layout.setContentsMargins(42, 42, 42, 42)
        card_layout.setSpacing(8)
        eyebrow = QLabel("ԱՇԽԱՏԱԿՑԻ ՀԱՇԻՎ")
        eyebrow.setObjectName("loginEyebrow")
        title = QLabel("Մուտք գործել")
        title.setObjectName("loginTitle")
        subtitle = QLabel("Մուտքագրեք ձեր տվյալները՝ համակարգ մուտք գործելու համար։")
        subtitle.setObjectName("loginSubtitle")
        card_layout.addWidget(eyebrow)
        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)
        card_layout.addLayout(form)
        card_layout.addSpacing(8)
        card_layout.addWidget(self._error_label)
        card_layout.addSpacing(4)
        card_layout.addWidget(self._login_button)
        card_layout.addStretch()
        security_note = QLabel("Ձեր տվյալները պաշտպանված են")
        security_note.setObjectName("securityNote")
        card_layout.addWidget(security_note)

        shell = QFrame()
        shell.setObjectName("loginShell")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(brand_panel, 5)
        shell_layout.addWidget(login_card, 6)

        layout = QVBoxLayout()
        configure_page_layout(layout)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.addWidget(shell)
        self.setLayout(layout)

    def _handle_login(self) -> None:
        username = self._username_edit.text().strip()
        password = self._password_edit.text()
        self._error_label.setText("")
        self._login_button.setEnabled(False)

        run_in_background(
            self,
            lambda: self._auth_service.login(username, password),
            self._on_login_succeeded,
            self._on_login_failed,
        )

    def _on_login_succeeded(self, user: User) -> None:
        self._login_button.setEnabled(True)
        self._password_edit.clear()
        self._on_success(user)

    def _on_login_failed(self, error: Exception) -> None:
        self._login_button.setEnabled(True)
        if isinstance(error, AuthenticationError):
            self._error_label.setText("Սխալ օգտանուն կամ գաղտնաբառ։")
        else:
            QMessageBox.critical(self, "Սխալ", "Ադմինիստրատոր հասանելի չէ։")

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        wait_for_pending_threads(self)
        super().closeEvent(event)
