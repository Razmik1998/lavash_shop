from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from exceptions import (
    CustomerNotFoundError,
    CustomerPhoneAlreadyExistsError,
    InvalidCreditPaymentError,
)
from models import (
    CreditCustomer,
    CustomerCreditPayment,
    CustomerCreditSale,
    Sale,
    SaleStatus,
)
from schemas.customer import (
    CustomerPaymentHistoryRow,
    CustomerPaymentRow,
    CustomerRow,
)


class CustomerRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create(
        self,
        first_name: str,
        last_name: str,
        phone: str,
        address: str | None = None,
        notes: str | None = None,
    ) -> CustomerRow:
        with self._session_factory() as session:
            customer = CreditCustomer(
                first_name=first_name.strip(),
                last_name=last_name.strip(),
                phone=phone.strip(),
                address=address,
                notes=notes,
            )
            session.add(customer)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise CustomerPhoneAlreadyExistsError(
                    "A customer with this phone already exists"
                ) from exc
            session.refresh(customer)
            return self._row(session, customer)

    def search(self, query: str = "", *, active_only: bool = True) -> list[CustomerRow]:
        with self._session_factory() as session:
            statement = select(CreditCustomer)
            if active_only:
                statement = statement.where(CreditCustomer.is_active)
            query = query.strip()
            if query:
                pattern = f"%{query}%"
                statement = statement.where(
                    or_(
                        CreditCustomer.first_name.ilike(pattern),
                        CreditCustomer.last_name.ilike(pattern),
                        CreditCustomer.phone.ilike(pattern),
                    )
                )
            customers = list(
                session.scalars(
                    statement.order_by(
                        CreditCustomer.last_name, CreditCustomer.first_name
                    )
                )
            )
            return [self._row(session, customer) for customer in customers]

    def get(self, customer_id: uuid.UUID) -> CustomerRow:
        with self._session_factory() as session:
            customer = session.get(CreditCustomer, customer_id)
            if customer is None:
                raise CustomerNotFoundError(f"Customer not found: {customer_id}")
            return self._row(session, customer)

    def list_payment_history(
        self,
        from_datetime: datetime | None = None,
        to_datetime: datetime | None = None,
        customer_id: uuid.UUID | None = None,
    ) -> list[CustomerPaymentHistoryRow]:
        with self._session_factory() as session:
            statement = (
                select(
                    CustomerCreditPayment,
                    CreditCustomer.first_name,
                    CreditCustomer.last_name,
                    CreditCustomer.phone,
                )
                .join(
                    CreditCustomer,
                    CreditCustomer.id == CustomerCreditPayment.customer_id,
                )
                .order_by(CustomerCreditPayment.paid_at.desc())
            )
            if from_datetime is not None:
                statement = statement.where(
                    CustomerCreditPayment.paid_at >= from_datetime
                )
            if to_datetime is not None:
                statement = statement.where(CustomerCreditPayment.paid_at < to_datetime)
            if customer_id is not None:
                statement = statement.where(
                    CustomerCreditPayment.customer_id == customer_id
                )
            return [
                CustomerPaymentHistoryRow(
                    payment.id,
                    payment.customer_id,
                    f"{first_name} {last_name}",
                    phone,
                    payment.amount,
                    payment.pos_session_id,
                    payment.pos_user_id,
                    payment.paid_at,
                )
                for payment, first_name, last_name, phone in session.execute(statement)
            ]

    def payment_totals_by_sessions(
        self, session_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, Decimal]:
        if not session_ids:
            return {}
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    CustomerCreditPayment.pos_session_id,
                    func.coalesce(func.sum(CustomerCreditPayment.amount), 0),
                )
                .where(CustomerCreditPayment.pos_session_id.in_(session_ids))
                .group_by(CustomerCreditPayment.pos_session_id)
            )
            return {session_id: Decimal(total) for session_id, total in rows}

    def record_full_payment(
        self,
        customer_id: uuid.UUID,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        amount: Decimal,
    ) -> CustomerPaymentRow:
        with self._session_factory() as session:
            customer = session.scalar(
                select(CreditCustomer)
                .where(CreditCustomer.id == customer_id)
                .with_for_update()
            )
            if customer is None or not customer.is_active:
                raise CustomerNotFoundError(f"Customer not found: {customer_id}")
            debt = self._debt(session, customer_id)
            if amount <= 0 or amount > debt:
                raise InvalidCreditPaymentError(
                    "Payment must be positive and cannot exceed "
                    "the customer's current debt"
                )
            payment = CustomerCreditPayment(
                customer_id=customer_id,
                amount=amount,
                pos_session_id=session_id,
                pos_user_id=user_id,
            )
            session.add(payment)
            session.commit()
            session.refresh(payment)
            return CustomerPaymentRow(
                payment.id,
                payment.customer_id,
                payment.amount,
                payment.pos_session_id,
                payment.pos_user_id,
                payment.paid_at,
            )

    @staticmethod
    def _debt(session: Session, customer_id: uuid.UUID) -> Decimal:
        sales = session.scalar(
            select(func.coalesce(func.sum(CustomerCreditSale.amount), 0))
            .join(Sale, Sale.id == CustomerCreditSale.sale_id)
            .where(
                CustomerCreditSale.customer_id == customer_id,
                Sale.status.not_in(
                    (SaleStatus.EDITING, SaleStatus.CANCELLED, SaleStatus.VOIDED)
                ),
            )
        ) or Decimal("0")
        payments = session.scalar(
            select(func.coalesce(func.sum(CustomerCreditPayment.amount), 0)).where(
                CustomerCreditPayment.customer_id == customer_id
            )
        ) or Decimal("0")
        return Decimal(sales) - Decimal(payments)

    def _row(self, session: Session, customer: CreditCustomer) -> CustomerRow:
        return CustomerRow(
            customer.id,
            customer.first_name,
            customer.last_name,
            customer.phone,
            customer.address,
            customer.notes,
            customer.is_active,
            self._debt(session, customer.id),
        )
