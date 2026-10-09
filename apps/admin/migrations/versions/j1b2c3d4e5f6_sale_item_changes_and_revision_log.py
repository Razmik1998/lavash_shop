"""Document history: revision log without items, per-item change table.

Revision ID: j1b2c3d4e5f6
Revises: i0a1b2c3d4e5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "j1b2c3d4e5f6"
down_revision: str = "i0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sale_revisions",
        sa.Column("closed_total", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column("sale_revisions", sa.Column("outcome", sa.String(32), nullable=True))
    op.add_column(
        "sale_revisions",
        sa.Column(
            "is_changed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "sale_revisions",
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Legacy rows: an unlock row is still "open" history; a reconfirm row is a
    # completed edit. Their old item snapshots are intentionally discarded.
    op.execute(
        """
        UPDATE sale_revisions
        SET outcome = CASE WHEN unlocked_by_user_id IS NULL
                           THEN 'completed' ELSE 'unlocked' END,
            closed_at = created_at,
            closed_total = total,
            is_changed = unlocked_by_user_id IS NULL
        """
    )
    # Legacy sales stuck in EDITING had every item deactivated; restore the
    # latest generation so the in-place edit flow has rows to work with.
    op.execute(
        """
        UPDATE sale_items si SET is_active = true
        FROM sales s
        WHERE si.sale_id = s.id AND s.status::text = 'editing'
          AND si.revision_number = (
              SELECT max(x.revision_number) FROM sale_items x
              WHERE x.sale_id = si.sale_id)
        """
    )
    op.drop_column("sale_revisions", "items")
    op.create_table(
        "sale_item_changes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "sale_id", sa.Uuid(), sa.ForeignKey("sales.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "sale_item_id", sa.Uuid(),
            sa.ForeignKey("sale_items.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column(
            "revision_id", sa.Uuid(),
            sa.ForeignKey("sale_revisions.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("old_data", sa.JSON(), nullable=True),
        sa.Column("new_data", sa.JSON(), nullable=True),
        sa.Column(
            "changed_by_user_id", sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_sale_item_changes_sale_created_at", "sale_item_changes",
        ["sale_id", "created_at"],
    )
    op.create_index(
        "ix_sale_item_changes_revision_id", "sale_item_changes", ["revision_id"]
    )
    op.create_index(
        "ix_sale_item_changes_sale_item_id", "sale_item_changes", ["sale_item_id"]
    )


def downgrade() -> None:
    op.drop_table("sale_item_changes")
    op.add_column(
        "sale_revisions",
        sa.Column("items", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.drop_column("sale_revisions", "closed_at")
    op.drop_column("sale_revisions", "is_changed")
    op.drop_column("sale_revisions", "outcome")
    op.drop_column("sale_revisions", "closed_total")
