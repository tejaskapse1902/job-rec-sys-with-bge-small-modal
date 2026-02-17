import os
import time
import threading
import faiss
import pandas as pd
from pymongo import MongoClient
from app.core.config import DATA_DIR
import dotenv
from app.services.drive_service import (
    download_index_from_drive,
    get_drive_last_modified
)

dotenv.load_dotenv()
# Load environment variables with fallback
if not dotenv.load_dotenv():
    dotenv.load_dotenv("app/.env")


# ---------------- CONFIG ----------------
LOCAL_INDEX = f"{DATA_DIR}/jobs.index"

# Add a check to fail gracefully or log clearly
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    print("⚠️ WARNING: MONGO_URI not found. Check your environment variables or .env file.")
DB_NAME = "job_recommendation"
COLLECTION = "jobs"
# ----------------------------------------



_index = None
_jobs_df = None
_last_modified = None
_lock = threading.Lock()


# ---------------- Internal helpers ----------------

def download_index():
    download_index_from_drive(LOCAL_INDEX, force_update=True)


def load_index_from_disk():
    global _index
    _index = faiss.read_index(LOCAL_INDEX)


def load_jobs_from_mongodb():
    client = MongoClient(MONGO_URI)
    col = client[DB_NAME][COLLECTION]
    jobs = list(col.find({}, {"_id": 0}))
    return pd.DataFrame(jobs)


# ---------------- Public API ----------------

def initialize_index():
    global _last_modified, _jobs_df

    print("📥 Loading FAISS index at startup...")

    download_index()
    load_index_from_disk()

    _jobs_df = load_jobs_from_mongodb()
    _last_modified = get_drive_last_modified()

    print("✅ FAISS index + jobs loaded")
    print(f"   - Jobs indexed: {_jobs_df.shape[0]}")


def get_index():
    with _lock:
        return _index


def get_jobs_df():
    with _lock:
        return _jobs_df


def reload_index_and_jobs():
    global _last_modified, _jobs_df

    with _lock:
        print("🔄 Reloading FAISS index + jobs...")

        download_index()
        load_index_from_disk()

        _jobs_df = load_jobs_from_mongodb()
        _last_modified = get_drive_last_modified()

        print("✅ Reload complete")
        print(f"   - Jobs indexed: {_jobs_df.shape[0]}")


def check_and_reload():
    global _last_modified

    try:
        drive_time = get_drive_last_modified()

        if _last_modified is None or drive_time > _last_modified:
            reload_index_and_jobs()

    except Exception as e:
        print("❌ Index refresh failed:", e)


def start_auto_refresh(interval=300):
    def loop():
        while True:
            check_and_reload()
            time.sleep(interval)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
