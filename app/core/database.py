import os
from pymongo import MongoClient
import dotenv 

dotenv.load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable not set")

DB_NAME = "job_recommendation"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

jobs_collection = db["jobs"]
jobs_collection.create_index([("is_active", 1)])
jobs_collection.create_index([("posted_by.user_id", 1), ("is_active", 1)])
jobs_collection.create_index([("created_at", -1)])

users_collection = db["users"]
users_collection.create_index([("email", 1)], unique=True)
users_collection.create_index([("role", 1), ("status", 1)])
users_collection.create_index([("is_active", 1), ("role", 1)])
users_collection.create_index([("reset_password.otp_hash", 1)], sparse=True)

applications_collection = db["applications"]
applications_collection.create_index([("user_id", 1), ("job_id", 1)], unique=True)
applications_collection.create_index([("user_id", 1), ("created_at", -1)])
applications_collection.create_index([("job_id", 1), ("created_at", -1)])

recommendation_sessions_collection = db["recommendation_sessions"]
recommendation_sessions_collection.create_index([("user_id", 1), ("created_at", -1)])

recommendation_items_collection = db["recommendation_items"]
recommendation_items_collection.create_index([("session_id", 1), ("rank", 1)])
recommendation_items_collection.create_index([("user_id", 1), ("created_at", -1)])
recommendation_items_collection.create_index([("job_id", 1), ("created_at", -1)])
