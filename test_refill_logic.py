import os
import sys
import types
from unittest.mock import MagicMock, patch
from datetime import date, timedelta

# 1. Setup in-memory MongoDB Mock before any other local imports to prevent connection errors
class MockCollection:
    def __init__(self):
        self.data = {}

    async def find_one(self, query):
        from bson import ObjectId
        for doc in list(self.data.values()):
            match = True
            for k, v in query.items():
                val = doc.get(k)
                if k == "_id" and isinstance(v, ObjectId):
                    val = ObjectId(val) if not isinstance(val, ObjectId) else val
                if val != v:
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

    async def delete_one(self, query):
        to_del = []
        for oid, doc in list(self.data.items()):
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                to_del.append(oid)
        for oid in to_del:
            if oid in self.data:
                del self.data[oid]
        res = MagicMock()
        res.deleted_count = len(to_del)
        return res

    async def update_one(self, query, update):
        doc = await self.find_one(query)
        if doc:
            if "$set" in update:
                doc.update(update["$set"])
        res = MagicMock()
        res.modified_count = 1
        return res

    def find(self, query=None):
        query = query or {}
        results = []
        for doc in list(self.data.values()):
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                results.append(doc)
        
        # Simple async cursor mock
        class AsyncCursor:
            def __init__(self, items):
                self.items = items
            def sort(self, key, direction=1):
                return self
            async def to_list(self, length=100):
                return self.items[:length]
                
        return AsyncCursor(results)

mock_orders_collection = MockCollection()
mock_reminders_collection = MockCollection()
mock_users_collection = MockCollection()
mock_medicines_collection = MockCollection()

# Create mock motor modules
motor_mock = types.ModuleType("motor")
motor_asyncio_mock = types.ModuleType("motor.motor_asyncio")
motor_mock.motor_asyncio = motor_asyncio_mock
sys.modules["motor"] = motor_mock
sys.modules["motor.motor_asyncio"] = motor_asyncio_mock

# Mock Client and Database chain
mock_db = MagicMock()
mock_db.orders = mock_orders_collection
mock_db.reminders = mock_reminders_collection
mock_db.users = mock_users_collection
mock_db.medicines = mock_medicines_collection

mock_client = MagicMock()
mock_client.__getitem__.return_value = mock_db
mock_client.medical_store = mock_db

motor_asyncio_mock.AsyncIOMotorClient = MagicMock(return_value=mock_client)

# Patch the config.database module so it gets our mock collections
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import config.database
config.database.orders_collection = mock_orders_collection
config.database.reminders_collection = mock_reminders_collection
config.database.users_collection = mock_users_collection
config.database.medicines_collection = mock_medicines_collection

from main import app
from fastapi.testclient import TestClient
from middleware.auth import get_current_user

# Mock auth dependency
async def override_get_current_user():
    return {
        "id": "507f1f77bcf86cd799439011",
        "name": "Test User",
        "email": "test@example.com",
        "role": "user"
    }

app.dependency_overrides[get_current_user] = override_get_current_user

