from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from exceptions import (
    InvalidPurchaseError,
    PaymentError,
    PurchaseCancellationError,
    PurchaseNotFoundError,
)
from models import (
    InventoryMovement,
    InventoryMovementType,
    PaymentMethod,
    Product,
    PurchaseStatus,
    Supplier,
    Unit,
)
from repository import ProductRepository, PurchaseRepository, SupplierRepository
from services import (
    PurchaseFilters,
    PurchaseLineInput,
    PurchaseService,
    SupplierService,
)


def _product(name: str = "Սուրճ", sku: str = "COF-001") -> Product:
    return Product(
        id=uuid.uuid4(),
        name=name,
        sku=sku,
        unit=Unit.PIECE,
        cost_price=Decimal("2.00"),
        selling_price=Decimal("3.00"),
        quantity_in_stock=Decimal("4"),
        is_active=True,
    )


def _setup(
    session_factory: sessionmaker[Session],
) -> tuple[Supplier, Product, PurchaseService]:
    supplier_repository = SupplierRepository(session_factory)
    product_repository = ProductRepository(session_factory)
    purchase_repository = PurchaseRepository(session_factory)
    supplier = supplier_repository.save(
        Supplier(id=uuid.uuid4(), name="Բարի մատակարար")
    )
    product = product_repository.add(_product())
    service = PurchaseService(purchase_repository, product_repository)
    return supplier, product, service


def test_supplier_name_is_required_and_lifecycle_is_non_destructive(
    session_factory: sessionmaker[Session],
) -> None:
    repository = SupplierRepository(session_factory)
    service = SupplierService(repository)

    with pytest.raises(InvalidPurchaseError):
        service.save_supplier(None, "  ", None, None)

    supplier = service.save_supplier(
        None, "  Արև  ", " 091 000000 ", "  Նկարագրություն "
    )
    archived = service.save_supplier(
        supplier.id, supplier.name, supplier.phone, supplier.description, False
    )
    assert archived.is_active is False
    assert service.get_supplier(supplier.id).name == "Արև"


def test_draft_isolated_and_item_snapshots_are_immutable(
    session_factory: sessionmaker[Session],
) -> None:
    supplier, product, service = _setup(session_factory)
    draft = service.create_draft(
        supplier.id,
        datetime.now(UTC),
        "draft note",
        [
            PurchaseLineInput(
                product.id, Decimal("2"), Decimal("5.25"), Decimal("8.00")
            )
        ],
    )

    assert draft.status is PurchaseStatus.DRAFT
    assert draft.total == Decimal("10.50")
    detail = service.get_detail(draft.id)
    assert detail.items[0].product_name == "Սուրճ"
    assert detail.items[0].unit_cost == Decimal("5.25")
    assert detail.items[0].selling_price == Decimal("8.00")
    assert detail.items[0].markup_percentage == Decimal("52.381")

    product.name = "Փոփոխված Սուրճ"
    product.selling_price = Decimal("99.00")
    product_repository = ProductRepository(session_factory)
    product_repository.update(product)

    unchanged = service.get_detail(draft.id)
    assert unchanged.items[0].product_name == "Սուրճ"
    assert unchanged.items[0].selling_price == Decimal("8.00")
    stored_product = product_repository.get_by_id(product.id)
    assert stored_product is not None
    assert stored_product.quantity_in_stock == Decimal("4.000")


def test_draft_can_be_updated_and_deleted_without_inventory_effect(
    session_factory: sessionmaker[Session],
) -> None:
    supplier, product, service = _setup(session_factory)
    draft = service.create_draft(
        supplier.id,
        datetime.now(UTC),
        "before",
        [PurchaseLineInput(product.id, Decimal("1"), Decimal("2.00"), Decimal("3.00"))],
    )
    service.update_draft(
        draft.id,
        supplier.id,
        datetime.now(UTC),
        "after",
        [PurchaseLineInput(product.id, Decimal("4"), Decimal("2.50"), Decimal("3.50"))],
    )
    detail = service.get_detail(draft.id)
    assert detail.purchase.total == Decimal("10.00")
    assert detail.purchase.notes == "after"
    assert detail.items[0].quantity == Decimal("4.000")
    assert ProductRepository(session_factory).get_by_id(product.id).quantity_in_stock == Decimal("4.000")  # type: ignore[union-attr]
    service.delete_draft(draft.id)
    with pytest.raises(PurchaseNotFoundError):
        service.get_detail(draft.id)


