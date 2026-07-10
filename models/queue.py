"""
Queue models — Pydantic schemas for the Live Clinic Queue system.
Extends the base appointment schema with real-time queue tracking fields.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


# ── Queue Status Enum ─────────────────────────────────────────────────────────

class QueueStatus(str, Enum):
    """Lifecycle state of a single patient's queue slot."""
    WAITING         = "waiting"
    IN_CONSULTATION = "in_consultation"
    COMPLETED       = "completed"
    DELAYED         = "delayed"
    CANCELLED       = "cancelled"


# ── Request Payloads ──────────────────────────────────────────────────────────

class JoinQueueRequest(BaseModel):
    """Patient requests to join a doctor's live queue for a given date."""
    doctor_id: str
    date: str                           # ISO date, e.g. "2026-07-11"
    reason: Optional[str] = None
    expo_push_token: Optional[str] = None   # For targeted push notifications


class DelayRequest(BaseModel):
    """Doctor sends a delay signal for the current session."""
    delay_minutes: int = Field(..., ge=1, le=120, description="Minutes to add to all waiting patients")


# ── Response Schemas ──────────────────────────────────────────────────────────

class QueueEntryOut(BaseModel):
    """Single patient's queue entry — returned to both patients and the doctor dashboard."""
    id: str
    user_id: str
    doctor_id: str
    patient_name: Optional[str] = None
    date: str
    queue_position: int
    queue_status: QueueStatus = QueueStatus.WAITING
    est_wait_time: int = 0              # Minutes until this patient's turn
    expo_push_token: Optional[str] = None


class QueueStateOut(BaseModel):
    """
    Full live snapshot of a doctor's queue — broadcast over WebSocket
    every time the queue changes. Also returned from REST endpoints.
    """
    doctor_id: str
    current_patient_number: int         # queue_position of the IN_CONSULTATION patient
    total_waiting: int
    queue_status: str = "active"        # "active" | "idle" | "ended"
    entries: List[QueueEntryOut] = []


# ── WebSocket broadcast payload (compact) ────────────────────────────────────

class WSBroadcastPayload(BaseModel):
    """
    Minimal payload pushed to all connected WebSocket clients on any queue change.
    Kept lightweight to minimise bandwidth over mobile connections.
    """
    event: str                          # "next_patient" | "delay" | "end_session" | "heartbeat"
    current_patient_number: int
    total_waiting: int
    est_wait_time: int                  # Wait time relevant to the receiving patient (set per-client)
    queue_status: str = "active"
