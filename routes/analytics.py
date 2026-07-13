from fastapi import APIRouter, status, Depends
from datetime import datetime, timezone

from config.database import sos_logs_collection
from models.analytics import SOSLogCreate

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

@router.post("/sos-logs", status_code=status.HTTP_201_CREATED)
async def log_sos(log: SOSLogCreate):
    """
    Log an emergency SOS trigger silently for analytics and heatmaps.
    """
    log_dict = log.model_dump()
    
    # Structure location as a GeoJSON Point for 2dsphere queries
    geojson_location = {
        "type": "Point",
        "coordinates": [log.longitude, log.latitude]
    }
    
    doc = {
        "user_id": log_dict.get("user_id"),
        "location": geojson_location,
        "pincode": log_dict.get("pincode"),
        "timestamp": log_dict.get("timestamp") or datetime.now(timezone.utc)
    }
    
    await sos_logs_collection.insert_one(doc)
    return {"status": "logged", "message": "Emergency SOS log saved successfully."}
