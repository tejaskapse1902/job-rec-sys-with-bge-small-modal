from pathlib import Path

import dotenv
import uvicorn


dotenv.load_dotenv(Path(__file__).resolve().parent / "app" / ".env")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
