from pydantic import BaseModel, Field
from typing import List, Optional

class DosageInput(BaseModel):
    medicine_id: str
    medicine_name: str
    daily_dosage: float = Field(..., gt=0.0)

class ReminderSetupRequest(BaseModel):
    order_id: str
    dosages: List[DosageInput]

class ReminderToggleRequest(BaseModel):
    is_active: bool

class ReminderOut(BaseModel):
    id: str
    user_id: str
    order_id: str
    medicine_id: str
    medicine_name: str
    unit_type: str
    quantity_per_unit: int
    quantity_bought: int
    daily_dosage: float
    total_units: float
    days_to_deplete: float
    trigger_date: str  # YYYY-MM-DD
    is_active: bool
    created_at: str
