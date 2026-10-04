from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.features.dashboard.repository import DashboardRepository
from app.features.dashboard.schemas import (
    DashboardSummaryOut,
    KpiOut,
    MonthSpendOut,
    StatusCountOut,
    VendorSpendOut,
)
from app.features.invoices.models import InvoiceStatus

SPEND_MONTHS = 6


def _add_months(day: date, months: int) -> date:
    month_index = day.year * 12 + (day.month - 1) + months
    return date(month_index // 12, month_index % 12 + 1, 1)


class DashboardService:
    def __init__(self, repository: DashboardRepository, timezone: str = "Asia/Kolkata") -> None:
        self._repo = repository
        self._tz = ZoneInfo(timezone)

    def summary(self, today: date | None = None) -> DashboardSummaryOut:
        today = today or datetime.now(self._tz).date()
        month_start = today.replace(day=1)
        next_month = _add_months(month_start, 1)
        spend_since = _add_months(month_start, -(SPEND_MONTHS - 1))

        total, bills = self._repo.total_between(month_start, next_month)
        statuses = self._repo.status_summary()
        approved, rejected = self._repo.decisions_between(
            datetime.combine(month_start, time.min, self._tz),
            datetime.combine(next_month, time.min, self._tz),
        )
        decided = approved + rejected

        def count(status: InvoiceStatus) -> int:
            return statuses.get(status, (0, Decimal(0)))[0]

        kpis = KpiOut(
            total_this_month=total,
            bills_this_month=bills,
            pending_amount=statuses.get(InvoiceStatus.NEEDS_REVIEW, (0, Decimal(0)))[1],
            needs_review_count=count(InvoiceStatus.NEEDS_REVIEW),
            approval_rate=round(approved / decided, 4) if decided else None,
            approved_this_month=approved,
            rejected_this_month=rejected,
            failed_count=count(InvoiceStatus.FAILED),
            processing_count=count(InvoiceStatus.QUEUED) + count(InvoiceStatus.PROCESSING),
        )

        # Fill empty months so the chart always shows a continuous axis.
        by_month = {m.month: m for m in self._repo.monthly_spend(spend_since)}
        monthly = []
        for offset in range(SPEND_MONTHS):
            month = _add_months(spend_since, offset)
            found = by_month.get(month)
            monthly.append(
                MonthSpendOut(
                    month=month,
                    approved=found.approved if found else Decimal("0"),
                    pending=found.pending if found else Decimal("0"),
                )
            )

        return DashboardSummaryOut(
            as_of=today,
            kpis=kpis,
            monthly_spend=monthly,
            top_vendors=[VendorSpendOut(**v.__dict__) for v in self._repo.top_vendors(spend_since)],
            status_breakdown=[
                StatusCountOut(status=s, count=c, amount=a)
                for s, (c, a) in sorted(statuses.items(), key=lambda kv: kv[0].value)
            ],
            total_bills=sum(c for c, _ in statuses.values()),
        )
