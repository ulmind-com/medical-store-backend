"""
Live Clinic Queue — REST + WebSocket endpoints.
═══════════════════════════════════════════════════════════════════════════════
Endpoint map:
  POST   /api/queue/join              → Patient joins a doctor's queue
  GET    /api/queue/{doctor_id}       → Get full live snapshot of a queue
  GET    /api/queue/my/{doctor_id}    → Patient's own slot details
  POST   /api/queue/{doctor_id}/next  → Doctor: advance to next patient
  POST   /api/queue/{doctor_id}/delay → Doctor: broadcast a delay
  POST   /api/queue/{doctor_id}/end   → Doctor: end the session
  WS     /api/queue/live/{doctor_id}  → Live real-time queue updates

MongoDB atomicity strategy:
  All queue mutations use findOneAndUpdate / update_one with $set / $inc
  operators — never a find-then-save pattern — to prevent race conditions
  under concurrent requests.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from config.database import appointments_collection, doctors_collection, users_collection
from middleware.auth import get_current_user, get_admin_user
from models.queue import (
    DelayRequest,
    JoinQueueRequest,
    QueueEntryOut,
    QueueStateOut,
    QueueStatus,
)
from utils.notifications import send_expo_push_notification
from utils.queue_manager import queue_manager

logger = logging.getLogger("queue.routes")

router = APIRouter(prefix="/api/queue", tags=["Live Queue"])

# ── Constants ─────────────────────────────────────────────────────────────────
MINS_PER_PATIENT = 15           # Estimated consultation time per patient


# ═════════════════════════════════════════════════════════════════════════════
# Helper utilities
# ═════════════════════════════════════════════════════════════════════════════

def _doc_to_entry(doc: dict) -> QueueEntryOut:
    """Map a raw MongoDB queue document to a clean QueueEntryOut."""
    return QueueEntryOut(
        id=str(doc["_id"]),
        user_id=doc["user_id"],
        doctor_id=doc["doctor_id"],
        patient_name=doc.get("patient_name"),
        date=doc["date"],
        queue_position=doc.get("queue_position", 0),
        queue_status=doc.get("queue_status", QueueStatus.WAITING),
        est_wait_time=doc.get("est_wait_time", 0),
        expo_push_token=doc.get("expo_push_token"),
    )


async def _build_queue_state(doctor_id: str, date: str) -> QueueStateOut:
    """
    Construct a full QueueStateOut snapshot from the DB.
    Called after every mutation so we always broadcast fresh data.
    """
    # Fetch ALL non-cancelled entries for this doctor/date, ordered by position
    cursor = appointments_collection.find(
        {
            "doctor_id": doctor_id,
            "date": date,
            "queue_status": {"$nin": [QueueStatus.CANCELLED, QueueStatus.COMPLETED]},
        }
    ).sort("queue_position", 1)
    docs = await cursor.to_list(length=200)

    entries = [_doc_to_entry(d) for d in docs]

    # Find the currently active patient
    active = next((e for e in entries if e.queue_status == QueueStatus.IN_CONSULTATION), None)
    current_number = active.queue_position if active else 0
    waiting_count = sum(1 for e in entries if e.queue_status == QueueStatus.WAITING)

    return QueueStateOut(
        doctor_id=doctor_id,
        current_patient_number=current_number,
        total_waiting=waiting_count,
        queue_status="active" if entries else "idle",
        entries=entries,
    )


async def _recalculate_wait_times(doctor_id: str, date: str, active_position: int):
    """
    Atomically recalculate est_wait_time for all WAITING patients in a queue.
    Formula: (patient_position - active_position) × MINS_PER_PATIENT
    Uses bulk_write for efficiency — one round-trip to MongoDB.
    """
    from pymongo import UpdateOne  # local import to keep top-level clean

    cursor = appointments_collection.find(
        {
            "doctor_id": doctor_id,
            "date": date,
            "queue_status": QueueStatus.WAITING,
        },
        {"_id": 1, "queue_position": 1},
    )
    docs = await cursor.to_list(length=200)

    if not docs:
        return

    ops = [
        UpdateOne(
            {"_id": doc["_id"]},
            {
                "$set": {
                    "est_wait_time": max(
                        0, (doc["queue_position"] - active_position) * MINS_PER_PATIENT
                    )
                }
            },
        )
        for doc in docs
    ]
    await appointments_collection.bulk_write(ops, ordered=False)


async def _broadcast_queue(doctor_id: str, date: str, event: str):
    """Rebuild queue state and broadcast it to all WebSocket clients in the room."""
    state = await _build_queue_state(doctor_id, date)
    payload = {
        "event": event,
        "current_patient_number": state.current_patient_number,
        "total_waiting": state.total_waiting,
        "queue_status": state.queue_status,
        # Full entries so the Doctor Command Centre can render the list
        "entries": [e.model_dump() for e in state.entries],
    }
    await queue_manager.broadcast(doctor_id, payload)
    logger.info(f"[Queue] Broadcast '{event}' to room '{doctor_id}'.")


# ═════════════════════════════════════════════════════════════════════════════
# REST: Patient endpoints
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/join", response_model=QueueEntryOut, status_code=status.HTTP_201_CREATED)
async def join_queue(
    data: JoinQueueRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Patient joins a doctor's live queue for a given date.
    The patient receives an auto-assigned queue_position (last in line).
    """
    # Verify doctor exists
    doctor = await doctors_collection.find_one({"_id": ObjectId(data.doctor_id)})
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    # Check if patient is already in this queue
    existing = await appointments_collection.find_one({
        "doctor_id": data.doctor_id,
        "user_id": str(current_user["_id"]),
        "date": data.date,
        "queue_status": {"$in": [QueueStatus.WAITING, QueueStatus.IN_CONSULTATION]},
    })
    if existing:
        raise HTTPException(status_code=400, detail="You are already in this queue")

    # Atomically determine next position: count existing non-cancelled entries + 1
    count = await appointments_collection.count_documents({
        "doctor_id": data.doctor_id,
        "date": data.date,
        "queue_status": {"$nin": [QueueStatus.CANCELLED]},
    })
    new_position = count + 1
    est_wait = (new_position - 1) * MINS_PER_PATIENT  # position 1 waits 0 mins

    doc = {
        "user_id": str(current_user["_id"]),
        "patient_name": current_user.get("name", "Patient"),
        "doctor_id": data.doctor_id,
        "date": data.date,
        "reason": data.reason,
        "queue_position": new_position,
        "queue_status": QueueStatus.WAITING,
        "est_wait_time": est_wait,
        "expo_push_token": data.expo_push_token,
        "created_at": datetime.utcnow().isoformat(),
    }

    result = await appointments_collection.insert_one(doc)
    doc["_id"] = result.inserted_id

    # Notify WebSocket room of new patient joining
    await _broadcast_queue(data.doctor_id, data.date, "patient_joined")

    return _doc_to_entry(doc)


