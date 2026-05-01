from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class OrderStatus(str, Enum):
    PLACED = "placed"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class PaymentMethod(str, Enum):
    COD = "cod"
    RAZORPAY = "razorpay"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class AddressType(str, Enum):
    HOME = "home"
    WORK = "work"
    OTHER = "other"


class OrderItem(BaseModel):
    medicine_id: str
    medicine_name: str
    quantity: int = Field(..., gt=0)
    price: float
    image_url: Optional[str] = None


class OrderCreate(BaseModel):
    items: List[OrderItem]
    delivery_address: str
    delivery_latitude: float
    delivery_longitude: float
    address_type: AddressType = AddressType.HOME
    address_details: Optional[str] = None
    payment_method: PaymentMethod = PaymentMethod.COD
    notes: Optional[str] = None


class OrderUpdate(BaseModel):
    status: Optional[OrderStatus] = None
    payment_status: Optional[PaymentStatus] = None
    notes: Optional[str] = None


class OrderOut(BaseModel):
    id: str
    user_id: str
    user_name: Optional[str] = None
    user_phone: Optional[str] = None
    items: List[OrderItem]
    subtotal: float
    delivery_charge: float
    total_amount: float
    delivery_address: str
    delivery_latitude: float
    delivery_longitude: float
    address_type: AddressType = AddressType.HOME
    address_details: Optional[str] = None
    distance_km: float = 0.0
    payment_method: PaymentMethod
    payment_status: PaymentStatus = PaymentStatus.PENDING
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    status: OrderStatus = OrderStatus.PLACED
    notes: Optional[str] = None
    created_at: Optional[str] = None