def run_refill_tests():
    print("=" * 60)
    print("  REFILL REMINDER SYSTEM MATH & SCHEDULER TESTS")
    print("=" * 60)

    client = TestClient(app)
    
    # 1. Setup mock order
    from bson import ObjectId
    order_id = str(ObjectId())
    
    mock_order = {
        "_id": ObjectId(order_id),
        "user_id": "507f1f77bcf86cd799439011",
        "items": [
            {
                "medicine_id": "med_tabs_1",
                "medicine_name": "Paracetamol Strips",
                "quantity": 2, # strips
                "price": 40.0,
                "unit_type": "tablet",
                "quantity_per_unit": 15 # 15 tabs per strip
            },
            {
                "medicine_id": "med_syrup_2",
                "medicine_name": "Cough Syrup",
                "quantity": 1, # bottle
                "price": 120.0,
                "unit_type": "syrup",
                "quantity_per_unit": 50 # 50ml per bottle
            },
            {
                "medicine_id": "med_tabs_short_3",
                "medicine_name": "Immediate Tabs",
                "quantity": 1,
                "price": 20.0,
                "unit_type": "tablet",
                "quantity_per_unit": 15
            }
        ],
        "subtotal": 200.0,
        "delivery_charge": 20.0,
        "total_amount": 220.0,
        "delivery_address": "Test Street 123",
        "delivery_latitude": 22.5,
        "delivery_longitude": 88.3,
        "payment_method": "cod",
        "payment_status": "pending",
        "status": "placed",
        "created_at": "2026-07-10T00:00:00"
    }
    
    mock_orders_collection.data[ObjectId(order_id)] = mock_order

    # Setup dosages for reminders setup
    setup_payload = {
        "order_id": order_id,
        "dosages": [
            {
                "medicine_id": "med_tabs_1",
                "medicine_name": "Paracetamol Strips",
                "daily_dosage": 1.0 # 1 tab / day
            },
            {
                "medicine_id": "med_syrup_2",
                "medicine_name": "Cough Syrup",
                "daily_dosage": 5.0 # 5ml / day
            },
            {
                "medicine_id": "med_tabs_short_3",
                "medicine_name": "Immediate Tabs",
                "daily_dosage": 5.0 # 5 tabs / day (depleted in 3 days)
            }
        ]
    }

    # 2. Test Setup Reminders endpoint
    print("[TEST 1] Setting up reminders via POST /api/reminders/setup...")
    response = client.post("/api/reminders/setup", json=setup_payload)
    if response.status_code != 201:
        print(f"❌ Failure: setup reminders failed: {response.status_code} - {response.text}")
        return False
        
    created_reminders = response.json()
    if len(created_reminders) != 3:
        print(f"❌ Failure: expected 3 reminders, got {len(created_reminders)}")
        return False
    print("✅ Success: POST /api/reminders/setup returned 201 Created")

    # 3. Test Math logic
    print("[TEST 2] Verifying calculation math correctness...")
    today = date.today()
    
    # Check Case 1: Paracetamol Strips
    # Total units = 2 * 15 = 30
    # Days to deplete = 30 / 1 = 30 days
    # Trigger date offset = 30 - 4 = 26 days
    case_1 = next(r for r in created_reminders if r["medicine_id"] == "med_tabs_1")
    expected_trigger_1 = (today + timedelta(days=26)).strftime("%Y-%m-%d")
    if case_1["trigger_date"] != expected_trigger_1:
        print(f"❌ Failure Case 1: expected trigger_date {expected_trigger_1}, got {case_1['trigger_date']}")
        return False
    print("✅ Success Case 1: 30 tablets at 1/day triggers in exactly 26 days")

    # Check Case 2: Cough Syrup
    # Total units = 1 * 50 = 50
    # Days to deplete = 50 / 5 = 10 days
    # Trigger date offset = 10 - 4 = 6 days
    case_2 = next(r for r in created_reminders if r["medicine_id"] == "med_syrup_2")
    expected_trigger_2 = (today + timedelta(days=6)).strftime("%Y-%m-%d")
    if case_2["trigger_date"] != expected_trigger_2:
        print(f"❌ Failure Case 2: expected trigger_date {expected_trigger_2}, got {case_2['trigger_date']}")
        return False
    print("✅ Success Case 2: 50ml syrup at 5ml/day triggers in exactly 6 days")

    # Check Case 3: Immediate Tabs (Short duration clamping)
    # Total units = 1 * 15 = 15
    # Days to deplete = 15 / 5 = 3 days
    # Trigger date offset = 3 - 4 = -1 day -> clamped to 0 days (today)
    case_3 = next(r for r in created_reminders if r["medicine_id"] == "med_tabs_short_3")
    expected_trigger_3 = today.strftime("%Y-%m-%d")
    if case_3["trigger_date"] != expected_trigger_3:
        print(f"❌ Failure Case 3: expected trigger_date {expected_trigger_3}, got {case_3['trigger_date']}")
        return False
    print("✅ Success Case 3: 15 tablets at 5/day clamps trigger date to today (offset <= 0)")

    # 4. Test Toggle endpoint
    print("[TEST 3] Toggling reminder active state...")
    reminder_id = case_1["id"]
    response = client.put(f"/api/reminders/{reminder_id}/toggle", json={"is_active": False})
    if response.status_code != 200:
        print(f"❌ Failure: toggle failed: {response.status_code}")
        return False
        
    toggled = response.json()
    if toggled["is_active"] is not False:
        print("❌ Failure: toggle did not disable reminder")
        return False
    print("✅ Success: Reminder toggled OFF")

    # 5. Test Scheduler Triggering (simulate daily midnight job)
    print("[TEST 4] Simulating background scheduler job execution...")
    # Add mock user with a push token to users collection
    user_oid = ObjectId("507f1f77bcf86cd799439011")
    mock_users_collection.data[user_oid] = {
        "_id": user_oid,
        "name": "Test User",
        "email": "test@example.com",
        "expo_push_token": "ExponentPushToken[mock_token_123]"
    }
    
    # Trigger should match Case 3 which has trigger_date = today
    from utils.reminder_scheduler import send_daily_refill_reminders
    import asyncio
    
    # Mock the actual expo push network request to count calls
    with patch("utils.notifications.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = '{"data":{"status":"ok"}}'
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        sent_count = loop.run_until_complete(send_daily_refill_reminders())
        loop.close()
        
        if sent_count != 1:
            print(f"❌ Failure: expected 1 notification sent, got {sent_count}")
            return False
            
        # Verify it was for Case 3 (Immediate Tabs)
        mock_post.assert_called_once()
        call_json = mock_post.call_args[1]["json"]
        if "Immediate Tabs" not in call_json["body"]:
            print(f"❌ Failure: notification body was wrong: {call_json['body']}")
            return False
            
    print("✅ Success: Daily scheduler successfully triggered 1 push notification for today's depleted medicine")

    print("\n🎉 ALL REFILL REMINDER MATH & SCHEDULER TESTS PASSED SUCCESSFULLY!")
    return True

if __name__ == "__main__":
    ok = run_refill_tests()
    if not ok:
        sys.exit(1)
    sys.exit(0)
