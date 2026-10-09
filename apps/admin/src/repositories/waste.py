from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from models import Product, User
from models.waste import WasteDocument, WasteDocumentItem
from schemas.waste import WASTE_REASONS, WasteLineInput, WasteRow


class WasteRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_documents(self) -> list[WasteRow]:
        with self._session_factory() as session:
            quantity = (
                select(func.coalesce(func.sum(WasteDocumentItem.quantity), 0))
                .where(WasteDocumentItem.document_id == WasteDocument.id)
                .correlate(WasteDocument)
                .scalar_subquery()
            )
            rows = session.execute(
                select(WasteDocument, User.full_name, quantity)
                .join(User, User.id == WasteDocument.created_by)
                .order_by(WasteDocument.created_at.desc(), WasteDocument.id.desc())
            ).all()
            return [
                WasteRow(
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

    def get_detail(self, document_id: uuid.UUID):
        with self._session_factory() as session:
            row = session.execute(
                select(WasteDocument, User.full_name)
                .join(User, User.id == WasteDocument.created_by)
                .where(WasteDocument.id == document_id)
            ).one_or_none()
            if row is None:
                return None
            doc, name = row
            items = list(
                session.scalars(
                    select(WasteDocumentItem)
                    .where(WasteDocumentItem.document_id == document_id)
                    .order_by(WasteDocumentItem.product_name)
                )
            )
            return doc, name, items

    def create_draft(
        self,
        user_id: uuid.UUID,
        notes: str | None,
        lines: list[WasteLineInput],
        *,
        complete: bool = False,
    ) -> WasteDocument:
        with self._session_factory() as session:
            self._require_user(session, user_id)
            doc = WasteDocument(
                id=uuid.uuid4(),
                document_number=f"WST-{uuid.uuid4().hex[:10].upper()}",
                created_by=user_id,
                status="draft",
                notes=notes,
            )
            self._save_lines(session, doc, lines)
            session.add(doc)
            session.flush()
            if complete:
                self._complete(session, doc)
            session.commit()
            session.refresh(doc)
            return doc

    def update_draft(
        self,
        document_id: uuid.UUID,
        notes: str | None,
        lines: list[WasteLineInput],
        *,
        complete: bool = False,
    ) -> WasteDocument:
        with self._session_factory() as session:
            doc = session.scalar(
                select(WasteDocument)
                .where(WasteDocument.id == document_id)
                .with_for_update()
            )
            if doc is None or doc.status != "draft":
                raise ValueError("Only draft Waste documents can be edited")
            doc.notes = notes
            self._save_lines(session, doc, lines)
            session.flush()
            if complete:
                self._complete(session, doc)
            session.commit()
            session.refresh(doc)
            return doc

    def lock(self, document_id: uuid.UUID) -> WasteDocument:
        with self._session_factory() as session:
            doc = session.scalar(
                select(WasteDocument)
                .where(WasteDocument.id == document_id)
                .with_for_update()
            )
            if doc is None or doc.status != "draft":
                raise ValueError("Only draft Waste documents can be locked")
            self._complete(session, doc)
            session.commit()
            session.refresh(doc)
            return doc

    @staticmethod
    def _complete(session: Session, doc: WasteDocument) -> None:
        items = list(
            session.scalars(
                select(WasteDocumentItem)
                .where(WasteDocumentItem.document_id == doc.id)
                .order_by(WasteDocumentItem.product_id)
                .with_for_update()
            )
        )
        if not items:
            raise ValueError("Waste document must contain items")
        for item in items:
            product = session.scalar(
                select(Product).where(Product.id == item.product_id).with_for_update()
            )
            if product is None or not product.is_active:
                raise ValueError("Waste product is unavailable")
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

    def reopen_for_edit(self, document_id: uuid.UUID) -> WasteDocument:
        with self._session_factory() as session:
            doc = session.scalar(
                select(WasteDocument)
                .where(WasteDocument.id == document_id)
                .with_for_update()
            )
            if doc is None:
                raise ValueError("Waste document not found")
            if doc.status == "draft":
                session.commit()
                return doc
            items = list(
                session.scalars(
                    select(WasteDocumentItem)
                    .where(WasteDocumentItem.document_id == document_id)
                    .order_by(WasteDocumentItem.product_id)
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
                    raise ValueError("Waste product is unavailable")
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
            raise ValueError("Waste document creator not found")

    @staticmethod
    def _save_lines(
        session: Session, doc: WasteDocument, lines: list[WasteLineInput]
    ) -> None:
        if not lines:
            raise ValueError("Waste document must contain at least one item")
        merged: dict[uuid.UUID, Decimal] = {}
        for line in lines:
            if (
                not line.quantity.is_finite()
                or line.quantity <= 0
                or line.quantity.as_tuple().exponent < -3
            ):
                raise ValueError(
                    "Waste quantities must be positive and use at most 3 decimals"
                )
            merged[line.product_id] = (
                merged.get(line.product_id, Decimal("0")) + line.quantity
            )
        reasons = {}
        for line in lines:
            if line.reason not in WASTE_REASONS:
                raise ValueError("Ընտրեք դուրսգրման պատճառը։")
            note = (line.reason_note or "").strip()
            if len(note) > 2000 or (line.reason == "custom" and not note):
                raise ValueError(
                    "Այլ պատճառի համար գրեք նշում (առավելագույնը 2000 նիշ)։"
                )
            if line.product_id in reasons and reasons[line.product_id] != (
                line.reason,
                note,
            ):
                raise ValueError("Նույն ապրանքի համար ընտրեք մեկ պատճառ։")
            reasons[line.product_id] = (line.reason, note)
        if doc.notes and len(doc.notes) > 2000:
            raise ValueError("Նշումը չափազանց երկար է։")
        prior_snapshots = {
            item.product_id: (
                item.product_name,
                item.product_sku,
                item.unit,
                Decimal(item.unit_cost),
            )
            for item in session.scalars(
                select(WasteDocumentItem).where(WasteDocumentItem.document_id == doc.id)
            )
        }
        session.query(WasteDocumentItem).filter(
            WasteDocumentItem.document_id == doc.id
        ).delete(synchronize_session=False)
        total = Decimal("0")
        items: list[WasteDocumentItem] = []
        for product_id, quantity in sorted(merged.items()):
            product = session.scalar(
                select(Product).where(Product.id == product_id).with_for_update()
            )
            if product is None or not product.is_active:
                raise ValueError("Waste product is unavailable")
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
                WasteDocumentItem(
                    id=uuid.uuid4(),
                    document_id=doc.id,
                    product_id=product.id,
                    product_name=product_name,
                    product_sku=product_sku,
                    reason=reasons[product_id][0],
                    reason_note=reasons[product_id][1] or None,
                    unit=unit,
                    quantity=quantity,
                    unit_cost=unit_cost,
                    line_total=line_total,
                )
            )
        doc.total_cost = total
        session.add_all(items)
