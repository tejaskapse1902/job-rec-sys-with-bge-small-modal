from pydantic import BaseModel, EmailStr
from typing import Literal, Optional
from datetime import datetime


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: Literal["job_seeker", "employer", "admin", "user"] = "job_seeker"


class UserCreate(UserBase):
    password: str
    company_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(UserBase):
    id: str
    status: Literal["pending", "active", "rejected"] = "active"
    is_active: bool = True
    company_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
