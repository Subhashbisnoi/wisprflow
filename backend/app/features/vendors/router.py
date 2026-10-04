import uuid

from fastapi import APIRouter, Depends, Query

from app.core.pagination import PageOut, PageParams, page_params
from app.features.vendors.dependencies import get_vendor_service
from app.features.vendors.schemas import VendorOut, VendorUpdateRequest
from app.features.vendors.service import VendorService

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.get("", response_model=PageOut[VendorOut])
def list_vendors(
    search: str | None = Query(None, max_length=100),
    page: PageParams = Depends(page_params),
    service: VendorService = Depends(get_vendor_service),
) -> PageOut[VendorOut]:
    return PageOut[VendorOut].from_page(service.list_vendors(search, page).map(VendorOut.from_row))


@router.get("/{vendor_id}", response_model=VendorOut)
def get_vendor(
    vendor_id: uuid.UUID, service: VendorService = Depends(get_vendor_service)
) -> VendorOut:
    return VendorOut.from_row(service.get(vendor_id))


@router.patch("/{vendor_id}", response_model=VendorOut)
def update_vendor(
    vendor_id: uuid.UUID,
    body: VendorUpdateRequest,
    service: VendorService = Depends(get_vendor_service),
) -> VendorOut:
    return VendorOut.from_row(service.update(vendor_id, body))
