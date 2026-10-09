"""backfill explicit key links from legacy audit JSON values"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d9e0f1a2b3c4"
down_revision: str | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE sale_audit_events
            SET authorization_key_id = (new_value->>'authorization_key_id')::uuid
            WHERE authorization_key_id IS NULL
              AND new_value IS NOT NULL
              AND new_value->>'authorization_key_id' IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    pass