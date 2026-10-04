import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.features.validation.gstin import state_label
from app.features.vendors.repository import VendorRow


class VendorRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    legal_name: str
    gstin: str


class VendorOut(BaseModel):
    id: uuid.UUID
    gstin: str
    legal_name: str
    display_name: str
    state_code: str
    state_name: str
    bill_count: int
    approved_spend: Decimal
    pending_amount: Decimal
    created_at: datetime

    @classmethod
    def from_row(cls, row: VendorRow) -> "VendorOut":
        v = row.vendor
        return cls(
            id=v.id,
            gstin=v.gstin,
            legal_name=v.legal_name,
            display_name=v.display_name,
            state_code=v.state_code,
            state_name=state_label(v.state_code).rsplit(",", 1)[0],
            bill_count=row.bill_count,
            approved_spend=row.approved_spend,
            pending_amount=row.pending_amount,
            created_at=v.created_at,
        )


class VendorUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=300)

    @field_validator("display_name")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Display name cannot be blank")
        return value
