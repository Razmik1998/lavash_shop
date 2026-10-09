"""Repository: owns Session usage for the users table."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from exceptions import (
    BarcodeAlreadyExistsError,
    SkuAlreadyExistsError,
)
from models import (
    Product,
    Unit,
)

ARMENIA_TIMEZONE = ZoneInfo("Asia/Yerevan")


class ProductRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_by_id(self, product_id: object) -> Product | None:
        with self._session_factory() as session:
            return session.get(Product, product_id)

    def get_latest_sku(self) -> str | None:
        with self._session_factory() as session:
            return session.scalar(
                select(Product.sku)
                .order_by(Product.created_at.desc(), Product.id.desc())
                .limit(1)
            )

    def list_all(self) -> list[Product]:
        with self._session_factory() as session:
            return list(session.scalars(select(Product).order_by(Product.name)))

    def list_by_unit(self, unit: Unit) -> list[Product]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(Product).where(Product.unit == unit).order_by(Product.name)
                )
            )

    def list_active(self) -> list[Product]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(Product).where(Product.is_active).order_by(Product.name)
                )
            )

    def list_active_for_sale(self) -> list[Product]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(Product)
                    .where(Product.is_active, Product.is_for_sale)
                    .order_by(Product.name)
                )
            )

    def search(self, term: str) -> list[Product]:
        with self._session_factory() as session:
            pattern = f"%{term}%"
            statement = select(Product).where(
                or_(
                    Product.name.ilike(pattern),
                    Product.sku == term,
                    Product.barcode == term,
                )
            )
            return list(session.scalars(statement.order_by(Product.name)))

    def add(self, product: Product) -> Product:
        with self._session_factory() as session:
            session.add(product)
            self._commit_product(session, product)
            session.refresh(product)
            return product

    def update(self, product: Product) -> Product:
        with self._session_factory() as session:
            managed_product = session.merge(product)
            self._commit_product(session, managed_product)
            session.refresh(managed_product)
            return managed_product

    @staticmethod
    def _commit_product(session: Session, product: Product) -> None:
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            diag = getattr(exc.orig, "diag", None)
            constraint_name = getattr(diag, "constraint_name", "")
            error_text = str(exc.orig).lower()
            if (
                constraint_name == "ix_products_sku"
                or "ix_products_sku" in error_text
            ):
                raise SkuAlreadyExistsError(product.sku) from exc
            if (
                constraint_name == "ix_products_barcode_unique"
                or "ix_products_barcode_unique" in error_text
            ):
                raise BarcodeAlreadyExistsError(product.barcode or "") from exc
            raise
