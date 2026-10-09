from __future__ import annotations

from unittest.mock import patch

import pytest

import main as pos_main


class _UnavailableConnection:
    def is_available(self) -> bool:
        return False


def test_main_blocks_with_armenian_error_when_admin_unavailable(
    qtbot,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Settings.load() requires POS_TERMINAL_ID; set it explicitly rather
    # than relying on a developer's local .env so this test is isolated
    # from ambient environment state.
    monkeypatch.setenv("POS_TERMINAL_ID", "pos-1")
    with (
        patch("main.LocalConnection", return_value=_UnavailableConnection()),
        patch("main.QMessageBox.critical") as mock_critical,
    ):
        exit_code = pos_main.main()

    assert exit_code == 1
    mock_critical.assert_called_once()
    assert "հասանելի չէ" in mock_critical.call_args.args[2]
