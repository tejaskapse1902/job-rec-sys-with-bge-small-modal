from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.core.auth import get_current_admin, get_current_active_employer
from app.core.database import (
    applications_collection,
    jobs_collection,
    recommendation_items_collection,
    users_collection,
)
from app.services.drive_service import download_resume

router = APIRouter(prefix="/admin/reports", tags=["Reports"])
employer_router = APIRouter(prefix="/employer/reports", tags=["Employer Reports"])


def _date_filter(field: str, date_from: Optional[datetime], date_to: Optional[datetime]):
    if not date_from and not date_to:
        return {}

    condition = {}
    if date_from:
        condition["$gte"] = date_from
    if date_to:
        condition["$lte"] = date_to
    return {field: condition}


def _parse_dt(raw: Optional[str], end_of_day: bool = False) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        try:
            dt = datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {raw}")
    if end_of_day:
        return dt + timedelta(days=1) - timedelta(microseconds=1)
    return dt


def _safe_rate(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def _job_title(job: dict) -> str:
    return job.get("title") or job.get("Job Title", "")


def _job_company(job: dict) -> str:
    return job.get("company") or job.get("Company Name", "")


def _job_location(job: dict) -> str:
    return job.get("location") or job.get("Location", "")


def _job_type(job: dict) -> str:
    return job.get("type") or job.get("Job Type", "")


def _job_category(job: dict) -> str:
    return job.get("category") or job.get("Category", "")


def _job_work_type(job: dict) -> str:
    return job.get("work_type") or job.get("Work Type", "")


def _job_created_at(job: dict):
    return job.get("created_at") or job.get("created_date")


def _serialize_recent_application(application: dict, job: dict | None = None, user: dict | None = None) -> dict:
    job = job or {}
    user = user or {}
    resume = user.get("resume") or {}
    return {
        "application_id": str(application["_id"]),
        "job_id": application.get("job_id"),
        "job_title": _job_title(job),
        "company": _job_company(job),
        "applicant_id": application.get("user_id"),
        "applicant_name": user.get("full_name", ""),
        "applicant_email": user.get("email", ""),
        "status": application.get("status", "pending"),
        "applied_at": application.get("applied_at") or application.get("created_at"),
        "created_at": application.get("created_at"),
        "resume": {
            "available": bool(resume.get("drive_file_id")),
            "filename": resume.get("filename"),
            "uploaded_at": resume.get("uploaded_at"),
        },
    }


def _load_jobs_map(job_ids: list[str]) -> dict[str, dict]:
    object_ids = [ObjectId(job_id) for job_id in job_ids if ObjectId.is_valid(job_id)]
    if not object_ids:
        return {}
    return {
        str(job["_id"]): job
        for job in jobs_collection.find({"_id": {"$in": object_ids}})
    }


def _load_users_map(user_ids: list[str]) -> dict[str, dict]:
    object_ids = [ObjectId(user_id) for user_id in user_ids if ObjectId.is_valid(user_id)]
    if not object_ids:
        return {}
    return {
        str(user["_id"]): user
        for user in users_collection.find({"_id": {"$in": object_ids}})
    }


@router.get("/overview")
def overview(
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
    current_admin: dict = Depends(get_current_admin),
):
    _ = current_admin
    from_dt = _parse_dt(from_date)
    to_dt = _parse_dt(to_date, end_of_day=True)
    app_filter = _date_filter("created_at", from_dt, to_dt)
    rec_filter = _date_filter("created_at", from_dt, to_dt)

    total_candidates = users_collection.count_documents({"role": "job_seeker"})
    total_employers = users_collection.count_documents({"role": "employer"})
    pending_employers = users_collection.count_documents({"role": "employer", "status": "pending"})
    active_jobs = jobs_collection.count_documents({"is_active": {"$ne": False}})
    inactive_jobs = jobs_collection.count_documents({"is_active": False})
    jobs_pending_index = jobs_collection.count_documents({"is_active": {"$ne": False}, "indexed": {"$ne": True}})

    total_recommendations = recommendation_items_collection.count_documents(rec_filter)
    applied_recommendations = recommendation_items_collection.count_documents({**rec_filter, "decision": "applied"})
    total_not_applied = recommendation_items_collection.count_documents({**rec_filter, "decision": "not_applied"})
    undecided_recommendations = max(total_recommendations - applied_recommendations - total_not_applied, 0)
    total_applications = applications_collection.count_documents(app_filter)
    conversion_rate = _safe_rate(total_applications, total_recommendations)
    recommendation_apply_rate = _safe_rate(applied_recommendations, total_recommendations)
    not_apply_rate = _safe_rate(total_not_applied, total_recommendations)
    applications_per_active_job = round((total_applications / active_jobs), 2) if active_jobs else 0.0

    top_jobs = list(
        applications_collection.aggregate(
            [
                {"$match": app_filter if app_filter else {}},
                {"$group": {"_id": "$job_id", "applications": {"$sum": 1}}},
                {"$sort": {"applications": -1}},
                {"$limit": 5},
            ]
        )
    )

    job_ids = [x["_id"] for x in top_jobs if ObjectId.is_valid(x["_id"])]
    jobs_map = {
        str(job["_id"]): job
        for job in jobs_collection.find({"_id": {"$in": [ObjectId(x) for x in job_ids]}})
    }

    top_jobs_payload = []
    for row in top_jobs:
        job = jobs_map.get(row["_id"], {})
        top_jobs_payload.append(
            {
                "job_id": row["_id"],
                "title": job.get("title") or job.get("Job Title", ""),
                "company": job.get("company") or job.get("Company Name", ""),
                "applications": row["applications"],
            }
        )

    category_rows = list(
        jobs_collection.aggregate(
            [
                {"$match": {"is_active": {"$ne": False}}},
                {
                    "$group": {
                        "_id": {"$ifNull": ["$category", {"$ifNull": ["$Category", "Uncategorized"]}]},
                        "count": {"$sum": 1},
                    }
                },
                {"$sort": {"count": -1}},
                {"$limit": 6},
            ]
        )
    )

    return {
        "total_candidates": total_candidates,
        "total_employers": total_employers,
        "pending_employers": pending_employers,
        "active_jobs": active_jobs,
        "inactive_jobs": inactive_jobs,
        "jobs_pending_index": jobs_pending_index,
        "total_recommendations": total_recommendations,
        "applied_recommendations": applied_recommendations,
        "total_not_applied": total_not_applied,
        "undecided_recommendations": undecided_recommendations,
        "total_applications": total_applications,
        "conversion_rate": conversion_rate,
        "recommendation_apply_rate": recommendation_apply_rate,
        "not_apply_rate": not_apply_rate,
        "applications_per_active_job": applications_per_active_job,
        "top_jobs_by_applications": top_jobs_payload,
        "top_categories_by_active_jobs": [
            {"category": row["_id"] or "Uncategorized", "count": row["count"]} for row in category_rows
        ],
    }


@router.get("/candidates")
def candidates_report(
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
    current_admin: dict = Depends(get_current_admin),
):
    _ = current_admin
    from_dt = _parse_dt(from_date)
    to_dt = _parse_dt(to_date, end_of_day=True)
    rec_filter = _date_filter("created_at", from_dt, to_dt)
    app_filter = _date_filter("created_at", from_dt, to_dt)

    rec_pipeline = [
        {"$match": rec_filter if rec_filter else {}},
        {
            "$group": {
                "_id": "$user_id",
                "recommended": {"$sum": 1},
                "not_applied": {
                    "$sum": {"$cond": [{"$eq": ["$decision", "not_applied"]}, 1, 0]}
                },
            }
        },
    ]
    app_pipeline = [
        {"$match": app_filter if app_filter else {}},
        {"$group": {"_id": "$user_id", "applied": {"$sum": 1}}},
    ]

    rec_rows = {x["_id"]: x for x in recommendation_items_collection.aggregate(rec_pipeline)}
    app_rows = {x["_id"]: x for x in applications_collection.aggregate(app_pipeline)}

    user_ids = list(set(list(rec_rows.keys()) + list(app_rows.keys())))
    users = list(users_collection.find({"_id": {"$in": [ObjectId(x) for x in user_ids if ObjectId.is_valid(x)]}}))
    users_map = {str(u["_id"]): u for u in users}

    report = []
    for uid in user_ids:
        rec = rec_rows.get(uid, {})
        app = app_rows.get(uid, {})
        u = users_map.get(uid, {})
        recommended = rec.get("recommended", 0)
        applied = app.get("applied", 0)
        not_applied = rec.get("not_applied", 0)
        report.append(
            {
                "user_id": uid,
                "email": u.get("email", ""),
                "full_name": u.get("full_name", ""),
                "recommended": recommended,
                "applied": applied,
                "not_applied": not_applied,
                "undecided": max(recommended - applied - not_applied, 0),
                "conversion_rate": _safe_rate(applied, recommended),
            }
        )

    report.sort(key=lambda x: (x["applied"], x["recommended"]), reverse=True)
    return report


@router.get("/employers")
def employers_report(
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
    current_admin: dict = Depends(get_current_admin),
):
    _ = current_admin
    from_dt = _parse_dt(from_date)
    to_dt = _parse_dt(to_date, end_of_day=True)
    date_filter = _date_filter("created_at", from_dt, to_dt)
    query = {"posted_by.role": "employer"}
    query.update(date_filter)

    rows = list(
        jobs_collection.aggregate(
            [
                {"$match": query},
                {
                    "$group": {
                        "_id": "$posted_by.user_id",
                        "company_name": {"$first": "$posted_by.company_name"},
                        "email": {"$first": "$posted_by.email"},
                        "jobs_posted": {"$sum": 1},
                        "active_jobs": {
                            "$sum": {"$cond": [{"$ne": ["$is_active", False]}, 1, 0]}
                        },
                        "pending_index_jobs": {
                            "$sum": {
                                "$cond": [
                                    {"$and": [{"$ne": ["$is_active", False]}, {"$ne": ["$indexed", True]}]},
                                    1,
                                    0,
                                ]
                            }
                        },
                        "job_ids": {"$push": {"$toString": "$_id"}},
                    }
                },
                {"$sort": {"jobs_posted": -1}},
            ]
        )
    )

    all_job_ids = []
    job_to_employer = {}
    for row in rows:
        for job_id in row.get("job_ids", []):
            all_job_ids.append(job_id)
            job_to_employer[job_id] = row["_id"]

    employer_application_counts = {row["_id"]: 0 for row in rows}
    if all_job_ids:
        app_query = {"job_id": {"$in": all_job_ids}}
        app_query.update(_date_filter("created_at", from_dt, to_dt))
        app_rows = applications_collection.aggregate(
            [
                {"$match": app_query},
                {"$group": {"_id": "$job_id", "applications": {"$sum": 1}}},
            ]
        )
        for app_row in app_rows:
            employer_id = job_to_employer.get(app_row["_id"])
            if employer_id is not None:
                employer_application_counts[employer_id] = employer_application_counts.get(employer_id, 0) + app_row["applications"]

    for row in rows:
        row["applications_received"] = employer_application_counts.get(row["_id"], 0)
        row["avg_applications_per_job"] = round(
            row["applications_received"] / row["jobs_posted"], 2
        ) if row["jobs_posted"] else 0.0
        row.pop("job_ids", None)
        row["user_id"] = row.pop("_id")
    return rows


@router.get("/not-apply-reasons")
def not_apply_reasons(
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
    current_admin: dict = Depends(get_current_admin),
):
    _ = current_admin
    from_dt = _parse_dt(from_date)
    to_dt = _parse_dt(to_date, end_of_day=True)
    date_filter = _date_filter("decision_at", from_dt, to_dt)
    query = {"decision": "not_applied"}
    query.update(date_filter)

    rows = list(
        recommendation_items_collection.aggregate(
            [
                {"$match": query},
                {"$group": {"_id": "$decision_reason", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
            ]
        )
    )

    total = sum(row["count"] for row in rows)

    return [
        {
            "reason": row["_id"] or "Unspecified",
            "count": row["count"],
            "percentage": _safe_rate(row["count"], total),
        }
        for row in rows
    ]


@employer_router.get("/overview")
def employer_overview(
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
    current_employer: dict = Depends(get_current_active_employer),
):
    job_query = {"posted_by.user_id": current_employer["id"]}
    employer_jobs = list(jobs_collection.find(job_query).sort("created_at", -1))
    job_ids = [str(job["_id"]) for job in employer_jobs]

    from_dt = _parse_dt(from_date)
    to_dt = _parse_dt(to_date, end_of_day=True)
    app_query = {"job_id": {"$in": job_ids}} if job_ids else {"job_id": {"$in": []}}
    app_query.update(_date_filter("created_at", from_dt, to_dt))

    total_jobs = len(employer_jobs)
    active_jobs = sum(1 for job in employer_jobs if job.get("is_active") is not False)
    inactive_jobs = max(total_jobs - active_jobs, 0)
    jobs_pending_index = sum(
        1
        for job in employer_jobs
        if job.get("is_active") is not False and job.get("indexed") is not True
    )

    total_applications = applications_collection.count_documents(app_query) if job_ids else 0
    applicant_ids = applications_collection.distinct("user_id", app_query) if job_ids else []
    unique_applicants = len(applicant_ids)

    application_rows = list(
        applications_collection.aggregate(
            [
                {"$match": app_query if job_ids else {"job_id": {"$in": []}}},
                {"$group": {"_id": "$job_id", "applications": {"$sum": 1}, "latest_application_at": {"$max": "$created_at"}}},
                {"$sort": {"applications": -1, "latest_application_at": -1}},
            ]
        )
    ) if job_ids else []
    application_map = {row["_id"]: row for row in application_rows}

    top_jobs = []
    for row in application_rows[:5]:
        job = next((item for item in employer_jobs if str(item["_id"]) == row["_id"]), {})
        top_jobs.append(
            {
                "job_id": row["_id"],
                "title": _job_title(job),
                "company": _job_company(job),
                "location": _job_location(job),
                "applications": row["applications"],
                "latest_application_at": row.get("latest_application_at"),
            }
        )

    recent_application_docs = list(
        applications_collection.find(app_query).sort("created_at", -1).limit(8)
    ) if job_ids else []
    recent_user_map = _load_users_map([row["user_id"] for row in recent_application_docs])
    recent_job_map = _load_jobs_map([row["job_id"] for row in recent_application_docs])

    jobs_with_applications = sum(1 for row in application_rows if row.get("applications", 0) > 0)
    latest_application_at = recent_application_docs[0].get("created_at") if recent_application_docs else None

    return {
        "company_name": current_employer.get("company_name"),
        "report_window": {
            "from": from_dt,
            "to": to_dt,
        },
        "total_jobs": total_jobs,
        "active_jobs": active_jobs,
        "inactive_jobs": inactive_jobs,
        "jobs_pending_index": jobs_pending_index,
        "total_applications": total_applications,
        "unique_applicants": unique_applicants,
        "applications_per_job": round((total_applications / total_jobs), 2) if total_jobs else 0.0,
        "jobs_with_applications": jobs_with_applications,
        "jobs_without_applications": max(total_jobs - jobs_with_applications, 0),
        "latest_application_at": latest_application_at,
        "top_jobs_by_applications": top_jobs,
        "recent_applications": [
            _serialize_recent_application(
                row,
                recent_job_map.get(row["job_id"]),
                recent_user_map.get(row["user_id"]),
            )
            for row in recent_application_docs
        ],
    }


@employer_router.get("/jobs")
def employer_jobs_report(
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
    current_employer: dict = Depends(get_current_active_employer),
):
    employer_jobs = list(
        jobs_collection.find({"posted_by.user_id": current_employer["id"]}).sort("created_at", -1)
    )
    job_ids = [str(job["_id"]) for job in employer_jobs]

    from_dt = _parse_dt(from_date)
    to_dt = _parse_dt(to_date, end_of_day=True)
    app_query = {"job_id": {"$in": job_ids}} if job_ids else {"job_id": {"$in": []}}
    app_query.update(_date_filter("created_at", from_dt, to_dt))

    application_rows = list(
        applications_collection.aggregate(
            [
                {"$match": app_query if job_ids else {"job_id": {"$in": []}}},
                {
                    "$group": {
                        "_id": "$job_id",
                        "applications": {"$sum": 1},
                        "latest_application_at": {"$max": "$created_at"},
                        "unique_applicants": {"$addToSet": "$user_id"},
                    }
                },
            ]
        )
    ) if job_ids else []
    application_map = {
        row["_id"]: {
            "applications": row.get("applications", 0),
            "latest_application_at": row.get("latest_application_at"),
            "unique_applicants": len(row.get("unique_applicants", [])),
        }
        for row in application_rows
    }

    report = []
    for job in employer_jobs:
        job_id = str(job["_id"])
        stats = application_map.get(job_id, {})
        report.append(
            {
                "job_id": job_id,
                "title": _job_title(job),
                "company": _job_company(job),
                "location": _job_location(job),
                "type": _job_type(job),
                "category": _job_category(job),
                "work_type": _job_work_type(job),
                "openings": job.get("openings") or job.get("Openings"),
                "is_active": job.get("is_active", True),
                "indexed": job.get("indexed", False),
                "created_at": _job_created_at(job),
                "applications": stats.get("applications", 0),
                "unique_applicants": stats.get("unique_applicants", 0),
                "latest_application_at": stats.get("latest_application_at"),
            }
        )

    report.sort(key=lambda row: (row["applications"], row["latest_application_at"] or datetime.min), reverse=True)
    return report


@employer_router.get("/jobs/{job_id}/applicants")
def employer_job_applicants(
    job_id: str,
    from_date: Optional[str] = Query(default=None, alias="from"),
    to_date: Optional[str] = Query(default=None, alias="to"),
    current_employer: dict = Depends(get_current_active_employer),
):
    if not ObjectId.is_valid(job_id):
        raise HTTPException(status_code=400, detail="Invalid job id")

    job = jobs_collection.find_one(
        {"_id": ObjectId(job_id), "posted_by.user_id": current_employer["id"]}
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    from_dt = _parse_dt(from_date)
    to_dt = _parse_dt(to_date, end_of_day=True)
    app_query = {"job_id": job_id}
    app_query.update(_date_filter("created_at", from_dt, to_dt))

    application_docs = list(applications_collection.find(app_query).sort("created_at", -1))
    users_map = _load_users_map([row["user_id"] for row in application_docs])

    return {
        "job": {
            "job_id": job_id,
            "title": _job_title(job),
            "company": _job_company(job),
            "location": _job_location(job),
            "type": _job_type(job),
            "category": _job_category(job),
            "work_type": _job_work_type(job),
            "is_active": job.get("is_active", True),
            "applications": len(application_docs),
        },
        "applicants": [
            _serialize_recent_application(row, job=job, user=users_map.get(row["user_id"]))
            for row in application_docs
        ],
    }


@employer_router.get("/applications/{application_id}/resume")
def employer_view_applicant_resume(
    application_id: str,
    current_employer: dict = Depends(get_current_active_employer),
):
    if not ObjectId.is_valid(application_id):
        raise HTTPException(status_code=400, detail="Invalid application id")

    application = applications_collection.find_one({"_id": ObjectId(application_id)})
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    job_id = application.get("job_id")
    if not job_id or not ObjectId.is_valid(job_id):
        raise HTTPException(status_code=404, detail="Associated job not found")

    job = jobs_collection.find_one(
        {"_id": ObjectId(job_id), "posted_by.user_id": current_employer["id"]}
    )
    if not job:
        raise HTTPException(status_code=404, detail="Application not found")

    applicant_id = application.get("user_id")
    if not applicant_id or not ObjectId.is_valid(applicant_id):
        raise HTTPException(status_code=404, detail="Applicant not found")

    applicant = users_collection.find_one({"_id": ObjectId(applicant_id)}, {"resume": 1, "full_name": 1})
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")

    resume = applicant.get("resume") or {}
    drive_file_id = resume.get("drive_file_id")
    if not drive_file_id:
        raise HTTPException(status_code=404, detail="Resume not available for this applicant")

    file_bytes, metadata = download_resume(drive_file_id)
    filename = resume.get("filename") or metadata.get("name") or f"resume-{application_id}"
    media_type = metadata.get("mimeType") or "application/octet-stream"
    quoted_name = quote(filename)

    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quoted_name}",
            "Cache-Control": "no-store",
        },
    )
