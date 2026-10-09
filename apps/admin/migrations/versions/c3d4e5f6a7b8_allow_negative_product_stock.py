"""allow negative product stock

Revision ID: c3d4e5f6a7b8
Revises: 8e4f6a2b1c90
Create Date: 2026-09-13 05:30:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "8e4f6a2b1c90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_products_quantity_nonnegative", "products", type_="check"
    )


def downgrade() -> None:
    op.create_check_constraint(
        "ck_products_quantity_nonnegative", "products", "quantity_in_stock >= 0"
    )