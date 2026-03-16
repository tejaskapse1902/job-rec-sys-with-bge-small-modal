import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserCreate, UserLogin, UserResponse, Token
from app.core.auth import (
    verify_password,
    create_access_token,
    get_current_user,
    get_password_hash,
)
from app.core.user_db import users_collection
from app.services.email_service import send_reset_otp_email

router = APIRouter(prefix="/auth", tags=["Authentication"])
RESET_OTP_EXPIRE_MINUTES = int(os.getenv("RESET_OTP_EXPIRE_MINUTES", "10"))


def _normalize_role(role: str | None) -> str:
    if role == "admin":
        return "admin"
    if role == "employer":
        return "employer"
    return "job_seeker"


def _is_active_from_status(status: str | None) -> bool:
    return status == "active"


def _is_strong_password(password: str) -> bool:
    if len(password) < 6:
        return False
    return bool(re.search(r"[a-z]", password) and re.search(r"[A-Z]", password) and re.search(r"\d", password))


def _to_utc_iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"


def _build_user_response(user: dict) -> UserResponse:
    status_value = user.get("status", "active")
    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        full_name=user["full_name"],
        role=_normalize_role(user.get("role")),
        status=status_value,
        is_active=bool(user.get("is_active", _is_active_from_status(status_value))),
        company_name=user.get("company_name"),
        created_at=user["created_at"],
    )


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=6, max_length=128)


@router.post("/signup", response_model=Token, status_code=status.HTTP_201_CREATED)
async def signup(user_data: UserCreate):
    """Register a new user"""
    normalized_role = _normalize_role(user_data.role)

    if normalized_role == "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin signup is disabled. Contact system administrator."
        )

    # Check if user already exists
    existing_user = users_collection.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    if normalized_role == "employer" and not user_data.company_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company name is required for employer signup."
        )

    role_status = "pending" if normalized_role == "employer" else "active"

    # Create user document
    user_doc = {
        "email": user_data.email,
        "full_name": user_data.full_name,
        "role": normalized_role,
        "status": role_status,
        "is_active": role_status == "active",
        "company_name": user_data.company_name,
        "password": get_password_hash(user_data.password),
        "created_at": datetime.utcnow(),
    }

    # Insert into database
    result = users_collection.insert_one(user_doc)

    # Create access token
    access_token = create_access_token(
        data={"sub": user_data.email, "role": normalized_role}
    )

    user_doc["_id"] = result.inserted_id
    user_response = _build_user_response(user_doc)

    return Token(access_token=access_token, user=user_response)


@router.post("/login", response_model=Token)
async def login(credentials: UserLogin):
    """Login user and return JWT token"""
    # Find user by email
    user = users_collection.find_one({"email": credentials.email})

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    # Verify password
    if not verify_password(credentials.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    normalized_role = _normalize_role(user.get("role"))
    normalized_status = user.get("status", "active")
    normalized_is_active = bool(user.get("is_active", _is_active_from_status(normalized_status)))

    updates = {}

    # Upgrade legacy plaintext passwords to bcrypt after successful login.
    if not str(user["password"]).startswith("$2"):
        updates["password"] = get_password_hash(credentials.password)

    if user.get("role") != normalized_role:
        updates["role"] = normalized_role
        user["role"] = normalized_role

    if user.get("status") != normalized_status:
        updates["status"] = normalized_status
        user["status"] = normalized_status

    if user.get("is_active") != normalized_is_active:
        updates["is_active"] = normalized_is_active
        user["is_active"] = normalized_is_active

    if updates:
        users_collection.update_one({"_id": user["_id"]}, {"$set": updates})

    # Create access token
    access_token = create_access_token(
        data={"sub": user["email"], "role": normalized_role}
    )

    user_response = _build_user_response(user)

    return Token(access_token=access_token, user=user_response)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user information"""
    user = users_collection.find_one({"email": current_user["email"]})

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return _build_user_response(user)


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest):
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=RESET_OTP_EXPIRE_MINUTES)

    user = users_collection.find_one({"email": payload.email})

    response = {
        "message": "If the email exists, OTP has been sent to email.",
        "otp_expires_in_seconds": RESET_OTP_EXPIRE_MINUTES * 60,
        "otp_expires_at": _to_utc_iso(expires_at),
        "server_time": _to_utc_iso(now),
    }
    if not user:
        return response

    otp = f"{secrets.randbelow(1000000):06d}"
    otp_hash = hashlib.sha256(otp.encode("utf-8")).hexdigest()

    users_collection.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "reset_password": {
                    "otp_hash": otp_hash,
                    "requested_at": now,
                    "expires_at": expires_at,
                    "attempts": 0,
                },
                "updated_at": now,
            }
        },
    )

    try:
        send_reset_otp_email(user["email"], otp, RESET_OTP_EXPIRE_MINUTES)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP email. Please try again later."
        )

    return response


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest):
    if not _is_strong_password(payload.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one uppercase letter, one lowercase letter, and one number."
        )

    user = users_collection.find_one({"email": payload.email})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email or OTP."
        )

    reset_meta = user.get("reset_password") or {}
    expires_at = reset_meta.get("expires_at")
    if not reset_meta.get("otp_hash"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP not requested. Please request OTP first."
        )
    now = datetime.utcnow()
    if not expires_at or expires_at < now:
        users_collection.update_one(
            {"_id": user["_id"]},
            {"$unset": {"reset_password": ""}, "$set": {"updated_at": now}},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Please request a new OTP."
        )

    submitted_otp_hash = hashlib.sha256(payload.otp.strip().encode("utf-8")).hexdigest()
    if submitted_otp_hash != reset_meta.get("otp_hash"):
        attempts = int(reset_meta.get("attempts", 0)) + 1
        users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"reset_password.attempts": attempts, "updated_at": now}},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP."
        )

    now = datetime.utcnow()
    users_collection.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "password": get_password_hash(payload.new_password),
                "updated_at": now,
            },
            "$unset": {"reset_password": ""},
        },
    )

    return {"status": "password_reset"}
