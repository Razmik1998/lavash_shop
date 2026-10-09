import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import (
    Base,
    CashRecipient,
    CashWithdrawal,
    PosSession,
    PosSessionStatus,
    Role,
    User,
)
from repositories.cash_withdrawal import CashWithdrawalRepository
from repositories.pos_session import PosSessionRepository


@pytest.fixture
def ledger():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            PosSession.__table__,
            CashRecipient.__table__,
            CashWithdrawal.__table__,
        ],
    )
    factory = sessionmaker(engine, expire_on_commit=False)
    user_id, session_id = uuid.uuid4(), uuid.uuid4()
    with factory() as db:
        db.add(
            User(
                id=user_id,
                username="cashier",
                full_name="Cashier",
                hashed_password="test",
                role=Role.EMPLOYEE,
                is_active=True,
            )
        )
        db.add(
            PosSession(
                id=session_id,
                terminal_id="POS1",
                user_id=user_id,
                status=PosSessionStatus.ACTIVE,
                opening_cash=Decimal("0"),
            )
        )
        db.commit()
    repo = CashWithdrawalRepository(factory)
    repo.save_recipient("Owner")
    recipient_id = uuid.UUID(repo.recipients()[0]["id"])
    return repo, factory, user_id, session_id, recipient_id


def test_withdrawal_duplicate_and_closeout(ledger):
    repo, factory, user_id, session_id, recipient_id = ledger
    identifier = uuid.uuid4()
    args = (
        identifier,
        session_id,
        user_id,
        recipient_id,
        Decimal("50000"),
        "Owner draw",
    )
    first = repo.record(*args)
    assert repo.record(*args) == first
    assert repo.total(session_id) == Decimal("50000")
    repo.save_recipient("Renamed owner", str(recipient_id), False)
    assert repo.history(session_id)[0]["recipient_name"] == "Owner"
    assert repo.recipients(active_only=True) == []
    closed = PosSessionRepository(factory).close(
        session_id, Decimal("0"), Decimal("100000")
    )
    assert closed.cash_difference == Decimal("50000")
    assert PosSessionRepository(factory).close(
        session_id, Decimal("0"), Decimal("100000")
    ).cash_difference == Decimal("50000")
    with pytest.raises(ValueError, match="closed"):
        repo.record(
            uuid.uuid4(), session_id, user_id, recipient_id, Decimal("1"), "draw"
        )


@pytest.mark.parametrize(
    "amount,reason",
    [("NaN", "draw"), ("0", "draw"), ("-1", "draw"), ("1.001", "draw"), ("10", " ")],
)
def test_invalid_withdrawal(ledger, amount, reason):
    repo, _, user_id, session_id, recipient_id = ledger
    with pytest.raises(ValueError):
        repo.record(
            uuid.uuid4(), session_id, user_id, recipient_id, Decimal(amount), reason
        )
    assert repo.history() == []


def test_wrong_cashier_and_inactive_recipient(ledger):
    repo, _, user_id, session_id, recipient_id = ledger
    with pytest.raises(ValueError, match="cashier"):
        repo.record(
            uuid.uuid4(), session_id, uuid.uuid4(), recipient_id, Decimal("10"), "draw"
        )
    repo.save_recipient("Owner", str(recipient_id), False)
    with pytest.raises(ValueError, match="authorized"):
        repo.record(
            uuid.uuid4(), session_id, user_id, recipient_id, Decimal("10"), "draw"
        )


def test_authenticated_cash_handler(ledger):
    import json
    from types import SimpleNamespace

    from networking.server import _RequestHandler

    repo, factory, user_id, session_id, recipient_id = ledger
    sent = []
    handler = object.__new__(_RequestHandler)
    handler.server = SimpleNamespace(
        session_service=SimpleNamespace(
            cash_repository=repo, _pos_session_repository=PosSessionRepository(factory)
        )
    )
    handler._authenticated_user = lambda token: SimpleNamespace(id=user_id)
    handler._send = lambda body: sent.append(json.loads(body))
    request = dict(
        op="record_cash_withdrawal",
        auth_token="valid",
        session_id=str(session_id),
        recipient_id=str(recipient_id),
        withdrawal_id=str(uuid.uuid4()),
        amount="50000",
        reason="Owner draw",
    )
    handler._handle_cash(request)
    assert sent[-1]["ok"] is True
    handler._handle_cash(request)
    assert len(repo.history()) == 1
    handler._handle_cash(
        dict(op="list_cash_withdrawals", auth_token="valid", session_id=str(session_id))
    )
    assert sent[-1]["withdrawals"][0]["amount"] == "50000.00"
    handler._handle_cash({**request, "session_id": str(uuid.uuid4())})
    assert sent[-1]["ok"] is False


def test_history_fetches_session_and_cashier_names(ledger):
    repo, _, user_id, session_id, recipient_id = ledger
    repo.record(uuid.uuid4(), session_id, user_id, recipient_id, Decimal("10"), "draw")
    row = repo.history()[0]
    assert row["cashier_name"] == "Cashier"
    assert row["session_name"].startswith("POS1 · ")
    assert row["cashier_id"] == str(user_id)
    assert row["session_id"] == str(session_id)
