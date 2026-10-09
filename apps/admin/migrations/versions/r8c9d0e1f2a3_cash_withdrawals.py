"""Authorized recipients and cash withdrawal documents."""

from alembic import op
import sqlalchemy as sa

revision = "r8c9d0e1f2a3"
down_revision = "q7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cash_recipients",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "cash_withdrawals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id", sa.Uuid(), sa.ForeignKey("pos_sessions.id"), nullable=False
        ),
        sa.Column(
            "recipient_id",
            sa.Uuid(),
            sa.ForeignKey("cash_recipients.id"),
            nullable=False,
        ),
        sa.Column("recipient_name", sa.String(256), nullable=False),
        sa.Column("cashier_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column(
            "taken_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("amount > 0", name="ck_cash_withdrawal_positive"),
    )
    op.create_index(
        "ix_cash_withdrawals_session_id", "cash_withdrawals", ["session_id"]
    )
    op.create_index("ix_cash_withdrawals_taken_at", "cash_withdrawals", ["taken_at"])


def downgrade():
    op.drop_table("cash_withdrawals")
    op.drop_table("cash_recipients")
