import math
import re
from datetime import datetime
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import get_current_user
from app.core.database import jobs_collection
from app.models.job import JobCreate, JobListResponse, JobResponse, JobUpdate

router = APIRouter(prefix="/jobs", tags=["Jobs"])

LEGACY_FIELD_MAP = {
    "title": "Job Title",
    "company": "Company Name",
    "location": "Location",
    "type": "Job Type",
    "experience_level": "Experience Level",
    "salary_min": "Salary Min (?)",
    "salary_max": "Salary Max (?)",
    "min_education": "Min Education",
    "category": "Category",
    "openings": "Openings",
    "notice_period": "Notice Period",
    "year_of_passing": "Year of Passing",
    "job_link": "Direct Link",
    "work_type": "Work Type",
    "interview_type": "Interview Type",
    "company_website": "Company Website",
    "company_description": "Company Description",
    "description": "Job Description",
    "requirements": "Requirements",
    "responsibilities": "Responsibilities",
}


def _normalize_skills(skills: Any) -> list[str]:
    if skills is None:
        return []
    if isinstance(skills, list):
        return [str(item).strip() for item in skills if str(item).strip()]
    if isinstance(skills, str):
        parts = [p.strip() for p in re.split(r"[,|]", skills)]
        return [p for p in parts if p]
    return [str(skills).strip()]


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _optional_text(value: Any) -> str | None:
    cleaned = _clean_text(value)
    return cleaned or None


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return _clean_text(value).lower() not in {"", "0", "false", "no", "off", "none", "null"}


def _serialize_skills(skills: list[str]) -> str:
    return ", ".join(skills)


def _normalize_job_link(raw: Any, fallback: Any = None) -> str | None:
    primary = str(raw or "").strip()
    backup = str(fallback or "").strip()
    candidate = primary or backup
    if not candidate:
        return None

    email_match = re.search(r"([A-Za-z0-9._%+-]+)\s*@\s*([A-Za-z0-9.-]+\.[A-Za-z]{2,})", candidate)
    if email_match:
        email = f"{email_match.group(1)}@{email_match.group(2)}".rstrip(".,;")
        return f"mailto:{email}"

    candidate = re.sub(r"^(https?):\s*", r"\1://", candidate, flags=re.IGNORECASE)
    candidate = re.sub(r"^(https?://[^/\s]+)\s+", r"\1/", candidate, flags=re.IGNORECASE)
    candidate = candidate.replace("\\", "/").strip().rstrip(".,;")
    candidate = re.sub(r"\s+", "", candidate)

    http_match = re.search(r"(https?://[^\s]+)", candidate, flags=re.IGNORECASE)
    if http_match:
        return http_match.group(1).rstrip(".,;")

    domain_match = re.search(r"((?:www\.)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s]*)?)", candidate)
    if domain_match:
        normalized = domain_match.group(1).rstrip(".,;")
        if not normalized.lower().startswith(("http://", "https://")):
            normalized = f"https://{normalized}"
        return normalized

    return None


