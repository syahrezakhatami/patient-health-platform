from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.clinical import router as clinical_router
from app.api.v1.clinical_read import router as clinical_read_router
from app.api.v1.governance import router as governance_router
from app.api.v1.health import router as health_router
from app.api.v1.iam import router as iam_router
from app.api.v1.manual_vitals import router as manual_vitals_router
from app.api.v1.mpi import router as mpi_router
from app.api.v1.organizations import router as organization_router
from app.api.v1.patient import router as patient_router
from app.api.v1.platform_governance import router as platform_governance_router

api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(iam_router)
api_v1_router.include_router(organization_router)
api_v1_router.include_router(governance_router)
api_v1_router.include_router(platform_governance_router)
api_v1_router.include_router(manual_vitals_router)
api_v1_router.include_router(mpi_router)
api_v1_router.include_router(clinical_router)
api_v1_router.include_router(clinical_read_router)
api_v1_router.include_router(patient_router)
