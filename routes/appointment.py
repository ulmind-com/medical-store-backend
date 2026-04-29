from fastapi import APIRouter, HTTPException, status, Depends, Query
from bson import ObjectId
from datetime import datetime
from typing import Optional

from config.database import appointments_collection, doctors_collection
from models.appointment import AppointmentCreate, AppointmentUpdate, AppointmentOut
from middleware.auth import get_current_user, get_admin_user

router = APIRouter(prefix="/api/appointments", tags=["Appointments"])


def appointment_doc_to_out(doc: dict) -> AppointmentOut:
    return AppointmentOut(
        id=str(doc["_id"]),
        user_id=doc["user_id"],
        doctor_id=doc["doctor_id"],
        doctor_name=doc.get("doctor_name"),
        doctor_specialty=doc.get("doctor_specialty"),
        doctor_image=doc.get("doctor_image"),
        date=doc["date"],
        time_slot=doc["time_slot"],
        reason=doc.get("reason"),
        notes=doc.get("notes"),
        status=doc.get("status", "pending"),
        created_at=doc.get("created_at", ""),
    )


@router.post("/", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    data: AppointmentCreate,
    current_user: dict = Depends(get_current_user),
):
    # Verify doctor exists
    doctor = await doctors_collection.find_one({"_id": ObjectId(data.doctor_id)})
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    # Check for duplicate booking
    existing = await appointments_collection.find_one({
        "doctor_id": data.doctor_id,
        "date": data.date,
        "time_slot": data.time_slot,
        "status": {"$in": ["pending", "confirmed"]},
    })
    if existing:
        raise HTTPException(
            status_code=400,
            detail="This time slot is already booked",
        )

    doc = {
        "user_id": str(current_user["_id"]),
        "doctor_id": data.doctor_id,
        "doctor_name": doctor["name"],
        "doctor_specialty": doctor["specialty"],
        "doctor_image": doctor.get("image_url"),
        "date": data.date,
        "time_slot": data.time_slot,
        "reason": data.reason,
        "notes": data.notes,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
    }

    result = await appointments_collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return appointment_doc_to_out(doc)


@router.get("/my", response_model=list[AppointmentOut])
async def get_my_appointments(
    status_filter: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    query = {"user_id": str(current_user["_id"])}
    if status_filter:
        query["status"] = status_filter

    cursor = appointments_collection.find(query).sort("created_at", -1)
    appointments = await cursor.to_list(length=100)
    return [appointment_doc_to_out(a) for a in appointments]


@router.put("/{appointment_id}/cancel")
async def cancel_appointment(
    appointment_id: str,
    current_user: dict = Depends(get_current_user),
):
    doc = await appointments_collection.find_one({"_id": ObjectId(appointment_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if doc["user_id"] != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="Not authorized")

    if doc["status"] in ["completed", "cancelled"]:
        raise HTTPException(status_code=400, detail="Cannot cancel this appointment")

    await appointments_collection.update_one(
        {"_id": ObjectId(appointment_id)},
        {"$set": {"status": "cancelled"}},
    )
    return {"message": "Appointment cancelled successfully"}


# ── Admin Endpoints ──────────────────────────────────────────────────

@router.get("/all", response_model=list[AppointmentOut])
async def get_all_appointments(
    status_filter: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin: dict = Depends(get_admin_user),
):
    query = {}
    if status_filter:
        query["status"] = status_filter

    skip = (page - 1) * limit
    cursor = appointments_collection.find(query).skip(skip).limit(limit).sort("created_at", -1)
    appointments = await cursor.to_list(length=limit)
    return [appointment_doc_to_out(a) for a in appointments]


@router.put("/{appointment_id}/status", response_model=AppointmentOut)
async def update_appointment_status(
    appointment_id: str,
    data: AppointmentUpdate,
    admin: dict = Depends(get_admin_user),
):
    update_fields = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await appointments_collection.update_one(
        {"_id": ObjectId(appointment_id)},
        {"$set": update_fields},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Appointment not found")

    doc = await appointments_collection.find_one({"_id": ObjectId(appointment_id)})
    return appointment_doc_to_out(doc)