def _normalize_job_doc(doc: dict) -> JobResponse:
    skills = _normalize_skills(doc.get("skills", doc.get("Skills")))
    title = _clean_text(doc.get("title") or doc.get("Job Title")) or "Untitled Job"
    company = _clean_text(doc.get("company") or doc.get("Company Name")) or "Unknown Company"
    location = _clean_text(doc.get("location") or doc.get("Location")) or "Not specified"
    description = _clean_text(doc.get("description") or doc.get("Job Description"))
    if len(description) < 10:
        description = "No description provided yet."

    created_date = doc.get("created_date") or doc.get("created_at") or datetime.utcnow()
    created_at = doc.get("created_at") or created_date or datetime.utcnow()
    updated_at = doc.get("updated_at")
    company_website = _normalize_job_link(doc.get("company_website") or doc.get("Company Website"))

    return JobResponse(
        id=str(doc["_id"]),
        title=title,
        company=company,
        location=location,
        type=_clean_text(doc.get("type") or doc.get("Job Type") or "Full-time"),
        experience_level=_optional_text(doc.get("experience_level") or doc.get("Experience Level")),
        description=description,
        requirements=_clean_text(doc.get("requirements") or doc.get("Requirements")),
        responsibilities=_clean_text(doc.get("responsibilities") or doc.get("Responsibilities")),
        skills=skills,
        salary_min=(None if doc.get("salary_min") is None else str(doc.get("salary_min")))
        or (None if doc.get("Salary Min (?)") is None else str(doc.get("Salary Min (?)"))),
        salary_max=(None if doc.get("salary_max") is None else str(doc.get("salary_max")))
        or (None if doc.get("Salary Max (?)") is None else str(doc.get("Salary Max (?)"))),
        min_education=_optional_text(doc.get("min_education") or doc.get("Min Education")),
        category=_optional_text(doc.get("category") or doc.get("Category")),
        openings=_optional_text(doc.get("openings") or doc.get("Openings")),
        notice_period=_optional_text(doc.get("notice_period") or doc.get("Notice Period")),
        year_of_passing=_optional_text(doc.get("year_of_passing") or doc.get("Year of Passing")),
        work_type=_optional_text(doc.get("work_type") or doc.get("Work Type")),
        interview_type=_optional_text(doc.get("interview_type") or doc.get("Interview Type")),
        company_website=company_website,
        company_description=_optional_text(doc.get("company_description") or doc.get("Company Description")),
        source=str(doc.get("source") or ("legacy_import" if "Job Title" in doc else "manual")),
        external_id=doc.get("external_id"),
        job_link=_normalize_job_link(doc.get("job_link") or doc.get("Direct Link"), company_website),
        posted_by=doc.get("posted_by"),
        is_active=_coerce_bool(doc.get("is_active", True), True),
        indexed=_coerce_bool(doc.get("indexed", False), False),
        created_date=created_date,
        created_at=created_at,
        updated_at=updated_at,
    )


def _expand_job_storage_fields(values: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}

    for field, value in values.items():
        if field == "skills":
            normalized_skills = _normalize_skills(value)
            updates["skills"] = normalized_skills
            updates["Skills"] = _serialize_skills(normalized_skills)
            continue

        if field in {"job_link", "company_website"}:
            normalized_link = _normalize_job_link(value)
            updates[field] = normalized_link
            updates[LEGACY_FIELD_MAP[field]] = normalized_link
            continue

        if field in {"is_active", "indexed"}:
            normalized_bool = _coerce_bool(value, field == "is_active")
            updates[field] = normalized_bool
            continue

        normalized_value = value.strip() if isinstance(value, str) else value
        updates[field] = normalized_value

        legacy_field = LEGACY_FIELD_MAP.get(field)
        if legacy_field:
            updates[legacy_field] = normalized_value

    return updates


def _normalize_role(role: str | None) -> str:
    if role == "admin":
        return "admin"
    if role == "employer":
        return "employer"
    return "job_seeker"


def _require_job_write_access(current_user: dict):
    role = _normalize_role(current_user.get("role"))
    if role == "admin":
        return
    if role == "employer" and current_user.get("status") == "active" and current_user.get("is_active", True):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only admin or active employer accounts can manage jobs."
    )


def _get_job_or_404(job_id: str) -> dict:
    if not ObjectId.is_valid(job_id):
        raise HTTPException(status_code=400, detail="Invalid job id.")
    job = jobs_collection.find_one({"_id": ObjectId(job_id), "is_active": {"$ne": False}})
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


def _ensure_job_owner_or_admin(job: dict, current_user: dict):
    role = _normalize_role(current_user.get("role"))
    if role == "admin":
        return

    posted_by = job.get("posted_by") or {}
    if role == "employer" and posted_by.get("user_id") == current_user.get("id"):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You can only modify your own jobs."
    )


