from fastapi import APIRouter, Depends
from config.database import (
    users_collection, medicines_collection, doctors_collection,
    orders_collection, prescriptions_collection, appointments_collection,
)
from middleware.auth import get_admin_user

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get("/dashboard")
async def get_dashboard_stats(admin: dict = Depends(get_admin_user)):
    total_users = await users_collection.count_documents({"role": "user"})
    total_medicines = await medicines_collection.count_documents({})
    total_doctors = await doctors_collection.count_documents({})
    total_orders = await orders_collection.count_documents({})
    pending_orders = await orders_collection.count_documents({"status": {"$in": ["pending", "placed"]}})
    total_prescriptions = await prescriptions_collection.count_documents({})
    pending_prescriptions = await prescriptions_collection.count_documents({"status": "pending"})
    total_appointments = await appointments_collection.count_documents({})
    pending_appointments = await appointments_collection.count_documents({"status": "pending"})

    # Revenue
    pipeline = [
        {"$match": {"payment_status": "completed"}},
        {"$group": {"_id": None, "total": {"$sum": "$total_amount"}}},
    ]
    revenue_result = await orders_collection.aggregate(pipeline).to_list(length=1)
    total_revenue = revenue_result[0]["total"] if revenue_result else 0

    # Recent orders
    recent_orders_cursor = orders_collection.find().sort("created_at", -1).limit(5)
    recent_orders = await recent_orders_cursor.to_list(length=5)
    recent_orders_data = [
        {
            "id": str(o["_id"]),
            "user_name": o.get("user_name", ""),
            "total_amount": o["total_amount"],
            "status": "placed" if o.get("status") == "pending" else o.get("status", "placed"),
            "created_at": o.get("created_at", ""),
        }
        for o in recent_orders
    ]

    return {
        "total_users": total_users,
        "total_medicines": total_medicines,
        "total_doctors": total_doctors,
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "total_prescriptions": total_prescriptions,
        "pending_prescriptions": pending_prescriptions,
        "total_appointments": total_appointments,
        "pending_appointments": pending_appointments,
        "total_revenue": total_revenue,
        "recent_orders": recent_orders_data,
    }
