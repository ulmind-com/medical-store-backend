from fastapi import APIRouter, HTTPException, status, UploadFile, File, Depends
from bson import ObjectId
from datetime import datetime

from config.settings import get_settings
from config.database import users_collection
from models.user import UserOut, UserUpdate
from middleware.auth import get_current_user
from utils.cloudinary_upload import upload_image

settings = get_settings()
router = APIRouter(prefix="/api/auth", tags=["Authentication"])


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
        expo_push_token=user.get("expo_push_token"),
        created_at=user.get("created_at", ""),
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
