from fastapi import APIRouter, HTTPException, status, UploadFile, File, Depends
from bson import ObjectId
from datetime import datetime

from config.settings import get_settings
from config.database import users_collection
from models.user import UserOut, UserUpdate, ClerkUpsertIn
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
async def upsert_me(
    body: ClerkUpsertIn = ClerkUpsertIn(),
    payload: dict = Depends(get_clerk_payload),
):
    """
    Create or update MongoDB user from Clerk JWT claims + profile data
    sent by the app. Idempotent — safe to call on every login.

    NOTE: Clerk's default session JWT does NOT include name/email claims,
    so the app sends the profile from its Clerk user object in the body.
    Identity (clerk_id) always comes from the verified token, never the body.
    """
    clerk_id = payload.get("sub")
    if not clerk_id:
        raise HTTPException(status_code=400, detail="Invalid token: missing sub")

    # Email: JWT claims first (present only with a custom JWT template),
    # then the profile sent by the app.
    email = (
        payload.get("email")
        or payload.get("primary_email_address")
        or body.email
        or ""
    ).strip().lower()

    # Name: claims → app-provided profile → "User"
    first = payload.get("first_name") or payload.get("given_name") or ""
    last  = payload.get("last_name")  or payload.get("family_name") or ""
    name  = (
        f"{first} {last}".strip()
        or payload.get("name")
        or (body.name or "").strip()
        or "User"
    )

    profile_image = (
        payload.get("image_url")
        or payload.get("picture")
        or (body.profile_image or "").strip()
        or ""
    )
    role = payload.get("public_metadata", {}).get("role", "user") if isinstance(payload.get("public_metadata"), dict) else "user"

    now = datetime.utcnow().isoformat()

    # Try to find existing user by clerk_id first, then by email
    existing = await users_collection.find_one({"clerk_id": clerk_id})
    if not existing and email:
        existing = await users_collection.find_one({"email": email})

    if existing:
        update = {
            "clerk_id": clerk_id,
            "role": existing.get("role", role),  # preserve existing role
        }
        # Fill/repair name: write it when we have a real one and the stored
        # record is missing it or still has the "User" placeholder.
        if name and name != "User":
            if not existing.get("name") or existing.get("name") == "User":
                update["name"] = name
        if email and not existing.get("email"):
            update["email"] = email
        if profile_image and not existing.get("profile_image"):
            update["profile_image"] = profile_image

        phone = (payload.get("phone_number") or payload.get("phone") or body.phone or "").strip()
        if phone and not existing.get("phone"):
            update["phone"] = phone

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
        phone = (payload.get("phone_number") or payload.get("phone") or body.phone or "").strip()
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
