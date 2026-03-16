from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PostedBy(BaseModel):
    user_id: str
    email: str
    role: str
    company_name: Optional[str] = None


class JobBase(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    company: str = Field(..., min_length=2, max_length=200)
    location: str = Field(..., min_length=2, max_length=200)
    type: str = Field(default="Full-time", max_length=100)
    experience_level: Optional[str] = None
    description: str = Field(..., min_length=10)
    requirements: Optional[str] = ""
    responsibilities: Optional[str] = ""
    skills: list[str] = Field(default_factory=list)
    salary_min: Optional[str] = None
    salary_max: Optional[str] = None
    min_education: Optional[str] = None
    category: Optional[str] = None
    openings: Optional[str] = None
    notice_period: Optional[str] = None
    year_of_passing: Optional[str] = None
    work_type: Optional[str] = None
    interview_type: Optional[str] = None
    company_website: Optional[str] = None
    company_description: Optional[str] = None
    source: str = "manual"
    external_id: Optional[str] = None
    job_link: Optional[str] = None


class JobCreate(JobBase):
    pass


class JobUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=200)
    company: Optional[str] = Field(default=None, min_length=2, max_length=200)
    location: Optional[str] = Field(default=None, min_length=2, max_length=200)
    type: Optional[str] = Field(default=None, max_length=100)
    experience_level: Optional[str] = None
    description: Optional[str] = Field(default=None, min_length=10)
    requirements: Optional[str] = None
    responsibilities: Optional[str] = None
    skills: Optional[list[str]] = None
    salary_min: Optional[str] = None
    salary_max: Optional[str] = None
    min_education: Optional[str] = None
    category: Optional[str] = None
    openings: Optional[str] = None
    notice_period: Optional[str] = None
    year_of_passing: Optional[str] = None
    work_type: Optional[str] = None
    interview_type: Optional[str] = None
    company_website: Optional[str] = None
    company_description: Optional[str] = None
    source: Optional[str] = None
    external_id: Optional[str] = None
    job_link: Optional[str] = None
    is_active: Optional[bool] = None
    indexed: Optional[bool] = None


class JobResponse(JobBase):
    id: str
    posted_by: Optional[PostedBy] = None
    is_active: bool = True
    indexed: bool = False
    created_date: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int
    page: int
    limit: int
    total_pages: int
