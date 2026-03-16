from datetime import datetime, timedelta
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_admin
from app.core.database import (
    applications_collection,
    jobs_collection,
    recommendation_items_collection,
    users_collection,
)

router = APIRouter(prefix="/admin/reports", tags=["Reports"])


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
    active_jobs = jobs_collection.count_documents({"is_active": {"$ne": False}})

    total_recommendations = recommendation_items_collection.count_documents(rec_filter)
    total_applications = applications_collection.count_documents(app_filter)
    conversion_rate = round((total_applications / total_recommendations) * 100, 2) if total_recommendations else 0.0

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

    return {
        "total_candidates": total_candidates,
        "total_employers": total_employers,
        "active_jobs": active_jobs,
        "total_recommendations": total_recommendations,
        "total_applications": total_applications,
        "conversion_rate": conversion_rate,
        "top_jobs_by_applications": top_jobs_payload,
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
        report.append(
            {
                "user_id": uid,
                "email": u.get("email", ""),
                "full_name": u.get("full_name", ""),
                "recommended": rec.get("recommended", 0),
                "applied": app.get("applied", 0),
                "not_applied": rec.get("not_applied", 0),
            }
        )

    report.sort(key=lambda x: x["recommended"], reverse=True)
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
                    }
                },
                {"$sort": {"jobs_posted": -1}},
            ]
        )
    )

    for row in rows:
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

    return [{"reason": row["_id"] or "Unspecified", "count": row["count"]} for row in rows]
