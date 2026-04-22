# Backend README

This backend is a FastAPI service for authentication, job management, resume-based recommendations, applications, reporting, external job import, and Google Drive integration.

## Purpose

The backend is responsible for:

- user signup, login, profile lookup, and password reset
- employer approval workflow
- job CRUD with role-based access
- resume upload and parsing
- recommendation generation and persistence
- application submission and history
- admin and employer reports
- external job search/import
- FAISS index lifecycle management

## Tech Stack

- FastAPI
- Uvicorn / Gunicorn
- MongoDB + PyMongo
- Sentence Transformers
- FAISS
- spaCy
- Google Drive API
- SMTP email

## Entry Points

- `app/main.py`: FastAPI app setup, router registration, startup lifecycle
- `run.py`: local convenience launcher
- `Dockerfile`: production container entrypoint

## Folder Map

```text
backend/
|-- app/
|   |-- api/          # FastAPI routers
|   |-- core/         # auth, database, config, collection alias
|   |-- models/       # request/response schemas
|   |-- services/     # domain logic
|   `-- utils/        # file parsing helpers
|-- data/             # skills list, import CSV/XLSX, jobs.index
|-- tools/            # manual setup / maintenance scripts
|-- requirements.txt
|-- requirements.lock.txt
|-- Dockerfile
`-- README.md
```

## Main Routers

### Authentication

- `POST /auth/signup`
- `POST /auth/login`
- `GET /auth/me`
- `POST /auth/forgot-password`
- `POST /auth/reset-password`

File: `app/api/auth_routes.py`

### User Profile

- `GET /users/profile`
- `PATCH /users/profile`

File: `app/api/user_routes.py`

### Jobs

- `GET /jobs`
- `GET /jobs/{job_id}`
- `POST /jobs`
- `PUT /jobs/{job_id}`
- `DELETE /jobs/{job_id}`

File: `app/api/jobs_routes.py`

### Resume + Recommendation Session Creation

- `POST /recommend`
- `GET /resumes`
- `DELETE /resumes`
- `POST /admin/reload-index`

File: `app/api/routes.py`

### Recommendation History

- `GET /recommendations/latest`
- `POST /recommendations/{item_id}/not-apply-reason`

File: `app/api/recommendations_routes.py`

### Applications

- `POST /applications`
- `GET /applications/my-applications`

File: `app/api/applications_routes.py`

### Admin Employer Approval

- `GET /admin/employers/pending`
- `PATCH /admin/employers/{user_id}/approve`
- `PATCH /admin/employers/{user_id}/reject`

File: `app/api/admin_routes.py`

### Reports

- `GET /admin/reports/overview`
- `GET /admin/reports/candidates`
- `GET /admin/reports/employers`
- `GET /admin/reports/not-apply-reasons`
- `GET /employer/reports/overview`
- `GET /employer/reports/jobs`
- `GET /employer/reports/jobs/{job_id}/applicants`
- `GET /employer/reports/applications/{application_id}/resume`

File: `app/api/reports_routes.py`

### External Jobs

- `POST /admin/jobs/import/search`
- `POST /admin/jobs/import`

File: `app/api/external_jobs_routes.py`

## Core Domain Rules

### Roles

- `admin`
- `employer`
- `job_seeker`

### Employer Approval

- employer signup is allowed
- new employer accounts are created with `status: pending`
- pending employers cannot manage jobs until approved

### Job Management

- admins can manage all jobs
- active employers can manage only their own jobs
- deletes are soft deletes using `is_active = false`

### Recommendations

- only active jobs are loaded into the recommendation dataset
- new/imported jobs start with `indexed = false`
- those jobs affect recommendations only after index refresh

## Environment Variables

Use `backend/app/.env`. A template is available at [app/.env.example](app/.env.example).

### Required / Primary

- `MONGO_URI`
- `SECRET_KEY`
- `GDRIVE_RESUMES_FOLDER_ID`
- `GDRIVE_INDEX_FOLDER_ID`

