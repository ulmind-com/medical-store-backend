"""
routes/order.py
---------------
Handles all /api/orders endpoints.

RACE-CONDITION FIX (2026-07):
  The original implementation used a two-step read-then-write pattern:
    1. find_one(...)           -> read current stock
    2. update_one($inc stock)  -> decrement

  Under concurrent load both steps can interleave, allowing two requests to
  both "see" sufficient stock and both decrement, driving stock below 0.

  The fix uses a single, atomic MongoDB find_one_and_update with a filter
  that only matches when stock >= requested_quantity.  If the document is
  not returned it means stock is insufficient and the operation never fired.

  Rollback strategy (manual compensation):
    MongoDB multi-document ACID transactions require a replica-set or sharded
    cluster.  Since the deployment is Atlas Free/Shared, we implement manual
    compensation: if item N fails we re-increment the stock of all previously
    decremented items before returning the error.
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from bson import ObjectId
from datetime import datetime
from typing import Optional, List

from config.database import orders_collection, medicines_collection
from models.order import OrderCreate, OrderUpdate, OrderOut, OrderItem
from middleware.auth import get_current_user, get_admin_user
from utils.delivery import calculate_delivery_charge

router = APIRouter(prefix="/api/orders", tags=["Orders"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def order_doc_to_out(doc: dict) -> OrderOut:
    """Convert a raw MongoDB document to an OrderOut Pydantic model."""
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
        # Normalise legacy "pending" status to "placed"
        status="placed" if doc.get("status") == "pending" else doc.get("status", "placed"),
        notes=doc.get("notes"),
        created_at=doc.get("created_at", ""),
        address_type=doc.get("address_type", "home"),
        address_details=doc.get("address_details"),
    )


async def _atomic_decrement_stock(
    medicine_id: str,
    quantity: int,
) -> Optional[dict]:
    """
    Atomically check stock and decrement in a SINGLE database operation.

    Uses find_one_and_update with:
      - Filter:  { _id: <id>, stock: { $gte: quantity } }
      - Update:  { $inc: { stock: -quantity } }
      - return_document=False  -> returns the document BEFORE the update
                                  (so we can read the medicine name for errors)

    Returns:
        The pre-update medicine document if the operation succeeded.
        None if no document matched (medicine missing OR stock insufficient).
    """
    return await medicines_collection.find_one_and_update(
        # The $gte guard is the atomic stock check — it will only match
        # (and therefore decrement) if stock is currently enough.
        filter={"_id": ObjectId(medicine_id), "stock": {"$gte": quantity}},
        update={"$inc": {"stock": -quantity}},
        # Return the document as it was BEFORE the update so we can inspect it.
        return_document=False,
    )


async def _compensate_stock(decremented: List[dict]) -> None:
    """
    Rollback helper — re-increments stock for every item that was already
    successfully decremented before a later item failed.

    This is a "manual compensation" pattern (saga-style rollback).  Each
    re-increment is itself atomic, so this is safe even under concurrent load.

    Args:
        decremented: list of {"medicine_id": str, "quantity": int} dicts
                     representing every decrement that succeeded BEFORE the
                     failure point.
    """
    for entry in decremented:
        await medicines_collection.update_one(
            {"_id": ObjectId(entry["medicine_id"])},
            {"$inc": {"stock": entry["quantity"]}},  # undo the decrement
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    data: OrderCreate,
    current_user: dict = Depends(get_current_user),
):
    """
    Create a new order.

    Race-condition-safe implementation:
      1. Iterate cart items.
      2. For each item, call _atomic_decrement_stock().
         - If None is returned → medicine not found or stock insufficient.
           Roll back every decrement that already succeeded, then abort.
      3. After all items are decremented atomically, insert the order document.

    This guarantees stock can NEVER go below 0, even under 1000 concurrent
    requests for the same medicine with stock=1.
    """
    subtotal = 0.0
    validated_items = []

    # Tracks which items we have already decremented so we can roll back
    # if a later item fails.
    successfully_decremented: List[dict] = []

    # ── Phase 1: Atomic per-item stock decrement ────────────────────────────
    for item in data.items:
        pre_update_doc = await _atomic_decrement_stock(
            medicine_id=item.medicine_id,
            quantity=item.quantity,
        )

        if pre_update_doc is None:
            # The atomic operation found no document matching
            # { _id, stock >= quantity }.  This means EITHER:
            #   a) The medicine_id does not exist in the database.
            #   b) Stock exists but is below the requested quantity.
            #
            # In both cases we must roll back previously decremented items.

            await _compensate_stock(successfully_decremented)

            # Try to fetch the medicine by ID alone to give a precise message.
            medicine_info = await medicines_collection.find_one(
                {"_id": ObjectId(item.medicine_id)},
                projection={"name": 1, "stock": 1},
            )

            if medicine_info is None:
                # Medicine ID doesn't exist at all
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Medicine '{item.medicine_id}' not found.",
                )
            else:
                # Medicine exists but stock is genuinely insufficient
                available_stock = medicine_info.get("stock", 0)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Insufficient stock for '{medicine_info['name']}'. "
                        f"Requested: {item.quantity}, Available: {available_stock}. "
                        f"Please update your cart and try again."
                    ),
                )

        # Decrement succeeded — record it for potential rollback.
        successfully_decremented.append(
            {"medicine_id": item.medicine_id, "quantity": item.quantity}
        )

        # Accumulate subtotal using the cart-submitted price.
        subtotal += item.price * item.quantity
        validated_items.append(item.model_dump())

    # ── Phase 2: Delivery charge calculation ────────────────────────────────
    # This is a pure read — no stock impact — so it is safe after Phase 1.
    delivery_info = await calculate_delivery_charge(
        data.delivery_latitude, data.delivery_longitude
    )
    delivery_charge = delivery_info["delivery_charge"]
    total_amount = round(subtotal + delivery_charge, 2)

    # ── Phase 3: Persist the order document ─────────────────────────────────
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
        "address_type": data.address_type,
        "address_details": data.address_details,
        "distance_km": delivery_info["distance_km"],
        "payment_method": data.payment_method,
        "payment_status": "pending",
        "status": "placed",
        "notes": data.notes,
        "created_at": datetime.utcnow().isoformat(),
    }

    result = await orders_collection.insert_one(order_doc)
    order_doc["_id"] = result.inserted_id

    return order_doc_to_out(order_doc)


# ── Read endpoints (unchanged) ───────────────────────────────────────────────

@router.get("/delivery-charge")
async def get_delivery_charge(
    latitude: float = Query(...),
    longitude: float = Query(...),
    current_user: dict = Depends(get_current_user),
):
    """Return delivery charge and distance for a given GPS coordinate."""
    return await calculate_delivery_charge(latitude, longitude)


@router.get("/my", response_model=list[OrderOut])
async def get_my_orders(
    status_filter: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Return the authenticated user's orders, newest first."""
    query = {"user_id": str(current_user["_id"])}
    if status_filter:
        query["status"] = status_filter
    cursor = orders_collection.find(query).sort("created_at", -1)
    orders = await cursor.to_list(length=100)
    return [order_doc_to_out(o) for o in orders]


@router.get("/all/list", response_model=list[OrderOut])
async def get_all_orders(
    status_filter: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin: dict = Depends(get_admin_user),
):
    """[Admin] Return all orders with pagination, newest first."""
    query = {}
    if status_filter:
        query["status"] = status_filter
    skip = (page - 1) * limit
    cursor = orders_collection.find(query).skip(skip).limit(limit).sort("created_at", -1)
    orders = await cursor.to_list(length=limit)
    return [order_doc_to_out(o) for o in orders]


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Return a single order. Users can only see their own; admins see all."""
    doc = await orders_collection.find_one({"_id": ObjectId(order_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    if doc["user_id"] != str(current_user["_id"]) and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    return order_doc_to_out(doc)


@router.put("/{order_id}/status", response_model=OrderOut)
async def update_order_status(
    order_id: str,
    data: OrderUpdate,
    admin: dict = Depends(get_admin_user),
):
    """[Admin] Update order status and/or payment status."""
    update_fields = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = await orders_collection.update_one(
        {"_id": ObjectId(order_id)}, {"$set": update_fields}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    doc = await orders_collection.find_one({"_id": ObjectId(order_id)})
    return order_doc_to_out(doc)
