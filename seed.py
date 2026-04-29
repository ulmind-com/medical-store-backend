"""
Seed script to populate the database with:
- Admin user
- Medicine categories
- Sample medicines
- Sample doctors
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from datetime import datetime

MONGODB_URL = "mongodb+srv://medical_store:medical_store@cluster0.sqqwifb.mongodb.net/medical_store?retryWrites=true&w=majority"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def seed():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client.medical_store

    # ── 1. Make admin@medstore.com an admin ──
    result = await db.users.update_one(
        {"email": "admin@medstore.com"},
        {"$set": {"role": "admin"}},
    )
    if result.modified_count:
        print("[OK] admin@medstore.com -> role=admin")
    else:
        # Create admin if not exists
        admin_doc = {
            "name": "Admin User",
            "email": "admin@medstore.com",
            "phone": "9876543210",
            "password": pwd_context.hash("admin123"),
            "role": "admin",
            "address": None,
            "latitude": None,
            "longitude": None,
            "profile_image": None,
            "created_at": datetime.utcnow().isoformat(),
        }
        await db.users.insert_one(admin_doc)
        print("[OK] Created admin user: admin@medstore.com / admin123")

    # ── 2. Categories ──
    categories = [
        {"name": "Tablets", "icon": "tablet-portrait-outline", "image_url": None, "created_at": datetime.utcnow().isoformat()},
        {"name": "Syrups", "icon": "water-outline", "image_url": None, "created_at": datetime.utcnow().isoformat()},
        {"name": "Injections", "icon": "fitness-outline", "image_url": None, "created_at": datetime.utcnow().isoformat()},
        {"name": "Vitamins", "icon": "sunny-outline", "image_url": None, "created_at": datetime.utcnow().isoformat()},
        {"name": "Skincare", "icon": "body-outline", "image_url": None, "created_at": datetime.utcnow().isoformat()},
        {"name": "First Aid", "icon": "bandage-outline", "image_url": None, "created_at": datetime.utcnow().isoformat()},
        {"name": "Baby Care", "icon": "happy-outline", "image_url": None, "created_at": datetime.utcnow().isoformat()},
        {"name": "Devices", "icon": "hardware-chip-outline", "image_url": None, "created_at": datetime.utcnow().isoformat()},
    ]
    existing_cats = await db.categories.count_documents({})
    if existing_cats == 0:
        await db.categories.insert_many(categories)
        print(f"[OK] Inserted {len(categories)} categories")
    else:
        print(f"[SKIP] {existing_cats} categories already exist")

    # ── 3. Sample Medicines ──
    medicines = [
        {
            "name": "Paracetamol 500mg",
            "generic_name": "Acetaminophen",
            "description": "Used for fever and mild to moderate pain relief. Take as directed by your physician.",
            "category": "Tablets",
            "manufacturer": "Cipla Ltd",
            "price": 35.0,
            "discount_price": 28.0,
            "stock": 500,
            "requires_prescription": False,
            "image_url": None,
            "dosage_form": "Tablet",
            "strength": "500mg",
            "pack_size": "10 Tablets",
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "name": "Amoxicillin 250mg",
            "generic_name": "Amoxicillin Trihydrate",
            "description": "Broad-spectrum antibiotic used to treat various bacterial infections.",
            "category": "Tablets",
            "manufacturer": "Sun Pharma",
            "price": 120.0,
            "discount_price": None,
            "stock": 200,
            "requires_prescription": True,
            "image_url": None,
            "dosage_form": "Capsule",
            "strength": "250mg",
            "pack_size": "10 Capsules",
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "name": "Cough Syrup",
            "generic_name": "Dextromethorphan",
            "description": "Relieves cough caused by common cold or flu. Suitable for adults and children above 12.",
            "category": "Syrups",
            "manufacturer": "Dabur",
            "price": 89.0,
            "discount_price": 75.0,
            "stock": 150,
            "requires_prescription": False,
            "image_url": None,
            "dosage_form": "Syrup",
            "strength": "100ml",
            "pack_size": "100ml Bottle",
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "name": "Vitamin C 1000mg",
            "generic_name": "Ascorbic Acid",
            "description": "Boosts immunity and supports overall health. Effervescent tablets with orange flavour.",
            "category": "Vitamins",
            "manufacturer": "Limcee",
            "price": 150.0,
            "discount_price": 120.0,
            "stock": 300,
            "requires_prescription": False,
            "image_url": None,
            "dosage_form": "Effervescent Tablet",
            "strength": "1000mg",
            "pack_size": "20 Tablets",
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "name": "Cetirizine 10mg",
            "generic_name": "Cetirizine Hydrochloride",
            "description": "Antihistamine used for allergic rhinitis, hay fever, and urticaria symptoms.",
            "category": "Tablets",
            "manufacturer": "Dr. Reddy's",
            "price": 45.0,
            "discount_price": 38.0,
            "stock": 400,
            "requires_prescription": False,
            "image_url": None,
            "dosage_form": "Tablet",
            "strength": "10mg",
            "pack_size": "10 Tablets",
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "name": "ORS Sachets",
            "generic_name": "Oral Rehydration Salts",
            "description": "Prevents dehydration caused by diarrhea. WHO-approved formula.",
            "category": "First Aid",
            "manufacturer": "Electral",
            "price": 25.0,
            "discount_price": 20.0,
            "stock": 600,
            "requires_prescription": False,
            "image_url": None,
            "dosage_form": "Powder",
            "strength": "21.8g",
            "pack_size": "5 Sachets",
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "name": "Betadine Antiseptic",
            "generic_name": "Povidone Iodine",
            "description": "Antiseptic solution for wound cleaning and minor skin infections.",
            "category": "First Aid",
            "manufacturer": "Win-Medicare",
            "price": 95.0,
            "discount_price": None,
            "stock": 100,
            "requires_prescription": False,
            "image_url": None,
            "dosage_form": "Solution",
            "strength": "5% w/v",
            "pack_size": "100ml Bottle",
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "name": "Multivitamin Gold",
            "generic_name": "Multivitamin & Mineral",
            "description": "Daily multivitamin with essential minerals for overall wellness and energy.",
            "category": "Vitamins",
            "manufacturer": "Revital",
            "price": 450.0,
            "discount_price": 380.0,
            "stock": 80,
            "requires_prescription": False,
            "image_url": None,
            "dosage_form": "Capsule",
            "strength": "Multi",
            "pack_size": "30 Capsules",
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "name": "Moisturizing Cream",
            "generic_name": "Cetaphil",
            "description": "Gentle, non-comedogenic moisturizer for sensitive and dry skin.",
            "category": "Skincare",
            "manufacturer": "Galderma",
            "price": 320.0,
            "discount_price": 280.0,
            "stock": 60,
            "requires_prescription": False,
            "image_url": None,
            "dosage_form": "Cream",
            "strength": "80g",
            "pack_size": "80g Tube",
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "name": "Digital Thermometer",
            "generic_name": None,
            "description": "Fast and accurate digital thermometer with beep alert. Suitable for oral, rectal, or underarm use.",
            "category": "Devices",
            "manufacturer": "Dr. Morepen",
            "price": 199.0,
            "discount_price": 149.0,
            "stock": 40,
            "requires_prescription": False,
            "image_url": None,
            "dosage_form": None,
            "strength": None,
            "pack_size": "1 Unit",
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "name": "Baby Gripe Water",
            "generic_name": "Dill Oil & Sodium Bicarbonate",
            "description": "Soothes colic, gas and hiccups in babies. Safe for infants above 1 month.",
            "category": "Baby Care",
            "manufacturer": "Woodward's",
            "price": 75.0,
            "discount_price": 65.0,
            "stock": 120,
            "requires_prescription": False,
            "image_url": None,
            "dosage_form": "Liquid",
            "strength": "130ml",
            "pack_size": "130ml Bottle",
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "name": "Azithromycin 500mg",
            "generic_name": "Azithromycin Dihydrate",
            "description": "Macrolide antibiotic for bacterial infections of the respiratory tract, skin, and ears.",
            "category": "Tablets",
            "manufacturer": "Zydus Cadila",
            "price": 180.0,
            "discount_price": None,
            "stock": 150,
            "requires_prescription": True,
            "image_url": None,
            "dosage_form": "Tablet",
            "strength": "500mg",
            "pack_size": "3 Tablets",
            "created_at": datetime.utcnow().isoformat(),
        },
    ]

    existing_meds = await db.medicines.count_documents({})
    if existing_meds == 0:
        await db.medicines.insert_many(medicines)
        print(f"[OK] Inserted {len(medicines)} medicines")
    else:
        print(f"[SKIP] {existing_meds} medicines already exist")

    # ── 4. Sample Doctors ──
    doctors = [
        {
            "name": "Rajesh Sharma",
            "specialty": "General Physician",
            "qualification": "MBBS, MD",
            "experience_years": 15,
            "consultation_fee": 500.0,
            "about": "Dr. Rajesh Sharma is a highly experienced general physician specializing in primary care, preventive medicine, and chronic disease management. He believes in patient-centered care.",
            "image_url": None,
            "phone": "9876500001",
            "is_active": True,
            "rating": 4.8,
            "total_reviews": 234,
            "availability": [
                {"day": "monday", "slots": [{"start_time": "09:00", "end_time": "13:00"}, {"start_time": "17:00", "end_time": "20:00"}]},
                {"day": "wednesday", "slots": [{"start_time": "09:00", "end_time": "13:00"}]},
                {"day": "friday", "slots": [{"start_time": "09:00", "end_time": "13:00"}, {"start_time": "17:00", "end_time": "20:00"}]},
            ],
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "name": "Priya Gupta",
            "specialty": "Dermatologist",
            "qualification": "MBBS, MD (Dermatology)",
            "experience_years": 10,
            "consultation_fee": 800.0,
            "about": "Dr. Priya Gupta is a board-certified dermatologist specializing in acne, eczema, psoriasis, and cosmetic dermatology. She uses the latest treatment methods.",
            "image_url": None,
            "phone": "9876500002",
            "is_active": True,
            "rating": 4.9,
            "total_reviews": 187,
            "availability": [
                {"day": "tuesday", "slots": [{"start_time": "10:00", "end_time": "14:00"}]},
                {"day": "thursday", "slots": [{"start_time": "10:00", "end_time": "14:00"}]},
                {"day": "saturday", "slots": [{"start_time": "10:00", "end_time": "13:00"}]},
            ],
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "name": "Amit Banerjee",
            "specialty": "Pediatrician",
            "qualification": "MBBS, DCH, MD (Pediatrics)",
            "experience_years": 12,
            "consultation_fee": 600.0,
            "about": "Dr. Amit Banerjee is a caring pediatrician with expertise in newborn care, childhood vaccinations, and developmental assessments.",
            "image_url": None,
            "phone": "9876500003",
            "is_active": True,
            "rating": 4.7,
            "total_reviews": 312,
            "availability": [
                {"day": "monday", "slots": [{"start_time": "10:00", "end_time": "14:00"}, {"start_time": "16:00", "end_time": "19:00"}]},
                {"day": "tuesday", "slots": [{"start_time": "10:00", "end_time": "14:00"}]},
                {"day": "thursday", "slots": [{"start_time": "10:00", "end_time": "14:00"}, {"start_time": "16:00", "end_time": "19:00"}]},
                {"day": "saturday", "slots": [{"start_time": "10:00", "end_time": "13:00"}]},
            ],
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "name": "Sneha Patel",
            "specialty": "Gynecologist",
            "qualification": "MBBS, MS (OBG)",
            "experience_years": 18,
            "consultation_fee": 1000.0,
            "about": "Dr. Sneha Patel is a senior gynecologist and obstetrician with vast experience in prenatal care, high-risk pregnancies, and women's health.",
            "image_url": None,
            "phone": "9876500004",
            "is_active": True,
            "rating": 4.9,
            "total_reviews": 420,
            "availability": [
                {"day": "monday", "slots": [{"start_time": "11:00", "end_time": "15:00"}]},
                {"day": "wednesday", "slots": [{"start_time": "11:00", "end_time": "15:00"}]},
                {"day": "friday", "slots": [{"start_time": "11:00", "end_time": "15:00"}]},
            ],
            "created_at": datetime.utcnow().isoformat(),
        },
        {
            "name": "Vikram Singh",
            "specialty": "Cardiologist",
            "qualification": "MBBS, DM (Cardiology)",
            "experience_years": 20,
            "consultation_fee": 1500.0,
            "about": "Dr. Vikram Singh is one of the leading cardiologists in the region with expertise in interventional cardiology, heart failure management, and preventive cardiology.",
            "image_url": None,
            "phone": "9876500005",
            "is_active": True,
            "rating": 4.8,
            "total_reviews": 156,
            "availability": [
                {"day": "tuesday", "slots": [{"start_time": "09:00", "end_time": "12:00"}]},
                {"day": "thursday", "slots": [{"start_time": "09:00", "end_time": "12:00"}]},
                {"day": "saturday", "slots": [{"start_time": "09:00", "end_time": "12:00"}]},
            ],
            "created_at": datetime.utcnow().isoformat(),
        },
    ]

    existing_docs = await db.doctors.count_documents({})
    if existing_docs == 0:
        await db.doctors.insert_many(doctors)
        print(f"[OK] Inserted {len(doctors)} doctors")
    else:
        print(f"[SKIP] {existing_docs} doctors already exist")

    print("\n[DONE] Seed complete!")
    print("  Admin Login: admin@medstore.com / admin123")
    print("  Backend: http://localhost:8000")
    print("  Swagger: http://localhost:8000/docs")

    client.close()


if __name__ == "__main__":
    asyncio.run(seed())
