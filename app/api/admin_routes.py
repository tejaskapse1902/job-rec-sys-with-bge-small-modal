from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import get_current_admin
from app.core.user_db import users_collection
from app.models.user import UserResponse

router = APIRouter(prefix="/admin", tags=["Admin"])


def _normalize_role(role: str | None) -> str:
    if role == "admin":
        return "admin"
    if role == "employer":
        return "employer"
    return "job_seeker"


def _to_user_response(user: dict) -> UserResponse:
    status_value = user.get("status", "active")
    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        full_name=user["full_name"],
        role=_normalize_role(user.get("role")),
        status=status_value,
        is_active=bool(user.get("is_active", status_value == "active")),
        company_name=user.get("company_name"),
        created_at=user["created_at"],
    )


def _get_user_by_id(user_id: str) -> dict:
    if not ObjectId.is_valid(user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user id."
        )

    user = users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )
    return user


@router.get("/employers/pending", response_model=list[UserResponse])
async def list_pending_employers(current_admin: dict = Depends(get_current_admin)):
    _ = current_admin
    users = users_collection.find({"role": "employer", "status": "pending"}).sort("created_at", -1)
    return [_to_user_response(user) for user in users]


@router.patch("/employers/{user_id}/approve", response_model=UserResponse)
async def approve_employer(user_id: str, current_admin: dict = Depends(get_current_admin)):
    _ = current_admin
    user = _get_user_by_id(user_id)

    if user.get("role") != "employer":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only employer accounts can be approved."
        )

    users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"status": "active", "is_active": True}}
    )
    user["status"] = "active"
    user["is_active"] = True
    return _to_user_response(user)


@router.patch("/employers/{user_id}/reject", response_model=UserResponse)
async def reject_employer(user_id: str, current_admin: dict = Depends(get_current_admin)):
    _ = current_admin
    user = _get_user_by_id(user_id)

    if user.get("role") != "employer":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only employer accounts can be rejected."
        )

    users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"status": "rejected", "is_active": False}}
    )
    user["status"] = "rejected"
    user["is_active"] = False
    return _to_user_response(user)
