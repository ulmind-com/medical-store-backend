from fastapi import APIRouter, HTTPException, status, Depends
from bson import ObjectId
from datetime import datetime, timedelta, date
from typing import List

from config.database import reminders_collection, orders_collection, medicines_collection
from models.reminder import ReminderSetupRequest, ReminderToggleRequest, ReminderOut, DosageInput
from middleware.auth import get_current_user

router = APIRouter(prefix="/api/reminders", tags=["Reminders"])

def reminder_doc_to_out(doc: dict) -> ReminderOut:
    return ReminderOut(
        id=str(doc["_id"]),
        user_id=doc["user_id"],
        order_id=doc["order_id"],
        medicine_id=doc["medicine_id"],
        medicine_name=doc["medicine_name"],
        unit_type=doc.get("unit_type", "tablet"),
        quantity_per_unit=doc.get("quantity_per_unit", 1),
        quantity_bought=doc.get("quantity_bought", 1),
        daily_dosage=doc["daily_dosage"],
        total_units=doc["total_units"],
        days_to_deplete=doc["days_to_deplete"],
        trigger_date=doc["trigger_date"],
        is_active=doc.get("is_active", True),
        created_at=doc.get("created_at", datetime.utcnow().isoformat())
    )

@router.post("/setup", response_model=List[ReminderOut], status_code=status.HTTP_201_CREATED)
async def setup_reminders(
    data: ReminderSetupRequest,
    current_user: dict = Depends(get_current_user)
):
    # Find order
    order = await orders_collection.find_one({"_id": ObjectId(data.order_id)})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    # Ensure user owns this order
    if order["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized to access this order")

    reminders = []
    today = date.today()

    for dosage_in in data.dosages:
        # Find item in the order
        order_item = None
        for item in order["items"]:
            if item["medicine_id"] == dosage_in.medicine_id:
                order_item = item
                break

        if not order_item:
            continue

        # Extract unit type and capacity
        unit_type = order_item.get("unit_type", "tablet")
        quantity_per_unit = order_item.get("quantity_per_unit", 1)
        quantity_bought = order_item.get("quantity")

        # The math
        total_units = float(quantity_bought * quantity_per_unit)
        days_to_deplete = total_units / dosage_in.daily_dosage
        
        # Trigger Date = Today + Days to Deplete - 4 Days
        days_offset = int(days_to_deplete) - 4
        if days_offset < 0:
            days_offset = 0
            
        trigger_date = today + timedelta(days=days_offset)
        trigger_date_str = trigger_date.strftime("%Y-%m-%d")

        # Create or update reminder
        reminder_doc = {
            "user_id": current_user["id"],
            "order_id": data.order_id,
            "medicine_id": dosage_in.medicine_id,
            "medicine_name": dosage_in.medicine_name,
            "unit_type": unit_type,
            "quantity_per_unit": quantity_per_unit,
            "quantity_bought": quantity_bought,
            "daily_dosage": dosage_in.daily_dosage,
            "total_units": total_units,
            "days_to_deplete": days_to_deplete,
            "trigger_date": trigger_date_str,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat()
        }

        # Check if reminder already exists for user and medicine
        existing = await reminders_collection.find_one({
            "user_id": current_user["id"],
            "medicine_id": dosage_in.medicine_id
        })

        if existing:
            await reminders_collection.update_one(
                {"_id": existing["_id"]},
                {"$set": reminder_doc}
            )
            reminder_doc["_id"] = existing["_id"]
        else:
            res = await reminders_collection.insert_one(reminder_doc)
            reminder_doc["_id"] = res.inserted_id

        reminders.append(reminder_doc_to_out(reminder_doc))

    return reminders

@router.get("/", response_model=List[ReminderOut])
async def get_reminders(current_user: dict = Depends(get_current_user)):
    cursor = reminders_collection.find({"user_id": current_user["id"]}).sort("created_at", -1)
    docs = await cursor.to_list(length=100)
    return [reminder_doc_to_out(d) for d in docs]

@router.put("/{reminder_id}/toggle", response_model=ReminderOut)
async def toggle_reminder(
    reminder_id: str,
    data: ReminderToggleRequest,
    current_user: dict = Depends(get_current_user)
):
    reminder = await reminders_collection.find_one({"_id": ObjectId(reminder_id)})
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
        
    if reminder["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    await reminders_collection.update_one(
        {"_id": ObjectId(reminder_id)},
        {"$set": {"is_active": data.is_active}}
    )
    reminder["is_active"] = data.is_active
    return reminder_doc_to_out(reminder)

@router.delete("/{reminder_id}")
async def delete_reminder(
    reminder_id: str,
    current_user: dict = Depends(get_current_user)
):
    reminder = await reminders_collection.find_one({"_id": ObjectId(reminder_id)})
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
        
    if reminder["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")

    await reminders_collection.delete_one({"_id": ObjectId(reminder_id)})
    return {"message": "Reminder deleted successfully"}
