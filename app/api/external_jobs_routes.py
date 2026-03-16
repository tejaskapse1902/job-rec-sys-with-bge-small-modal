from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.auth import get_current_admin
from app.services.external_jobs import import_jobs_from_jsearch

router = APIRouter(prefix="/admin/jobs/import", tags=["External Jobs"])


class JSearchImportRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=120)
    page: int = Field(default=1, ge=1, le=100)
    num_pages: int = Field(default=1, ge=1, le=20)


@router.post("/jsearch")
def import_jsearch(payload: JSearchImportRequest, current_admin: dict = Depends(get_current_admin)):
    _ = current_admin
    return import_jobs_from_jsearch(payload.query.strip(), page=payload.page, num_pages=payload.num_pages)
