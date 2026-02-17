# =============================
# app/services/build_faiss_index.py
# HNSW + accuracy-safe + S3 upload
# =============================
# ---------------- Path & env setup ----------------
import sys
import os
import dotenv
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

ENV_PATH = os.path.join(PROJECT_ROOT, "app", ".env")
dotenv.load_dotenv(ENV_PATH)

# ---------------- Imports ----------------
import numpy as np
import faiss
from pymongo import MongoClient
from app.services.drive_service import upload_index_to_drive
from app.core.config import DATA_DIR
from app.services.recommender import get_model

# ---------------- Config ----------------
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = "job_recommendation"
COLLECTION_NAME = "jobs"

OUTPUT_INDEX_PATH = f"{DATA_DIR}/jobs.index"
# ------------------------------------------------


def build_job_text(row):
    return f"""
Job Title: {row.get('Job Title', '')}
Category: {row.get('Category', '')}
Experience Level: {row.get('Experience Level', '')}
Skills: {row.get('Skills', '')}
Requirements: {row.get('Requirements', '')}
Responsibilities: {row.get('Responsibilities', '')}
Job Description: {row.get('Job Description', '')}
"""


def build_faiss_index():
    print("🔌 Connecting to MongoDB...")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    jobs = list(collection.find({}, {"_id": 0}))
    if not jobs:
        raise ValueError("No jobs found in database")

    df = pd.DataFrame(jobs)

    print(f"📄 Jobs loaded: {len(df)}")

    print("📝 Building job texts...")
    job_texts = df.apply(build_job_text, axis=1).tolist()

    print("🤖 Loading embedding model...")
    model = get_model()

    print("🧠 Generating embeddings...")
    embeddings = model.encode(
        job_texts,
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=True
    ).astype("float32")

    print("📐 Creating FAISS HNSW index (accuracy-safe)...")
    dim = embeddings.shape[1]

    # HNSW parameters tuned for accuracy
    M = 32
    index = faiss.IndexHNSWFlat(dim, M, faiss.METRIC_INNER_PRODUCT)
    index.hnsw.efConstruction = 200
    index.hnsw.efSearch = 64

    index.add(embeddings)

    print("💾 Saving index locally...")
    os.makedirs(DATA_DIR, exist_ok=True)
    faiss.write_index(index, OUTPUT_INDEX_PATH)

    print("✅ FAISS index created successfully")

    return OUTPUT_INDEX_PATH



def main():
    try:
        index_path = build_faiss_index()
        upload_index_to_drive(index_path)
        print("🎉 Build + Upload pipeline completed successfully")

    except Exception as e:
        print("❌ Pipeline failed:", str(e))
        raise


if __name__ == "__main__":
    main()

