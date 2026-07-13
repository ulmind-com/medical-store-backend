import sys
import os
import types
from unittest.mock import MagicMock

# 1. Setup in-memory MongoDB Mock before any other local imports to prevent connection errors
class MockCollection:
    def __init__(self):
        self.data = {}

    async def find_one(self, query):
        is_available_filter = query.get("is_available")

        # Handle exact pincode match
        if "assigned_pincodes" in query:
            pincode = query["assigned_pincodes"]
            for doc in list(self.data.values()):
                if is_available_filter is not None and doc.get("is_available", True) != is_available_filter:
                    continue
                if pincode in doc.get("assigned_pincodes", []):
                    return doc
            return None

        # Handle spatial $near fallback check
        if "base_location" in query and "$near" in query["base_location"]:
            near_data = query["base_location"]["$near"]
            target_coords = near_data["$geometry"]["coordinates"]  # [longitude, latitude]
            max_dist = near_data.get("$maxDistance")

            import math
            closest_doc = None
            min_dist = float("inf")

            for doc in list(self.data.values()):
                if is_available_filter is not None and doc.get("is_available", True) != is_available_filter:
                    continue
                coords = doc["base_location"]["coordinates"]  # [longitude, latitude]
                
                # Approximate distance in meters (1 degree ~ 111,000 meters)
                diff_long = coords[0] - target_coords[0]
                diff_lat = coords[1] - target_coords[1]
                dist_meters = math.sqrt(diff_long**2 + diff_lat**2) * 111000
                if max_dist is not None and dist_meters > max_dist:
                    continue
                
                dist_sq = diff_long**2 + diff_lat**2
                if dist_sq < min_dist:
                    min_dist = dist_sq
                    closest_doc = doc
            return closest_doc

        # General query match
        for doc in list(self.data.values()):
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                return doc
        return None

    async def insert_one(self, doc):
        from bson import ObjectId
        if "_id" not in doc:
            doc["_id"] = ObjectId()
        self.data[doc["_id"]] = doc
        res = MagicMock()
        res.inserted_id = doc["_id"]
        return res

    async def find_one_and_update(self, query, update, return_document=True):
        target_id = query.get("_id")
        if not target_id:
            return None
        doc = self.data.get(target_id)
        if not doc:
            return None
        
        # Apply update
        if "$set" in update:
            for k, v in update["$set"].items():
                doc[k] = v
        self.data[target_id] = doc
        return doc

    async def create_index(self, keys, **kwargs):
        pass


mock_ambulances_collection = MockCollection()
mock_users_collection = MockCollection()
mock_sos_logs_collection = MockCollection()

# Create mock motor modules
motor_mock = types.ModuleType("motor")
motor_asyncio_mock = types.ModuleType("motor.motor_asyncio")
motor_mock.motor_asyncio = motor_asyncio_mock
sys.modules["motor"] = motor_mock
sys.modules["motor.motor_asyncio"] = motor_asyncio_mock

# Mock Database Client
mock_db = MagicMock()
mock_db.ambulances = mock_ambulances_collection
mock_db.users = mock_users_collection
mock_db.sos_logs = mock_sos_logs_collection

mock_client = MagicMock()
mock_client.__getitem__.return_value = mock_db
mock_client.medical_store = mock_db

motor_asyncio_mock.AsyncIOMotorClient = MagicMock(return_value=mock_client)

# Patch configuration and database module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import config.database
config.database.ambulances_collection = mock_ambulances_collection
config.database.users_collection = mock_users_collection
config.database.sos_logs_collection = mock_sos_logs_collection

import pytest
from fastapi.testclient import TestClient
from main import app
from middleware.auth import get_admin_user

# Override Clerk auth middleware to bypass during local unit testing
app.dependency_overrides[get_admin_user] = lambda: {"role": "admin", "email": "admin@medstore.com"}

client = TestClient(app)