def test_draft_rejects_unknown_supplier(
    session_factory: sessionmaker[Session],
) -> None:
    product_repository = ProductRepository(session_factory)
    product = product_repository.add(_product())
    service = PurchaseService(PurchaseRepository(session_factory), product_repository)

    with pytest.raises(InvalidPurchaseError):
        service.create_draft(
            uuid.uuid4(),
            datetime.now(UTC),
            None,
            [
                PurchaseLineInput(
                    product.id, Decimal("1"), Decimal("2.00"), Decimal("3.00")
                )
            ],
        )


def test_confirm_receives_inventory_once_and_cancellation_reverses_once(
    session_factory: sessionmaker[Session],
) -> None:
    supplier, product, service = _setup(session_factory)
    draft = service.create_draft(
        supplier.id,
        datetime.now(UTC),
        None,
        [
            PurchaseLineInput(
                product.id, Decimal("3"), Decimal("5.00"), Decimal("7.50")
            )
        ],
    )

    confirmed = service.confirm(
        draft.id,
        Decimal("5.00"),
        PaymentMethod.CASH,
        {product.id: Decimal("7.50")},
    )
    assert confirmed.status is PurchaseStatus.PARTIALLY_PAID
    stored_product = ProductRepository(session_factory).get_by_id(product.id)
    assert stored_product is not None
    assert stored_product.quantity_in_stock == Decimal("7.000")
    item_id = service.get_detail(draft.id).items[0].id
    with session_factory() as session:
        assert session.scalar(
            select(func.count(InventoryMovement.id)).where(
                InventoryMovement.purchase_item_id == item_id,
                InventoryMovement.movement_type == InventoryMovementType.RECEIPT,
            )
        ) == 1

    with pytest.raises(InvalidPurchaseError):
        service.confirm(draft.id)

    with pytest.raises(PurchaseCancellationError):
        service.cancel(draft.id)


def test_internal_product_can_be_purchased_into_inventory_without_sale_price(
    session_factory: sessionmaker[Session],
) -> None:
    supplier_repository = SupplierRepository(session_factory)
    product_repository = ProductRepository(session_factory)
    supplier = supplier_repository.save(Supplier(id=uuid.uuid4(), name="Oil supplier"))
    product = product_repository.add(
        Product(
            id=uuid.uuid4(),
            name="Oil",
            sku="OIL-001",
            unit=Unit.LITER,
            cost_price=Decimal("4.00"),
            selling_price=None,
            minimum_price=None,
            quantity_in_stock=Decimal("0"),
            is_active=True,
            is_for_sale=False,
        )
    )
    service = PurchaseService(PurchaseRepository(session_factory), product_repository)
    draft = service.create_draft(
        supplier.id,
        datetime.now(UTC),
        None,
        [PurchaseLineInput(product.id, Decimal("5"), Decimal("4.00"), None)],
    )

    service.confirm(draft.id)

    stored = product_repository.get_by_id(product.id)
    assert stored is not None
    assert stored.quantity_in_stock == Decimal("5.000")
    assert stored.is_for_sale is False
    assert stored.selling_price is None


