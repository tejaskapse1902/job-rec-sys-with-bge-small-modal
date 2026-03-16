# Backend README

## Overview

This is the FastAPI backend for the Job Recommendation System.

It handles:

- authentication and authorization
- employer approval
- job CRUD
- profile APIs
- resume upload
- Google Drive storage
- resume parsing
- recommendation generation
- applications
- not-apply reason tracking
- admin reports
- external job import
- FAISS index initialization and reload

## Stack

- FastAPI
- Uvicorn
- Gunicorn
- MongoDB + PyMongo
- Sentence Transformers
- FAISS
- spaCy
- Google Drive API
- SMTP email

## Project Structure

```text
backend/
|-- app/
|   |-- api/
|   |-- core/
|   |-- models/
|   |-- services/
|   |-- utils/
|   `-- main.py
|-- data/
|-- tools/
|-- app/.env
|-- Dockerfile
|-- requirements.txt
|-- run.py
`-- README.md
```

## Requirements

- Python 3.10+
- MongoDB
- Google Drive API credentials
- spaCy English model

## Install

From the `backend/` directory:

```powershell
python -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

## Environment

Create `backend/app/.env`.

Example:

```env
MONGO_URI=mongodb://localhost:27017/job_recommendation
SECRET_KEY=change-this-secret
RESET_OTP_EXPIRE_MINUTES=10

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@example.com
SMTP_PASSWORD=your-app-password
SMTP_USE_TLS=true
SMTP_FROM_EMAIL=your-email@example.com
SMTP_FROM_NAME=JobMatch

GDRIVE_AUTH_MODE=oauth
GDRIVE_RESUMES_FOLDER_ID=your-google-drive-folder-id
GDRIVE_INDEX_FOLDER_ID=your-google-drive-index-folder-id
GDRIVE_INDEX_FILENAME=jobs.index
GDRIVE_OAUTH_TOKEN_FILE=app/keys/gdrive_token.json
GDRIVE_OAUTH_TOKEN_JSON=

HF_CACHE_DIR=

