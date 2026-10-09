"""Suppress a known macOS text-input diagnostic on native stderr."""

from __future__ import annotations

import os
import sys
import threading

_installed = False
_NOISE = (
    b"TSMSendMessageToUIServer: CFMessagePortSendRequest FAILED(-1) "
    b"to send to port com.apple.tsm.uiserver"
)


def _forward_stderr(read_fd: int, output_fd: int) -> None:
    def forward(data: bytes) -> None:
        while data:
            count = os.write(output_fd, data)
            data = data[count:]

    pending = b""
    try:
        while chunk := os.read(read_fd, 4096):
            pending += chunk
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                if _NOISE not in line:
                    forward(line + b"\n")
            # Bound buffering for native output with no newline.
            if len(pending) > 65536:
                forward(pending)
                pending = b""
        if pending and _NOISE not in pending:
            forward(pending)
    finally:
        os.close(read_fd)
        os.close(output_fd)


def suppress_macos_input_diagnostic() -> None:
    """Filter native fd 2 once; retain the original stderr destination."""
    global _installed
    if sys.platform != "darwin" or _installed:
        return
    sys.stderr.flush()
    output_fd = os.dup(2)
    read_fd, write_fd = os.pipe()
    os.dup2(write_fd, 2)
    os.close(write_fd)
    _installed = True
    threading.Thread(
        target=_forward_stderr,
        args=(read_fd, output_fd),
        name="native-stderr-filter",
        daemon=True,
    ).start()
