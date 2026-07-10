import os
import sys
import types
from unittest.mock import MagicMock, AsyncMock
import unittest
from bson import ObjectId

# 1. Setup Mock Collection for medicines database calls
class MockCursor:
    def __init__(self, data):
        self.data = data
        self.index = 0

    def skip(self, n):
        self.data = self.data[n:]
        return self

    def limit(self, n):
        self.data = self.data[:n]
        return self

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self, length=None):
        return self.data

class MockCollection:
    def __init__(self):
        self.data = []
        self.aggregate_called = False
        self.aggregate_pipeline = []
        self.create_index_called = False
        self.find_called = False

    async def insert_one(self, doc):
        if "_id" not in doc:
            doc["_id"] = ObjectId()
        self.data.append(doc)
        res = MagicMock()
        res.inserted_id = doc["_id"]
        return res

    def find(self, query=None, projection=None):
        self.find_called = True
        # Filter based on mock criteria
        filtered = list(self.data)
        if query:
            # Simple simulation of query matching
            if "category" in query:
                filtered = [m for m in filtered if m.get("category") == query["category"]]
            if "$or" in query:
                regex_or = query["$or"]
                matched = []
                for item in filtered:
                    found = False
                    for r_expr in regex_or:
                        for field, val in r_expr.items():
                            pattern = val.get("$regex")
                            if pattern and pattern.lower() in item.get(field, "").lower():
                                found = True
                    if found:
                        matched.append(item)
                filtered = matched
        return MockCursor(filtered)

    def aggregate(self, pipeline):
        self.aggregate_called = True
        self.aggregate_pipeline = pipeline
        
        # Simulate Atlas Search behavior
        search_stage = pipeline[0] if pipeline else {}
        if "$search" in search_stage:
            search_query = search_stage["$search"]["text"]["query"]
            # If search is Parasetamol (fuzzy match simulation) or Paracetamol, return mock Paracetamol
            results = []
            for item in self.data:
                if "para" in search_query.lower() or "para" in item.get("name", "").lower():
                    results.append(item)
            return MockCursor(results)
        return MockCursor([])

    async def create_index(self, keys, **kwargs):
        self.create_index_called = True
        return "mock_index_name"

mock_medicines_collection = MockCollection()
mock_categories_collection = MockCollection()

# 2. Patch motor modules before importing FastAPI app
motor_mock = types.ModuleType("motor")
motor_asyncio_mock = types.ModuleType("motor.motor_asyncio")
motor_mock.motor_asyncio = motor_asyncio_mock
sys.modules["motor"] = motor_mock
sys.modules["motor.motor_asyncio"] = motor_asyncio_mock

mock_db = MagicMock()
mock_db.medicines = mock_medicines_collection
mock_db.categories = mock_categories_collection

mock_client = MagicMock()
mock_client.__getitem__.return_value = mock_db
mock_client.medical_store = mock_db
motor_asyncio_mock.AsyncIOMotorClient = MagicMock(return_value=mock_client)

# Patch configuration and database module references
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import config.database
config.database.medicines_collection = mock_medicines_collection
config.database.categories_collection = mock_categories_collection

from main import app
import routes.medicine
routes.medicine.medicines_collection = mock_medicines_collection
routes.medicine.categories_collection = mock_categories_collection

from fastapi.testclient import TestClient

client = TestClient(app)

class TestFuzzySearch(unittest.TestCase):
    def setUp(self):
        # Clear mock data and flags
        mock_medicines_collection.data = []
        mock_medicines_collection.aggregate_called = False
        mock_medicines_collection.find_called = False
        mock_medicines_collection.create_index_called = False
        mock_medicines_collection.aggregate = MockCollection.aggregate.__get__(mock_medicines_collection, MockCollection)

    def test_get_medicines_no_search(self):
        # Seed a medicine
        import asyncio
        asyncio.run(mock_medicines_collection.insert_one({
            "name": "Paracetamol 650",
            "category": "Tablets",
            "price": 30.0,
            "stock": 100
        }))

        response = client.get("/api/medicines/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "Paracetamol 650")
        self.assertTrue(mock_medicines_collection.find_called)
        self.assertFalse(mock_medicines_collection.aggregate_called)

    def test_get_medicines_fuzzy_atlas_search(self):
        import asyncio
        asyncio.run(mock_medicines_collection.insert_one({
            "name": "Paracetamol 650",
            "category": "Tablets",
            "price": 30.0,
            "stock": 100
        }))

        # Send search query
        response = client.get("/api/medicines/?search=Parasetamol")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Verify aggregate is called representing the Atlas Search flow
        self.assertTrue(mock_medicines_collection.aggregate_called)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], "Paracetamol 650")

    def test_get_medicines_atlas_search_fallback(self):
        # Force aggregate to fail to trigger fallback to text index
        mock_medicines_collection.aggregate = MagicMock(side_effect=Exception("Atlas Search index not ready"))
        
        import asyncio
        asyncio.run(mock_medicines_collection.insert_one({
            "name": "Crocin Syrup",
            "generic_name": "Paracetamol",
            "category": "Syrup",
            "price": 60.0,
            "stock": 50
        }))

        response = client.get("/api/medicines/?search=Syrup")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_medicines_collection.create_index_called)
        self.assertTrue(mock_medicines_collection.find_called)

if __name__ == "__main__":
    unittest.main()
