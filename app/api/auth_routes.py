from fastapi import APIRouter, HTTPException, status, Depends
from datetime import datetime
from bson import ObjectId

from app.models.user import UserCreate, UserLogin, UserResponse, Token
from app.core.auth import verify_password, create_access_token, get_current_user
from app.core.user_db import users_collection

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/signup", response_model=Token, status_code=status.HTTP_201_CREATED)
async def signup(user_data: UserCreate):
    """Register a new user"""
    
    # Check if user already exists
    existing_user = users_collection.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Hash password
    # hashed_password = hash_password(user_data.password)
    
    # Create user document
    user_doc = {
        "email": user_data.email,
        "full_name": user_data.full_name,
        "role": user_data.role,
        "password": user_data.password,
        "created_at": datetime.utcnow()
    }
    
    # Insert into database
    result = users_collection.insert_one(user_doc)
    
    # Create access token
    access_token = create_access_token(
        data={"sub": user_data.email, "role": user_data.role}
    )
    
    # Prepare user response
    user_response = UserResponse(
        id=str(result.inserted_id),
        email=user_data.email,
        full_name=user_data.full_name,
        role=user_data.role,
        created_at=user_doc["created_at"]
    )
    
    return Token(access_token=access_token, user=user_response)


@router.post("/login", response_model=Token)
async def login(credentials: UserLogin):
    """Login user and return JWT token"""
    
    # Find user by email
    user = users_collection.find_one({"email": credentials.email})
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # Verify password
    if not verify_password(credentials.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # Create access token
    access_token = create_access_token(
        data={"sub": user["email"], "role": user["role"]}
    )
    
    # Prepare user response
    user_response = UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        full_name=user["full_name"],
        role=user["role"],
        created_at=user["created_at"]
    )
    
    return Token(access_token=access_token, user=user_response)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user information"""
    
    user = users_collection.find_one({"email": current_user["email"]})
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        full_name=user["full_name"],
        role=user["role"],
        created_at=user["created_at"]
    )
