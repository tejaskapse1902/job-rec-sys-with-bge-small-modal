import html
import os
import re
from datetime import datetime
from typing import Any

import dotenv
import requests
from requests import RequestException

from app.core.database import jobs_collection

dotenv.load_dotenv()
dotenv.load_dotenv("app/.env")

ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
PROVIDER = "arbeitnow"
PROVIDER_LABEL = "Arbeitnow"
PROVIDER_SOURCE = "external_arbeitnow"
PROVIDER_SOURCE_URL = "https://www.arbeitnow.com/"


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def _clean_html_text(value: Any) -> str:
    text = html.unescape(_clean_text(value))
    if not text:
        return ""

    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"(?i)</li>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _compact_spaces(value: Any) -> str:
    return re.sub(r"\s+", " ", _clean_text(value)).strip()


def _to_optional_text(value: Any) -> str | None:
    text = _compact_spaces(value)
    return text or None


def _iso_from_epoch(value: Any) -> str:
    try:
        timestamp = int(float(value))
    except (TypeError, ValueError):
        return ""
    return datetime.utcfromtimestamp(timestamp).isoformat() + "Z"


def _arbeitnow_enabled() -> tuple[bool, str | None]:
    enabled = os.getenv("ENABLE_ARBEITNOW_IMPORT", "true").lower() == "true"
    if enabled:
        return True, None
    return False, "Arbeitnow integration is disabled. Set ENABLE_ARBEITNOW_IMPORT=true to enable it."


def _provider_error(exc: RequestException) -> RuntimeError:
    response = getattr(exc, "response", None)

    if response is not None:
        detail = _compact_spaces(response.text)
        if response.status_code == 429:
            message = "Arbeitnow rate limit exceeded (429). Please retry later."
            if detail:
                message = f"{message} Provider response: {detail[:300]}"
            return RuntimeError(message)

        if detail:
            return RuntimeError(f"Arbeitnow request failed ({response.status_code}): {detail[:300]}")

    return RuntimeError(f"Arbeitnow request failed: {exc}")


def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except RequestException as exc:
        raise _provider_error(exc) from exc


def _match_query(values: list[Any], query: str) -> bool:
    target = _compact_spaces(query).lower()
    if not target:
        return True
    haystack = " ".join(_compact_spaces(value).lower() for value in values if _compact_spaces(value))
    return target in haystack


def _preview_item(item: dict[str, Any]) -> dict[str, Any]:
    type_value = ", ".join(_compact_spaces(value) for value in (item.get("job_types") or []) if _compact_spaces(value))
    skills = [_compact_spaces(skill) for skill in (item.get("tags") or []) if _compact_spaces(skill)]

    return {
        "external_id": _clean_text(item.get("slug")),
        "title": _clean_text(item.get("title")) or "Untitled Job",
        "company": _clean_text(item.get("company_name")) or "Unknown Company",
        "location": _clean_text(item.get("location")) or "Not specified",
        "type": type_value or "Not specified",
        "work_type": "Remote" if item.get("remote") is True else "On-Site",
        "description": _clean_html_text(item.get("description")) or "No description provided yet.",
        "salary_min": "",
        "salary_max": "",
        "job_link": _clean_text(item.get("url")),
        "company_website": "",
        "publisher": PROVIDER_LABEL,
        "posted_at": _iso_from_epoch(item.get("created_at")),
        "category": _compact_spaces((item.get("tags") or [None])[0]),
        "skills": skills,
        "source": PROVIDER_SOURCE,
        "external_provider": PROVIDER,
        "source_label": PROVIDER_LABEL,
        "attribution_required": False,
        "attribution_text": "Source: Arbeitnow",
        "attribution_url": PROVIDER_SOURCE_URL,
    }


def search_external_jobs(query: str, page: int = 1, num_pages: int = 1) -> dict[str, Any]:
    enabled, message = _arbeitnow_enabled()
    if not enabled:
        return {
            "status": "deferred",
            "provider": PROVIDER,
            "provider_label": PROVIDER_LABEL,
            "query": _compact_spaces(query),
            "page": page,
            "num_pages": num_pages,
            "fetched": 0,
            "items": [],
            "message": message,
        }

    normalized_query = _compact_spaces(query)
    if len(normalized_query) < 2:
        raise RuntimeError("Please enter at least 2 characters to search external jobs.")

    items: list[dict[str, Any]] = []
    current_page = page
    final_page = page + max(num_pages, 1) - 1

    while current_page <= final_page:
        payload = _get_json(ARBEITNOW_URL, params={"page": current_page, "limit": 100})
        data = payload.get("data") or []

        for item in data:
            if not _match_query(
                [
                    item.get("title"),
                    item.get("company_name"),
                    item.get("location"),
                    " ".join(item.get("tags") or []),
                    _clean_html_text(item.get("description")),
                ],
                normalized_query,
            ):
                continue
            items.append(_preview_item(item))

        next_link = ((payload.get("links") or {}).get("next")) or ""
        if not next_link:
            break
        current_page += 1

    return {
        "status": "ok",
        "provider": PROVIDER,
        "provider_label": PROVIDER_LABEL,
        "query": normalized_query,
        "page": page,
        "num_pages": num_pages,
        "fetched": len(items),
        "items": items,
        "message": "",
    }


