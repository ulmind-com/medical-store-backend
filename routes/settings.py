from fastapi import APIRouter, HTTPException, Depends
from config.database import settings_collection
from models.settings import ShopSettings, ShopSettingsUpdate
from middleware.auth import get_admin_user, get_current_user

router = APIRouter(prefix="/api/settings", tags=["Settings"])


@router.get("/shop", response_model=ShopSettings)
async def get_shop_settings(current_user: dict = Depends(get_current_user)):
    doc = await settings_collection.find_one({"key": "shop_config"})
    if not doc:
        return ShopSettings()
    return ShopSettings(
        shop_name=doc.get("shop_name", "Medical Store"),
        shop_address=doc.get("shop_address", ""),
        shop_phone=doc.get("shop_phone", ""),
        shop_latitude=doc.get("shop_latitude", 0),
        shop_longitude=doc.get("shop_longitude", 0),
        free_delivery_radius_km=doc.get("free_delivery_radius_km", 1.0),
        per_km_delivery_charge=doc.get("per_km_delivery_charge", 10.0),
        min_order_for_free_delivery=doc.get("min_order_for_free_delivery", 0),
    )


@router.put("/shop", response_model=ShopSettings)
async def update_shop_settings(
    data: ShopSettingsUpdate,
    admin: dict = Depends(get_admin_user),
):
    update_fields = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    await settings_collection.update_one(
        {"key": "shop_config"},
        {"$set": update_fields},
        upsert=True,
    )

    doc = await settings_collection.find_one({"key": "shop_config"})
    return ShopSettings(
        shop_name=doc.get("shop_name", "Medical Store"),
        shop_address=doc.get("shop_address", ""),
        shop_phone=doc.get("shop_phone", ""),
        shop_latitude=doc.get("shop_latitude", 0),
        shop_longitude=doc.get("shop_longitude", 0),
        free_delivery_radius_km=doc.get("free_delivery_radius_km", 1.0),
        per_km_delivery_charge=doc.get("per_km_delivery_charge", 10.0),
        min_order_for_free_delivery=doc.get("min_order_for_free_delivery", 0),
    )
