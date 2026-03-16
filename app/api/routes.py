from datetime import datetime
import os
import tempfile

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel

from app.core.auth import get_current_admin, get_current_user
from app.core.database import (
    recommendation_items_collection,
    recommendation_sessions_collection,
    users_collection,
)
from app.services.drive_service import delete_resume, list_resumes, upload_to_drive
from app.services.index_builder import incremental_index_new_jobs
from app.services.index_manager import reload_index_and_jobs
from app.services.recommender import recommend_jobs
from app.services.resume_parser import parse_resume_file

router = APIRouter()


class DeleteRequest(BaseModel):
    key: str


@router.post("/recommend")
async def recommend(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    suffix = os.path.splitext(file.filename)[1]

    data = await file.read()
    await file.close()

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    resume_text = parse_resume_file(tmp_path)
    drive_file_id = upload_to_drive(tmp_path, file.filename, delete_after=True)

    users_collection.update_one(
        {"email": current_user["email"]},
        {
            "$set": {
                "resume": {
                    "drive_file_id": drive_file_id,
                    "filename": file.filename,
                    "uploaded_at": datetime.utcnow(),
                },
                "updated_at": datetime.utcnow(),
            }
        },
    )

    results = recommend_jobs(resume_text)
    if isinstance(results, dict) and results.get("error"):
        return results

    session_doc = {
        "user_id": current_user["id"],
        "email": current_user["email"],
        "filename": file.filename,
        "resume_drive_file_id": drive_file_id,
        "recommendation_count": len(results),
        "created_at": datetime.utcnow(),
    }
    session_result = recommendation_sessions_collection.insert_one(session_doc)
    session_id = str(session_result.inserted_id)

    enriched_results = []
    for rank, rec in enumerate(results, start=1):
        item_doc = {
            "session_id": session_id,
            "user_id": current_user["id"],
            "job_id": rec.get("job_id"),
            "rank": rank,
            "match_percentage": rec.get("match_percentage"),
            "decision": "pending",
            "snapshot": rec,
            "created_at": datetime.utcnow(),
        }
        item_result = recommendation_items_collection.insert_one(item_doc)

        rec_copy = dict(rec)
        rec_copy["recommendation_item_id"] = str(item_result.inserted_id)
        enriched_results.append(rec_copy)

    return {
        "session_id": session_id,
        "resume_drive_file_id": drive_file_id,
        "filename": file.filename,
        "no. of recommendations": len(enriched_results),
        "recommendations": enriched_results,
    }


@router.get("/resumes")
def get_all_resumes(current_user: dict = Depends(get_current_user)):
    _ = current_user
    return list_resumes()


@router.delete("/resumes")
def delete_resume_api(req: DeleteRequest, current_user: dict = Depends(get_current_user)):
    _ = current_user
    delete_resume(req.key)
    return {"status": "deleted"}


@router.post("/admin/reload-index")
def reload_index(current_admin: dict = Depends(get_current_admin)):
    _ = current_admin
    index_result = incremental_index_new_jobs()
    reload_index_and_jobs()
    return {
        "status": "reloaded",
        "indexed_count": index_result["indexed_count"],
        "index_status": index_result["status"],
    }
