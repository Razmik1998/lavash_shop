"""Store the reason a sale was cancelled.

Revision ID: k2c3d4e5f6
Revises: j1b2c3d4e5f6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "k2c3d4e5f6"
down_revision: str | None = "j1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sales",
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sales", "cancellation_reason")
