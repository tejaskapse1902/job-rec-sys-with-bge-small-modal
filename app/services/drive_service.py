import os
import io
import json
import mimetypes
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path
import time
from io import BytesIO
from googleapiclient.http import MediaIoBaseUpload


import dotenv
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Load .env (local/dev)
dotenv.load_dotenv()
dotenv.load_dotenv("app/.env")

SCOPES = ["https://www.googleapis.com/auth/drive"]

BASE_DIR = Path(__file__).resolve().parents[2]  # backend/

AUTH_MODE = os.getenv("GDRIVE_AUTH_MODE", "oauth").lower()

OAUTH_CLIENT_FILE = os.getenv("GDRIVE_OAUTH_CLIENT_FILE", "app/keys/gdrive_oauth_client.json")
OAUTH_TOKEN_FILE = os.getenv("GDRIVE_OAUTH_TOKEN_FILE", "app/keys/gdrive_token.json")

# For deployment (recommended): store token json in env
OAUTH_TOKEN_JSON_ENV = os.getenv("GDRIVE_OAUTH_TOKEN_JSON", "")

RESUMES_FOLDER_ID = os.getenv("GDRIVE_RESUMES_FOLDER_ID", "")
INDEX_FOLDER_ID = os.getenv("GDRIVE_INDEX_FOLDER_ID", "")
INDEX_FILENAME = os.getenv("GDRIVE_INDEX_FILENAME", "jobs.index")


def _abs_path(rel: str) -> str:
    return str((BASE_DIR / rel).resolve())


def _guess_mime(path: str) -> str:
    mt, _ = mimetypes.guess_type(path)
    return mt or "application/octet-stream"


def _load_oauth_creds() -> Credentials:
    """
    Loads OAuth credentials from:
    1) env var GDRIVE_OAUTH_TOKEN_JSON (deployment)
    2) token file (local)
    Refreshes if expired and saves back (env cannot be written, file can).
    """
    # 1) Deployment: token json in env
    if OAUTH_TOKEN_JSON_ENV.strip():
        info = json.loads(OAUTH_TOKEN_JSON_ENV)
        creds = Credentials.from_authorized_user_info(info, SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds

    # 2) Local: token file
    token_path = Path(_abs_path(OAUTH_TOKEN_FILE))
    if not token_path.exists():
        raise FileNotFoundError(
            f"OAuth token not found: {token_path}. "
            f"Run: python tools/gdrive_auth.py"
        )

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Save refreshed token locally
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return creds


def _drive():
    if AUTH_MODE != "oauth":
        raise RuntimeError("This project is configured for OAuth. Set GDRIVE_AUTH_MODE=oauth.")
    creds = _load_oauth_creds()
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _find_file_by_name(folder_id: str, name: str):
    service = _drive()
    q = f"'{folder_id}' in parents and name = '{name}' and trashed = false"
    resp = service.files().list(q=q, fields="files(id,name,modifiedTime,size)", pageSize=10).execute()
    files = resp.get("files", [])
    return files[0] if files else None


# ==================================================
# RESUMES
# ==================================================

def upload_to_drive(file_path: str, original_name: str, delete_after: bool = False) -> str:
    if not RESUMES_FOLDER_ID:
        raise RuntimeError("GDRIVE_RESUMES_FOLDER_ID missing in env")

    ext = os.path.splitext(original_name)[1] or ""
    drive_name = f"{uuid4()}{ext}"

    # ✅ Read file into memory first (releases file lock)
    with open(file_path, "rb") as f:
        data = f.read()

    service = _drive()

    media = MediaIoBaseUpload(
        BytesIO(data),
        mimetype=_guess_mime(original_name),
        resumable=True
    )

    created = service.files().create(
        body={"name": drive_name, "parents": [RESUMES_FOLDER_ID]},
        media_body=media,
        fields="id"
    ).execute()

    # ✅ Now deletion is safe (file not used by Drive client anymore)
    if delete_after:
        _safe_delete(file_path)

    return created["id"]



def list_resumes() -> list:
    if not RESUMES_FOLDER_ID:
        raise RuntimeError("GDRIVE_RESUMES_FOLDER_ID missing in env")

    service = _drive()
    q = f"'{RESUMES_FOLDER_ID}' in parents and trashed = false"

    results = []
    page_token = None
    while True:
        resp = service.files().list(
            q=q,
            fields="nextPageToken, files(id,name,size,modifiedTime)",
            pageToken=page_token,
            pageSize=100
        ).execute()

        for f in resp.get("files", []):
            results.append({
                "key": f["id"],
                "name": f.get("name", ""),
                "size": int(f.get("size") or 0),
                "modifiedTime": f.get("modifiedTime", "")
            })

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return results


def delete_resume(file_id: str):
    service = _drive()
    service.files().delete(fileId=file_id).execute()


# ==================================================
# FAISS INDEX
# ==================================================

def get_drive_last_modified() -> datetime | None:
    if not INDEX_FOLDER_ID:
        raise RuntimeError("GDRIVE_INDEX_FOLDER_ID missing in env")

    meta = _find_file_by_name(INDEX_FOLDER_ID, INDEX_FILENAME)
    if not meta:
        return None

    iso = meta["modifiedTime"].replace("Z", "+00:00")
    return datetime.fromisoformat(iso).astimezone(timezone.utc)


def download_index_from_drive(local_path: str, force_update: bool = True):
    if not INDEX_FOLDER_ID:
        raise RuntimeError("GDRIVE_INDEX_FOLDER_ID missing in env")

    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    if os.path.exists(local_path) and force_update:
        os.remove(local_path)

    meta = _find_file_by_name(INDEX_FOLDER_ID, INDEX_FILENAME)
    if not meta:
        raise FileNotFoundError(f"{INDEX_FILENAME} not found in Drive indexes folder")

    service = _drive()
    request = service.files().get_media(fileId=meta["id"])

    fh = io.FileIO(local_path, "wb")
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()


def upload_index_to_drive(local_path: str):
    if not INDEX_FOLDER_ID:
        raise RuntimeError("GDRIVE_INDEX_FOLDER_ID missing in env")

    if not os.path.exists(local_path):
        raise FileNotFoundError(f"Index file not found: {local_path}")

    service = _drive()
    existing = _find_file_by_name(INDEX_FOLDER_ID, INDEX_FILENAME)

    media = MediaFileUpload(local_path, mimetype="application/octet-stream", resumable=True)

    if existing:
        service.files().update(
            fileId=existing["id"],
            media_body=media
        ).execute()
    else:
        service.files().create(
            body={"name": INDEX_FILENAME, "parents": [INDEX_FOLDER_ID]},
            media_body=media
        ).execute()

def _safe_delete(path: str, tries: int = 8, delay: float = 0.4):
    for _ in range(tries):
        try:
            if os.path.exists(path):
                os.remove(path)
            return
        except PermissionError:
            time.sleep(delay)
    # final attempt
    if os.path.exists(path):
        os.remove(path)

