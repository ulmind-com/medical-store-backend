from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Query
from bson import ObjectId
from datetime import datetime
from typing import Optional

from config.database import doctors_collection
from models.doctor import DoctorCreate, DoctorUpdate, DoctorOut
from middleware.auth import get_current_user, get_admin_user
from utils.cloudinary_upload import upload_image

router = APIRouter(prefix="/api/doctors", tags=["Doctors"])


def doctor_doc_to_out(doc: dict) -> DoctorOut:
    return DoctorOut(
        id=str(doc["_id"]),
        name=doc["name"],
        specialty=doc["specialty"],
        qualification=doc.get("qualification"),
        experience_years=doc.get("experience_years", 0),
        consultation_fee=doc["consultation_fee"],
        about=doc.get("about"),
        image_url=doc.get("image_url"),
        phone=doc.get("phone"),
        availability=doc.get("availability"),
        is_active=doc.get("is_active", True),
        rating=doc.get("rating", 0.0),
        total_reviews=doc.get("total_reviews", 0),
        created_at=doc.get("created_at", ""),
    )


# ── User Endpoints ──────────────────────────────────────────────────

@router.get("/", response_model=list[DoctorOut])
async def get_doctors(
    specialty: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    query = {"is_active": True}
    if specialty:
        query["specialty"] = specialty
    if search:
        query["name"] = {"$regex": search, "$options": "i"}

    skip = (page - 1) * limit
    cursor = doctors_collection.find(query).skip(skip).limit(limit).sort("name", 1)
    doctors = await cursor.to_list(length=limit)
    return [doctor_doc_to_out(d) for d in doctors]


@router.get("/specialties")
async def get_specialties():
    """Get unique list of specialties."""
    specialties = await doctors_collection.distinct("specialty")
    return specialties


@router.get("/{doctor_id}", response_model=DoctorOut)
async def get_doctor(doctor_id: str):
    doc = await doctors_collection.find_one({"_id": ObjectId(doctor_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return doctor_doc_to_out(doc)


# ── Admin Endpoints ──────────────────────────────────────────────────

@router.post("/", response_model=DoctorOut, status_code=status.HTTP_201_CREATED)
async def create_doctor(
    data: DoctorCreate,
    admin: dict = Depends(get_admin_user),
):
    doc = data.model_dump()
    doc["rating"] = 0.0
    doc["total_reviews"] = 0
    doc["created_at"] = datetime.utcnow().isoformat()
    result = await doctors_collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doctor_doc_to_out(doc)


@router.post("/{doctor_id}/image", response_model=DoctorOut)
async def upload_doctor_image(
    doctor_id: str,
    file: UploadFile = File(...),
    admin: dict = Depends(get_admin_user),
):
    doc = await doctors_collection.find_one({"_id": ObjectId(doctor_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Doctor not found")

    image_url = await upload_image(file, folder="medical_store/doctors")
    await doctors_collection.update_one(
        {"_id": ObjectId(doctor_id)},
        {"$set": {"image_url": image_url}},
    )
    doc["image_url"] = image_url
    return doctor_doc_to_out(doc)


@router.put("/{doctor_id}", response_model=DoctorOut)
async def update_doctor(
    doctor_id: str,
    data: DoctorUpdate,
    admin: dict = Depends(get_admin_user),
):
    update_fields = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await doctors_collection.update_one(
        {"_id": ObjectId(doctor_id)},
        {"$set": update_fields},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Doctor not found")

    doc = await doctors_collection.find_one({"_id": ObjectId(doctor_id)})
    return doctor_doc_to_out(doc)


@router.delete("/{doctor_id}")
async def delete_doctor(
    doctor_id: str,
    admin: dict = Depends(get_admin_user),
):
    result = await doctors_collection.delete_one({"_id": ObjectId(doctor_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return {"message": "Doctor deleted successfully"}
