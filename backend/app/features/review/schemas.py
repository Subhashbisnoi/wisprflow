from typing import Literal

from pydantic import BaseModel, Field, field_validator

HeaderField = Literal[
    "vendor_name",
    "vendor_gstin",
    "buyer_gstin",
    "invoice_number",
    "invoice_date",
    "due_date",
    "subtotal",
    "cgst",
    "sgst",
    "igst",
    "total",
]
LineField = Literal["description", "hsn_sac", "quantity", "rate", "amount"]


class FieldChange(BaseModel):
    field: HeaderField
    value: str | None = Field(default=None, max_length=300)


class LineFieldChange(BaseModel):
    field: LineField
    value: str | None = Field(default=None, max_length=1000)


class VersionedRequest(BaseModel):
    version: int = Field(ge=1, description="The bill version the client last saw (D-047)")


class FieldCorrectionRequest(VersionedRequest):
    changes: list[FieldChange] = Field(min_length=1, max_length=20)


class LineItemCorrectionRequest(VersionedRequest):
    changes: list[LineFieldChange] = Field(min_length=1, max_length=10)


class LineItemCreateRequest(VersionedRequest):
    description: str | None = Field(default=None, max_length=1000)
    hsn_sac: str | None = Field(default=None, max_length=20)
    quantity: str | None = Field(default=None, max_length=30)
    rate: str | None = Field(default=None, max_length=30)
    amount: str | None = Field(default=None, max_length=30)


class ApproveRequest(VersionedRequest):
    comment: str | None = Field(default=None, max_length=1000)


class RejectRequest(VersionedRequest):
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Give a reason of at least 3 characters")
        return value
