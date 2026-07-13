from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from config.database import master_catalog_collection
from middleware.auth import get_admin_user

router = APIRouter(prefix="/api/catalog", tags=["Catalog"])

class CatalogItem(BaseModel):
    gtin: str
    name: str
    brand: Optional[str] = None
    power_dosage: Optional[str] = None
    default_mrp: float
    category: Optional[str] = None
    dosage_form: Optional[str] = None
    pack_size: Optional[str] = None

class ScanResponse(BaseModel):
    source: str
    data: CatalogItem

# Mock external API call
async def fetch_from_external_api(gtin: str) -> Optional[dict]:
    # In a real scenario, this would call OpenFDA, UPCitemdb, etc.
    # Here we simulate a mock external DB hit for a specific barcode
    mock_db = {
        "08901030925763": {
            "name": "Paracetamol 500mg",
            "brand": "Crocin",
            "power_dosage": "500mg",
            "default_mrp": 30.50,
            "category": "Pain Relief",
            "dosage_form": "tablet",
            "pack_size": "15 tablets"
        }
    }
    
    if gtin in mock_db:
        return mock_db[gtin]
    
    # Generic mock response if we assume the 3rd party always finds something (for testing)
    # We will return None if it starts with '00000' to simulate not found
    if gtin.startswith("00000"):
        return None
        
    return {
        "name": f"Scanned Medicine {gtin}",
        "brand": "Global Pharma",
        "power_dosage": "Unknown",
        "default_mrp": 100.0,
        "category": "General",
        "dosage_form": "tablet",
        "pack_size": "10s"
    }


@router.get("/scan/{gtin}", response_model=ScanResponse)
async def scan_barcode(gtin: str, admin: dict = Depends(get_admin_user)):
    # Phase 1: Local Brain (MasterCatalog)
    doc = await master_catalog_collection.find_one({"gtin": gtin})
    if doc:
        item = CatalogItem(
            gtin=doc["gtin"],
            name=doc["name"],
            brand=doc.get("brand"),
            power_dosage=doc.get("power_dosage"),
            default_mrp=doc.get("default_mrp", 0.0),
            category=doc.get("category"),
            dosage_form=doc.get("dosage_form"),
            pack_size=doc.get("pack_size"),
        )
        return ScanResponse(source="local", data=item)
        
    # Phase 2: 3rd-Party Fallback
    external_data = await fetch_from_external_api(gtin)
    if external_data:
        item = CatalogItem(
            gtin=gtin,
            name=external_data["name"],
            brand=external_data.get("brand"),
            power_dosage=external_data.get("power_dosage"),
            default_mrp=external_data.get("default_mrp", 0.0),
            category=external_data.get("category"),
            dosage_form=external_data.get("dosage_form"),
            pack_size=external_data.get("pack_size"),
        )
        return ScanResponse(source="external", data=item)
        
    raise HTTPException(status_code=404, detail="Medicine not found in local or external catalog.")