def _storage_doc(item: dict[str, Any]) -> dict[str, Any]:
    now = datetime.utcnow()
    skills = [_compact_spaces(skill) for skill in (item.get("skills") or []) if _compact_spaces(skill)]

    return {
        "title": _clean_text(item.get("title")) or "Untitled Job",
        "company": _clean_text(item.get("company")) or "Unknown Company",
        "location": _clean_text(item.get("location")) or "Not specified",
        "type": _clean_text(item.get("type")) or "Not specified",
        "experience_level": None,
        "description": _clean_html_text(item.get("description")) or "No description provided yet.",
        "requirements": "",
        "responsibilities": "",
        "skills": skills,
        "salary_min": _to_optional_text(item.get("salary_min")),
        "salary_max": _to_optional_text(item.get("salary_max")),
        "min_education": None,
        "category": _to_optional_text(item.get("category")),
        "openings": None,
        "notice_period": None,
        "year_of_passing": None,
        "work_type": _to_optional_text(item.get("work_type")),
        "interview_type": None,
        "company_website": _to_optional_text(item.get("company_website")),
        "company_description": "",
        "source": PROVIDER_SOURCE,
        "external_provider": PROVIDER,
        "source_label": PROVIDER_LABEL,
        "attribution_required": False,
        "attribution_text": "Source: Arbeitnow",
        "attribution_url": PROVIDER_SOURCE_URL,
        "external_id": _clean_text(item.get("external_id")),
        "job_link": _to_optional_text(item.get("job_link")),
        "publisher": PROVIDER_LABEL,
        "posted_by": {
            "user_id": f"external_{PROVIDER}",
            "email": "",
            "role": "system",
            "company_name": "",
        },
        "is_active": True,
        "indexed": False,
        "updated_at": now,
        "Job Title": _clean_text(item.get("title")) or "Untitled Job",
        "Company Name": _clean_text(item.get("company")) or "Unknown Company",
        "Location": _clean_text(item.get("location")) or "Not specified",
        "Job Type": _clean_text(item.get("type")) or "Not specified",
        "Work Type": _clean_text(item.get("work_type")),
        "Job Description": _clean_html_text(item.get("description")) or "No description provided yet.",
        "Requirements": "",
        "Responsibilities": "",
        "Skills": ", ".join(skills),
        "Salary Min (?)": _clean_text(item.get("salary_min")),
        "Salary Max (?)": _clean_text(item.get("salary_max")),
        "Company Website": _clean_text(item.get("company_website")),
        "Company Description": "",
        "Direct Link": _clean_text(item.get("job_link")),
    }


def import_external_jobs(query: str, page: int = 1, num_pages: int = 1) -> dict[str, Any]:
    search_result = search_external_jobs(query=query, page=page, num_pages=num_pages)

    if search_result["status"] == "deferred":
        return {
            "status": "deferred",
            "provider": PROVIDER,
            "provider_label": PROVIDER_LABEL,
            "query": search_result["query"],
            "page": page,
            "num_pages": num_pages,
            "fetched": 0,
            "created": 0,
            "updated": 0,
            "message": search_result["message"] or "Arbeitnow is unavailable.",
        }

    created = 0
    updated = 0

    for item in search_result["items"]:
        normalized = _storage_doc(item)
        ext_id = normalized.get("external_id")
        if not ext_id:
            continue

        existing = jobs_collection.find_one({"external_id": ext_id, "source": PROVIDER_SOURCE})
        if existing:
            jobs_collection.update_one({"_id": existing["_id"]}, {"$set": normalized})
            updated += 1
        else:
            normalized["created_at"] = datetime.utcnow()
            normalized["created_date"] = normalized["created_at"]
            jobs_collection.insert_one(normalized)
            created += 1

    return {
        "status": "ok",
        "provider": PROVIDER,
        "provider_label": PROVIDER_LABEL,
        "query": search_result["query"],
        "page": page,
        "num_pages": num_pages,
        "fetched": search_result["fetched"],
        "created": created,
        "updated": updated,
        "message": "External jobs imported successfully. Run index sync if you want them included in recommendations.",
    }
