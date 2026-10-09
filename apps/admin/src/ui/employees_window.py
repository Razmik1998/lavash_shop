"""Main admin window: employees table + add-employee flow."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from exceptions import UsernameAlreadyExistsError
from models import User
from services import EmployeeService
from ui.add_employee_dialog import AddEmployeeDialog
from ui.components import AddButton, DataTable, report_error, warn
from ui.style import configure_page_layout
from ui.workers import run_in_background, wait_for_pending_threads

_HEADERS = ["Օգտանուն", "Անուն ազգանուն", "Ակտիվ է"]


class EmployeesWindow(QWidget):
    def __init__(self, employee_service: EmployeeService, admin_user: User) -> None:
        super().__init__()
        self._employee_service = employee_service
        self.setWindowTitle(f"Աշխատակիցներ — {admin_user.full_name}")

        self._table = DataTable(_HEADERS)
        self._model = self._table.item_model
        self._add_button = AddButton("Աշխատակից", on_click=self._handle_add_employee)

        layout = QVBoxLayout()
        configure_page_layout(layout)
        layout.addWidget(self._table, stretch=1)
        layout.addWidget(self._add_button, alignment=Qt.AlignmentFlag.AlignRight)
        self.setLayout(layout)

        self.reload_employees()

    def reload_employees(self) -> None:
        run_in_background(
            self,
            self._employee_service.list_employees,
            self._on_employees_loaded,
            self._on_operation_failed,
        )

    def _on_employees_loaded(self, employees: list[User]) -> None:
        self._table.set_rows(
            [
                employee.username,
                employee.full_name,
                "Այո" if employee.is_active else "Ոչ",
            ]
            for employee in employees
        )

    def _handle_add_employee(self) -> None:
        dialog = AddEmployeeDialog(self)
        if dialog.exec() != AddEmployeeDialog.DialogCode.Accepted:
            return
        username, full_name, temp_password = dialog.values()
        if not username or not full_name or not temp_password:
            warn(self, "Բոլոր դաշտերը պարտադիր են։")
            return

        self._add_button.setEnabled(False)
        run_in_background(
            self,
            lambda: self._employee_service.create_employee(
                username, full_name, temp_password
            ),
            self._on_employee_created,
            self._on_operation_failed,
        )

    def _on_employee_created(self, _employee: User) -> None:
        self._add_button.setEnabled(True)
        self.reload_employees()

    def _on_operation_failed(self, error: Exception) -> None:
        self._add_button.setEnabled(True)
        if isinstance(error, UsernameAlreadyExistsError):
            warn(self, "Այս օգտանունն արդեն օգտագործվում է։")
        else:
            report_error(self, "Չհաջողվեց միանալ շտեմարանին։")

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        wait_for_pending_threads(self)
        super().closeEvent(event)