ENABLE_JSEARCH_IMPORT=false
RAPIDAPI_KEY=
RAPIDAPI_HOST=jsearch.p.rapidapi.com
```

Important config sources:

- MongoDB: [database.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/core/database.py:7)
- JWT auth: [auth.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/core/auth.py:13)
- OTP expiry: [auth_routes.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/api/auth_routes.py:21)
- SMTP mail: [email_service.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/services/email_service.py:6)
- Google Drive: [drive_service.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/services/drive_service.py:19)

## Run Locally

Option 1:

```powershell
uvicorn app.main:app --reload
```

Option 2:

```powershell
python run.py
```

Default local API URL:

```text
http://127.0.0.1:8000
```

Health check:

```text
GET /health
```

## Docker

Build:

```powershell
docker build -t job-rec-backend .
```

Run:

```powershell
docker run -p 8000:8000 --env-file app/.env job-rec-backend
```

Docker entrypoint is defined in [Dockerfile](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/Dockerfile:1).

## API Modules

### Authentication

- `POST /auth/signup`
- `POST /auth/login`
- `GET /auth/me`
- `POST /auth/forgot-password`
- `POST /auth/reset-password`

File:

- [auth_routes.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/api/auth_routes.py:1)

### Users

- `GET /users/profile`
- `PATCH /users/profile`

File:

- [user_routes.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/api/user_routes.py:1)

### Jobs

- `GET /jobs`
- `GET /jobs/{job_id}`
- `POST /jobs`
- `PUT /jobs/{job_id}`
- `DELETE /jobs/{job_id}`

File:

- [jobs_routes.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/api/jobs_routes.py:1)

### Applications

- `POST /applications`
- `GET /applications/my-applications`

File:

- [applications_routes.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/api/applications_routes.py:1)

### Recommendations

- `POST /recommend`
- `GET /recommendations/latest`
- `POST /recommendations/{item_id}/not-apply-reason`

Files:

- [routes.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/api/routes.py:27)
- [recommendations_routes.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/api/recommendations_routes.py:1)

### Admin

- `GET /admin/employers/pending`
- `PATCH /admin/employers/{user_id}/approve`
- `PATCH /admin/employers/{user_id}/reject`
- `POST /admin/reload-index`

Files:

- [admin_routes.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/api/admin_routes.py:1)
- [routes.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/api/routes.py:113)

### Reports

- `GET /admin/reports/overview`
- `GET /admin/reports/candidates`
- `GET /admin/reports/employers`
- `GET /admin/reports/not-apply-reasons`

File:

- [reports_routes.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/api/reports_routes.py:1)

### External Import

- `POST /admin/jobs/import/jsearch`

File:

- [external_jobs_routes.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/api/external_jobs_routes.py:1)

## Auth Rules

- public signup allows `job_seeker` and `employer`
- public admin signup is blocked
- employer signup creates `status: pending`
- only approved employers can post jobs
- admin can manage all jobs
- job seeker can apply to jobs

## Job Model Notes

The backend supports your MongoDB job schema, including fields such as:

- `Job Title`
- `Job Type`
- `Location`
- `Experience Level`
- `Salary Min (?)`
- `Salary Max (?)`
- `Min Education`
- `Category`
- `Openings`
- `Notice Period`
- `Year of Passing`
- `Direct Link`
- `Work Type`
- `Interview Type`
- `Company Name`
- `Company Website`
- `Company Description`
- `Job Description`
- `Requirements`
- `Responsibilities`
- `Skills`
- `created_date`
- `indexed`
- `is_active`

Normalization logic lives in [jobs_routes.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/api/jobs_routes.py:104).

## Recommendation Flow

1. user uploads resume to `POST /recommend`
2. backend parses the resume
3. resume is uploaded to Google Drive
4. recommendation engine loads FAISS index and Mongo job data
5. matching jobs are returned
6. recommendation session and recommendation items are stored in MongoDB

Relevant files:

- [routes.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/api/routes.py:27)
- [resume_parser.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/services/resume_parser.py:1)
- [recommender.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/services/recommender.py:1)

## Indexing Workflow

### Startup

On app startup:

- backend tries to load the FAISS index from Google Drive
- active jobs are loaded from MongoDB
- background refresh starts

This is handled in [main.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/main.py:14) and [index_manager.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/services/index_manager.py:67).

### Admin reload

`POST /admin/reload-index` now does real incremental indexing:

- finds active jobs where `indexed != true`
- generates embeddings for those jobs
- appends them to the existing FAISS index
- uploads the updated index to Google Drive
- marks those jobs as `indexed: true`
- reloads the live in-memory index

Relevant files:

- [index_builder.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/services/index_builder.py:54)
- [routes.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/api/routes.py:113)

## Google Drive

Drive is used for:

- uploaded resumes
- stored FAISS index file

Resume upload:

- [drive_service.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/services/drive_service.py:97)

Index upload/download:

- [drive_service.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/services/drive_service.py:164)

If your Drive OAuth token is expired or revoked, you may see:

```text
invalid_grant: Token has been expired or revoked.
```

Fix:

- generate a fresh Google OAuth token
- replace `app/keys/gdrive_token.json` or `GDRIVE_OAUTH_TOKEN_JSON`
- restart the backend

## OTP Email Reset

Forgot password uses email OTP.

Behavior:

- OTP is generated server-side
- OTP is hashed before storing
- OTP is emailed to user
- OTP expires after configured minutes

Relevant files:

- [auth_routes.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/api/auth_routes.py:191)
- [email_service.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/services/email_service.py:1)

## Database Collections

Main collections:

- `users`
- `jobs`
- `applications`
- `recommendation_sessions`
- `recommendation_items`

Index definitions are created in [database.py](d:/Clg Notes/MCA/4th Semester/job-rec-sys (production)/backend/app/core/database.py:1).

## Troubleshooting

### `POST /recommend` returns 500

Check:

- FAISS index exists
- MongoDB is reachable
- Google Drive credentials are valid
- `en_core_web_sm` is installed

### `invalid_grant` on startup or upload

Cause:

- Google Drive OAuth token expired or revoked

Fix:

- refresh the token
- update env or token file

### New jobs do not appear in recommendations

Cause:

- jobs are still `indexed: false`

Fix:

- use the admin reload-index action

### SMTP errors during forgot password

Check:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM_EMAIL`

### Local Windows permission issues for HF cache

The recommender now supports `HF_CACHE_DIR`. If needed, set it explicitly in `.env`.

## Notes

- This backend currently uses open CORS in development.
- Replace the default JWT secret before production use.
- Python 3.11+ is recommended for longer-term dependency compatibility.
