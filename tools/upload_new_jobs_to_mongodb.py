import sys
import os
import dotenv

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

ENV_PATH = os.path.join(PROJECT_ROOT, "app", ".env")
dotenv.load_dotenv(ENV_PATH)

import pandas as pd
from pymongo import MongoClient
from datetime import datetime
from app.core.config import DATA_DIR

# ===== MongoDB Config =====
MONGO_URI = os.getenv("MONGO_URI")   # change if using Atlas
DB_NAME = "job_recommendation"
COLLECTION_NAME = "jobs"

CSV_PATH = f"{DATA_DIR}/new_jobs.csv"
# ==========================

def main():
    df = pd.read_csv(CSV_PATH)

    # Add system fields
    df["created_date"] = datetime.utcnow()
    df["indexed"] = False   

    # Convert to dict
    records = df.to_dict(orient="records")

    # MongoDB connection
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    # Insert into MongoDB
    result = collection.insert_many(records)

    print(f"✅ Inserted {len(result.inserted_ids)} jobs successfully!")

if __name__ == "__main__":
    main()
