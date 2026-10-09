from __future__ import annotations

from PySide6.QtWidgets import QDialog

from ui.components.feedback import _TextPromptDialog


def test_cancellation_reason_prompt_requires_nonblank_text(qtbot) -> None:  # type: ignore[no-untyped-def]
    dialog = _TextPromptDialog(
        None,
        "Cancel sale",
        "Enter a reason",
        placeholder="Reason",
        confirm_text="Cancel sale",
        confirm_variant="danger",
        cancel_text="Back",
    )
    qtbot.addWidget(dialog)

    assert not dialog._confirm_button.isEnabled()
    dialog._text.setPlainText("   ")
    assert not dialog._confirm_button.isEnabled()
    dialog._text.setPlainText("Duplicate order")
    assert dialog._confirm_button.isEnabled()

    dialog._confirm_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.value() == "Duplicate order"
