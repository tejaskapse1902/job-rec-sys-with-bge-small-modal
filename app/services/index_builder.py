import os
from datetime import datetime

import faiss
import numpy as np

from app.core.config import DATA_DIR
from app.core.database import jobs_collection
from app.services.drive_service import download_index_from_drive, upload_index_to_drive
from app.services.recommender import get_model

LOCAL_INDEX = f"{DATA_DIR}/jobs.index"


def _job_value(job: dict, *keys: str) -> str:
    for key in keys:
        raw = job.get(key)
        if raw is None:
            continue
        if isinstance(raw, (float, np.floating)) and np.isnan(raw):
            continue
        value = str(raw).strip()
        if value.lower() in {"nan", "none", "null"}:
            continue
        if value:
            return value
    return ""


def _build_job_text(job: dict) -> str:
    return "\n".join(
        [
            f"Job Title: {_job_value(job, 'title', 'Job Title')}",
            f"Company: {_job_value(job, 'company', 'Company Name')}",
            f"Category: {_job_value(job, 'category', 'Category')}",
            f"Experience Level: {_job_value(job, 'experience_level', 'Experience Level')}",
            f"Work Type: {_job_value(job, 'work_type', 'Work Type')}",
            f"Skills: {_job_value(job, 'skills', 'Skills')}",
            f"Requirements: {_job_value(job, 'requirements', 'Requirements')}",
            f"Responsibilities: {_job_value(job, 'responsibilities', 'Responsibilities')}",
            f"Job Description: {_job_value(job, 'description', 'Job Description')}",
        ]
    )


def _download_existing_index():
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        download_index_from_drive(LOCAL_INDEX)
        return faiss.read_index(LOCAL_INDEX)
    except Exception:
        return None


def _create_index(dimension: int):
    index = faiss.IndexHNSWFlat(dimension, 32, faiss.METRIC_INNER_PRODUCT)
    index.hnsw.efConstruction = 200
    index.hnsw.efSearch = 64
    return index


def incremental_index_new_jobs() -> dict:
    new_jobs = list(
        jobs_collection.find({"is_active": {"$ne": False}, "indexed": {"$ne": True}}).sort(
            [("created_at", 1), ("created_date", 1), ("_id", 1)]
        )
    )

    if not new_jobs:
        return {"status": "no_new_jobs", "indexed_count": 0}

    job_texts = [_build_job_text(job) for job in new_jobs]
    model = get_model()
    embeddings = model.encode(
        job_texts,
        batch_size=min(32, len(job_texts)),
        normalize_embeddings=True,
        show_progress_bar=False,
    ).astype("float32")

    index = _download_existing_index()
    if index is None:
        index = _create_index(embeddings.shape[1])
    elif isinstance(index, faiss.IndexHNSWFlat):
        index.hnsw.efSearch = 64

    index.add(embeddings)

    os.makedirs(DATA_DIR, exist_ok=True)
    faiss.write_index(index, LOCAL_INDEX)
    upload_index_to_drive(LOCAL_INDEX)

    jobs_collection.update_many(
        {"_id": {"$in": [job["_id"] for job in new_jobs]}},
        {"$set": {"indexed": True, "updated_at": datetime.utcnow()}},
    )

    return {"status": "indexed", "indexed_count": len(new_jobs)}
