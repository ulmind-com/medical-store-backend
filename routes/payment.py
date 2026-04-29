import razorpay
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from config.settings import get_settings
from config.database import orders_collection
from middleware.auth import get_current_user
from bson import ObjectId

settings = get_settings()
router = APIRouter(prefix="/api/payment", tags=["Payment"])

razorpay_client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
)


class CreatePaymentOrder(BaseModel):
    order_id: str  # Our internal order ID


class VerifyPayment(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    order_id: str  # Our internal order ID


@router.post("/create-order")
async def create_razorpay_order(
    data: CreatePaymentOrder,
    current_user: dict = Depends(get_current_user),
):
    order = await orders_collection.find_one({"_id": ObjectId(data.order_id)})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order["user_id"] != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="Not authorized")

    if order.get("payment_method") != "razorpay":
        raise HTTPException(status_code=400, detail="Payment method is not Razorpay")

    amount_in_paise = int(order["total_amount"] * 100)

    razorpay_order = razorpay_client.order.create({
        "amount": amount_in_paise,
        "currency": "INR",
        "receipt": str(order["_id"]),
    })

    await orders_collection.update_one(
        {"_id": ObjectId(data.order_id)},
        {"$set": {"razorpay_order_id": razorpay_order["id"]}},
    )

    return {
        "razorpay_order_id": razorpay_order["id"],
        "amount": amount_in_paise,
        "currency": "INR",
        "key_id": settings.RAZORPAY_KEY_ID,
    }


@router.post("/verify")
async def verify_payment(
    data: VerifyPayment,
    current_user: dict = Depends(get_current_user),
):
    try:
        razorpay_client.utility.verify_payment_signature({
            "razorpay_order_id": data.razorpay_order_id,
            "razorpay_payment_id": data.razorpay_payment_id,
            "razorpay_signature": data.razorpay_signature,
        })
    except Exception:
        await orders_collection.update_one(
            {"_id": ObjectId(data.order_id)},
            {"$set": {"payment_status": "failed"}},
        )
        raise HTTPException(status_code=400, detail="Payment verification failed")

    await orders_collection.update_one(
        {"_id": ObjectId(data.order_id)},
        {"$set": {
            "payment_status": "completed",
            "razorpay_payment_id": data.razorpay_payment_id,
            "status": "confirmed",
        }},
    )

    return {"message": "Payment verified successfully", "status": "completed"}
