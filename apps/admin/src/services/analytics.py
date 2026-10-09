"""Sales analytics assembled from immutable sale item snapshots."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from repositories.sale import SaleRepository


class AnalyticsService:
    def __init__(self, sale_repository: SaleRepository, timezone: str = "UTC") -> None:
        self._sales = sale_repository
        self._timezone = ZoneInfo(timezone)

    def report(
        self, period: str = "daily", *, today: date | None = None
    ) -> dict[str, Any]:
        if period not in {"daily", "weekly", "monthly"}:
            raise ValueError("period must be daily, weekly, or monthly")
        local_today = today or datetime.now(self._timezone).date()
        days = {"daily": 1, "weekly": 7, "monthly": 30}[period]
        start_date = local_today - timedelta(days=days - 1)
        start = datetime.combine(start_date, time.min, self._timezone).astimezone(UTC)
        end = datetime.combine(
            local_today + timedelta(days=1), time.min, self._timezone
        ).astimezone(UTC)
        previous_start = start - (end - start)
        rows = self._sales.analytics_rows(start, end)
        previous_rows = self._sales.analytics_rows(previous_start, start)

        revenue = Decimal("0")
        profit = Decimal("0")
        known_cost_revenue = Decimal("0")
        sales: dict[object, Decimal] = {}
        products: dict[str, dict[str, Any]] = {}
        product_sales: dict[str, set[object]] = defaultdict(set)
        product_hour_sales: dict[str, dict[int, set[object]]] = defaultdict(
            lambda: defaultdict(set)
        )
        daily: dict[date, Decimal] = defaultdict(Decimal)
        hourly: dict[int, Decimal] = defaultdict(Decimal)
        hourly_sales: dict[int, set[object]] = defaultdict(set)
        weekdays: dict[int, Decimal] = defaultdict(Decimal)
        for row in rows:
            (
                sale_id,
                created_at,
                _sale_total,
                name,
                sku,
                unit,
                quantity,
                line_total,
                cost,
            ) = row
            local_at = created_at.astimezone(self._timezone)
            line_revenue = Decimal(line_total or 0)
            units = Decimal(quantity or 0)
            revenue += line_revenue
            sales[sale_id] = sales.get(sale_id, Decimal("0")) + line_revenue
            daily[local_at.date()] += line_revenue
            hourly_sales[local_at.hour].add(sale_id)
            weekdays[local_at.weekday()] += line_revenue
            key = str(sku)
            product = products.setdefault(
                key,
                {
                    "name": str(name),
                    "unit": str(unit),
                    "quantity": Decimal("0"),
                    "revenue": Decimal("0"),
                    "profit": Decimal("0"),
                    "cost_known": Decimal("0"),
                    "orders": Decimal("0"),
                },
            )
            product_hour_sales[key][local_at.hour].add(sale_id)
            product["quantity"] = Decimal(product["quantity"]) + units
            product["revenue"] = Decimal(product["revenue"]) + line_revenue
            if sale_id not in product_sales[key]:
                product["orders"] = Decimal(product["orders"]) + 1
                product_sales[key].add(sale_id)
            if cost is not None:
                line_profit = line_revenue - Decimal(cost) * units
                product["profit"] = Decimal(product["profit"]) + line_profit
                product["cost_known"] = Decimal(product["cost_known"]) + line_revenue
                profit += line_profit
                known_cost_revenue += line_revenue

        previous_revenue = sum(
            (Decimal(row[6] or 0) for row in previous_rows), Decimal("0")
        )
        for product_sku, product in products.items():
            hours = product_hour_sales[product_sku]
            product["peak_hour"] = (
                max(hours, key=lambda hour: len(hours[hour])) if hours else None
            )
        hourly = {hour: Decimal(len(hourly_sales[hour])) for hour in range(24)}
        top_products = sorted(
            products.values(), key=lambda item: Decimal(item["orders"]), reverse=True
        )[:8]
        revenue_products = sorted(
            products.values(), key=lambda item: Decimal(item["revenue"]), reverse=True
        )[:8]
        profit_products = sorted(
            (item for item in products.values() if Decimal(item["cost_known"]) > 0),
            key=lambda item: Decimal(item["profit"]),
            reverse=True,
        )[:8]
        peak_hour = max(hourly, key=lambda hour: hourly[hour]) if hourly else None
        peak_weekday = (
            max(weekdays, key=lambda weekday: weekdays[weekday]) if weekdays else None
        )
        return {
            "period": period,
            "start_date": start_date,
            "end_date": local_today,
            "revenue": revenue,
            "orders": len(sales),
            "average_order": revenue / len(sales) if sales else Decimal("0"),
            "estimated_profit": profit,
            "cost_coverage": known_cost_revenue,
            "previous_revenue": previous_revenue,
            "revenue_change": ((revenue - previous_revenue) / previous_revenue * 100)
            if previous_revenue
            else None,
            "daily": [
                (start_date + timedelta(days=i), daily[start_date + timedelta(days=i)])
                for i in range(days)
            ],
            "hourly": [(hour, hourly[hour]) for hour in range(24)],
            "weekdays": [(weekday, weekdays[weekday]) for weekday in range(7)],
            "peak_hour": peak_hour,
            "peak_weekday": peak_weekday,
            "top_products": top_products,
            "revenue_products": revenue_products,
            "profit_products": profit_products,
        }
