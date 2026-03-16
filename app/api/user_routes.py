from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_user
from app.core.user_db import users_collection

router = APIRouter(prefix="/users", tags=["Users"])


class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    company_name: Optional[str] = None


def _normalize_role(role: str | None) -> str:
    if role == "admin":
        return "admin"
    if role == "employer":
        return "employer"
    return "job_seeker"


def _serialize_user(user: dict) -> dict:
    status_value = user.get("status", "active")
    return {
        "id": str(user["_id"]),
        "email": user.get("email"),
        "full_name": user.get("full_name"),
        "role": _normalize_role(user.get("role")),
        "status": status_value,
        "is_active": bool(user.get("is_active", status_value == "active")),
        "company_name": user.get("company_name"),
        "created_at": user.get("created_at"),
        "updated_at": user.get("updated_at"),
        "resume": user.get("resume"),
    }


@router.get("/profile")
def get_profile(current_user: dict = Depends(get_current_user)):
    user = users_collection.find_one({"email": current_user["email"]}, {"password": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return _serialize_user(user)


@router.patch("/profile")
def update_profile(payload: UserProfileUpdate, current_user: dict = Depends(get_current_user)):
    updates = {}

    if payload.full_name is not None:
        full_name = payload.full_name.strip()
        if not full_name:
            raise HTTPException(status_code=400, detail="Full name cannot be empty.")
        updates["full_name"] = full_name
    if payload.company_name is not None:
        company_name = payload.company_name.strip()
        if current_user.get("role") == "employer" and not company_name:
            raise HTTPException(status_code=400, detail="Company name cannot be empty for employer.")
        updates["company_name"] = company_name

    if not updates:
        return {"status": "no_changes"}

    updates["updated_at"] = datetime.utcnow()
    users_collection.update_one({"email": current_user["email"]}, {"$set": updates})

    user = users_collection.find_one({"email": current_user["email"]}, {"password": 0})
    return _serialize_user(user)
