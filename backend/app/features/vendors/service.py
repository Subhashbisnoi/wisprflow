import uuid

from sqlalchemy.orm import Session

from app.core.pagination import Page, PageParams
from app.features.audit.models import AuditAction
from app.features.audit.service import AuditService
from app.features.vendors.repository import VendorRepository, VendorRow
from app.features.vendors.schemas import VendorUpdateRequest


class VendorService:
    def __init__(self, session: Session, vendors: VendorRepository, audit: AuditService) -> None:
        self._session = session
        self._vendors = vendors
        self._audit = audit

    def list_vendors(self, search: str | None, params: PageParams) -> Page[VendorRow]:
        return self._vendors.list_with_stats(search, params)

    def get(self, vendor_id: uuid.UUID) -> VendorRow:
        return self._vendors.stats_for(vendor_id)

    def update(self, vendor_id: uuid.UUID, cmd: VendorUpdateRequest) -> VendorRow:
        vendor = self._vendors.get_or_raise(vendor_id)
        if vendor.display_name != cmd.display_name:
            self._audit.record(
                AuditAction.VENDOR_UPDATED,
                entity_type="vendor",
                entity_id=vendor.id,
                field_name="display_name",
                old_value=vendor.display_name,
                new_value=cmd.display_name,
            )
            vendor.display_name = cmd.display_name
            self._session.commit()
        return self._vendors.stats_for(vendor_id)
