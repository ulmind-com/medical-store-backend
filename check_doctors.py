import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = "mongodb+srv://medical_store:medical_store@cluster0.sqqwifb.mongodb.net/medical_store?retryWrites=true&w=majority"
client = AsyncIOMotorClient(MONGO_URI)
db = client.get_database("medical_store")

async def main():
    docs = await db.doctors.find({}).to_list(100)
    for d in docs:
        name = d.get('name', 'unknown')
        avail = d.get('availability', 'NONE')
        print(f"Doctor: {name}")
        print(f"  availability: {avail}")
        print()

asyncio.run(main())
