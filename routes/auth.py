from fastapi import APIRouter, HTTPException, status, UploadFile, File, Depends
from bson import ObjectId
from datetime import datetime

from config.settings import get_settings
from config.database import users_collection
from models.user import UserOut, UserUpdate
from middleware.auth import get_current_user, get_clerk_payload
from utils.cloudinary_upload import upload_image

settings = get_settings()
router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def user_doc_to_out(user: dict) -> UserOut:
    return UserOut(
        id=str(user["_id"]),
        name=user.get("name") or "User",
        email=user.get("email") or "",
        phone=user.get("phone"),
        role=user.get("role", "user"),
        address=user.get("address"),
        latitude=user.get("latitude"),
        longitude=user.get("longitude"),
        profile_image=user.get("profile_image"),
        expo_push_token=user.get("expo_push_token"),
        created_at=user.get("created_at", ""),
    )



# ─────────────────────────────────────────────────────────────────────────────
# POST /api/auth/upsert
# ─────────────────────────────────────────────────────────────────────────────
# Called by the app immediately after Clerk sign-in/sign-up.
# Reads the Clerk JWT claims and creates/updates the user in MongoDB.
# This is the RELIABLE fallback when the Svix webhook is not configured.
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/upsert", response_model=UserOut)
async def upsert_me(payload: dict = Depends(get_clerk_payload)):
    """
    Create or update MongoDB user from Clerk JWT claims.
    Idempotent — safe to call on every login.
    """
    clerk_id = payload.get("sub")
    if not clerk_id:
        raise HTTPException(status_code=400, detail="Invalid token: missing sub")

    # Clerk puts email in different claims depending on version
    email = (
        payload.get("email")
        or payload.get("primary_email_address")
        or ""
    ).lower()

    # Build name from first/last name claims
    first = payload.get("first_name") or payload.get("given_name") or ""
    last  = payload.get("last_name")  or payload.get("family_name") or ""
    name  = f"{first} {last}".strip() or payload.get("name") or "User"

    profile_image = payload.get("image_url") or payload.get("picture") or ""
    role = payload.get("public_metadata", {}).get("role", "user") if isinstance(payload.get("public_metadata"), dict) else "user"

    now = datetime.utcnow().isoformat()

    # Try to find existing user by clerk_id first, then by email
    existing = await users_collection.find_one({"clerk_id": clerk_id})
    if not existing and email:
        existing = await users_collection.find_one({"email": email})

    if existing:
        # Update existing record — never overwrite name/phone if already set
        update = {
            "clerk_id": clerk_id,
            "role": existing.get("role", role),  # preserve existing role
        }
        if name and name != "User":
            update["name"] = name
        if email:
            update["email"] = email
        if profile_image:
            update["profile_image"] = profile_image

        await users_collection.update_one(
            {"_id": existing["_id"]},
            {"$set": update}
        )
        user = await users_collection.find_one({"_id": existing["_id"]})
    else:
        # Create new user record
        user_doc = {
            "clerk_id": clerk_id,
            "name": name,
            "email": email,
            "role": role,
            "profile_image": profile_image,
            "created_at": now,
        }
        
        # Only set phone if actually provided and not empty
        phone = (payload.get("phone_number") or payload.get("phone") or "").strip()
        if phone:
            user_doc["phone"] = phone

        result = await users_collection.insert_one(user_doc)
        user = await users_collection.find_one({"_id": result.inserted_id})

    return user_doc_to_out(user)










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