@router.get("", response_model=JobListResponse)
def list_jobs(
    q: str | None = Query(default=None),
    location: str | None = Query(default=None),
    company: str | None = Query(default=None),
    type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    work_type: str | None = Query(default=None),
    experience_level: str | None = Query(default=None),
    mine: bool = Query(default=False),
    include_inactive: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    role = _normalize_role(current_user.get("role"))

    query: dict[str, Any] = {}
    if not include_inactive or role != "admin":
        query["is_active"] = {"$ne": False}

    if mine:
        if role not in {"admin", "employer"}:
            raise HTTPException(status_code=403, detail="Only admin or employer can use mine filter.")
        query["posted_by.user_id"] = current_user["id"]

    and_conditions: list[dict[str, Any]] = []

    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        and_conditions.append({"$or": [
            {"title": rx},
            {"company": rx},
            {"description": rx},
            {"requirements": rx},
            {"responsibilities": rx},
            {"skills": rx},
            {"category": rx},
            {"experience_level": rx},
            {"work_type": rx},
            {"company_description": rx},
            {"Job Title": rx},
            {"Company Name": rx},
            {"Job Description": rx},
            {"Requirements": rx},
            {"Responsibilities": rx},
            {"Skills": rx},
            {"Category": rx},
            {"Experience Level": rx},
            {"Work Type": rx},
            {"Company Description": rx},
        ]})

    if location:
        rx = {"$regex": re.escape(location), "$options": "i"}
        and_conditions.append({"$or": [{"location": rx}, {"Location": rx}]})

    if company:
        rx = {"$regex": re.escape(company), "$options": "i"}
        and_conditions.append({"$or": [{"company": rx}, {"Company Name": rx}]})

    if type:
        rx = {"$regex": re.escape(type), "$options": "i"}
        and_conditions.append({"$or": [{"type": rx}, {"Job Type": rx}]})

    if category:
        rx = {"$regex": re.escape(category), "$options": "i"}
        and_conditions.append({"$or": [{"category": rx}, {"Category": rx}]})

    if work_type:
        rx = {"$regex": re.escape(work_type), "$options": "i"}
        and_conditions.append({"$or": [{"work_type": rx}, {"Work Type": rx}]})

    if experience_level:
        rx = {"$regex": re.escape(experience_level), "$options": "i"}
        and_conditions.append({"$or": [{"experience_level": rx}, {"Experience Level": rx}]})

    if and_conditions:
        query["$and"] = and_conditions

    total = jobs_collection.count_documents(query)
    total_pages = max(math.ceil(total / limit), 1)
    skip = (page - 1) * limit

    docs = list(
        jobs_collection.find(query)
        .sort([("created_at", -1), ("created_date", -1)])
        .skip(skip)
        .limit(limit)
    )
    items = [_normalize_job_doc(doc) for doc in docs]

    return JobListResponse(items=items, total=total, page=page, limit=limit, total_pages=total_pages)


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, current_user: dict = Depends(get_current_user)):
    _ = current_user
    job = _get_job_or_404(job_id)
    return _normalize_job_doc(job)


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreate, current_user: dict = Depends(get_current_user)):
    _require_job_write_access(current_user)
    role = _normalize_role(current_user.get("role"))

    company_value = payload.company
    if role == "employer" and current_user.get("company_name"):
        company_value = current_user["company_name"]

    now = datetime.utcnow()
    payload_data = payload.dict()
    payload_data["company"] = company_value
    payload_data["source"] = payload.source.strip() if payload.source else "manual"
    doc = _expand_job_storage_fields(payload_data)
    doc.update({
        "posted_by": {
            "user_id": current_user["id"],
            "email": current_user["email"],
            "role": role,
            "company_name": current_user.get("company_name"),
        },
        "is_active": True,
        "indexed": False,
        "created_date": now,
        "created_at": now,
        "updated_at": now,
    })

    result = jobs_collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _normalize_job_doc(doc)


@router.put("/{job_id}", response_model=JobResponse)
def update_job(job_id: str, payload: JobUpdate, current_user: dict = Depends(get_current_user)):
    _require_job_write_access(current_user)
    existing = _get_job_or_404(job_id)
    _ensure_job_owner_or_admin(existing, current_user)

    raw_updates = payload.dict(exclude_unset=True)
    if _normalize_role(current_user.get("role")) == "employer" and current_user.get("company_name"):
        raw_updates["company"] = current_user["company_name"]

    if not raw_updates:
        return _normalize_job_doc(existing)

    updates = _expand_job_storage_fields(raw_updates)
    updates["updated_at"] = datetime.utcnow()
    jobs_collection.update_one({"_id": existing["_id"]}, {"$set": updates})

    updated = jobs_collection.find_one({"_id": existing["_id"]})
    return _normalize_job_doc(updated)


@router.delete("/{job_id}")
def delete_job(job_id: str, current_user: dict = Depends(get_current_user)):
    _require_job_write_access(current_user)
    existing = _get_job_or_404(job_id)
    _ensure_job_owner_or_admin(existing, current_user)

    jobs_collection.update_one(
        {"_id": existing["_id"]},
        {"$set": {"is_active": False, "updated_at": datetime.utcnow()}}
    )
    return {"status": "deleted"}
