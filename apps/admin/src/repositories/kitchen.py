from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from models import KitchenExport, KitchenExportItem, KitchenProduction, KitchenProductionItem, Product, Unit, User
from schemas.kitchen import KitchenAnalyticsRow, KitchenExportLineInput, KitchenExportRow, KitchenProductionLineInput, KitchenProductionRow


class KitchenRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_exports(self) -> list[KitchenExportRow]:
        with self._session_factory() as session:
            quantity = (
                select(func.coalesce(func.sum(KitchenExportItem.quantity), 0))
                .where(KitchenExportItem.export_id == KitchenExport.id)
                .correlate(KitchenExport)
                .scalar_subquery()
            )
            rows = session.execute(
                select(KitchenExport, User.full_name, quantity)
                .join(User, User.id == KitchenExport.created_by)
                .order_by(KitchenExport.created_at.desc(), KitchenExport.id.desc())
            ).all()
            return [
                KitchenExportRow(
                    doc.id,
                    doc.document_number,
                    doc.created_at,
                    name,
                    doc.status,
                    Decimal(qty or 0),
                    doc.total_cost,
                )
                for doc, name, qty in rows
            ]

    def list_productions(self) -> list[KitchenProductionRow]:
        with self._session_factory() as session:
            qty = select(func.coalesce(func.sum(KitchenProductionItem.quantity), 0)).where(
                KitchenProductionItem.production_id == KitchenProduction.id
            ).correlate(KitchenProduction).scalar_subquery()
            count = select(func.count(KitchenProductionItem.id)).where(
                KitchenProductionItem.production_id == KitchenProduction.id
            ).correlate(KitchenProduction).scalar_subquery()
            rows = session.execute(
                select(KitchenProduction, User.full_name, qty, count)
                .join(User, User.id == KitchenProduction.created_by)
                .order_by(KitchenProduction.created_at.desc(), KitchenProduction.id.desc())
            ).all()
            return [KitchenProductionRow(doc.id, doc.document_number, doc.created_at, name, Decimal(total or 0), int(items or 0)) for doc, name, total, items in rows]

    def analytics_rows(self, direction: str, start: datetime | None, end: datetime | None) -> list[KitchenAnalyticsRow]:
        with self._session_factory() as session:
            if direction == "issue":
                query = (select(KitchenExport.document_number, KitchenExport.created_at,
                                KitchenExportItem.product_name, KitchenExportItem.product_sku,
                                KitchenExportItem.unit, KitchenExportItem.quantity, KitchenExportItem.line_total)
                         .join(KitchenExportItem, KitchenExportItem.export_id == KitchenExport.id)
                         .where(KitchenExport.status == "locked"))
            else:
                query = (select(KitchenProduction.document_number, KitchenProduction.created_at,
                                KitchenProductionItem.product_name, KitchenProductionItem.product_sku,
                                KitchenProductionItem.unit, KitchenProductionItem.quantity)
                         .join(KitchenProductionItem, KitchenProductionItem.production_id == KitchenProduction.id))
            doc_model = KitchenExport if direction == "issue" else KitchenProduction
            if start is not None:
                query = query.where(doc_model.created_at >= start)
            if end is not None:
                query = query.where(doc_model.created_at < end)
            query = query.order_by(doc_model.created_at.desc(), doc_model.document_number)
            result = []
            for values in session.execute(query):
                if direction == "issue":
                    number, created, name, sku, unit, quantity, amount = values
                else:
                    number, created, name, sku, unit, quantity = values
                    amount = Decimal("0")
                result.append(KitchenAnalyticsRow(number, created, name, sku, unit, Decimal(quantity), Decimal(amount)))
            return result

    def get_production_detail(self, production_id: uuid.UUID):
        with self._session_factory() as session:
            row = session.execute(
                select(KitchenProduction, User.full_name)
                .join(User, User.id == KitchenProduction.created_by)
                .where(KitchenProduction.id == production_id)
            ).one_or_none()
            if row is None:
                return None
            doc, name = row
            items = list(session.scalars(
                select(KitchenProductionItem)
                .where(KitchenProductionItem.production_id == production_id)
                .order_by(KitchenProductionItem.product_name)
            ))
            return doc, name, items

    def create_production(self, user_id: uuid.UUID, notes: str | None, lines: list[KitchenProductionLineInput]) -> KitchenProduction:
        if not lines:
            raise ValueError("Արտադրության փաստաթուղթը պետք է պարունակի ապրանքներ։")
        merged: dict[uuid.UUID, Decimal] = {}
        for line in lines:
            if not line.quantity.is_finite() or line.quantity <= 0 or line.quantity.as_tuple().exponent < -3:
                raise ValueError("Մուտքագրված քանակը պետք է լինի դրական և առավելագույնը 3 տասնորդականով։")
            merged[line.product_id] = merged.get(line.product_id, Decimal("0")) + line.quantity
        with self._session_factory() as session:
            KitchenRepository._require_user(session, user_id)
            doc = KitchenProduction(id=uuid.uuid4(), document_number=f"KPR-{uuid.uuid4().hex[:10].upper()}", created_by=user_id, notes=notes)
            items = []
            for product_id, quantity in merged.items():
                product = session.scalar(select(Product).where(Product.id == product_id).with_for_update())
                if product is None or not product.is_active or product.unit == Unit.BARBECUE:
                    raise ValueError("Ընտրված ապրանքն անհասանելի է պահեստ մուտքագրելու համար։")
                product.quantity_in_stock = Decimal(product.quantity_in_stock or 0) + quantity
                items.append(KitchenProductionItem(id=uuid.uuid4(), production_id=doc.id, product_id=product.id, product_name=product.name, product_sku=product.sku, unit=product.unit.value, quantity=quantity))
            session.add(doc)
            session.add_all(items)
            session.commit()
            session.refresh(doc)
            return doc

    def get_detail(self, export_id: uuid.UUID):
        with self._session_factory() as session:
            row = session.execute(
                select(KitchenExport, User.full_name)
                .join(User, User.id == KitchenExport.created_by)
                .where(KitchenExport.id == export_id)
            ).one_or_none()
            if row is None:
                return None
            doc, name = row
            items = list(
                session.scalars(
                    select(KitchenExportItem)
                    .where(KitchenExportItem.export_id == export_id)
                    .order_by(KitchenExportItem.product_name)
                )
            )
            return doc, name, items

    def create_draft(
        self, user_id: uuid.UUID, notes: str | None, lines: list[KitchenExportLineInput]
    ) -> KitchenExport:
        with self._session_factory() as session:
            self._require_user(session, user_id)
            doc = KitchenExport(
                id=uuid.uuid4(),
                document_number=f"KEX-{uuid.uuid4().hex[:10].upper()}",
                created_by=user_id,
                status="draft",
                notes=notes,
            )
            self._save_lines(session, doc, lines)
            session.add(doc)
            session.commit()
            session.refresh(doc)
            return doc

    def update_draft(
        self,
        export_id: uuid.UUID,
        notes: str | None,
        lines: list[KitchenExportLineInput],
    ) -> KitchenExport:
        with self._session_factory() as session:
            doc = session.scalar(
                select(KitchenExport)
                .where(KitchenExport.id == export_id)
                .with_for_update()
            )
            if doc is None or doc.status != "draft":
                raise ValueError("Only draft Kitchen documents can be edited")
            self._save_lines(session, doc, lines)
            doc.notes = notes
            session.commit()
            session.refresh(doc)
            return doc

    def lock(self, export_id: uuid.UUID) -> KitchenExport:
        with self._session_factory() as session:
            doc = session.scalar(
                select(KitchenExport)
                .where(KitchenExport.id == export_id)
                .with_for_update()
            )
            if doc is None or doc.status != "draft":
                raise ValueError("Only draft Kitchen documents can be locked")
            items = list(
                session.scalars(
                    select(KitchenExportItem)
                    .where(KitchenExportItem.export_id == export_id)
                    .order_by(KitchenExportItem.product_id)
                    .with_for_update()
                )
            )
            if not items:
                raise ValueError("Kitchen document must contain items")
            for item in items:
                product = session.scalar(
                    select(Product)
                    .where(Product.id == item.product_id)
                    .with_for_update()
                )
                if product is None or not product.is_active:
                    raise ValueError("Kitchen product is unavailable")
                if Decimal(product.quantity_in_stock or 0) < item.quantity:
                    raise ValueError(
                        f"Անբավարար պաշար՝ {item.product_name}։ "
                        "Նվազեցրեք փաստաթղթի քանակը կամ համալրեք ապրանքի պաշարը, "
                        "ապա կրկին կողպեք փաստաթուղթը։"
                    )
                product.quantity_in_stock = (
                    Decimal(product.quantity_in_stock or 0) - item.quantity
                )
            doc.status = "locked"
            doc.locked_at = datetime.now(UTC)
            session.commit()
            session.refresh(doc)
            return doc

    def reopen_for_edit(self, export_id: uuid.UUID) -> KitchenExport:
        with self._session_factory() as session:
            doc = session.scalar(
                select(KitchenExport)
                .where(KitchenExport.id == export_id)
                .with_for_update()
            )
            if doc is None:
                raise ValueError("Kitchen document not found")
            if doc.status == "draft":
                session.commit()
                return doc
            items = list(
                session.scalars(
                    select(KitchenExportItem)
                    .where(KitchenExportItem.export_id == export_id)
                    .order_by(KitchenExportItem.product_id)
                    .with_for_update()
                )
            )
            for item in items:
                product = session.scalar(
                    select(Product)
                    .where(Product.id == item.product_id)
                    .with_for_update()
                )
                if product is None:
                    raise ValueError("Kitchen product is unavailable")
                product.quantity_in_stock = (
                    Decimal(product.quantity_in_stock or 0) + item.quantity
                )
            doc.status = "draft"
            doc.locked_at = None
            session.commit()
            session.refresh(doc)
            return doc

    @staticmethod
    def _require_user(session: Session, user_id: uuid.UUID) -> None:
        if session.get(User, user_id) is None:
            raise ValueError("Kitchen document creator not found")

    @staticmethod
    def _save_lines(
        session: Session, doc: KitchenExport, lines: list[KitchenExportLineInput]
    ) -> None:
        if not lines:
            raise ValueError("Kitchen document must contain at least one item")
        merged: dict[uuid.UUID, Decimal] = {}
        for line in lines:
            if (
                not line.quantity.is_finite()
                or line.quantity <= 0
                or line.quantity.as_tuple().exponent < -3
            ):
                raise ValueError(
                    "Kitchen quantities must be positive and use at most 3 decimals"
                )
            merged[line.product_id] = (
                merged.get(line.product_id, Decimal("0")) + line.quantity
            )
        prior_snapshots = {
            item.product_id: (
                item.product_name,
                item.product_sku,
                item.unit,
                Decimal(item.unit_cost),
            )
            for item in session.scalars(
                select(KitchenExportItem).where(KitchenExportItem.export_id == doc.id)
            )
        }
        session.query(KitchenExportItem).filter(
            KitchenExportItem.export_id == doc.id
        ).delete(synchronize_session=False)
        total = Decimal("0")
        items: list[KitchenExportItem] = []
        for product_id, quantity in merged.items():
            product = session.scalar(
                select(Product).where(Product.id == product_id).with_for_update()
            )
            if product is None or not product.is_active:
                raise ValueError("Kitchen product is unavailable")
            # Keep historical values for unchanged product lines. A product
            # added while editing takes its current inventory cost snapshot.
            prior = prior_snapshots.get(product.id)
            product_name, product_sku, unit, unit_cost = (
                prior
                if prior is not None
                else (
                    product.name,
                    product.sku,
                    product.unit.value,
                    Decimal(product.cost_price or 0),
                )
            )
            line_total = (unit_cost * quantity).quantize(Decimal("0.01"))
            total += line_total
            items.append(
                KitchenExportItem(
                    id=uuid.uuid4(),
                    export_id=doc.id,
                    product_id=product.id,
                    product_name=product_name,
                    product_sku=product_sku,
                    unit=unit,
                    quantity=quantity,
                    unit_cost=unit_cost,
                    line_total=line_total,
                )
            )
        doc.total_cost = total
        session.add_all(items)
