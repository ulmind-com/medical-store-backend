from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Query, Form
from bson import ObjectId
from datetime import datetime
from typing import Optional, List

from config.database import prescriptions_collection, users_collection
from models.prescription import PrescriptionOut, PrescriptionUpdate
from middleware.auth import get_current_user, get_admin_user
from utils.cloudinary_upload import upload_image

router = APIRouter(prefix="/api/prescriptions", tags=["Prescriptions"])


def prescription_doc_to_out(doc: dict) -> PrescriptionOut:
    return PrescriptionOut(
        id=str(doc["_id"]),
        user_id=doc["user_id"],
        user_name=doc.get("user_name"),
        user_phone=doc.get("user_phone"),
        image_urls=doc.get("image_urls", []),
        notes=doc.get("notes"),
        status=doc.get("status", "pending"),
        admin_notes=doc.get("admin_notes"),
        delivery_address=doc.get("delivery_address"),
        delivery_latitude=doc.get("delivery_latitude"),
        delivery_longitude=doc.get("delivery_longitude"),
        quoted_price=doc.get("quoted_price"),
        payment_status=doc.get("payment_status", "unpaid"),
        razorpay_order_id=doc.get("razorpay_order_id"),
        razorpay_payment_id=doc.get("razorpay_payment_id"),
        created_at=doc.get("created_at", ""),
    )


@router.post("/upload", response_model=PrescriptionOut, status_code=status.HTTP_201_CREATED)
async def upload_prescription(
    files: List[UploadFile] = File(...),
    notes: Optional[str] = Form(None),
    delivery_address: Optional[str] = Form(None),
    delivery_latitude: Optional[float] = Form(None),
    delivery_longitude: Optional[float] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    image_urls = []
    for file in files:
        url = await upload_image(file, folder="medical_store/prescriptions")
        image_urls.append(url)

    doc = {
        "user_id": str(current_user["_id"]),
        "user_name": current_user.get("name", ""),
        "user_phone": current_user.get("phone", ""),
        "image_urls": image_urls,
        "notes": notes,
        "status": "pending",
        "admin_notes": None,
        "delivery_address": delivery_address,
        "delivery_latitude": delivery_latitude,
        "delivery_longitude": delivery_longitude,
        "quoted_price": None,
        "payment_status": "unpaid",
        "created_at": datetime.utcnow().isoformat(),
    }

    result = await prescriptions_collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return prescription_doc_to_out(doc)


@router.get("/my", response_model=list[PrescriptionOut])
async def get_my_prescriptions(current_user: dict = Depends(get_current_user)):
    cursor = prescriptions_collection.find(
        {"user_id": str(current_user["_id"])}
    ).sort("created_at", -1)
    prescriptions = await cursor.to_list(length=100)
    return [prescription_doc_to_out(p) for p in prescriptions]


@router.get("/{prescription_id}", response_model=PrescriptionOut)
async def get_prescription(
    prescription_id: str, current_user: dict = Depends(get_current_user),
):
    doc = await prescriptions_collection.find_one({"_id": ObjectId(prescription_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Prescription not found")
    if doc["user_id"] != str(current_user["_id"]) and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    return prescription_doc_to_out(doc)


# ── Admin ──────────────────────────────────────────────────

@router.get("/all/list", response_model=list[PrescriptionOut])
async def get_all_prescriptions(
    status_filter: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin: dict = Depends(get_admin_user),
):
    query = {}
    if status_filter:
        query["status"] = status_filter
    skip = (page - 1) * limit
    cursor = prescriptions_collection.find(query).skip(skip).limit(limit).sort("created_at", -1)
    prescriptions = await cursor.to_list(length=limit)
    return [prescription_doc_to_out(p) for p in prescriptions]


@router.put("/{prescription_id}/status", response_model=PrescriptionOut)
async def update_prescription_status(
    prescription_id: str,
    data: PrescriptionUpdate,
    admin: dict = Depends(get_admin_user),
):
    update_fields = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await prescriptions_collection.update_one(
        {"_id": ObjectId(prescription_id)}, {"$set": update_fields}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Prescription not found")

    doc = await prescriptions_collection.find_one({"_id": ObjectId(prescription_id)})
    return prescription_doc_to_out(doc)
