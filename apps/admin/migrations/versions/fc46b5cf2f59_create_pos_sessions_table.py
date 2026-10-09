"""create pos sessions table

Revision ID: fc46b5cf2f59
Revises: 9b2f4e7a1c63
Create Date: 2026-09-10 19:47:28.961990

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fc46b5cf2f59"
down_revision: str | None = "9b2f4e7a1c63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pos_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("terminal_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "closed", name="pos_session_status"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_connected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pos_sessions_terminal_id", "pos_sessions", ["terminal_id"], unique=False
    )
    op.create_index(
        "ix_pos_sessions_active_terminal_unique",
        "pos_sessions",
        ["terminal_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pos_sessions_active_terminal_unique",
        table_name="pos_sessions",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_index("ix_pos_sessions_terminal_id", table_name="pos_sessions")
    op.drop_table("pos_sessions")
    # Autogenerate does not drop the enum type it created for the
    # `status` column; without this, re-running upgrade after a downgrade
    # fails with "type pos_session_status already exists".
    sa.Enum(name="pos_session_status").drop(op.get_bind(), checkfirst=True)
