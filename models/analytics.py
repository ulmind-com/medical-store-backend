from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class GeoPoint(BaseModel):
    type: str = "Point"
    coordinates: List[float]  # [longitude, latitude]

class SOSLogCreate(BaseModel):
    user_id: Optional[str] = None
    latitude: float
    longitude: float
    pincode: Optional[str] = None
    timestamp: Optional[datetime] = None

class SOSLogOut(BaseModel):
    id: str = Field(alias="_id")
    user_id: Optional[str]
    location: GeoPoint
    pincode: Optional[str]
    timestamp: datetime