def test_unpaid_cancellation_reverses_inventory_and_is_idempotent(
    session_factory: sessionmaker[Session],
) -> None:
    supplier, product, service = _setup(session_factory)
    draft = service.create_draft(
        supplier.id,
        datetime.now(UTC),
        None,
        [
            PurchaseLineInput(
                product.id, Decimal("2"), Decimal("5.00"), Decimal("7.50")
            )
        ],
    )
    service.confirm(draft.id)
    service.cancel(draft.id)
    service.cancel(draft.id)

    stored_product = ProductRepository(session_factory).get_by_id(product.id)
    assert stored_product is not None
    assert stored_product.quantity_in_stock == Decimal("4.000")
    item_id = service.get_detail(draft.id).items[0].id
    with session_factory() as session:
        assert session.scalar(
            select(func.count(InventoryMovement.id)).where(
                InventoryMovement.purchase_item_id == item_id,
                InventoryMovement.movement_type == InventoryMovementType.REVERSAL,
            )
        ) == 1


def test_payments_update_status_reject_overpayment_and_cancel_paid_purchase(
    session_factory: sessionmaker[Session],
) -> None:
    supplier, product, service = _setup(session_factory)
    draft = service.create_draft(
        supplier.id,
        datetime.now(UTC),
        None,
        [
            PurchaseLineInput(
                product.id, Decimal("1"), Decimal("10.00"), Decimal("15.00")
            )
        ],
    )
    service.confirm(draft.id)
    service.add_payment(
        draft.id, Decimal("4.00"), PaymentMethod.TRANSFER, datetime.now(UTC)
    )
    assert service.get_detail(draft.id).purchase.status is PurchaseStatus.PARTIALLY_PAID

    with pytest.raises(PaymentError):
        service.add_payment(
            draft.id, Decimal("7.00"), PaymentMethod.CASH, datetime.now(UTC)
        )
    service.add_payment(
        draft.id, Decimal("6.00"), PaymentMethod.CASH, datetime.now(UTC)
    )
    detail = service.get_detail(draft.id)
    assert detail.purchase.status is PurchaseStatus.PAID
    paid_total = sum(
        (payment.amount for payment in detail.payments), Decimal("0")
    )
    assert paid_total == Decimal("10.00")

    with pytest.raises(PurchaseCancellationError):
        service.cancel(draft.id)


def test_supplier_purchase_page_is_newest_first_and_reports_balances(
    session_factory: sessionmaker[Session],
) -> None:
    supplier, product, service = _setup(session_factory)
    purchase_dates = [
        datetime(2026, 9, 8, tzinfo=UTC),
        datetime(2026, 9, 10, tzinfo=UTC),
        datetime(2026, 9, 10, tzinfo=UTC),
    ]
    purchases = []
    for purchase_date in purchase_dates:
        draft = service.create_draft(
            supplier.id,
            purchase_date,
            None,
            [
                PurchaseLineInput(
                    product.id, Decimal("1"), Decimal("10.00"), Decimal("15.00")
                )
            ],
        )
        purchases.append(service.confirm(draft.id))
    service.add_payment(
        purchases[1].id,
        Decimal("4.00"),
        PaymentMethod.CASH,
        datetime.now(UTC),
    )

    first_page = service.list_purchase_page(
        PurchaseFilters(supplier_id=supplier.id), offset=0, limit=2
    )
    second_page = service.list_purchase_page(
        PurchaseFilters(supplier_id=supplier.id), offset=2, limit=2
    )

    assert [row.id for row in first_page.items] == sorted(
        [purchases[1].id, purchases[2].id], reverse=True
    )
    paid_purchase = next(row for row in first_page.items if row.id == purchases[1].id)
    assert paid_purchase.paid == Decimal("4.00")
    assert paid_purchase.debt == Decimal("6.00")
    assert first_page.has_more is True
    assert [row.id for row in second_page.items] == [purchases[0].id]
    assert second_page.has_more is False


def _confirmed_purchase(
    service: PurchaseService,
    supplier: Supplier,
    product: Product,
    purchase_date: datetime,
    unit_cost: str,
) -> uuid.UUID:
    draft = service.create_draft(
        supplier.id,
        purchase_date,
        None,
        [PurchaseLineInput(product.id, Decimal("1"), Decimal(unit_cost), Decimal("99.00"))],
    )
    return service.confirm(draft.id).id