### Password Reset Email

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_USE_TLS`
- `SMTP_FROM_EMAIL`
- `SMTP_FROM_NAME`
- `RESET_OTP_EXPIRE_MINUTES`

### Google Drive

- `GDRIVE_AUTH_MODE`
- `GDRIVE_SERVICE_ACCOUNT_JSON`
- `GDRIVE_SERVICE_ACCOUNT_FILE`
- `GDRIVE_OAUTH_TOKEN_FILE`
- `GDRIVE_OAUTH_TOKEN_JSON`
- `GDRIVE_INDEX_FILENAME`

### Recommendation Runtime

- `HF_CACHE_DIR`

### External Import

- `ENABLE_ARBEITNOW_IMPORT`

### Optional Tooling Variable

- `GDRIVE_OAUTH_CLIENT_FILE`

Used by `tools/gdrive_auth.py` to generate the OAuth token file.

Auth mode notes:

- `GDRIVE_AUTH_MODE=auto` tries service-account credentials first, then OAuth
- `GDRIVE_AUTH_MODE=service_account` is the recommended deployment mode
- `GDRIVE_AUTH_MODE=oauth` is convenient for local development after running `tools/gdrive_auth.py`
- files under `app/keys` are not committed to the repo, so production should use env-based secrets or a mounted secret file

## Local Setup

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

If you prefer the bundled wheel, you can install the local spaCy model file from the `backend/` folder instead.

Create `app/.env` from `app/.env.example`, then run:

```powershell
uvicorn app.main:app --reload
```

Or:

```powershell
python run.py
```

## Docker

Build:

```powershell
cd backend
docker build -t job-rec-backend .
```

Run:

```powershell
docker run -p 8000:8000 --env-file app/.env job-rec-backend
```

For cloud deployments, prefer setting `GDRIVE_AUTH_MODE=service_account` and injecting `GDRIVE_SERVICE_ACCOUNT_JSON` as a secret. If you stay on OAuth, you must also inject `GDRIVE_OAUTH_TOKEN_JSON` or mount the token file into the container.

On Railway, the container must listen on the runtime `PORT` variable. The Dockerfile is configured to bind Gunicorn to `0.0.0.0:${PORT:-8000}` for this reason.

## Data Storage

### MongoDB Collections

- `users`
- `jobs`
- `applications`
- `recommendation_sessions`
- `recommendation_items`

Collection indexes are created in `app/core/database.py`.

### Google Drive

The backend uses Drive for:

- uploaded resume files
- the shared FAISS index file `jobs.index`

Drive logic lives in `app/services/drive_service.py`.

## Job Schema Notes

The backend supports both:

- normalized job fields used by manual creation through the app
- legacy imported fields like `Job Title`, `Company Name`, and `Direct Link`

Normalization and response shaping live in `app/api/jobs_routes.py`.

## Recommendation Pipeline

1. The API receives a resume file on `POST /recommend`.
2. The file is saved temporarily and uploaded to Google Drive.
3. Resume text is parsed using the file readers and spaCy skill matching.
4. The recommender loads the FAISS index and active jobs.
5. Jobs are scored and sorted.
6. A recommendation session plus item snapshots are stored in MongoDB.

Primary files:

- `app/api/routes.py`
- `app/services/resume_parser.py`
- `app/services/skill_matcher.py`
- `app/services/recommender.py`

## Index Lifecycle

### Startup

On app startup:

- the backend downloads the current `jobs.index` from Google Drive
- the FAISS index is loaded into memory
- active jobs are loaded from MongoDB
- a background refresh loop starts

Main file: `app/services/index_manager.py`

### Admin Reload

`POST /admin/reload-index`:

- finds active jobs where `indexed != true`
- embeds those jobs
- appends them to the FAISS index
- uploads the updated index to Google Drive
- marks jobs as indexed
- reloads the live in-memory index

Main files:

- `app/services/index_builder.py`
- `app/api/routes.py`

## External Job Import

Provider currently supported:

- Arbeitnow

The backend can:

- search external jobs without saving
- import matching external jobs into MongoDB

Imported jobs:

- are stored as active jobs
- are marked `indexed = false`
- require index refresh before they participate in recommendations

Main file: `app/services/external_jobs.py`

## Tool Scripts

### `tools/gdrive_auth.py`

Creates a local Google OAuth token file for Drive access.

### `tools/build_faiss_index.py`

Builds a fresh FAISS index from all jobs and uploads it to Drive.

### `tools/incremental_index_builder.py`

Legacy/manual incremental index builder script. Useful as a maintenance helper outside the API path.

### `tools/upload_new_jobs_to_mongodb.py`

Imports `data/new_jobs.csv` into MongoDB.

## Files Worth Reading First

- `app/main.py`
- `app/core/database.py`
- `app/core/auth.py`
- `app/api/auth_routes.py`
- `app/api/jobs_routes.py`
- `app/api/routes.py`
- `app/services/recommender.py`
- `app/services/index_manager.py`
- `app/services/drive_service.py`

## Troubleshooting

### API starts but recommendations fail

Check:

- MongoDB connection
- Google Drive credentials
- `jobs.index` availability
- spaCy model installation

### Railway returns 502 for `/health` or every API route

This usually means the proxy cannot reach the app process. Check that the container is listening on Railway's injected `PORT` variable instead of a hardcoded port.

### `invalid_grant` or Drive auth failures

Usually means the OAuth token is expired, revoked, or missing from the deployed container. Regenerate the token and update the configured token source.

If startup says `OAuth token not found: /app/app/keys/gdrive_token.json`, the deployment is still using OAuth without a deployed token file. Fix it by either:

- switching to `GDRIVE_AUTH_MODE=service_account` and setting `GDRIVE_SERVICE_ACCOUNT_JSON`
- or keeping OAuth and setting `GDRIVE_OAUTH_TOKEN_JSON`

If you use a service account, share both Google Drive folders referenced by `GDRIVE_RESUMES_FOLDER_ID` and `GDRIVE_INDEX_FOLDER_ID` with the service account email.

### New jobs do not appear in recommendations

Those jobs are probably still `indexed = false`. Trigger the admin reload-index flow.

### Password reset email is not sent

Check all SMTP variables in `app/.env`.

### 401 redirects in the frontend

Usually means the JWT is missing, expired, or invalid relative to `SECRET_KEY`.

## Backend Summary For Handoff

If a new developer or AI needs to understand the backend quickly, the shortest useful path is:

1. `app/main.py`
2. `app/api/jobs_routes.py`
3. `app/api/routes.py`
4. `app/api/auth_routes.py`
5. `app/services/recommender.py`
6. `app/services/index_manager.py`
