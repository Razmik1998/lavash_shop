"""Add spoilage write-off documents and product lines."""

import sqlalchemy as sa
from alembic import op

revision = "p6a7b8c9d0e1"
down_revision = "o5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "waste_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_number", sa.String(32), nullable=False),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("total_cost", sa.Numeric(12, 2), nullable=False),
        sa.Column("notes", sa.String(2000)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "total_cost >= 0", name="ck_waste_documents_total_cost_nonnegative"
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'locked')", name="ck_waste_documents_status"
        ),
    )
    op.create_index(
        "ix_waste_documents_document_number",
        "waste_documents",
        ["document_number"],
        unique=True,
    )
    op.create_index("ix_waste_documents_created_at", "waste_documents", ["created_at"])
    op.create_table(
        "waste_document_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("waste_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Uuid(),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("product_sku", sa.String(64), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("reason_note", sa.String(2000)),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint(
            "quantity > 0", name="ck_waste_document_items_quantity_positive"
        ),
        sa.CheckConstraint(
            "unit_cost >= 0", name="ck_waste_document_items_cost_nonnegative"
        ),
        sa.CheckConstraint(
            "line_total >= 0", name="ck_waste_document_items_total_nonnegative"
        ),
    )
    op.create_index(
        "ix_waste_document_items_product", "waste_document_items", ["product_id"]
    )


def downgrade():
    op.drop_table("waste_document_items")
    op.drop_table("waste_documents")
