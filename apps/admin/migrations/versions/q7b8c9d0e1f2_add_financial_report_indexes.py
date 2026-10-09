"""Index financial report date filters and active sale-item joins."""

from alembic import op

revision = "q7b8c9d0e1f2"
down_revision = "p6a7b8c9d0e1"
branch_labels = None
depends_on = None

INDEXES = (
    ("ix_customer_credit_payments_paid_at", "customer_credit_payments", ["paid_at"]),
    ("ix_supplier_payments_payment_date", "supplier_payments", ["payment_date"]),
    ("ix_waste_documents_locked_at", "waste_documents", ["locked_at"]),
    ("ix_sale_items_sale_active", "sale_items", ["sale_id", "is_active"]),
)


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
