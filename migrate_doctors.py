import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

MONGO_URI = "mongodb+srv://medical_store:medical_store@cluster0.sqqwifb.mongodb.net/medical_store?retryWrites=true&w=majority"

client = AsyncIOMotorClient(MONGO_URI)
db = client.get_database("medical_store")
doctors_collection = db.get_collection("doctors")

async def migrate_doctors():
    print("Starting migration...")
    cursor = doctors_collection.find({})
    count = 0
    async for doctor in cursor:
        if "availability" not in doctor or not doctor["availability"]:
            # Default availability: Mon-Fri, 10:00 to 17:00
            default_availability = [
                {"day": "monday", "slots": [{"start_time": "10:00", "end_time": "17:00"}]},
                {"day": "tuesday", "slots": [{"start_time": "10:00", "end_time": "17:00"}]},
                {"day": "wednesday", "slots": [{"start_time": "10:00", "end_time": "17:00"}]},
                {"day": "thursday", "slots": [{"start_time": "10:00", "end_time": "17:00"}]},
                {"day": "friday", "slots": [{"start_time": "10:00", "end_time": "17:00"}]},
            ]
            await doctors_collection.update_one(
                {"_id": doctor["_id"]},
                {"$set": {"availability": default_availability}}
            )
            count += 1
            print(f"Updated doctor: {doctor.get('name')}")
    
    print(f"Migration complete. Updated {count} doctors.")

if __name__ == "__main__":
    asyncio.run(migrate_doctors())
