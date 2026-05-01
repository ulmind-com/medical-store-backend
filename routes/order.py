from fastapi import APIRouter, HTTPException, status, Depends, Query
from bson import ObjectId
from datetime import datetime
from typing import Optional

from config.database import orders_collection, medicines_collection
from models.order import OrderCreate, OrderUpdate, OrderOut, OrderItem
from middleware.auth import get_current_user, get_admin_user
from utils.delivery import calculate_delivery_charge

router = APIRouter(prefix="/api/orders", tags=["Orders"])


def order_doc_to_out(doc: dict) -> OrderOut:
    return OrderOut(
        id=str(doc["_id"]),
        user_id=doc["user_id"],
        user_name=doc.get("user_name"),
        user_phone=doc.get("user_phone"),
        items=[OrderItem(**item) for item in doc["items"]],
        subtotal=doc["subtotal"],
        delivery_charge=doc.get("delivery_charge", 0),
        total_amount=doc["total_amount"],
        delivery_address=doc["delivery_address"],
        delivery_latitude=doc["delivery_latitude"],
        delivery_longitude=doc["delivery_longitude"],
        distance_km=doc.get("distance_km", 0),
        payment_method=doc["payment_method"],
        payment_status=doc.get("payment_status", "pending"),
        razorpay_order_id=doc.get("razorpay_order_id"),
        razorpay_payment_id=doc.get("razorpay_payment_id"),
        status=doc.get("status", "placed"),
        notes=doc.get("notes"),
        created_at=doc.get("created_at", ""),
    )


@router.post("/", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(data: OrderCreate, current_user: dict = Depends(get_current_user)):
    subtotal = 0.0
    validated_items = []

    for item in data.items:
        medicine = await medicines_collection.find_one({"_id": ObjectId(item.medicine_id)})
        if not medicine:
            raise HTTPException(status_code=404, detail=f"Medicine {item.medicine_id} not found")
        if medicine.get("stock", 0) < item.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for {medicine['name']}")
        subtotal += item.price * item.quantity
        validated_items.append(item.model_dump())

    delivery_info = await calculate_delivery_charge(data.delivery_latitude, data.delivery_longitude)
    delivery_charge = delivery_info["delivery_charge"]
    total_amount = round(subtotal + delivery_charge, 2)

    order_doc = {
        "user_id": str(current_user["_id"]),
        "user_name": current_user.get("name", ""),
        "user_phone": current_user.get("phone", ""),
        "items": validated_items,
        "subtotal": round(subtotal, 2),
        "delivery_charge": delivery_charge,
        "total_amount": total_amount,
        "delivery_address": data.delivery_address,
        "delivery_latitude": data.delivery_latitude,
        "delivery_longitude": data.delivery_longitude,
        "distance_km": delivery_info["distance_km"],
        "payment_method": data.payment_method,
        "payment_status": "pending",
        "status": "placed",
        "notes": data.notes,
        "created_at": datetime.utcnow().isoformat(),
    }

    result = await orders_collection.insert_one(order_doc)
    order_doc["_id"] = result.inserted_id

    for item in data.items:
        await medicines_collection.update_one(
            {"_id": ObjectId(item.medicine_id)}, {"$inc": {"stock": -item.quantity}}
        )

    return order_doc_to_out(order_doc)


@router.get("/delivery-charge")
async def get_delivery_charge(
    latitude: float = Query(...), longitude: float = Query(...),
    current_user: dict = Depends(get_current_user),
):
    return await calculate_delivery_charge(latitude, longitude)


@router.get("/my", response_model=list[OrderOut])
async def get_my_orders(
    status_filter: Optional[str] = None, current_user: dict = Depends(get_current_user),
):
    query = {"user_id": str(current_user["_id"])}
    if status_filter:
        query["status"] = status_filter
    cursor = orders_collection.find(query).sort("created_at", -1)
    orders = await cursor.to_list(length=100)
    return [order_doc_to_out(o) for o in orders]


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: str, current_user: dict = Depends(get_current_user)):
    doc = await orders_collection.find_one({"_id": ObjectId(order_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    if doc["user_id"] != str(current_user["_id"]) and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    return order_doc_to_out(doc)


@router.get("/all/list", response_model=list[OrderOut])
async def get_all_orders(
    status_filter: Optional[str] = None, page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100), admin: dict = Depends(get_admin_user),
):
    query = {}
    if status_filter:
        query["status"] = status_filter
    skip = (page - 1) * limit
    cursor = orders_collection.find(query).skip(skip).limit(limit).sort("created_at", -1)
    orders = await cursor.to_list(length=limit)
    return [order_doc_to_out(o) for o in orders]


@router.put("/{order_id}/status", response_model=OrderOut)
async def update_order_status(
    order_id: str, data: OrderUpdate, admin: dict = Depends(get_admin_user),
):
    update_fields = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = await orders_collection.update_one({"_id": ObjectId(order_id)}, {"$set": update_fields})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    doc = await orders_collection.find_one({"_id": ObjectId(order_id)})
    return order_doc_to_out(doc)
