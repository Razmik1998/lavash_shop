"""add supplier opening debt

Revision ID: l2c3d4e5f6a7
Revises: k2c3d4e5f6
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "l2c3d4e5f6a7"
down_revision: str | None = "k2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "suppliers",
        sa.Column(
            "opening_debt",
            sa.Numeric(12, 2),
            server_default="0",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_suppliers_opening_debt_nonnegative",
        "suppliers",
        "opening_debt >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_suppliers_opening_debt_nonnegative", "suppliers", type_="check"
    )
    op.drop_column("suppliers", "opening_debt")
