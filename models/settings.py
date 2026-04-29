from pydantic import BaseModel, Field
from typing import Optional


class ShopSettings(BaseModel):
    shop_name: str = "Medical Store"
    shop_address: str = ""
    shop_phone: str = ""
    shop_latitude: float = 22.5726
    shop_longitude: float = 88.3639
    free_delivery_radius_km: float = Field(default=1.0, ge=0)
    per_km_delivery_charge: float = Field(default=10.0, ge=0)
    min_order_for_free_delivery: float = Field(default=0, ge=0)


class ShopSettingsUpdate(BaseModel):
    shop_name: Optional[str] = None
    shop_address: Optional[str] = None
    shop_phone: Optional[str] = None
    shop_latitude: Optional[float] = None
    shop_longitude: Optional[float] = None
    free_delivery_radius_km: Optional[float] = None
    per_km_delivery_charge: Optional[float] = None
    min_order_for_free_delivery: Optional[float] = None
