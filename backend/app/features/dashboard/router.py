from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.container import Container, get_container
from app.core.database import get_db
from app.core.tenant import TenantContext
from app.features.auth.dependencies import get_tenant
from app.features.dashboard.repository import DashboardRepository
from app.features.dashboard.schemas import DashboardSummaryOut
from app.features.dashboard.service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def get_dashboard_service(
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    container: Container = Depends(get_container),
) -> DashboardService:
    return DashboardService(DashboardRepository(db, tenant), container.settings.business_timezone)


@router.get("/summary", response_model=DashboardSummaryOut)
def summary(service: DashboardService = Depends(get_dashboard_service)) -> DashboardSummaryOut:
    return service.summary()
