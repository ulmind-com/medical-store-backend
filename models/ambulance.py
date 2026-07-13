from pydantic import BaseModel, Field
from typing import List, Optional

class GeoPoint(BaseModel):
    type: str = "Point"
    coordinates: List[float] # [longitude, latitude]

class AmbulanceCreate(BaseModel):
    driver_name: str = Field(..., min_length=2, max_length=100)
    phone_number: str = Field(..., min_length=5, max_length=20)
    assigned_pincodes: List[str] = Field(default_factory=list)
    base_location: GeoPoint
    is_available: bool = Field(default=True)

class AmbulanceOut(BaseModel):
    id: str
    driver_name: str
    phone_number: str
    assigned_pincodes: List[str]
    base_location: GeoPoint
    is_available: bool
