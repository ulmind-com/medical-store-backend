from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class MedicineCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    generic_name: Optional[str] = None
    description: Optional[str] = None
    category: str = Field(..., min_length=2)
    manufacturer: Optional[str] = None
    price: float = Field(..., gt=0)
    discount_price: Optional[float] = None
    discount_valid_until: Optional[str] = None
    stock: int = Field(default=0, ge=0)
    requires_prescription: bool = False
    image_url: Optional[str] = None
    dosage_form: Optional[str] = None  # tablet, syrup, injection, etc.
    strength: Optional[str] = None  # e.g., "500mg"
    pack_size: Optional[str] = None  # e.g., "10 tablets"


class MedicineUpdate(BaseModel):
    name: Optional[str] = None
    generic_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    manufacturer: Optional[str] = None
    price: Optional[float] = None
    discount_price: Optional[float] = None
    discount_valid_until: Optional[str] = None
    stock: Optional[int] = None
    requires_prescription: Optional[bool] = None
    image_url: Optional[str] = None
    dosage_form: Optional[str] = None
    strength: Optional[str] = None
    pack_size: Optional[str] = None


class MedicineOut(BaseModel):
    id: str
    name: str
    generic_name: Optional[str] = None
    description: Optional[str] = None
    category: str
    manufacturer: Optional[str] = None
    price: float
    discount_price: Optional[float] = None
    discount_valid_until: Optional[str] = None
    stock: int
    requires_prescription: bool = False
    image_url: Optional[str] = None
    dosage_form: Optional[str] = None
    strength: Optional[str] = None
    pack_size: Optional[str] = None
    created_at: Optional[str] = None


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    icon: Optional[str] = None
    image_url: Optional[str] = None
