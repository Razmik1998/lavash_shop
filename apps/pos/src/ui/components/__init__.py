"""The POS UI component library.

Screens build themselves out of these components only. If a screen needs a
widget that is not here, add it to the matching module (``buttons``,
``inputs``, ``tables``, ``panels``, ``layouts``, ``feedback``) with its
style baked in, then import it — never re-style a raw Qt widget in a screen.
"""

from __future__ import annotations

from ui.components.buttons import (
    BUTTON_VARIANTS,
    AcceptButton,
    AddButton,
    AppButton,
    CancelButton,
    CloseButton,
    QuitButton,
    ConfirmButton,
    DeleteButton,
    DetailsButton,
    EditButton,
    GhostButton,
    PaymentButton,
    PrimaryButton,
    RefreshButton,
    SaveButton,
    SearchButton,
    SecondaryButton,
)
from ui.components.customer_dialog import CreditCustomerDialog, CustomerSelection
from ui.components.discount_dialog import DiscountDialog
from ui.components.feedback import (
    choose_unsaved_action,
    confirm,
    inform,
    prompt_text,
    report_error,
    warn,
)
from ui.components.inputs import (
    AmountField,
    ChildProductSelectionDialog,
    MoneyField,
    QuantityDialog,
    SearchField,
    SelectField,
    TextArea,
    TextField,
)
from ui.components.layouts import ActionBar, DialogButtonBar
from ui.components.panels import (
    ChangeDueLabel,
    ErrorLabel,
    IconLabel,
    PageHeader,
    PageSubtitle,
    PageTitle,
    Panel,
    StatusBadge,
)
from ui.components.sale_editor import SaleEditDialog, UnlockKeyDialog
from ui.components.tables import DataTable, SimpleTable

__all__ = [
    "BUTTON_VARIANTS",
    "AcceptButton",
    "ActionBar",
    "AddButton",
    "AmountField",
    "ChildProductSelectionDialog",
    "CreditCustomerDialog",
    "AppButton",
    "CancelButton",
    "ChangeDueLabel",
    "CloseButton",
    "QuitButton",
    "ConfirmButton",
    "DataTable",
    "CustomerSelection",
    "DeleteButton",
    "DiscountDialog",
    "DetailsButton",
    "DialogButtonBar",
    "EditButton",
    "ErrorLabel",
    "GhostButton",
    "IconLabel",
    "MoneyField",
    "PageHeader",
    "PageSubtitle",
    "PageTitle",
    "Panel",
    "PaymentButton",
    "PrimaryButton",
    "QuantityDialog",
    "RefreshButton",
    "SaveButton",
    "SaleEditDialog",
    "UnlockKeyDialog",
    "SearchButton",
    "SearchField",
    "SecondaryButton",
    "SelectField",
    "SimpleTable",
    "StatusBadge",
    "TextArea",
    "TextField",
    "confirm",
    "choose_unsaved_action",
    "inform",
    "prompt_text",
    "report_error",
    "warn",
]
