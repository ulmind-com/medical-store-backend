from fastapi import APIRouter, Request, HTTPException, status
from svix.webhooks import Webhook, WebhookVerificationError
from config.settings import get_settings
from config.database import users_collection
from datetime import datetime

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])
settings = get_settings()

@router.post("/clerk")
async def clerk_webhook(request: Request):
    """Handle Clerk user events securely verified by Svix signatures."""
    headers = request.headers
    svix_id = headers.get("svix-id")
    svix_timestamp = headers.get("svix-timestamp")
    svix_signature = headers.get("svix-signature")

    if not svix_id or not svix_timestamp or not svix_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Svix verification headers",
        )

    body = await request.body()
    body_str = body.decode("utf-8")

    webhook_secret = settings.CLERK_WEBHOOK_SECRET
    if not webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured in backend settings",
        )

    try:
        wh = Webhook(webhook_secret)
        payload = wh.verify(body_str, {
            "svix-id": svix_id,
            "svix-timestamp": svix_timestamp,
            "svix-signature": svix_signature,
        })
    except WebhookVerificationError as err:
        print(f"Webhook signature verification failed: {err}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Svix signature",
        )

    event_type = payload.get("type")
    event_data = payload.get("data", {})

    if event_type == "user.created":
        clerk_id = event_data.get("id")
        email_addresses = event_data.get("email_addresses", [])
        primary_email = ""
        for email_item in email_addresses:
            if email_item.get("id") == event_data.get("primary_email_address_id"):
                primary_email = email_item.get("email_address")
                break
        if not primary_email and email_addresses:
            primary_email = email_addresses[0].get("email_address")

        phone_numbers = event_data.get("phone_numbers", [])
        primary_phone = ""
        for phone_item in phone_numbers:
            if phone_item.get("id") == event_data.get("primary_phone_number_id"):
                primary_phone = phone_item.get("phone_number")
                break
        if not primary_phone and phone_numbers:
            primary_phone = phone_numbers[0].get("phone_number")

        first_name = event_data.get("first_name") or ""
        last_name = event_data.get("last_name") or ""
        full_name = f"{first_name} {last_name}".strip() or "User"
        profile_image = event_data.get("image_url") or event_data.get("profile_image_url")

        role = event_data.get("public_metadata", {}).get("role", "user")

        user_doc = {
            "clerk_id": clerk_id,
            "name": full_name,
            "email": primary_email.lower() if primary_email else "",
            "phone": primary_phone,
            "role": role,
            "profile_image": profile_image,
            "created_at": datetime.utcnow().isoformat(),
        }

        # Check if user already exists in DB by email to link them
        if primary_email:
            existing = await users_collection.find_one({"email": primary_email.lower()})
            if existing:
                await users_collection.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {
                        "clerk_id": clerk_id,
                        "name": full_name,
                        "phone": primary_phone if primary_phone else existing.get("phone"),
                        "profile_image": profile_image if profile_image else existing.get("profile_image"),
                    }}
                )
                return {"status": "success", "message": "Linked Clerk ID to existing user account"}

        # Upsert the user profile by clerk_id
        await users_collection.update_one(
            {"clerk_id": clerk_id},
            {"$set": user_doc},
            upsert=True
        )

    elif event_type == "user.updated":
        clerk_id = event_data.get("id")
        email_addresses = event_data.get("email_addresses", [])
        primary_email = ""
        for email_item in email_addresses:
            if email_item.get("id") == event_data.get("primary_email_address_id"):
                primary_email = email_item.get("email_address")
                break

        phone_numbers = event_data.get("phone_numbers", [])
        primary_phone = ""
        for phone_item in phone_numbers:
            if phone_item.get("id") == event_data.get("primary_phone_number_id"):
                primary_phone = phone_item.get("phone_number")
                break

        first_name = event_data.get("first_name") or ""
        last_name = event_data.get("last_name") or ""
        full_name = f"{first_name} {last_name}".strip() or "User"
        profile_image = event_data.get("image_url") or event_data.get("profile_image_url")
        role = event_data.get("public_metadata", {}).get("role", "user")

        update_doc = {
            "name": full_name,
            "role": role,
        }
        if primary_email:
            update_doc["email"] = primary_email.lower()
        if primary_phone:
            update_doc["phone"] = primary_phone
        if profile_image:
            update_doc["profile_image"] = profile_image

        await users_collection.update_one(
            {"clerk_id": clerk_id},
            {"$set": update_doc}
        )

    elif event_type == "user.deleted":
        clerk_id = event_data.get("id")
        await users_collection.delete_one({"clerk_id": clerk_id})

    return {"status": "success"}
