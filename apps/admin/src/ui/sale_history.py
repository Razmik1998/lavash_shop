"""Shared readable labels and rows for sale revision history."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from schemas import SaleRevisionRow
from schemas import SaleAuditHistoryRow
from ui.style import format_currency, format_quantity


def sale_timeline_rows(
    revisions: list[SaleRevisionRow],
    audit_events: list[SaleAuditHistoryRow] | None = None,
) -> list[tuple[datetime, str, str, str]]:
    rows: list[tuple[datetime, str, str, str]] = []
    for revision in revisions:
        closer = revision.user_full_name or "Անհայտ օգտատեր"
        if revision.outcome == "created":
            amount = (
                format_currency(revision.closed_total)
                if revision.closed_total is not None
                else "—"
            )
            rows.append(
                (
                    revision.opened_at,
                    "Վաճառքը ստեղծվել է",
                    f"Գումար՝ {amount}",
                    closer,
                )
            )
            continue
        rows.append(
            (
                revision.opened_at,
                "Փաստաթուղթը բացվել է խմբագրման",
                f"Խմբագրման փուլ՝ {revision.revision_number}",
                revision.opened_by_user_full_name or closer,
            )
        )
        if revision.closed_at is not None:
            amount = (
                format_currency(revision.closed_total)
                if revision.closed_total is not None
                else "—"
            )
            rows.append(
                (
                    revision.closed_at,
                    revision_outcome_label(revision.outcome),
                    f"Գումար՝ {amount}",
                    closer,
                )
            )
    for event in audit_events or []:
        if event.event_type == "created":
            details = f"Գումար՝ {format_currency(Decimal(str((event.new_value or {}).get('total', '0'))))}; {_payment_text(event.new_value)}"
            label = "Վաճառքը ստեղծվել է"
        else:
            old = _payment_text(event.old_value)
            new = _payment_text(event.new_value)
            details = f"{old} → {new}"
            label = "Վճարման ձևը կամ պարտապանը փոխվել է"
        rows.append(
            (
                event.created_at,
                label,
                details,
                event.user_full_name or "Անհայտ օգտատեր",
            )
        )
    return sorted(rows)


def _payment_text(value: dict[str, object] | None) -> str:
    if not value or value.get("payment") != "credit":
        return "Կանխիկ"
    customer = value.get("customer")
    return f"Պարտքով՝ {customer}" if customer else "Պարտքով"


def revision_outcome_label(outcome: str | None) -> str:
    return {
        "created": "Ստեղծվել է",
        "unlocked": "Բացվել է խմբագրման",
        "completed": "Փոփոխությունները պահպանվել են",
        "completed_unchanged": "Պահպանվել է առանց փոփոխության",
        "cancelled": "Վաճառքը չեղարկվել է",
    }.get(outcome or "", "Փակվել է")


def item_action_label(action: str) -> str:
    return {
        "added": "Ավելացվել է",
        "edited": "Փոփոխվել է",
        "deleted": "Ջնջվել է",
        "discount_added": "Զեղչ ավելացվել է",
        "discount_removed": "Զեղչը հանվել է",
        "discount_changed": "Զեղչը փոխվել է",
    }.get(action, action)


def item_data_text(data: dict[str, object] | None) -> str:
    if not data:
        return "-"
    try:
        quantity = Decimal(str(data.get("quantity", "0")))
        unit_price = Decimal(str(data.get("unit_price", "0")))
        line_total = Decimal(str(data.get("line_total", "0")))
    except (ArithmeticError, TypeError, ValueError):
        return str(data)
    return (
        f"{format_quantity(quantity)} × {format_currency(unit_price)} = "
        f"{format_currency(line_total)}"
    )