def test_ambulance_routing():
    # Clear in-memory mock collection
    mock_ambulances_collection.data.clear()

    # 1. Create two ambulances with distinct assigned pincodes and locations
    amb1_payload = {
        "driver_name": "Ambulance One",
        "phone_number": "+1111111111",
        "assigned_pincodes": ["721154"],
        "base_location": {
            "type": "Point",
            "coordinates": [88.3639, 22.5726]  # [longitude, latitude]
        }
    }

    amb2_payload = {
        "driver_name": "Ambulance Two",
        "phone_number": "+2222222222",
        "assigned_pincodes": ["712501"],
        "base_location": {
            "type": "Point",
            "coordinates": [89.0, 23.0]  # [longitude, latitude]
        }
    }

    # Add Ambulance 1 as Admin
    resp1 = client.post("/api/admin/ambulances", json=amb1_payload)
    assert resp1.status_code == 201
    assert resp1.json()["driver_name"] == "Ambulance One"

    # Add Ambulance 2 as Admin
    resp2 = client.post("/api/admin/ambulances", json=amb2_payload)
    assert resp2.status_code == 201
    assert resp2.json()["driver_name"] == "Ambulance Two"

    # 2. Query exact PIN (721154) -> matches Ambulance One (Phase 1 Exact Match)
    resp_exact = client.get("/api/ambulances/nearest?pincode=721154&latitude=23.0&longitude=89.0")
    assert resp_exact.status_code == 200
    assert resp_exact.json()["driver_name"] == "Ambulance One"
    assert resp_exact.json()["phone_number"] == "+1111111111"
    assert resp_exact.json()["is_available"] is True

    # 3. Query unassigned PIN (75435) -> falls back to closest coordinates (Ambulance Two) (Phase 2 Spatial Fallback)
    resp_fallback = client.get("/api/ambulances/nearest?pincode=75435&latitude=22.95&longitude=88.95")
    assert resp_fallback.status_code == 200
    assert resp_fallback.json()["driver_name"] == "Ambulance Two"
    assert resp_fallback.json()["phone_number"] == "+2222222222"
    assert resp_fallback.json()["is_available"] is True

    # 4. Toggle Ambulance One availability to False (busy)
    amb1_id = resp1.json()["id"]
    resp_toggle = client.put(f"/api/ambulances/{amb1_id}/availability?is_available=false")
    assert resp_toggle.status_code == 200
    assert resp_toggle.json()["is_available"] is False

    # 5. Query exact PIN (721154) again -> should NOT match Ambulance One (busy) but fall back to closest available (Ambulance Two)
    resp_exact_after_busy = client.get("/api/ambulances/nearest?pincode=721154&latitude=22.95&longitude=88.95")
    assert resp_exact_after_busy.status_code == 200
    assert resp_exact_after_busy.json()["driver_name"] == "Ambulance Two"
    assert resp_exact_after_busy.json()["phone_number"] == "+2222222222"

    # 6. Toggle Ambulance Two availability to False too
    amb2_id = resp2.json()["id"]
    resp_toggle2 = client.put(f"/api/ambulances/{amb2_id}/availability?is_available=false")
    assert resp_toggle2.status_code == 200
    assert resp_toggle2.json()["is_available"] is False

    # 7. Querying nearest should return 404 since no ambulances are available
    resp_none = client.get("/api/ambulances/nearest?pincode=721154&latitude=22.5726&longitude=88.3639")
    assert resp_none.status_code == 404
    assert resp_none.json()["detail"] == "All our ambulances are currently far away. Please call the national emergency number (102/112)."

    # 8. Set them back to True, and search from coordinates that are very far (e.g. lat=0.0, lng=0.0) -> should fail with 404
    client.put(f"/api/ambulances/{amb1_id}/availability?is_available=true")
    client.put(f"/api/ambulances/{amb2_id}/availability?is_available=true")
    resp_far = client.get("/api/ambulances/nearest?pincode=75435&latitude=0.0&longitude=0.0")
    assert resp_far.status_code == 404
    assert resp_far.json()["detail"] == "All our ambulances are currently far away. Please call the national emergency number (102/112)."

    # 9. Test SOS Analytics Logging endpoint
    analytics_payload = {
        "user_id": "test_user_123",
        "latitude": 22.5726,
        "longitude": 88.3639,
        "pincode": "721154"
    }
    resp_analytics = client.post("/api/analytics/sos-logs", json=analytics_payload)
    assert resp_analytics.status_code == 201
    assert resp_analytics.json()["status"] == "logged"
    
    # Verify it got inserted into the mock collection
    assert len(mock_sos_logs_collection.data) == 1
    logged_doc = list(mock_sos_logs_collection.data.values())[0]
    assert logged_doc["user_id"] == "test_user_123"
    assert logged_doc["pincode"] == "721154"
    assert logged_doc["location"]["coordinates"] == [88.3639, 22.5726]
