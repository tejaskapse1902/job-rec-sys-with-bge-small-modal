import os
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive"]

BASE_DIR = Path(__file__).resolve().parents[1]  # backend/
CLIENT_FILE = os.getenv("GDRIVE_OAUTH_CLIENT_FILE", "app/keys/gdrive_oauth_client.json")
TOKEN_FILE = os.getenv("GDRIVE_OAUTH_TOKEN_FILE", "app/keys/gdrive_token.json")

client_path = (BASE_DIR / CLIENT_FILE).resolve()
token_path = (BASE_DIR / TOKEN_FILE).resolve()

if not client_path.exists():
    raise FileNotFoundError(f"OAuth client JSON not found: {client_path}")

flow = InstalledAppFlow.from_client_secrets_file(str(client_path), SCOPES)
creds = flow.run_local_server(port=0)

token_path.parent.mkdir(parents=True, exist_ok=True)
token_path.write_text(creds.to_json(), encoding="utf-8")

print("✅ OAuth token saved to:", token_path)
print("➡️ Next: copy this token JSON for deployment (see steps).")
