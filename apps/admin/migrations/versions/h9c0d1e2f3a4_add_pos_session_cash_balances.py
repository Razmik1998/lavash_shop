"""store POS session cash balances

Revision ID: h9c0d1e2f3a4
Revises: g8b9c0d1e2f3
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "h9c0d1e2f3a4"
down_revision: str | None = "g8b9c0d1e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pos_sessions",
        sa.Column("opening_cash", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("pos_sessions", sa.Column("closing_cash", sa.Numeric(12, 2), nullable=True))
    op.add_column("pos_sessions", sa.Column("cash_difference", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("pos_sessions", "cash_difference")
    op.drop_column("pos_sessions", "closing_cash")
    op.drop_column("pos_sessions", "opening_cash")