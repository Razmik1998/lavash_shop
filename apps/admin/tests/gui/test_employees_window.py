from __future__ import annotations

import uuid

from models import Role, User
from ui.employees_window import EmployeesWindow


class _FakeEmployeeService:
    def __init__(self, employees: list[User]) -> None:
        self._employees = employees

    def list_employees(self) -> list[User]:
        return self._employees


def test_employees_window_renders_employee_rows(qtbot) -> None:  # type: ignore[no-untyped-def]
    employee = User(
        id=uuid.uuid4(),
        username="emp1",
        full_name="Employee One",
        hashed_password="x",
        role=Role.EMPLOYEE,
        is_active=True,
    )
    admin_user = User(
        id=uuid.uuid4(),
        username="admin",
        full_name="Admin",
        hashed_password="x",
        role=Role.ADMIN,
        is_active=True,
    )
    window = EmployeesWindow(_FakeEmployeeService([employee]), admin_user)
    qtbot.addWidget(window)

    qtbot.waitUntil(lambda: window._model.rowCount() == 1, timeout=2000)
    assert window._model.item(0, 0).text() == "emp1"
