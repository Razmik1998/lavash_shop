"""Financial definitions and zero-filled comparison periods."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Protocol
from zoneinfo import ZoneInfo


class ReportsData(Protocol):
    def daily(
        self, start: datetime, end: datetime, timezone: str
    ) -> list[dict[str, Any]]: ...
    def balances(self) -> dict[str, Decimal]: ...


METRICS = (
    "revenue",
    "credit",
    "orders",
    "cost",
    "missing_cost",
    "free_sales",
    "repayments",
    "payments",
    "purchases",
    "waste",
)


class ReportsService:
    def __init__(self, repository: ReportsData, timezone: str = "Asia/Yerevan") -> None:
        self._repository = repository
        self._timezone = ZoneInfo(timezone)

    def today(self) -> date:
        return datetime.now(self._timezone).date()

    def report(self, start: date, end: date) -> dict[str, Any]:
        if start > end:
            raise ValueError("Սկզբի ամսաթիվը պետք է նախորդի ավարտին։")
        if end > self.today():
            raise ValueError("Ապագա օրերի համար փաստացի տվյալներ չկան։")
        days = (end - start).days + 1
        if days > 366:
            raise ValueError("Ընտրեք առավելագույնը 366 օր։")
        previous_start = start - timedelta(days=days)
        rows = self._repository.daily(
            datetime.combine(previous_start, time.min, self._timezone).astimezone(UTC),
            datetime.combine(
                end + timedelta(days=1), time.min, self._timezone
            ).astimezone(UTC),
            str(self._timezone),
        )
        daily = {}
        for offset in range(days * 2):
            day = previous_start + timedelta(days=offset)
            daily[day] = {key: Decimal(0) for key in METRICS}
        for row in rows:
            if row["day"] in daily:
                daily[row["day"]][row["metric"]] = Decimal(row["amount"] or 0)
        for values in daily.values():
            values["received"] = (
                values["revenue"] - values["credit"] + values["repayments"]
            )
            values["cash_flow"] = values["received"] - values["payments"]
            values["profit"] = values["revenue"] - values["cost"] - values["waste"]

        def summary(first: date, last: date) -> dict[str, Any]:
            totals: dict[str, Any] = {
                key: sum(
                    (v[key] for d, v in daily.items() if first <= d <= last), Decimal(0)
                )
                for key in next(iter(daily.values()))
            }
            totals["average_order"] = (
                totals["revenue"] / totals["orders"] if totals["orders"] else Decimal(0)
            )
            if totals["missing_cost"]:
                totals["profit"] = None
            return totals

        return {
            "start": start,
            "end": end,
            "current": summary(start, end),
            "previous": summary(previous_start, start - timedelta(days=1)),
            "daily": [(d, v) for d, v in daily.items() if d >= start],
            "previous_daily": [(d, v) for d, v in daily.items() if d < start],
            "balances": self._repository.balances(),
        }

    @staticmethod
    def chart(
        report: dict[str, Any], key: str, monthly: bool
    ) -> tuple[list[str], list[tuple[str, list[float]]]]:
        current = report["daily"]
        previous = report["previous_daily"]
        if key == "profit" and any(v["missing_cost"] for _, v in current + previous):
            return [], []
        buckets: dict[str, tuple[Decimal, Decimal]] = {}
        for (day, value), (old_day, old_value) in zip(current, previous, strict=True):
            label = day.strftime("%m.%Y" if monthly else "%d.%m")
            if not monthly:
                label += " / " + old_day.strftime("%d.%m")
            total, old_total = buckets.get(label, (Decimal(0), Decimal(0)))
            buckets[label] = (total + value[key], old_total + old_value[key])
        return list(buckets), [
            ("Ընտրված ժամանակահատված", [float(v[0]) for v in buckets.values()]),
            ("Նախորդ նույն տևողությունը", [float(v[1]) for v in buckets.values()]),
        ]
