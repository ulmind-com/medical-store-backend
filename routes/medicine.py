from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Query
from bson import ObjectId
from datetime import datetime
from typing import Optional

from config.database import medicines_collection, categories_collection
from models.medicine import MedicineCreate, MedicineUpdate, MedicineOut, CategoryCreate
from middleware.auth import get_current_user, get_admin_user
from utils.cloudinary_upload import upload_image

router = APIRouter(prefix="/api/medicines", tags=["Medicines"])


def medicine_doc_to_out(doc: dict) -> MedicineOut:
    return MedicineOut(
        id=str(doc["_id"]),
        name=doc["name"],
        generic_name=doc.get("generic_name"),
        description=doc.get("description"),
        category=doc["category"],
        manufacturer=doc.get("manufacturer"),
        price=doc["price"],
        discount_price=doc.get("discount_price"),
        stock=doc.get("stock", 0),
        requires_prescription=doc.get("requires_prescription", False),
        image_url=doc.get("image_url"),
        dosage_form=doc.get("dosage_form"),
        strength=doc.get("strength"),
        pack_size=doc.get("pack_size"),
        created_at=doc.get("created_at", ""),
    )


# ── User Endpoints ──────────────────────────────────────────────────

@router.get("/", response_model=list[MedicineOut])
async def get_medicines(
    category: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    query = {}
    if category:
        query["category"] = category
    if search:
        query["name"] = {"$regex": search, "$options": "i"}

    skip = (page - 1) * limit
    cursor = medicines_collection.find(query).skip(skip).limit(limit).sort("name", 1)
    medicines = await cursor.to_list(length=limit)
    return [medicine_doc_to_out(m) for m in medicines]


@router.get("/featured", response_model=list[MedicineOut])
async def get_featured_medicines():
    """Get medicines with discounts or latest additions."""
    cursor = medicines_collection.find(
        {"discount_price": {"$ne": None, "$gt": 0}}
    ).limit(10).sort("created_at", -1)
    medicines = await cursor.to_list(length=10)

    if len(medicines) < 10:
        extra_cursor = medicines_collection.find().limit(10 - len(medicines)).sort("created_at", -1)
        extra = await extra_cursor.to_list(length=10 - len(medicines))
        medicines.extend(extra)

    return [medicine_doc_to_out(m) for m in medicines]


@router.get("/categories")
async def get_categories():
    cursor = categories_collection.find().sort("name", 1)
    categories = await cursor.to_list(length=100)
    return [
        {
            "id": str(c["_id"]),
            "name": c["name"],
            "icon": c.get("icon"),
            "image_url": c.get("image_url"),
        }
        for c in categories
    ]


@router.get("/{medicine_id}", response_model=MedicineOut)
async def get_medicine(medicine_id: str):
    doc = await medicines_collection.find_one({"_id": ObjectId(medicine_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Medicine not found")
    return medicine_doc_to_out(doc)


# ── Admin Endpoints ──────────────────────────────────────────────────

@router.post("/", response_model=MedicineOut, status_code=status.HTTP_201_CREATED)
async def create_medicine(
    data: MedicineCreate,
    admin: dict = Depends(get_admin_user),
):
    doc = data.model_dump()
    doc["created_at"] = datetime.utcnow().isoformat()
    result = await medicines_collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return medicine_doc_to_out(doc)


@router.post("/{medicine_id}/image", response_model=MedicineOut)
async def upload_medicine_image(
    medicine_id: str,
    file: UploadFile = File(...),
    admin: dict = Depends(get_admin_user),
):
    doc = await medicines_collection.find_one({"_id": ObjectId(medicine_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Medicine not found")

    image_url = await upload_image(file, folder="medical_store/medicines")
    await medicines_collection.update_one(
        {"_id": ObjectId(medicine_id)},
        {"$set": {"image_url": image_url}},
    )
    doc["image_url"] = image_url
    return medicine_doc_to_out(doc)


@router.put("/{medicine_id}", response_model=MedicineOut)
async def update_medicine(
    medicine_id: str,
    data: MedicineUpdate,
    admin: dict = Depends(get_admin_user),
):
    update_fields = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await medicines_collection.update_one(
        {"_id": ObjectId(medicine_id)},
        {"$set": update_fields},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Medicine not found")

    doc = await medicines_collection.find_one({"_id": ObjectId(medicine_id)})
    return medicine_doc_to_out(doc)


@router.delete("/{medicine_id}")
async def delete_medicine(
    medicine_id: str,
    admin: dict = Depends(get_admin_user),
):
    result = await medicines_collection.delete_one({"_id": ObjectId(medicine_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Medicine not found")
    return {"message": "Medicine deleted successfully"}


# ── Category Admin Endpoints ────────────────────────────────────────

@router.post("/categories/create")
async def create_category(
    data: CategoryCreate,
    admin: dict = Depends(get_admin_user),
):
    doc = data.model_dump()
    doc["created_at"] = datetime.utcnow().isoformat()
    result = await categories_collection.insert_one(doc)
    return {"id": str(result.inserted_id), "name": doc["name"]}


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: str,
    admin: dict = Depends(get_admin_user),
):
    result = await categories_collection.delete_one({"_id": ObjectId(category_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"message": "Category deleted successfully"}