@router.get("/my/{doctor_id}", response_model=Optional[QueueEntryOut])
async def get_my_queue_slot(
    doctor_id: str,
    date: str = Query(..., description="ISO date e.g. 2026-07-11"),
    current_user: dict = Depends(get_current_user),
):
    """Return this patient's own slot in a doctor's queue."""
    doc = await appointments_collection.find_one({
        "doctor_id": doctor_id,
        "user_id": str(current_user["_id"]),
        "date": date,
        "queue_status": {"$nin": [QueueStatus.CANCELLED]},
    })
    if not doc:
        return None
    return _doc_to_entry(doc)


# ═════════════════════════════════════════════════════════════════════════════
# REST: Doctor Command Centre endpoints
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/{doctor_id}", response_model=QueueStateOut)
async def get_queue_state(
    doctor_id: str,
    date: str = Query(..., description="ISO date e.g. 2026-07-11"),
    current_user: dict = Depends(get_current_user),
):
    """Fetch the full live snapshot of a doctor's queue."""
    return await _build_queue_state(doctor_id, date)


@router.post("/{doctor_id}/next")
async def advance_to_next_patient(
    doctor_id: str,
    date: str = Query(..., description="ISO date e.g. 2026-07-11"),
    current_user: dict = Depends(get_current_user),
):
    """
    Doctor advances the queue to the next patient.

    Atomic sequence:
      1. Mark current IN_CONSULTATION patient as COMPLETED.
      2. Promote the lowest-position WAITING patient to IN_CONSULTATION.
      3. Recalculate est_wait_time for all remaining WAITING patients.
      4. Broadcast updated state over WebSocket.
      5. Send a targeted push notification to the patient now 2nd in line.
    """
    # ── Step 1: Complete current active patient ──────────────────────────
    active_doc = await appointments_collection.find_one_and_update(
        {"doctor_id": doctor_id, "date": date, "queue_status": QueueStatus.IN_CONSULTATION},
        {"$set": {"queue_status": QueueStatus.COMPLETED}},
        return_document=True,  # returns the updated document
    )
    # If no active patient, check if we should promote the first WAITING one
    logger.info(f"[Queue /next] Completed active: {active_doc}")

    # ── Step 2: Promote the next WAITING patient ─────────────────────────
    next_doc = await appointments_collection.find_one_and_update(
        {"doctor_id": doctor_id, "date": date, "queue_status": QueueStatus.WAITING},
        {"$set": {"queue_status": QueueStatus.IN_CONSULTATION, "est_wait_time": 0}},
        sort=[("queue_position", 1)],   # Smallest position wins
        return_document=True,
    )

    if not next_doc:
        # No more patients — the session is effectively idle
        await queue_manager.broadcast(doctor_id, {
            "event": "queue_empty",
            "current_patient_number": 0,
            "total_waiting": 0,
            "queue_status": "idle",
            "entries": [],
        })
        return {"message": "No more patients in queue", "queue_status": "idle"}

    new_active_position = next_doc["queue_position"]

    # ── Step 3: Recalculate wait times ───────────────────────────────────
    await _recalculate_wait_times(doctor_id, date, new_active_position)

    # ── Step 4: Broadcast updated state ──────────────────────────────────
    await _broadcast_queue(doctor_id, date, "next_patient")

    # ── Step 5: Targeted push — notify the patient NOW 2nd in line ───────
    second_in_line = await appointments_collection.find_one(
        {
            "doctor_id": doctor_id,
            "date": date,
            "queue_status": QueueStatus.WAITING,
        },
        sort=[("queue_position", 1)],
    )
    if second_in_line and second_in_line.get("expo_push_token"):
        # Run in background — don't block the HTTP response
        asyncio.create_task(
            asyncio.to_thread(
                send_expo_push_notification,
                second_in_line["expo_push_token"],
                "🔔 You're Next!",
                "Please make your way to the clinic. Doctor will see you shortly.",
                {"screen": "LiveQueueTracker", "doctor_id": doctor_id},
            )
        )

    state = await _build_queue_state(doctor_id, date)
    return {"message": "Advanced to next patient", "state": state.model_dump()}


