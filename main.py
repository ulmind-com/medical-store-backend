from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config.database import init_db
from routes.auth import router as auth_router
from routes.medicine import router as medicine_router
from routes.doctor import router as doctor_router
from routes.appointment import router as appointment_router
from routes.order import router as order_router
from routes.prescription import router as prescription_router
from routes.payment import router as payment_router
from routes.settings import router as settings_router
from routes.admin import router as admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    print("[OK] Database initialized and indexes created")
    yield
    # Shutdown
    print("[BYE] Shutting down...")


app = FastAPI(
    title="Medical Store API",
    description="API for Medical Store - Medicine Sales, Doctor Booking & Prescription Management",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(medicine_router)
app.include_router(doctor_router)
app.include_router(appointment_router)
app.include_router(order_router)
app.include_router(prescription_router)
app.include_router(payment_router)
app.include_router(settings_router)
app.include_router(admin_router)


@app.get("/")
async def root():
    return {
        "message": "Medical Store API is running 🏥",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}
