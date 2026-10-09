from __future__ import annotations

import uuid

from PySide6.QtCore import Qt

from exceptions import AuthenticationError
from models import Role, User
from ui.login_window import LoginWindow


class _FailingAuthService:
    def login(self, username: str, password: str) -> User:
        raise AuthenticationError("Invalid username or password.")


class _SucceedingAuthService:
    def __init__(self, user: User) -> None:
        self._user = user

    def login(self, username: str, password: str) -> User:
        return self._user


def test_login_window_renders_armenian_labels(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = LoginWindow(_FailingAuthService(), on_success=lambda _user: None)
    qtbot.addWidget(window)

    assert window.windowTitle() == "Աշխատակցի մուտք"


def test_invalid_login_shows_error_message(qtbot) -> None:  # type: ignore[no-untyped-def]
    window = LoginWindow(_FailingAuthService(), on_success=lambda _user: None)
    qtbot.addWidget(window)

    window._username_edit.setText("nobody")
    window._password_edit.setText("wrong")
    qtbot.mouseClick(window._login_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: window._error_label.text() != "", timeout=2000)
    assert window._error_label.text() == "Սխալ օգտանուն կամ գաղտնաբառ։"


def test_successful_login_invokes_callback(qtbot) -> None:  # type: ignore[no-untyped-def]
    logged_in_user = User(
        id=uuid.uuid4(),
        username="emp1",
        full_name="Employee One",
        role=Role.EMPLOYEE,
        is_active=True,
    )
    result: list[User] = []
    window = LoginWindow(
        _SucceedingAuthService(logged_in_user), on_success=result.append
    )
    qtbot.addWidget(window)

    window._username_edit.setText("emp1")
    window._password_edit.setText("secret")
    window._handle_login()

    qtbot.waitUntil(lambda: len(result) == 1, timeout=2000)
    assert result[0].username == "emp1"
