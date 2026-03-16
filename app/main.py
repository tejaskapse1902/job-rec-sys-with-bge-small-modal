from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api.routes import router
from app.api.auth_routes import router as auth_router
from app.api.admin_routes import router as admin_router
from app.api.jobs_routes import router as jobs_router
from app.api.user_routes import router as user_router
from app.api.applications_routes import router as applications_router
from app.api.recommendations_routes import router as recommendations_router
from app.api.reports_routes import router as reports_router
from app.api.external_jobs_routes import router as external_jobs_router
from app.services.index_manager import initialize_index, start_auto_refresh


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ✅ Fast, non-blocking startup
    try:
        initialize_index()
    except Exception as e:
        print(f"Index init failed: {e}")

    # ✅ Start refresh in background INSIDE the function
    start_auto_refresh(900)

    yield  # 👈 app is READY here

    print("App shutting down")


app = FastAPI(
    title="Job Recommendation API",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(jobs_router)
app.include_router(user_router)
app.include_router(applications_router)
app.include_router(recommendations_router)
app.include_router(reports_router)
app.include_router(external_jobs_router)

@app.get("/health")
def health():
    return {"status": "ok"}
