from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class PrescriptionStatus(str, Enum):
    PENDING = "pending"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSED = "processed"


class PrescriptionOut(BaseModel):
    id: str
    user_id: str
    user_name: Optional[str] = None
    user_phone: Optional[str] = None
    image_urls: List[str] = []
    notes: Optional[str] = None
    status: PrescriptionStatus = PrescriptionStatus.PENDING
    admin_notes: Optional[str] = None
    delivery_address: Optional[str] = None
    delivery_latitude: Optional[float] = None
    delivery_longitude: Optional[float] = None
    quoted_price: Optional[float] = None
    payment_status: str = "unpaid"
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    created_at: Optional[str] = None


class PrescriptionUpdate(BaseModel):
    status: Optional[PrescriptionStatus] = None
    admin_notes: Optional[str] = None
    quoted_price: Optional[float] = None
    payment_status: Optional[str] = None
