import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient

# Using the connection string provided earlier by user
MONGO_URI = "mongodb+srv://medical_store:medical_store@cluster0.sqqwifb.mongodb.net/medical_store?retryWrites=true&w=majority"

med_images = [
    "https://images.unsplash.com/photo-1584308666744-24d5c474f2ae?w=800&q=80", # Paracetamol/Pills
    "https://images.unsplash.com/photo-1550572017-edb7df089602?w=800&q=80", # Syrup
    "https://images.unsplash.com/photo-1628771065518-0d82f1938462?w=800&q=80", # First Aid / Bandage
    "https://images.unsplash.com/photo-1631549916768-4119b2e5f926?w=800&q=80", # Vials/Injections
    "https://images.unsplash.com/photo-1585435557343-3b092031a831?w=800&q=80", # Vitamins/Capsules
]

doc_images = [
    "https://images.unsplash.com/photo-1612349317150-e413f6a5b16d?w=800&q=80", # Male doc 1
    "https://images.unsplash.com/photo-1559839734-2b71ea197ec2?w=800&q=80", # Female doc 1
    "https://images.unsplash.com/photo-1537368910025-700350fe46c7?w=800&q=80", # Male doc 2
    "https://images.unsplash.com/photo-1594824432258-290fbb0db362?w=800&q=80", # Female doc 2
    "https://images.unsplash.com/photo-1622253692010-333f2da6031d?w=800&q=80", # Male doc 3
]

async def update_images():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client.medical_store
    
    # Update Medicines
    print("Updating Medicines...")
    medicines = await db.medicines.find({}).to_list(length=100)
    for i, med in enumerate(medicines):
        img_url = med_images[i % len(med_images)]
        await db.medicines.update_one(
            {"_id": med["_id"]},
            {"$set": {"image_url": img_url}}
        )
        print(f"Updated medicine {med['name']}")

    # Update Doctors
    print("\nUpdating Doctors...")
    doctors = await db.doctors.find({}).to_list(length=100)
    for i, doc in enumerate(doctors):
        img_url = doc_images[i % len(doc_images)]
        await db.doctors.update_one(
            {"_id": doc["_id"]},
            {"$set": {"image_url": img_url}}
        )
        print(f"Updated doctor Dr. {doc['name']}")

    print("Done!")
    client.close()

if __name__ == "__main__":
    asyncio.run(update_images())
