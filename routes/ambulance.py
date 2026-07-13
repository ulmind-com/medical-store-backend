from fastapi import APIRouter, HTTPException, status, Query, Depends
from bson import ObjectId
from datetime import datetime
from typing import List, Optional

from config.database import ambulances_collection
from models.ambulance import AmbulanceCreate, AmbulanceOut, GeoPoint
from middleware.auth import get_admin_user

router = APIRouter(tags=["Ambulances"])


def ambulance_doc_to_out(doc: dict) -> AmbulanceOut:
    return AmbulanceOut(
        id=str(doc["_id"]),
        driver_name=doc["driver_name"],
        phone_number=doc["phone_number"],
        assigned_pincodes=doc.get("assigned_pincodes", []),
        base_location=GeoPoint(
            type=doc["base_location"]["type"],
            coordinates=doc["base_location"]["coordinates"]
        ),
        is_available=doc.get("is_available", True)
    )


@router.post("/api/admin/ambulances", response_model=AmbulanceOut, status_code=status.HTTP_201_CREATED)
async def create_ambulance(
    data: AmbulanceCreate,
    admin: dict = Depends(get_admin_user)
):
    """
    Admin endpoint to manually add/seed a new ambulance in the database.
    """
    doc = data.model_dump()
    result = await ambulances_collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return ambulance_doc_to_out(doc)


@router.get("/api/ambulances/nearest", response_model=AmbulanceOut)
async def get_nearest_ambulance(
    pincode: str = Query(..., description="User's current PIN code"),
    latitude: float = Query(..., description="User's current latitude"),
    longitude: float = Query(..., description="User's current longitude")
):
    """
    Finds the optimal ambulance:
    Phase 1: Search for an exact match where the requested pincode is in assigned_pincodes AND is_available is True.
    Phase 2: Fall back to spatial proximity using 2dsphere index and $near query, filtering for is_available is True.
    """
    # Phase 1: Exact Match
    exact_match = await ambulances_collection.find_one({
        "assigned_pincodes": pincode,
        "is_available": True
    })
    if exact_match:
        return ambulance_doc_to_out(exact_match)

    # Phase 2: Spatial Fallback
    near_query = {
        "is_available": True,
        "base_location": {
            "$near": {
                "$geometry": {
                    "type": "Point",
                    "coordinates": [longitude, latitude]
                },
                "$maxDistance": 20000
            }
        }
    }

    closest = await ambulances_collection.find_one(near_query)
    if not closest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="All our ambulances are currently far away. Please call the national emergency number (102/112)."
        )

    return ambulance_doc_to_out(closest)


@router.put("/api/ambulances/{ambulance_id}/availability", response_model=AmbulanceOut)
async def toggle_ambulance_availability(
    ambulance_id: str,
    is_available: bool = Query(..., description="Availability status to set")
):
    """
    Toggle availability status of an ambulance.
    """
    if not ObjectId.is_valid(ambulance_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid ambulance ID format."
        )
    
    result = await ambulances_collection.find_one_and_update(
        {"_id": ObjectId(ambulance_id)},
        {"$set": {"is_available": is_available}},
        return_document=True
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ambulance not found."
        )
    
    return ambulance_doc_to_out(result)
