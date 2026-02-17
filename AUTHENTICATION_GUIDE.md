# Authentication Guide

## Overview
Authentication has been added to your job recommendation system using JWT (JSON Web Tokens) without modifying any existing working code.

## New Files Created

1. **app/models/user.py** - User data models (UserCreate, UserLogin, UserResponse, Token)
2. **app/core/auth.py** - Authentication utilities (JWT, password hashing, middleware)
3. **app/core/user_db.py** - MongoDB users collection
4. **app/api/auth_routes.py** - Authentication endpoints (signup, login, /me)

## New Dependencies
Added to requirements.txt:
- `python-jose[cryptography]` - JWT token handling
- `passlib[bcrypt]` - Password hashing
- `email-validator` - Email validation for Pydantic

## Setup Instructions

### 1. Install New Dependencies
```bash
pip install -r requirements.txt
```

### 2. Add SECRET_KEY to .env file
Add this line to your `app/.env` file:
```
SECRET_KEY=your-super-secret-key-change-this-in-production-use-a-long-random-string
```

**Important**: Generate a secure secret key for production! You can use:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## API Endpoints

### Authentication Endpoints (New)

#### 1. Signup (Register New User)
```
POST /auth/signup
Content-Type: application/json

{
  "email": "user@example.com",
  "full_name": "John Doe",
  "password": "yourpassword",
  "role": "user"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "user": {
    "id": "65abc123...",
    "email": "user@example.com",
    "full_name": "John Doe",
    "role": "user",
    "created_at": "2026-02-09T10:30:00"
  }
}
```

#### 2. Login
```
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "yourpassword"
}
```

**Response:** Same as signup

#### 3. Get Current User Info
```
GET /auth/me
Authorization: Bearer <your_access_token>
```

**Response:**
```json
{
  "id": "65abc123...",
  "email": "user@example.com",
  "full_name": "John Doe",
  "role": "user",
  "created_at": "2026-02-09T10:30:00"
}
```

### Your Existing Endpoints (Unchanged)
All your existing endpoints continue to work exactly as before:
- `POST /recommend` - Job recommendations
- `GET /resumes` - List resumes
- `DELETE /resumes` - Delete resume
- `POST /admin/reload-index` - Reload index
- `GET /health` - Health check

## How to Protect Your Existing Routes (Optional)

If you want to add authentication to your existing routes, you can do so without breaking them. Here's how:

### Example: Protect the /recommend endpoint

**Original route (in app/api/routes.py):**
```python
@router.post("/recommend")
async def recommend(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    # ... your existing code
```

**Protected route (add Depends):**
```python
from app.core.auth import get_current_user

@router.post("/recommend")
async def recommend(
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)  # Add this line
):
    # ... your existing code (no changes needed)
    # You can access user info via current_user["email"] and current_user["role"]
```

### Example: Admin-only endpoint

**Protect admin endpoint:**
```python
from app.core.auth import get_current_admin

@router.post("/admin/reload-index")
def reload_index(current_admin: dict = Depends(get_current_admin)):  # Only admins can access
    reload_index_and_jobs()
    return {"status": "reloaded"}
```

## User Roles

- **user** - Regular user (default)
- **admin** - Administrator with special permissions

## Testing with cURL

### 1. Signup
```bash
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","full_name":"Test User","password":"testpass123","role":"user"}'
```

### 2. Login
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpass123"}'
```

### 3. Access Protected Route
```bash
curl -X GET http://localhost:8000/auth/me \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN_HERE"
```

## Security Features

✅ Password hashing using bcrypt  
✅ JWT token authentication  
✅ Token expiration (7 days by default)  
✅ Email uniqueness validation  
✅ Role-based access control (user/admin)  
✅ Secure password verification  

## Important Notes

1. **Your existing code is untouched** - All your working endpoints continue to function exactly as before
2. **Authentication is optional** - You can gradually add it to endpoints that need protection
3. **SECRET_KEY security** - Make sure to use a strong, random secret key in production
4. **HTTPS in production** - Always use HTTPS in production to protect tokens in transit
5. **Token storage** - Frontend should store tokens securely (httpOnly cookies or secure storage)

## Next Steps

1. Install dependencies: `pip install -r requirements.txt`
2. Add `SECRET_KEY` to your `.env` file
3. Restart your FastAPI server
4. Test the authentication endpoints
5. Optionally protect your existing endpoints by adding `Depends(get_current_user)` or `Depends(get_current_admin)`

Your backend is now ready with authentication! 🎉