@router.post("/{doctor_id}/delay")
async def add_delay(
    doctor_id: str,
    payload: DelayRequest,
    date: str = Query(..., description="ISO date e.g. 2026-07-11"),
    current_user: dict = Depends(get_current_user),
):
    """
    Doctor signals a delay — adds `delay_minutes` to all WAITING patients' est_wait_time.
    Sends a bulk Expo Push Notification to all affected patients.
    Atomic: uses $inc to avoid read-modify-write races.
    """
    delay_mins = payload.delay_minutes

    # ── Atomically increment wait time for all WAITING patients ──────────
    await appointments_collection.update_many(
        {"doctor_id": doctor_id, "date": date, "queue_status": QueueStatus.WAITING},
        {"$inc": {"est_wait_time": delay_mins}},
    )

    # ── Broadcast WebSocket update ────────────────────────────────────────
    await _broadcast_queue(doctor_id, date, "delay")

    # ── Bulk push notification to all waiting patients ────────────────────
    cursor = appointments_collection.find(
        {"doctor_id": doctor_id, "date": date, "queue_status": QueueStatus.WAITING},
        {"expo_push_token": 1, "patient_name": 1},
    )
    waiting_docs = await cursor.to_list(length=200)

    for doc in waiting_docs:
        token = doc.get("expo_push_token")
        if token:
            asyncio.create_task(
                asyncio.to_thread(
                    send_expo_push_notification,
                    token,
                    "⏱ Queue Delay",
                    f"Doctor has added a {delay_mins}-minute delay. Updated wait time calculated.",
                    {"screen": "LiveQueueTracker", "delay_added": delay_mins},
                )
            )

    return {
        "message": f"Delay of {delay_mins} minutes added to all waiting patients",
        "affected": len(waiting_docs),
    }


