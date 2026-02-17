"""
EXAMPLE FILE - Shows how to add authentication to your existing routes.py
This is just a reference - your original routes.py remains unchanged and working.

To use authentication on your existing endpoints, you can gradually add 
Depends(get_current_user) or Depends(get_current_admin) to the routes that need protection.
"""

from fastapi import APIRouter, UploadFile, File, BackgroundTasks, Depends
from pydantic import BaseModel
from app.services.resume_parser import parse_resume_file
from app.services.recommender import recommend_jobs
from backend.app.services.drive_service import upload_to_s3, list_resumes, delete_resume
from app.services.index_manager import reload_index_and_jobs
from app.core.auth import get_current_user, get_current_admin  # Import auth dependencies
import os
import tempfile

router = APIRouter()


class DeleteRequest(BaseModel):
    key: str
    

# EXAMPLE: Protected endpoint - requires authentication
@router.post("/recommend")
async def recommend(
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)  # ✅ Added authentication
):
    """
    Now this endpoint requires a valid JWT token.
    You can access user info via:
    - current_user["email"]
    - current_user["role"]
    """
    
    suffix = os.path.splitext(file.filename)[1]

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name

    try:
        background_tasks.add_task(upload_to_s3, tmp_path, file.filename, delete_after=True)
        
        resume_text = parse_resume_file(file)
        results = recommend_jobs(resume_text)

        return {
            "filename": file.filename,
            "no. of recommendations": len(results),
            "recommendations": results,
            "user": current_user["email"]  # ✅ Can include user info in response
        }
    finally:
        pass


# EXAMPLE: Protected endpoint - requires authentication
@router.get("/resumes")
def get_all_resumes(current_user: dict = Depends(get_current_user)):  # ✅ Added authentication
    """
    Only authenticated users can list resumes
    """
    return list_resumes()


# EXAMPLE: Protected endpoint - requires authentication
@router.delete("/resumes")
def delete_resume_api(req: DeleteRequest, current_user: dict = Depends(get_current_user)):  # ✅ Added authentication
    """
    Only authenticated users can delete resumes
    """
    delete_resume(req.key)
    return {"status": "deleted"}


# EXAMPLE: Admin-only endpoint - requires admin role
@router.post("/admin/reload-index")
def reload_index(current_admin: dict = Depends(get_current_admin)):  # ✅ Added admin-only protection
    """
    Only admins can reload the index.
    get_current_admin checks that the user has role="admin"
    """
    reload_index_and_jobs()
    return {
        "status": "reloaded",
        "reloaded_by": current_admin["email"]  # ✅ Track who performed the action
    }


"""
SUMMARY OF CHANGES:

1. Import authentication dependencies:
   from app.core.auth import get_current_user, get_current_admin

2. Add to any endpoint that needs authentication:
   current_user: dict = Depends(get_current_user)

3. Add to admin-only endpoints:
   current_admin: dict = Depends(get_current_admin)

4. Access user information:
   - current_user["email"]
   - current_user["role"]

REMEMBER: This is just an example. Your original routes.py is still working.
You can add authentication gradually to the endpoints that need it.
"""
