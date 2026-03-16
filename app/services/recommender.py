# =============================
# app/services/recommender.py
# Production-safe + optimized
# =============================

import os
import re
import numpy as np
import torch
from datetime import datetime, timezone
from sentence_transformers import SentenceTransformer

from app.core.config import DATA_DIR
from app.services.resume_parser import parse_resume
from app.services.index_manager import get_index, get_jobs_df

# -----------------------------
# HuggingFace cache config
# -----------------------------
CACHE_DIR = os.getenv("HF_CACHE_DIR", os.path.join(DATA_DIR, "hf_cache"))
os.environ["HF_HOME"] = CACHE_DIR
os.environ["TRANSFORMERS_CACHE"] = CACHE_DIR
os.makedirs(CACHE_DIR, exist_ok=True)

# -----------------------------
# Model config
# -----------------------------
MODEL_NAME = "BAAI/bge-small-en-v1.5"
TOP_K = 20

# -----------------------------
# Load model once (singleton)
# -----------------------------
_model = None


def get_model():
    global _model
    if _model is None:
        print("🔥 Loading embedding model at runtime...")
        _model = SentenceTransformer(
            MODEL_NAME,
            cache_folder=CACHE_DIR
        )
        # Performance optimization for CPU
        if not torch.cuda.is_available():
            torch.set_num_threads(4) 
    return _model


# -----------------------------
# Utils
# -----------------------------
def clean_text(raw):
    if raw is None:
        return ""

    if isinstance(raw, (float, np.floating)) and np.isnan(raw):
        return ""

    try:
        if np.isscalar(raw) and np.isnan(raw):
            return ""
    except TypeError:
        pass

    text = str(raw).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def pick_first_value(source, *keys):
    for key in keys:
        value = clean_text(source.get(key))
        if value:
            return value
    return ""


def clean_job_link(raw):
    raw = clean_text(raw)
    if not raw:
        return ""

    email_match = re.search(r"([A-Za-z0-9._%+-]+)\s*@\s*([A-Za-z0-9.-]+\.[A-Za-z]{2,})", raw)
    if email_match:
        email = f"{email_match.group(1)}@{email_match.group(2)}".rstrip(".,;")
        return f"mailto:{email}"

    raw = re.sub(r"^(https?):\s*", r"\1://", raw, flags=re.IGNORECASE)
    raw = re.sub(r"^(https?://[^/\s]+)\s+", r"\1/", raw, flags=re.IGNORECASE)
    raw = raw.replace("\\", "/").strip().rstrip(".,;")
    raw = re.sub(r"\s+", "", raw)

    match = re.search(r"(https?://[^\s]+)", raw)
    if match:
        return match.group(1).rstrip(".,;")

    domain_match = re.search(r"((?:www\.)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s]*)?)", raw)
    if domain_match:
        normalized = domain_match.group(1).rstrip(".,;")
        if not normalized.lower().startswith(("http://", "https://")):
            normalized = f"https://{normalized}"
        return normalized

    return raw


def recency_boost(created_date, max_boost=0.08, decay_days=30):
    try:
        if isinstance(created_date, str):
            created_dt = datetime.fromisoformat(created_date.replace("Z", "+00:00"))
        elif isinstance(created_date, datetime):
            created_dt = created_date
        else:
            return 0.0

        now = datetime.now(timezone.utc)
        age_days = max((now - created_dt).days, 0)
        return max_boost * max(0, (decay_days - age_days) / decay_days)

    except Exception:
        return 0.0


def final_score(similarity, row, resume_data):
    score = similarity

    job_skills = pick_first_value(row, "skills", "Skills").lower()
    overlap = sum(1 for s in resume_data["skills"] if s in job_skills)
    score += 0.07 * overlap

    if resume_data.get("experience_years"):
        exp_value = pick_first_value(row, "experience_level", "Experience Level")
        if str(resume_data["experience_years"]) in exp_value:
            score += 0.15

    score += recency_boost(row.get("created_date"))
    return score


# -----------------------------
# Main recommender
# -----------------------------
def recommend_jobs(resume_text: str):
    index = get_index()
    df = get_jobs_df()

    if index is None or df is None or df.empty:
        return {
            "error": "Recommendation system is warming up. Please try again shortly."
        }

    resume_data = parse_resume(resume_text)
    model = get_model()

    emb_vec = model.encode(
        [resume_text],
        normalize_embeddings=True
    )[0]

    emb = np.asarray([emb_vec], dtype="float32")
    scores, indices = index.search(emb, TOP_K)

    ranked = []
    for rank, idx in enumerate(indices[0]):
        if idx >= len(df):
            continue

        row = df.iloc[idx]
        sim = float(scores[0][rank])
        score = final_score(sim, row, resume_data)

        created_date = row.get("created_date")
        try:
            if isinstance(created_date, str):
                created_dt = datetime.fromisoformat(created_date.replace("Z", "+00:00"))
            else:
                created_dt = created_date
        except Exception:
            created_dt = datetime.min

        ranked.append((score, created_dt, idx))

    ranked.sort(key=lambda x: (x[0], x[1]), reverse=True)

    results = []
    for score, _, idx in ranked[:TOP_K]:
        job = df.iloc[idx]
        raw_id = job.get("_id")
        job_id = str(raw_id) if raw_id is not None else None

        results.append({
            "job_id": job_id,
            "job_title": pick_first_value(job, "title", "Job Title"),
            "company": pick_first_value(job, "company", "Company Name"),
            "location": pick_first_value(job, "location", "Location"),
            "type": pick_first_value(job, "type", "Job Type"),
            "experience": pick_first_value(job, "experience_level", "Experience Level"),
            "experience_level": pick_first_value(job, "experience_level", "Experience Level"),
            "min_education": pick_first_value(job, "min_education", "Min Education"),
            "category": pick_first_value(job, "category", "Category"),
            "openings": pick_first_value(job, "openings", "Openings"),
            "notice_period": pick_first_value(job, "notice_period", "Notice Period"),
            "year_of_passing": pick_first_value(job, "year_of_passing", "Year of Passing"),
            "work_type": pick_first_value(job, "work_type", "Work Type"),
            "interview_type": pick_first_value(job, "interview_type", "Interview Type"),
            "company_website": clean_job_link(pick_first_value(job, "company_website", "Company Website")),
            "company_description": pick_first_value(job, "company_description", "Company Description"),
            "description": pick_first_value(job, "description", "Job Description"),
            "requirements": pick_first_value(job, "requirements", "Requirements"),
            "responsibilities": pick_first_value(job, "responsibilities", "Responsibilities"),
            "skills": pick_first_value(job, "skills", "Skills"),
            "salary_min": pick_first_value(job, "salary_min", "Salary Min (?)"),
            "salary_max": pick_first_value(job, "salary_max", "Salary Max (?)"),
            "match_percentage": round(min(score * 100, 100), 2),
            "created_date": clean_text(job.get("created_at") or job.get("created_date", "")),
            "job_link": clean_job_link(pick_first_value(job, "job_link", "Direct Link")),
        })

    return results
