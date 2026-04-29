from motor.motor_asyncio import AsyncIOMotorClient
from config.settings import get_settings

settings = get_settings()

client = AsyncIOMotorClient(settings.MONGODB_URL)
database = client.medical_store

# Collections
users_collection = database.get_collection("users")
medicines_collection = database.get_collection("medicines")
doctors_collection = database.get_collection("doctors")
appointments_collection = database.get_collection("appointments")
orders_collection = database.get_collection("orders")
prescriptions_collection = database.get_collection("prescriptions")
settings_collection = database.get_collection("shop_settings")
categories_collection = database.get_collection("categories")


async def init_db():
    """Create indexes for collections."""
    await users_collection.create_index("email", unique=True)
    await users_collection.create_index("phone", unique=True)
    await medicines_collection.create_index("name")
    await medicines_collection.create_index("category")
    await doctors_collection.create_index("specialty")
    await orders_collection.create_index("user_id")
    await prescriptions_collection.create_index("user_id")
    await appointments_collection.create_index("user_id")
    await appointments_collection.create_index("doctor_id")

    # Ensure default shop settings exist
    existing = await settings_collection.find_one({"key": "shop_config"})
    if not existing:
        await settings_collection.insert_one({
            "key": "shop_config",
            "shop_name": "Medical Store",
            "shop_latitude": 22.5726,
            "shop_longitude": 88.3639,
            "free_delivery_radius_km": 1.0,
            "per_km_delivery_charge": 10.0,
            "min_order_for_free_delivery": 0,
            "shop_phone": "",
            "shop_address": "",
        })