def test_supplier_account_filters_period_and_reports_totals(
    session_factory: sessionmaker[Session],
) -> None:
    supplier, product, service = _setup(session_factory)
    supplier_service = SupplierService(SupplierRepository(session_factory))
    old = _confirmed_purchase(
        service, supplier, product, datetime(2026, 1, 5, tzinfo=UTC), "10.00"
    )
    recent = _confirmed_purchase(
        service, supplier, product, datetime(2026, 9, 5, tzinfo=UTC), "30.00"
    )
    service.add_payment(
        recent, Decimal("5.00"), PaymentMethod.CASH, datetime(2026, 9, 6, tzinfo=UTC)
    )
    service.add_payment(
        old, Decimal("2.00"), PaymentMethod.CARD, datetime(2026, 2, 1, tzinfo=UTC)
    )

    account = supplier_service.get_account(
        supplier.id,
        datetime(2026, 9, 1, tzinfo=UTC),
        datetime(2026, 10, 1, tzinfo=UTC),
    )

    assert [row.id for row in account.purchases] == [recent]
    assert account.purchased_total == Decimal("30.00")
    assert account.paid_total == Decimal("5.00")
    assert account.debt == Decimal("25.00")
    assert [payment.amount for payment in account.payments] == [Decimal("5.00")]
    assert account.payments[0].purchase_number is not None
    assert account.total_debt == Decimal("33.00")


def test_pay_supplier_debt_spreads_payment_oldest_first(
    session_factory: sessionmaker[Session],
) -> None:
    supplier, product, service = _setup(session_factory)
    first = _confirmed_purchase(
        service, supplier, product, datetime(2026, 9, 1, tzinfo=UTC), "10.00"
    )
    second = _confirmed_purchase(
        service, supplier, product, datetime(2026, 9, 2, tzinfo=UTC), "20.00"
    )

    paid_documents = service.pay_supplier_debt(
        supplier.id, Decimal("15.00"), PaymentMethod.CASH, datetime.now(UTC)
    )

    assert paid_documents == 2
    assert service.get_detail(first).purchase.status is PurchaseStatus.PAID
    second_detail = service.get_detail(second)
    assert second_detail.purchase.status is PurchaseStatus.PARTIALLY_PAID
    assert sum(p.amount for p in second_detail.payments) == Decimal("5.00")

    with pytest.raises(PaymentError):
        service.pay_supplier_debt(
            supplier.id, Decimal("15.01"), PaymentMethod.CASH, datetime.now(UTC)
        )
    assert sum(
        p.amount for p in service.get_detail(second).payments
    ) == Decimal("5.00")


def test_pay_supplier_debt_only_pays_documents_in_period(
    session_factory: sessionmaker[Session],
) -> None:
    supplier, product, service = _setup(session_factory)
    outside = _confirmed_purchase(
        service, supplier, product, datetime(2026, 1, 1, tzinfo=UTC), "10.00"
    )
    inside = _confirmed_purchase(
        service, supplier, product, datetime(2026, 9, 1, tzinfo=UTC), "10.00"
    )

    with pytest.raises(PaymentError):
        service.pay_supplier_debt(
            supplier.id,
            Decimal("20.00"),
            PaymentMethod.CASH,
            datetime.now(UTC),
            datetime(2026, 8, 1, tzinfo=UTC),
            datetime(2026, 10, 1, tzinfo=UTC),
        )
    service.pay_supplier_debt(
        supplier.id,
        Decimal("10.00"),
        PaymentMethod.CASH,
        datetime.now(UTC),
        datetime(2026, 8, 1, tzinfo=UTC),
        datetime(2026, 10, 1, tzinfo=UTC),
    )

    assert service.get_detail(inside).purchase.status is PurchaseStatus.PAID
    assert service.get_detail(outside).purchase.status is PurchaseStatus.OPEN