@router.post("/{doctor_id}/end")
async def end_session(
    doctor_id: str,
    date: str = Query(..., description="ISO date e.g. 2026-07-11"),
    current_user: dict = Depends(get_current_user),
):
    """
    Doctor ends the session.
    All remaining WAITING patients are marked CANCELLED and the WebSocket room
    receives an 'end_session' event so every client can redirect.
    """
    # Mark any leftover WAITING/IN_CONSULTATION entries as cancelled
    result = await appointments_collection.update_many(
        {
            "doctor_id": doctor_id,
            "date": date,
            "queue_status": {"$in": [QueueStatus.WAITING, QueueStatus.IN_CONSULTATION]},
        },
        {"$set": {"queue_status": QueueStatus.CANCELLED}},
    )

    await queue_manager.broadcast(doctor_id, {
        "event": "end_session",
        "current_patient_number": 0,
        "total_waiting": 0,
        "queue_status": "ended",
        "entries": [],
    })

    return {
        "message": "Session ended",
        "cancelled_count": result.modified_count,
    }


@router.post("/{doctor_id}/start")
async def start_first_patient(
    doctor_id: str,
    date: str = Query(..., description="ISO date e.g. 2026-07-11"),
    current_user: dict = Depends(get_current_user),
):
    """
    Doctor starts the session by calling the first patient.
    Convenience endpoint equivalent to /next when no one is IN_CONSULTATION yet.
    """
    # Re-use the /next logic
    return await advance_to_next_patient(doctor_id, date, current_user)


# ═════════════════════════════════════════════════════════════════════════════
# WebSocket: Real-time live queue stream
# ═════════════════════════════════════════════════════════════════════════════

@router.websocket("/live/{doctor_id}")
async def websocket_queue_live(
    ws: WebSocket,
    doctor_id: str,
):
    """
    Real-time queue WebSocket endpoint.

    Protocol:
      • Client connects: immediately receives the current queue snapshot.
      • Server sends updates whenever /next, /delay, or /end is called.
      • Server sends {"event": "heartbeat"} every HEARTBEAT_INTERVAL seconds.
      • Client should handle reconnection with exponential backoff on disconnect.

    URL: ws://<host>/api/queue/live/{doctor_id}?date=2026-07-11
    """
    # Start heartbeat on first connection (idempotent)
    queue_manager.start_heartbeat()

    # Parse optional date from query params for sending initial snapshot
    date_param = ws.query_params.get("date", datetime.utcnow().strftime("%Y-%m-%d"))

    await queue_manager.connect(doctor_id, ws)
    logger.info(f"[WS] New client connected to doctor '{doctor_id}'. "
                f"Room size: {queue_manager.room_size(doctor_id)}")

    try:
        # ── Send initial snapshot immediately on connect ───────────────────
        state = await _build_queue_state(doctor_id, date_param)
        await ws.send_text(json.dumps({
            "event": "initial_snapshot",
            "current_patient_number": state.current_patient_number,
            "total_waiting": state.total_waiting,
            "queue_status": state.queue_status,
            "entries": [e.model_dump() for e in state.entries],
        }))

        # ── Keep the connection open; wait for client messages or disconnect ─
        # We don't need to receive anything from the client for this use-case,
        # but we must await something to avoid busy-looping.
        while True:
            # Receive any message from client (heartbeat pong, etc.) — ignore content
            data = await ws.receive_text()
            # Future: handle client-side events here if needed

    except WebSocketDisconnect:
        logger.info(f"[WS] Client disconnected from doctor '{doctor_id}'.")
    except Exception as e:
        logger.warning(f"[WS] Unexpected error in room '{doctor_id}': {e}")
    finally:
        await queue_manager.disconnect(doctor_id, ws)
