from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class DayOfWeek(str, Enum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class TimeSlot(BaseModel):
    start_time: str  # "09:00"
    end_time: str  # "12:00"


class Availability(BaseModel):
    day: DayOfWeek
    slots: List[TimeSlot]


class DoctorCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    specialty: str = Field(..., min_length=2)
    qualification: Optional[str] = None
    experience_years: int = Field(default=0, ge=0)
    consultation_fee: float = Field(..., gt=0)
    about: Optional[str] = None
    image_url: Optional[str] = None
    phone: Optional[str] = None
    availability: Optional[List[Availability]] = None
    is_active: bool = True


class DoctorUpdate(BaseModel):
    name: Optional[str] = None
    specialty: Optional[str] = None
    qualification: Optional[str] = None
    experience_years: Optional[int] = None
    consultation_fee: Optional[float] = None
    about: Optional[str] = None
    image_url: Optional[str] = None
    phone: Optional[str] = None
    availability: Optional[List[Availability]] = None
    is_active: Optional[bool] = None


class DoctorOut(BaseModel):
    id: str
    name: str
    specialty: str
    qualification: Optional[str] = None
    experience_years: int
    consultation_fee: float
    about: Optional[str] = None
    image_url: Optional[str] = None
    phone: Optional[str] = None
    availability: Optional[List[Availability]] = None
    is_active: bool = True
    rating: float = 0.0
    total_reviews: int = 0
    created_at: Optional[str] = None
