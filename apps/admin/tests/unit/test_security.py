from __future__ import annotations

from security import hash_password, verify_password


def test_hash_password_does_not_return_plaintext() -> None:
    hashed = hash_password("correct horse battery staple")

    assert hashed != "correct horse battery staple"


def test_verify_password_accepts_correct_password() -> None:
    hashed = hash_password("s3cret")

    assert verify_password("s3cret", hashed) is True


def test_verify_password_rejects_wrong_password() -> None:
    hashed = hash_password("s3cret")

    assert verify_password("wrong", hashed) is False
