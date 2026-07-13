import pytest
import httpx
import asyncio

BASE_URL = "http://localhost:8000"

# Assuming the demo admin user exists as requested previously
ADMIN_EMAIL = "healthhubteam2025@gmail.com"
ADMIN_PASSWORD = "abc123"

@pytest.fixture
async def admin_token():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # Login to get admin token
        response = await client.post("/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
            "role": "admin"
        })
        assert response.status_code == 200, "Admin login failed"
        data = response.json()
        return data["access_token"]

@pytest.mark.asyncio
async def test_scan_known_barcode(admin_token):
    """
    Test scanning a barcode that is known to the mocked external API.
    Since it's not in MasterCatalog yet, it should fallback and return source='external'.
    """
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        headers = {"Authorization": f"Bearer {admin_token}"}
        gtin = "08901030925763"
        response = await client.get(f"/api/catalog/scan/{gtin}", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["source"] in ["local", "external"]
        assert data["data"]["name"] == "Paracetamol 500mg"

@pytest.mark.asyncio
async def test_scan_unknown_barcode(admin_token):
    """
    Test scanning an unknown barcode that falls back to the mocked external API.
    """
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        headers = {"Authorization": f"Bearer {admin_token}"}
        gtin = "12345678901234"
        response = await client.get(f"/api/catalog/scan/{gtin}", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "external"
        assert "Scanned Medicine" in data["data"]["name"]

@pytest.mark.asyncio
async def test_auto_learn_new_medicine(admin_token):
    """
    Test adding a new medicine to inventory. 
    It should automatically learn this GTIN into the MasterCatalog.
    """
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        test_gtin = "99999999999999"
        
        new_med = {
            "gtin": test_gtin,
            "batch_number": "BCH-001",
            "name": "Auto Learn Test Med",
            "category": "Test Category",
            "price": 100.0,
            "stock": 50
        }
        
        # Add to inventory
        add_res = await client.post("/api/medicines", json=new_med, headers=headers)
        assert add_res.status_code == 200
        
        # Now scan it again, it should come from 'local' (MasterCatalog)
        scan_res = await client.get(f"/api/catalog/scan/{test_gtin}", headers=headers)
        assert scan_res.status_code == 200
        
        data = scan_res.json()
        assert data["source"] == "local"
        assert data["data"]["name"] == "Auto Learn Test Med"
