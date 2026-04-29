import math
from config.database import settings_collection


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points
    on the Earth using the Haversine formula.
    Returns distance in kilometers.
    """
    R = 6371.0  # Earth radius in km

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


async def calculate_delivery_charge(
    user_lat: float, user_lon: float
) -> dict:
    """
    Calculate delivery charge based on distance from shop.

    Returns:
        {
            "distance_km": float,
            "delivery_charge": float,
            "is_free_delivery": bool,
            "free_radius_km": float,
            "per_km_rate": float,
        }
    """
    shop_config = await settings_collection.find_one({"key": "shop_config"})

    if not shop_config:
        return {
            "distance_km": 0,
            "delivery_charge": 0,
            "is_free_delivery": True,
            "free_radius_km": 0,
            "per_km_rate": 0,
        }

    shop_lat = shop_config.get("shop_latitude", 0)
    shop_lon = shop_config.get("shop_longitude", 0)
    free_radius = shop_config.get("free_delivery_radius_km", 1.0)
    per_km_rate = shop_config.get("per_km_delivery_charge", 10.0)

    distance = haversine_distance(shop_lat, shop_lon, user_lat, user_lon)
    distance = round(distance, 2)

    if distance <= free_radius:
        return {
            "distance_km": distance,
            "delivery_charge": 0,
            "is_free_delivery": True,
            "free_radius_km": free_radius,
            "per_km_rate": per_km_rate,
        }

    delivery_charge = round(distance * per_km_rate, 2)

    return {
        "distance_km": distance,
        "delivery_charge": delivery_charge,
        "is_free_delivery": False,
        "free_radius_km": free_radius,
        "per_km_rate": per_km_rate,
    }
