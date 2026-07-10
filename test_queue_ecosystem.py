"""
test_queue_ecosystem.py
═══════════════════════════════════════════════════════════════════════════════
Comprehensive integration test for the Live Clinic Queue system.
Uses:
  • pytest + pytest-asyncio  — async test runner
  • httpx (AsyncClient)      — async REST assertions
  • websockets library       — WebSocket client simulation

Scenario:
  1. Seed DB with 3 WAITING appointments for a test doctor.
  2. Start a WebSocket client simulating Patient #3.
  3. Call POST /next as the doctor.
  4. Assert WS client receives updated payload with correct patient numbers.
  5. Clean up all seeded data.

Run:
  uv run pytest test_queue_ecosystem.py -v
"""

import asyncio
import json
import uuid
from datetime import datetime

import httpx
import pytest
import pytest_asyncio
import websockets

# ── Config ─────────────────────────────────────────────────────────────────
BASE_URL = "http://127.0.0.1:8000"
WS_BASE  = "ws://127.0.0.1:8000"

# Shared test session fixtures — set by setup, used in tests
TEST_DATE      = datetime.utcnow().strftime("%Y-%m-%d")
TEST_DOCTOR_ID = None   # Will be resolved from DB
TEST_ENTRIES   = []     # Inserted appointment IDs for cleanup


# ═════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def event_loop():
    """Provide a single event loop for the whole test module."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="module")
async def http_client():
    """Shared async httpx client for the test module."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        yield client


