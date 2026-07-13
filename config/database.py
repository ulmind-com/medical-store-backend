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
crash_logs_collection = database.get_collection("crash_logs")
reminders_collection = database.get_collection("reminders")
ambulances_collection = database.get_collection("ambulances")
sos_logs_collection = database.get_collection("sos_logs")
master_catalog_collection = database.get_collection("master_catalog")


async def init_db():
    """Create indexes for collections."""
    await ambulances_collection.create_index([("base_location", "2dsphere")])
    await sos_logs_collection.create_index([("location", "2dsphere")])
    await users_collection.create_index("email", unique=True)
    # Drop the old unique index on phone if it exists to avoid IndexOptionsConflict,
    # then recreate it with sparse=True so that documents missing 'phone' are not indexed
    try:
        await users_collection.drop_index("phone_1")
    except Exception:
        pass
    await users_collection.create_index("phone", unique=True, sparse=True)
    await medicines_collection.create_index("name")
    await medicines_collection.create_index("category")
    await doctors_collection.create_index("specialty")
    await orders_collection.create_index("user_id")
    await prescriptions_collection.create_index("user_id")
    await appointments_collection.create_index("user_id")
    await appointments_collection.create_index("doctor_id")
    await reminders_collection.create_index("user_id")
    await reminders_collection.create_index("trigger_date")
    # Queue indexes: compound index for (doctor_id, date, queue_status) is critical
    # for the atomic /next query that must find the earliest WAITING patient fast.
    await appointments_collection.create_index(
        [("doctor_id", 1), ("date", 1), ("queue_status", 1), ("queue_position", 1)],
        name="queue_lookup_idx"
    )
    await master_catalog_collection.create_index("gtin", unique=True)

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
