import os
from datetime import datetime

import requests

from app.core.database import jobs_collection

JSEARCH_URL = "https://jsearch.p.rapidapi.com/search"


def jsearch_enabled() -> bool:
    return os.getenv("ENABLE_JSEARCH_IMPORT", "false").lower() == "true"


def _headers() -> dict:
    api_key = os.getenv("RAPIDAPI_KEY", "").strip()
    api_host = os.getenv("RAPIDAPI_HOST", "jsearch.p.rapidapi.com").strip()
    if not api_key:
        raise RuntimeError("RAPIDAPI_KEY is missing.")
    return {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": api_host,
    }


def _normalize_jsearch_item(item: dict) -> dict:
    return {
        "title": item.get("job_title") or "Untitled Job",
        "company": item.get("employer_name") or "Unknown Company",
        "location": item.get("job_city")
        or item.get("job_state")
        or item.get("job_country")
        or "Not specified",
        "type": item.get("job_employment_type") or "Full-time",
        "description": item.get("job_description") or "No description provided yet.",
        "requirements": "",
        "responsibilities": "",
        "skills": [],
        "salary_min": str(item.get("job_min_salary")) if item.get("job_min_salary") is not None else None,
        "salary_max": str(item.get("job_max_salary")) if item.get("job_max_salary") is not None else None,
        "source": "external_jsearch",
        "external_id": item.get("job_id"),
        "job_link": item.get("job_apply_link"),
        "posted_by": {"user_id": "external_jsearch", "email": "", "role": "system", "company_name": ""},
        "is_active": True,
        "updated_at": datetime.utcnow(),
    }


def import_jobs_from_jsearch(query: str, page: int = 1, num_pages: int = 1) -> dict:
    if not jsearch_enabled():
        return {
            "status": "deferred",
            "message": "JSearch integration is disabled. Set ENABLE_JSEARCH_IMPORT=true to enable.",
        }

    params = {"query": query, "page": str(page), "num_pages": str(num_pages)}
    response = requests.get(JSEARCH_URL, headers=_headers(), params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()

    items = payload.get("data", [])
    created = 0
    updated = 0

    for item in items:
        normalized = _normalize_jsearch_item(item)
        ext_id = normalized.get("external_id")
        if not ext_id:
            continue

        existing = jobs_collection.find_one({"external_id": ext_id, "source": "external_jsearch"})
        if existing:
            jobs_collection.update_one(
                {"_id": existing["_id"]},
                {"$set": normalized}
            )
            updated += 1
        else:
            normalized["created_at"] = datetime.utcnow()
            jobs_collection.insert_one(normalized)
            created += 1

    return {
        "status": "ok",
        "query": query,
        "fetched": len(items),
        "created": created,
        "updated": updated,
    }
