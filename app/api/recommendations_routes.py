from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import get_current_user
from app.core.database import recommendation_items_collection, recommendation_sessions_collection

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])


class NotApplyReasonRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
    note: Optional[str] = Field(default=None, max_length=1000)


@router.get("/latest")
def get_latest_recommendations(current_user: dict = Depends(get_current_user)):
    session = recommendation_sessions_collection.find_one(
        {"user_id": current_user["id"]},
        sort=[("created_at", -1)]
    )
    if not session:
        return {"session": None, "items": []}

    items = list(
        recommendation_items_collection.find({"session_id": str(session["_id"])}).sort("rank", 1)
    )
    for item in items:
        item["id"] = str(item.pop("_id"))

    return {
        "session": {
            "id": str(session["_id"]),
            "filename": session.get("filename"),
            "recommendation_count": session.get("recommendation_count", 0),
            "created_at": session.get("created_at"),
        },
        "items": items,
    }


@router.post("/{item_id}/not-apply-reason")
def add_not_apply_reason(
    item_id: str,
    payload: NotApplyReasonRequest,
    current_user: dict = Depends(get_current_user),
):
    if not ObjectId.is_valid(item_id):
        raise HTTPException(status_code=400, detail="Invalid recommendation item id.")

    result = recommendation_items_collection.update_one(
        {"_id": ObjectId(item_id), "user_id": current_user["id"]},
        {
            "$set": {
                "decision": "not_applied",
                "decision_reason": payload.reason.strip(),
                "decision_note": (payload.note or "").strip(),
                "decision_at": datetime.utcnow(),
            }
        },
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Recommendation item not found.")

    return {"status": "saved"}
