import os
import sys
import re
import types
from unittest.mock import MagicMock

# 1. Setup in-memory MongoDB Mock before any other local imports to prevent connection errors
class MockCollection:
    def __init__(self):
        self.data = {}

    async def find_one(self, query):
        from bson import ObjectId
        for doc in list(self.data.values()):
            match = True
            for k, v in query.items():
                # Handle ObjectId casting
                val = doc.get(k)
                if k == "_id" and isinstance(v, ObjectId):
                    val = ObjectId(val) if not isinstance(val, ObjectId) else val
                elif k == "_id" and isinstance(v, dict) and "$in" in v:
                    # Not needed for simple auth tests
                    pass
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
        if doc and "$set" in update:
            doc.update(update["$set"])
        res = MagicMock()
        res.modified_count = 1
        return res

mock_users_collection = MockCollection()

# Create mock motor modules
motor_mock = types.ModuleType("motor")
motor_asyncio_mock = types.ModuleType("motor.motor_asyncio")
motor_mock.motor_asyncio = motor_asyncio_mock
sys.modules["motor"] = motor_mock
sys.modules["motor.motor_asyncio"] = motor_asyncio_mock

# Mock Client and Database chain
mock_db = MagicMock()
mock_db.users = mock_users_collection

mock_client = MagicMock()
mock_client.__getitem__.return_value = mock_db
mock_client.medical_store = mock_db

motor_asyncio_mock.AsyncIOMotorClient = MagicMock(return_value=mock_client)

# Patch the db.py / config.database module so it gets our mock_users_collection
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import config.database
config.database.users_collection = mock_users_collection

# Import main and TestClient
from main import app
from fastapi.testclient import TestClient

def run_static_checks():
    print("=" * 60)
    print("  STATIC CLEANUP VERIFICATION CHECKS")
    print("=" * 60)

    errors = 0

    # 1. Check requirements.txt
    print("[CHECK 1] Verifying requirements.txt...")
    reqs_path = "requirements.txt"
    if os.path.exists(reqs_path):
        with open(reqs_path, "r") as f:
            content = f.read()
        if "firebase-admin" in content or "firebase" in content:
            print("❌ Failure: 'firebase' package reference found in requirements.txt")
            errors += 1
        else:
            print("✅ Success: No Firebase packages in requirements.txt")
    else:
        print("⚠️ Warning: requirements.txt not found")

    # 2. Check routes/auth.py for imports and code references
    print("[CHECK 2] Verifying routes/auth.py content...")
    auth_routes_path = "routes/auth.py"
    if os.path.exists(auth_routes_path):
        with open(auth_routes_path, "r") as f:
            content = f.read()
        
        forbidden_patterns = [
            (r"firebase_admin", "Firebase Admin module import"),
            (r"GoogleLoginRequest", "GoogleLoginRequest schema import"),
            (r"/google-login", "google-login endpoint route"),
            (r"/google/start", "google/start endpoint route"),
            (r"/google/callback", "google/callback endpoint route"),
            (r"_upsert_google_user", "Google user helper function")
        ]

        for pattern, label in forbidden_patterns:
            if re.search(pattern, content):
                print(f"❌ Failure: Reference to '{label}' found in routes/auth.py")
                errors += 1
            else:
                print(f"✅ Success: No reference to '{label}' in routes/auth.py")
    else:
        print("❌ Failure: routes/auth.py not found!")
        errors += 1

    # 3. Check models/user.py for GoogleLoginRequest
    print("[CHECK 3] Verifying models/user.py content...")
    user_models_path = "models/user.py"
    if os.path.exists(user_models_path):
        with open(user_models_path, "r") as f:
            content = f.read()
        if "GoogleLoginRequest" in content:
            print("❌ Failure: 'GoogleLoginRequest' found in models/user.py")
            errors += 1
        else:
            print("✅ Success: No 'GoogleLoginRequest' in models/user.py")
    else:
        print("❌ Failure: models/user.py not found!")
        errors += 1

    return errors == 0

def run_functional_tests():
    print("\n" + "=" * 60)
    print("  FUNCTIONAL JWT AUTHENTICATION FLOW TESTS (IN-MEMORY)")
    print("=" * 60)

    client = TestClient(app)
    
    test_email = "cleanup_test_user@example.com"
    test_password = "securePassword123"
    test_phone = "9876543210"
    test_name = "Cleanup Verification User"

    # 1. Test registration flow
    print("[TEST 1] Registering a new custom user...")
    register_payload = {
        "name": test_name,
        "email": test_email,
        "phone": test_phone,
        "password": test_password
    }
    response = client.post("/api/auth/register", json=register_payload)
    if response.status_code != 201:
        print(f"❌ Failure: Registration failed with status {response.status_code}: {response.text}")
        return False
    
    reg_data = response.json()
    access_token = reg_data.get("access_token")
    refresh_token = reg_data.get("refresh_token")
    if not access_token or not refresh_token:
        print("❌ Failure: Registration response missing access/refresh tokens")
        return False
    print("✅ Success: User registered and tokens returned successfully")

    # 2. Test login flow
    print("[TEST 2] Logging in with new credentials...")
    login_payload = {
        "email": test_email,
        "password": test_password
    }
    response = client.post("/api/auth/login", json=login_payload)
    if response.status_code != 200:
        print(f"❌ Failure: Login failed with status {response.status_code}: {response.text}")
        return False
    
    login_data = response.json()
    access_token = login_data.get("access_token")
    refresh_token = login_data.get("refresh_token")
    print("✅ Success: Login successful")

    # 3. Test access to secure route (/api/auth/me)
    print("[TEST 3] Accessing /api/auth/me with access token...")
    headers = {"Authorization": f"Bearer {access_token}"}
    response = client.get("/api/auth/me", headers=headers)
    if response.status_code != 200:
        print(f"❌ Failure: Failed to access secure route: {response.status_code}: {response.text}")
        return False
    print("✅ Success: Secure route accessed correctly")

    # 4. Test Token Refresh flow
    print("[TEST 4] Refreshing tokens...")
    refresh_payload = {
        "refresh_token": refresh_token
    }
    response = client.post("/api/auth/refresh", json=refresh_payload)
    if response.status_code != 200:
        print(f"❌ Failure: Token refresh failed with status {response.status_code}: {response.text}")
        return False
    
    refresh_data = response.json()
    new_access_token = refresh_data.get("access_token")
    new_refresh_token = refresh_data.get("refresh_token")
    if not new_access_token or not new_refresh_token:
        print("❌ Failure: Refresh response missing new tokens")
        return False
    print("✅ Success: Token refresh and rotation completed")

    # 5. Verify /me works with the new access token
    print("[TEST 5] Accessing /api/auth/me with the new access token...")
    new_headers = {"Authorization": f"Bearer {new_access_token}"}
    response = client.get("/api/auth/me", headers=new_headers)
    if response.status_code != 200:
        print(f"❌ Failure: Failed to access secure route with refreshed token: {response.status_code}")
        return False
    print("✅ Success: Secure route accepts the new access token")

    print("\n🎉 ALL FUNCTIONAL AUTH FLOW TESTS PASSED SUCCESSFULLY!")
    return True

if __name__ == "__main__":
    static_ok = run_static_checks()
    if not static_ok:
        print("\n❌ Static checks failed. Please fix before running functional tests.")
        sys.exit(1)
        
    func_ok = run_functional_tests()
    if not func_ok:
        sys.exit(1)
        
    print("\n🌟 ALL SYSTEMS CLEAR: CODEBASE CLEANED SUCCESSFULLY!")
    sys.exit(0)