def test_pay_supplier_debt_rejects_invalid_amounts(
    session_factory: sessionmaker[Session],
) -> None:
    supplier, _product, service = _setup(session_factory)
    for amount in (Decimal("0"), Decimal("-1"), Decimal("1.001")):
        with pytest.raises(PaymentError):
            service.pay_supplier_debt(
                supplier.id, amount, PaymentMethod.CASH, datetime.now(UTC)
            )


def test_reopen_for_edit_reverts_stock_payment_and_allows_item_removal(
    session_factory: sessionmaker[Session],
) -> None:
    supplier, product, service = _setup(session_factory)
    second_product = ProductRepository(session_factory).add(
        _product(name="Թեյ", sku="TEA-001")
    )
    draft = service.create_draft(
        supplier.id,
        datetime.now(UTC),
        None,
        [
            PurchaseLineInput(
                product.id, Decimal("10"), Decimal("2.00"), Decimal("3.00")
            ),
            PurchaseLineInput(
                second_product.id, Decimal("5"), Decimal("4.00"), Decimal("6.00")
            ),
        ],
    )
    service.confirm(draft.id, Decimal("5.00"), PaymentMethod.CASH)

    reopened = service.reopen_for_edit(draft.id)

    assert reopened.status is PurchaseStatus.DRAFT
    stored_product = ProductRepository(session_factory).get_by_id(product.id)
    assert stored_product is not None
    assert stored_product.quantity_in_stock == Decimal("4.000")
    detail = service.get_detail(draft.id)
    assert detail.payments == []
    assert len(detail.items) == 2

    service.update_draft(
        draft.id,
        supplier.id,
        datetime.now(UTC),
        None,
        [PurchaseLineInput(product.id, Decimal("10"), Decimal("2.00"), Decimal("3.00"))],
    )
    assert len(service.get_detail(draft.id).items) == 1


def test_database_constraints_reject_invalid_purchase_values(
    session_factory: sessionmaker[Session],
) -> None:
    supplier, product, _service = _setup(session_factory)
    repository = PurchaseRepository(session_factory)
    from models import Purchase, PurchaseItem

    purchase = Purchase(
        id=uuid.uuid4(),
        purchase_number="PUR-CONSTRAINT",
        supplier_id=supplier.id,
        purchase_date=datetime.now(UTC),
        total=Decimal("0"),
        status=PurchaseStatus.DRAFT,
    )
    item = PurchaseItem(
        id=uuid.uuid4(),
        product_id=product.id,
        product_name=product.name,
        product_sku=product.sku,
        unit=product.unit.value,
        quantity=Decimal("0"),
        unit_cost=Decimal("1.00"),
        line_total=Decimal("0"),
        selling_price=Decimal("2.00"),
    )
    with pytest.raises(IntegrityError):
        repository.create_draft(purchase, [item])


def test_supplier_report_aggregates_purchase_quantity_payment_and_debt(
    session_factory: sessionmaker[Session],
) -> None:
    supplier, product, service = _setup(session_factory)
    purchase_date = datetime(2026, 9, 10, tzinfo=UTC)
    draft = service.create_draft(
        supplier.id,
        purchase_date,
        None,
        [
            PurchaseLineInput(
                product.id, Decimal("3"), Decimal("5.00"), Decimal("7.50")
            )
        ],
    )
    service.confirm(draft.id, Decimal("4.00"))

    rows = service.supplier_report(
        PurchaseFilters(
            from_datetime=datetime(2026, 9, 1, tzinfo=UTC),
            to_datetime=datetime(2026, 9, 11, tzinfo=UTC),
        )
    )

    assert len(rows) == 1
    assert rows[0].supplier_id == supplier.id
    assert rows[0].purchase_count == 1
    assert rows[0].purchased_quantity == Decimal("3.000")
    assert rows[0].purchase_amount == Decimal("15.00")
    assert rows[0].paid_amount == Decimal("4.00")
    assert rows[0].outstanding_debt == Decimal("11.00")
