from datetime import datetime
from typing import Optional

from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.auth import get_current_user
from app.core.database import applications_collection, jobs_collection, recommendation_items_collection

router = APIRouter(prefix="/applications", tags=["Applications"])


class ApplyRequest(BaseModel):
    job_id: str
    recommendation_item_id: Optional[str] = None


def _mark_recommendation_applied(user_id: str, recommendation_item_id: Optional[str], job_id: str) -> None:
    now = datetime.utcnow()

    if recommendation_item_id and ObjectId.is_valid(recommendation_item_id):
        recommendation_items_collection.update_one(
            {"_id": ObjectId(recommendation_item_id), "user_id": user_id},
            {"$set": {"decision": "applied", "decision_at": now, "updated_at": now}},
        )
        return

    # Fallback: mark the latest pending recommendation item for this user+job as applied.
    fallback_item = recommendation_items_collection.find_one(
        {"user_id": user_id, "job_id": job_id, "decision": "pending"},
        sort=[("created_at", -1)],
    )
    if fallback_item:
        recommendation_items_collection.update_one(
            {"_id": fallback_item["_id"]},
            {"$set": {"decision": "applied", "decision_at": now, "updated_at": now}},
        )


def _serialize_application(doc: dict, job: Optional[dict] = None) -> dict:
    out = {
        "_id": str(doc["_id"]),
        "job_id": doc["job_id"],
        "user_id": doc["user_id"],
        "status": doc.get("status", "pending"),
        "appliedAt": doc.get("applied_at") or doc.get("created_at"),
        "createdAt": doc.get("created_at"),
    }
    if job:
        out["job"] = {
            "id": str(job.get("_id")) if job.get("_id") else None,
            "title": job.get("title") or job.get("Job Title", ""),
            "company": job.get("company") or job.get("Company Name", ""),
            "location": job.get("location") or job.get("Location", ""),
            "type": job.get("type") or job.get("Job Type", ""),
            "experience_level": job.get("experience_level") or job.get("Experience Level", ""),
            "category": job.get("category") or job.get("Category", ""),
            "work_type": job.get("work_type") or job.get("Work Type", ""),
            "description": job.get("description") or job.get("Job Description", ""),
        }
    return out


@router.post("", status_code=status.HTTP_201_CREATED)
def apply_to_job(payload: ApplyRequest, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "job_seeker":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only job seeker accounts can apply to jobs."
        )

    if not ObjectId.is_valid(payload.job_id):
        raise HTTPException(status_code=400, detail="Invalid job id")

    job = jobs_collection.find_one({"_id": ObjectId(payload.job_id), "is_active": {"$ne": False}})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    doc = {
        "job_id": payload.job_id,
        "user_id": current_user["id"],
        "status": "pending",
        "recommendation_item_id": payload.recommendation_item_id,
        "created_at": datetime.utcnow(),
        "applied_at": datetime.utcnow(),
    }

    try:
        result = applications_collection.insert_one(doc)
    except DuplicateKeyError:
        _mark_recommendation_applied(current_user["id"], payload.recommendation_item_id, payload.job_id)
        raise HTTPException(status_code=409, detail="You have already applied to this job.")

    _mark_recommendation_applied(current_user["id"], payload.recommendation_item_id, payload.job_id)

    doc["_id"] = result.inserted_id
    return _serialize_application(doc, job=job)


@router.get("/my-applications")
def my_applications(current_user: dict = Depends(get_current_user)):
    rows = list(
        applications_collection.find({"user_id": current_user["id"]}).sort("created_at", -1)
    )

    if not rows:
        return []

    job_ids = [row["job_id"] for row in rows if ObjectId.is_valid(row["job_id"])]
    jobs_map = {
        str(job["_id"]): job
        for job in jobs_collection.find({"_id": {"$in": [ObjectId(i) for i in job_ids]}})
    }

    return [_serialize_application(row, job=jobs_map.get(row["job_id"])) for row in rows]
