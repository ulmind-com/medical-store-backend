from pydantic import BaseModel, Field
from typing import Optional

class CrashLogCreate(BaseModel):
    error_message: str
    component_stack: str
    user_id: Optional[str] = None
    timestamp: Optional[str] = None
