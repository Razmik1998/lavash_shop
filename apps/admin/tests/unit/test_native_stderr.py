import os
import threading

from native_stderr import _NOISE, _forward_stderr


def test_filters_only_input_diagnostic_and_preserves_other_output(tmp_path):
    destination = tmp_path / "stderr.log"
    output_fd = os.open(destination, os.O_WRONLY | os.O_CREAT, 0o600)
    read_fd, write_fd = os.pipe()
    thread = threading.Thread(target=_forward_stderr, args=(read_fd, output_fd))
    thread.start()
    os.write(write_fd, b"server started\n2026 Python[123] " + _NOISE[:40])
    os.write(write_fd, _NOISE[40:] + b"\nreal error\npartial final error")
    os.close(write_fd)
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert destination.read_bytes() == (
        b"server started\nreal error\npartial final error"
    )
