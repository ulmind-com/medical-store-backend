from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class AppointmentStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AppointmentCreate(BaseModel):
    doctor_id: str
    date: str  # "2026-05-01"
    time_slot: str  # "09:00 - 09:30"
    reason: Optional[str] = None
    notes: Optional[str] = None
    payment_method: str = "offline"  # "offline" | "online"


class AppointmentUpdate(BaseModel):
    status: Optional[AppointmentStatus] = None
    notes: Optional[str] = None
    payment_status: Optional[str] = None
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None


class AppointmentOut(BaseModel):
    id: str
    user_id: str
    doctor_id: str
    doctor_name: Optional[str] = None
    doctor_specialty: Optional[str] = None
    doctor_image: Optional[str] = None
    date: str
    time_slot: str
    reason: Optional[str] = None
    notes: Optional[str] = None
    status: AppointmentStatus = AppointmentStatus.PENDING
    payment_method: str = "offline"
    payment_status: str = "pending"
    consultation_fee: float = 0.0
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    created_at: Optional[str] = None
