import boto3
import os
import dotenv
from app.services.drive_service import download_index_from_drive
from app.core.config import DATA_DIR

dotenv.load_dotenv()

LOCAL_PATH = f"{DATA_DIR}/jobs.index"

def download_index(force_update=True):
    os.makedirs("data", exist_ok=True)

    if os.path.exists(LOCAL_PATH):
        if force_update:
            print("♻️ Existing FAISS index found. Replacing with latest version...")
            os.remove(LOCAL_PATH)
        else:
            raise FileExistsError("FAISS index already exists locally")

    print("⬇️ Downloading FAISS index from Drive...")

    download_index_from_drive(LOCAL_PATH, force_update=True)

    print("✅ FAISS index downloaded and updated")
