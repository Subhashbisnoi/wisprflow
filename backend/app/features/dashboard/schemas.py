from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.features.invoices.models import InvoiceStatus


class KpiOut(BaseModel):
    total_this_month: Decimal
    bills_this_month: int
    pending_amount: Decimal
    needs_review_count: int
    approval_rate: float | None  # None when nothing was decided this month
    approved_this_month: int
    rejected_this_month: int
    failed_count: int
    processing_count: int


class MonthSpendOut(BaseModel):
    month: date
    approved: Decimal
    pending: Decimal


class VendorSpendOut(BaseModel):
    vendor_id: str
    display_name: str
    amount: Decimal
    bill_count: int


class StatusCountOut(BaseModel):
    status: InvoiceStatus
    count: int
    amount: Decimal


class DashboardSummaryOut(BaseModel):
    as_of: date
    kpis: KpiOut
    monthly_spend: list[MonthSpendOut]
    top_vendors: list[VendorSpendOut]
    status_breakdown: list[StatusCountOut]
    total_bills: int
