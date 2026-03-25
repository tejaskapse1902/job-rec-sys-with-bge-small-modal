from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.auth import get_current_admin
from app.services.external_jobs import import_external_jobs, search_external_jobs

router = APIRouter(prefix="/admin/jobs/import", tags=["External Jobs"])


class ExternalJobsRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=120)
    page: int = Field(default=1, ge=1, le=100)
    num_pages: int = Field(default=1, ge=1, le=20)


@router.post("/search")
def search_external(payload: ExternalJobsRequest, current_admin: dict = Depends(get_current_admin)):
    _ = current_admin
    try:
        return search_external_jobs(
            query=payload.query.strip(),
            page=payload.page,
            num_pages=payload.num_pages,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("")
def import_external(payload: ExternalJobsRequest, current_admin: dict = Depends(get_current_admin)):
    _ = current_admin
    try:
        return import_external_jobs(
            query=payload.query.strip(),
            page=payload.page,
            num_pages=payload.num_pages,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
