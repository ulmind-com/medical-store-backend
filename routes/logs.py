from fastapi import APIRouter, status
from config.database import crash_logs_collection
from models.crash_log import CrashLogCreate
from datetime import datetime

router = APIRouter(prefix="/api/logs", tags=["Logs"])

@router.post("/crash", status_code=status.HTTP_201_CREATED)
async def log_crash(log: CrashLogCreate):
    log_dict = log.model_dump()
    if not log_dict.get("timestamp"):
        log_dict["timestamp"] = datetime.utcnow().isoformat()
    
    await crash_logs_collection.insert_one(log_dict)
    return {"status": "logged", "message": "Crash report stored successfully"}
