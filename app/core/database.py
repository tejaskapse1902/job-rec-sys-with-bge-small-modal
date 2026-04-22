import os
import threading
from pathlib import Path

import dotenv
from pymongo import MongoClient

dotenv.load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable not set")

DB_NAME = "job_recommendation"
SERVER_SELECTION_TIMEOUT_MS = int(os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "5000"))

_client = None
_db = None
_connect_lock = threading.Lock()
_indexes_initialized = False
_indexes_lock = threading.Lock()


def _connect():
    global _client, _db

    if _db is not None:
        return _db

    with _connect_lock:
        if _db is None:
            _client = MongoClient(
                MONGO_URI,
                serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS,
            )
            _db = _client[DB_NAME]

    return _db


def get_db():
    return _connect()


def get_client():
    _connect()
    return _client


class LazyCollection:
    def __init__(self, name: str):
        self._name = name

    def _collection(self):
        return get_db()[self._name]

    def __getattr__(self, item):
        return getattr(self._collection(), item)


jobs_collection = LazyCollection("jobs")
users_collection = LazyCollection("users")
applications_collection = LazyCollection("applications")
recommendation_sessions_collection = LazyCollection("recommendation_sessions")
recommendation_items_collection = LazyCollection("recommendation_items")


def ensure_indexes():
    global _indexes_initialized

    if _indexes_initialized:
        return

    with _indexes_lock:
        if _indexes_initialized:
            return

        db = get_db()

        jobs = db["jobs"]
        jobs.create_index([("is_active", 1)])
        jobs.create_index([("posted_by.user_id", 1), ("is_active", 1)])
        jobs.create_index([("created_at", -1)])

        users = db["users"]
        users.create_index([("email", 1)], unique=True)
        users.create_index([("role", 1), ("status", 1)])
        users.create_index([("is_active", 1), ("role", 1)])
        users.create_index([("reset_password.otp_hash", 1)], sparse=True)

        applications = db["applications"]
        applications.create_index([("user_id", 1), ("job_id", 1)], unique=True)
        applications.create_index([("user_id", 1), ("created_at", -1)])
        applications.create_index([("job_id", 1), ("created_at", -1)])

        recommendation_sessions = db["recommendation_sessions"]
        recommendation_sessions.create_index([("user_id", 1), ("created_at", -1)])

        recommendation_items = db["recommendation_items"]
        recommendation_items.create_index([("session_id", 1), ("rank", 1)])
        recommendation_items.create_index([("user_id", 1), ("created_at", -1)])
        recommendation_items.create_index([("job_id", 1), ("created_at", -1)])

        _indexes_initialized = True
