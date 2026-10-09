"""Bounded financial aggregates; no transaction or relationship rows leave SQL."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, bindparam, case, cast, func, literal, select, union_all
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.elements import BindParameter

from models.customer import CustomerCreditPayment, CustomerCreditSale
from models.enums import PurchaseStatus, SaleStatus
from models.product import Product
from models.purchase import Purchase
from models.sale import Sale, SaleItem
from models.supplier import Supplier, SupplierPayment
from models.waste import WasteDocument


class ReportsRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def daily(
        self, start: datetime, end: datetime, timezone: str
    ) -> list[dict[str, Any]]:
        # Each source aggregates independently: joining payments to sale items
        # would multiply both amounts. PostgreSQL groups in business-local days.
        # Reuse one named bind: PostgreSQL treats distinct timezone parameters
        # in SELECT and GROUP BY as distinct expressions, even with equal values.
        timezone_parameter: BindParameter[str] = bindparam(
            "business_timezone", timezone
        )

        def day(column: Any) -> Any:
            return cast(func.timezone(timezone_parameter, column), Date)

        credit = select(
            CustomerCreditSale.sale_id, CustomerCreditSale.amount
        ).subquery()
        sources = [
            select(
                day(Sale.created_at).label("day"),
                literal("revenue").label("metric"),
                func.sum(Sale.total).label("amount"),
            )
            .where(
                Sale.status == SaleStatus.COMPLETED,
                Sale.created_at >= start,
                Sale.created_at < end,
            )
            .group_by(day(Sale.created_at)),
            select(day(Sale.created_at), literal("credit"), func.sum(credit.c.amount))
            .join(credit, credit.c.sale_id == Sale.id)
            .where(
                Sale.status == SaleStatus.COMPLETED,
                Sale.created_at >= start,
                Sale.created_at < end,
            )
            .group_by(day(Sale.created_at)),
            select(day(Sale.created_at), literal("orders"), func.count(Sale.id))
            .where(
                Sale.status == SaleStatus.COMPLETED,
                Sale.created_at >= start,
                Sale.created_at < end,
            )
            .group_by(day(Sale.created_at)),
        ]
        for metric, expression in (
            ("cost", func.sum(SaleItem.quantity * SaleItem.cost_price)),
            (
                "missing_cost",
                func.sum(case((SaleItem.cost_price.is_(None), 1), else_=0)),
            ),
            (
                "free_sales",
                func.sum(
                    case(
                        (
                            SaleItem.line_total == 0,
                            SaleItem.quantity * SaleItem.cost_price,
                        ),
                        else_=0,
                    )
                ),
            ),
        ):
            sources.append(
                select(day(Sale.created_at), literal(metric), expression)
                .join(SaleItem, SaleItem.sale_id == Sale.id)
                .where(
                    Sale.status == SaleStatus.COMPLETED,
                    SaleItem.is_active,
                    Sale.created_at >= start,
                    Sale.created_at < end,
                )
                .group_by(day(Sale.created_at))
            )
        for model, date_column, amount, metric, conditions in (
            (
                CustomerCreditPayment,
                CustomerCreditPayment.paid_at,
                CustomerCreditPayment.amount,
                "repayments",
                (),
            ),
            (
                SupplierPayment,
                SupplierPayment.payment_date,
                SupplierPayment.amount,
                "payments",
                (),
            ),
            (
                Purchase,
                Purchase.purchase_date,
                Purchase.total,
                "purchases",
                (
                    Purchase.status.not_in(
                        (PurchaseStatus.DRAFT, PurchaseStatus.CANCELLED)
                    ),
                ),
            ),
            (
                WasteDocument,
                WasteDocument.locked_at,
                WasteDocument.total_cost,
                "waste",
                (WasteDocument.status == "locked",),
            ),
        ):
            sources.append(
                select(day(date_column), literal(metric), func.sum(amount))
                .select_from(model)
                .where(date_column >= start, date_column < end, *conditions)
                .group_by(day(date_column))
            )
        with self._session_factory() as session:
            return [
                dict(row) for row in session.execute(union_all(*sources)).mappings()
            ]

    def balances(self) -> dict[str, Decimal]:
        def total(column: Any, *conditions: Any) -> Any:
            return (
                select(func.coalesce(func.sum(column), 0))
                .where(*conditions)
                .scalar_subquery()
            )

        credit_total = (
            select(func.coalesce(func.sum(CustomerCreditSale.amount), 0))
            .join(Sale, Sale.id == CustomerCreditSale.sale_id)
            .where(Sale.status == SaleStatus.COMPLETED)
            .scalar_subquery()
        )
        statement = select(
            total(Product.quantity_in_stock * Product.cost_price).label("stock_cost"),
            total(Product.quantity_in_stock * Product.selling_price).label(
                "stock_retail"
            ),
            total(
                case((Product.cost_price.is_(None), 1), else_=0),
                Product.quantity_in_stock != 0,
            ).label("stock_missing_cost"),
            total(case((Product.quantity_in_stock < 0, 1), else_=0)).label(
                "negative_stock"
            ),
            (credit_total - total(CustomerCreditPayment.amount)).label("customer_debt"),
            (
                total(Supplier.opening_debt)
                + total(
                    Purchase.total,
                    Purchase.status.not_in(
                        (PurchaseStatus.DRAFT, PurchaseStatus.CANCELLED)
                    ),
                )
                - total(SupplierPayment.amount)
            ).label("supplier_debt"),
        )
        with self._session_factory() as session:
            return {
                key: Decimal(value)
                for key, value in session.execute(statement).mappings().one().items()
            }
