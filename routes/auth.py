from fastapi import APIRouter, HTTPException, status, UploadFile, File, Depends
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
from bson import ObjectId

from config.settings import get_settings
from config.database import users_collection
from models.user import (
    UserCreate,
    UserLogin,
    UserOut,
    UserUpdate,
    TokenResponse,
)
from middleware.auth import get_current_user
from utils.cloudinary_upload import upload_image

settings = get_settings()
router = APIRouter(prefix="/api/auth", tags=["Authentication"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": user_id, "exp": expire}
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def user_doc_to_out(user: dict) -> UserOut:
    return UserOut(
        id=str(user["_id"]),
        name=user["name"],
        email=user["email"],
        phone=user["phone"],
        role=user.get("role", "user"),
        address=user.get("address"),
        latitude=user.get("latitude"),
        longitude=user.get("longitude"),
        profile_image=user.get("profile_image"),
        created_at=user.get("created_at", ""),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate):
    # Check if email already exists
    existing_email = await users_collection.find_one({"email": user_data.email})
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Check if phone already exists
    existing_phone = await users_collection.find_one({"phone": user_data.phone})
    if existing_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number already registered",
        )

    # Hash password and create user
    hashed_password = pwd_context.hash(user_data.password)
    user_doc = {
        "name": user_data.name,
        "email": user_data.email,
        "phone": user_data.phone,
        "password": hashed_password,
        "role": "user",
        "address": None,
        "latitude": None,
        "longitude": None,
        "profile_image": None,
        "created_at": datetime.utcnow().isoformat(),
    }

    result = await users_collection.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id

    token = create_access_token(str(result.inserted_id))
    return TokenResponse(
        access_token=token,
        user=user_doc_to_out(user_doc),
    )


@router.post("/login", response_model=TokenResponse)
async def login(user_data: UserLogin):
    user = await users_collection.find_one({"email": user_data.email})
    if not user or not pwd_context.verify(user_data.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(str(user["_id"]))
    return TokenResponse(
        access_token=token,
        user=user_doc_to_out(user),
    )


@router.get("/me", response_model=UserOut)
async def get_me(current_user: dict = Depends(get_current_user)):
    return user_doc_to_out(current_user)


@router.put("/me", response_model=UserOut)
async def update_profile(
    update_data: UserUpdate,
    current_user: dict = Depends(get_current_user),
):
    update_fields = {k: v for k, v in update_data.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    await users_collection.update_one(
        {"_id": current_user["_id"]},
        {"$set": update_fields},
    )

    updated_user = await users_collection.find_one({"_id": current_user["_id"]})
    return user_doc_to_out(updated_user)


@router.post("/me/profile-image", response_model=UserOut)
async def upload_profile_image(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    image_url = await upload_image(file, folder="medical_store/profiles")
    await users_collection.update_one(
        {"_id": current_user["_id"]},
        {"$set": {"profile_image": image_url}},
    )
    updated_user = await users_collection.find_one({"_id": current_user["_id"]})
    return user_doc_to_out(updated_user)