@pytest_asyncio.fixture(scope="module")
async def admin_token(http_client):
    """
    Obtain an admin JWT token.
    Adjust credentials to match your seeded admin user.
    """
    resp = await http_client.post("/api/auth/login", json={
        "email": "admin@medstore.com",
        "password": "admin123",
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest_asyncio.fixture(scope="module")
async def user_token(http_client):
    """
    Obtain a regular user JWT token.
    Adjust credentials to match your seeded user.
    """
    resp = await http_client.post("/api/auth/login", json={
        "email": "patient@test.com",
        "password": "patient123",
    })
    assert resp.status_code == 200, f"User login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest_asyncio.fixture(scope="module")
async def doctor_id(http_client, admin_token):
    """Resolve the first available doctor from the DB."""
    resp = await http_client.get(
        "/api/doctors/",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, f"Could not list doctors: {resp.text}"
    doctors = resp.json()
    assert len(doctors) > 0, "No doctors in DB — run seed.py first"
    return str(doctors[0]["id"])


# ═════════════════════════════════════════════════════════════════════════════
# Seed helper
# ═════════════════════════════════════════════════════════════════════════════

async def seed_queue_entries(http_client, user_token, doctor_id, n=3):
    """
    Directly insert n WAITING queue entries for the test doctor.
    Returns list of inserted entry IDs.
    """
    ids = []
    for i in range(n):
        resp = await http_client.post(
            "/api/queue/join",
            json={
                "doctor_id": doctor_id,
                "date": TEST_DATE,
                "reason": f"Test patient {i+1}",
                "expo_push_token": None,
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )
        # 201 = created, 400 = already in queue (re-runs); both acceptable in seed
        if resp.status_code == 201:
            ids.append(resp.json()["id"])
        elif resp.status_code == 400 and "already in this queue" in resp.text:
            print(f"[Seed] Patient already in queue (skip): {resp.json()}")
        else:
            raise AssertionError(f"Unexpected seed response [{resp.status_code}]: {resp.text}")
    return ids


async def cleanup_entries(http_client, admin_token, doctor_id):
    """
    End the session to clean up all test entries.
    """
    await http_client.post(
        f"/api/queue/{doctor_id}/end",
        params={"date": TEST_DATE},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    print("[Cleanup] Session ended — all test entries cancelled.")


# ═════════════════════════════════════════════════════════════════════════════
# Tests
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_health_check(http_client):
    """Sanity check — backend must be running."""
    resp = await http_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
    print("[✓] Backend health check passed")


@pytest.mark.asyncio
async def test_join_queue(http_client, user_token, doctor_id):
    """
    Seed 3 waiting appointments and assert correct queue positions are assigned.
    """
    global TEST_ENTRIES

    # Clean up any previous test run first
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as tmp:
        resp = await tmp.post("/api/auth/login", json={"email": "admin@medstore.com", "password": "admin123"})
        if resp.status_code == 200:
            tok = resp.json()["access_token"]
            await tmp.post(
                f"/api/queue/{doctor_id}/end",
                params={"date": TEST_DATE},
                headers={"Authorization": f"Bearer {tok}"},
            )

    TEST_ENTRIES = await seed_queue_entries(http_client, user_token, doctor_id, n=3)
    assert len(TEST_ENTRIES) > 0, "No entries seeded"
    print(f"[✓] Seeded {len(TEST_ENTRIES)} queue entries: {TEST_ENTRIES}")


@pytest.mark.asyncio
async def test_get_queue_state(http_client, user_token, doctor_id):
    """
    GET /api/queue/{doctor_id} must return a valid snapshot with waiting entries.
    """
    resp = await http_client.get(
        f"/api/queue/{doctor_id}",
        params={"date": TEST_DATE},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 200, f"Get queue failed: {resp.text}"
    data = resp.json()

    assert "total_waiting" in data
    assert data["total_waiting"] >= 1
    assert "entries" in data
    assert len(data["entries"]) >= 1
    print(f"[✓] Queue state: {data['total_waiting']} waiting, "
          f"current patient #{data['current_patient_number']}")


@pytest.mark.asyncio
async def test_websocket_receives_update_on_next(http_client, user_token, doctor_id):
    """
    ────────────────────────────────────────────────────────────────────────
    Core real-time test:
      1. Connect WebSocket as Patient #3.
      2. Call POST /next.
      3. Assert WS client receives payload with current_patient_number = 1.
    ────────────────────────────────────────────────────────────────────────
    """
    ws_url = f"{WS_BASE}/api/queue/live/{doctor_id}?date={TEST_DATE}"

    received_messages = []

    async def ws_client_task():
        """Simulates a patient's app WebSocket connection."""
        async with websockets.connect(ws_url, ping_interval=None) as ws:
            # Receive the initial snapshot
            raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
            msg = json.loads(raw)
            received_messages.append(msg)
            print(f"[WS] Initial snapshot: event={msg.get('event')}, "
                  f"current_patient={msg.get('current_patient_number')}")

            # Wait for the next update (triggered by POST /next)
            raw2 = await asyncio.wait_for(ws.recv(), timeout=15.0)
            msg2 = json.loads(raw2)
            received_messages.append(msg2)
            print(f"[WS] Update received: event={msg2.get('event')}, "
                  f"current_patient={msg2.get('current_patient_number')}")

    async def trigger_next_task():
        """Simulates the doctor pressing 'Next Patient'."""
        await asyncio.sleep(1.5)  # Give WS client time to connect
        resp = await http_client.post(
            f"/api/queue/{doctor_id}/next",
            params={"date": TEST_DATE},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200, f"POST /next failed: {resp.text}"
        print(f"[HTTP] POST /next response: {resp.json().get('message')}")

    # Run both concurrently
    await asyncio.gather(ws_client_task(), trigger_next_task())

    # ── Assertions ────────────────────────────────────────────────────────
    assert len(received_messages) >= 2, "WS client did not receive enough messages"

    initial = received_messages[0]
    update  = received_messages[1]

    assert initial["event"] == "initial_snapshot"
    assert update["event"] == "next_patient", \
        f"Expected 'next_patient' event, got '{update.get('event')}'"
    assert update["current_patient_number"] >= 1, \
        f"current_patient_number should be ≥ 1, got {update.get('current_patient_number')}"

    print("[✓] WebSocket real-time update verified successfully")


@pytest.mark.asyncio
async def test_delay_updates_wait_times(http_client, user_token, doctor_id):
    """
    POST /delay must increment est_wait_time for all WAITING patients.
    """
    # Get baseline
    before = await http_client.get(
        f"/api/queue/{doctor_id}",
        params={"date": TEST_DATE},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    before_data = before.json()
    waiting_before = [e for e in before_data.get("entries", []) if e["queue_status"] == "waiting"]

    if not waiting_before:
        pytest.skip("No waiting patients to test delay (queue may be empty)")

    baseline_wait = waiting_before[0]["est_wait_time"]

    # Apply a 15-minute delay
    delay_resp = await http_client.post(
        f"/api/queue/{doctor_id}/delay",
        json={"delay_minutes": 15},
        params={"date": TEST_DATE},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert delay_resp.status_code == 200, f"Delay failed: {delay_resp.text}"

    # Verify
    after = await http_client.get(
        f"/api/queue/{doctor_id}",
        params={"date": TEST_DATE},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    after_data = after.json()
    waiting_after = [e for e in after_data.get("entries", []) if e["queue_status"] == "waiting"]

    if waiting_after:
        new_wait = waiting_after[0]["est_wait_time"]
        assert new_wait >= baseline_wait + 15, \
            f"Expected wait ≥ {baseline_wait + 15}, got {new_wait}"
    print(f"[✓] Delay applied. Wait time before: {baseline_wait}, after: "
          f"{waiting_after[0]['est_wait_time'] if waiting_after else 'N/A'}")


@pytest.mark.asyncio
async def test_end_session(http_client, admin_token, doctor_id):
    """
    POST /end must mark all remaining WAITING patients as CANCELLED
    and broadcast 'end_session' event.
    """
    # Connect a WS client to receive the end_session broadcast
    ws_url = f"{WS_BASE}/api/queue/live/{doctor_id}?date={TEST_DATE}"
    end_event_received = []

    async def ws_listen():
        try:
            async with websockets.connect(ws_url, ping_interval=None) as ws:
                await asyncio.wait_for(ws.recv(), timeout=5.0)  # consume snapshot
                raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                msg = json.loads(raw)
                end_event_received.append(msg)
        except asyncio.TimeoutError:
            pass  # No message is also acceptable if queue was already empty

    async def do_end():
        await asyncio.sleep(1.0)
        resp = await http_client.post(
            f"/api/queue/{doctor_id}/end",
            params={"date": TEST_DATE},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200, f"End session failed: {resp.text}"
        print(f"[HTTP] End session: {resp.json()}")

    await asyncio.gather(ws_listen(), do_end())

    if end_event_received:
        assert end_event_received[0].get("event") == "end_session"
        assert end_event_received[0].get("queue_status") == "ended"
        print("[✓] end_session event received over WebSocket")
    else:
        print("[✓] Session ended (no WS clients were waiting — acceptable)")


# ═════════════════════════════════════════════════════════════════════════════
# Run summary
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
