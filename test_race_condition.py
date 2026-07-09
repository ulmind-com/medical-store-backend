"""
test_race_condition.py
======================
Concurrency regression test for the atomic stock-decrement fix.

Simulates N concurrent users placing an order for the SAME medicine at the
same instant.  After all requests complete, it asserts:

  1. Stock in MongoDB is >= 0  (no overselling).
  2. Exactly `initial_stock` orders succeeded (not more).
  3. All remaining requests received HTTP 409 Conflict.

Usage
-----
1. Make sure the FastAPI server is running locally:
       uv run uvicorn main:app --reload

2. Register an admin and a test user, then fill in the constants below.

3. Run:
       python test_race_condition.py

Requirements
------------
    pip install aiohttp

The script uses only stdlib + aiohttp — no pytest needed.
"""

import asyncio
import aiohttp
import json
import sys
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# ★  CONFIGURE THESE BEFORE RUNNING  ★
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL = "http://127.0.0.1:8000"

# A pre-registered test user JWT token (not admin).
# You can obtain one via: POST /api/auth/login
USER_TOKEN = "PASTE_YOUR_USER_JWT_HERE"

# The MongoDB _id (string) of the medicine you want to test against.
# Set its stock to INITIAL_STOCK before running (via admin panel or seed).
MEDICINE_ID = "PASTE_MEDICINE_ID_HERE"
MEDICINE_NAME = "Test Medicine"

# How many units of stock the medicine has at the start.
# The test will attempt to buy CONCURRENT_USERS units total.
INITIAL_STOCK = 3

# Total concurrent order attempts — should be > INITIAL_STOCK to force
# some to fail, proving the race condition guard works.
CONCURRENT_USERS = 10

# Delivery coordinates (can be any valid coords for your shop area)
DELIVERY_LATITUDE = 22.5726
DELIVERY_LONGITUDE = 88.3639
DELIVERY_ADDRESS = "1, Test Street, Kolkata, West Bengal 700001"

# ─────────────────────────────────────────────────────────────────────────────


async def place_order(
    session: aiohttp.ClientSession,
    user_id: int,
    results: list,
) -> None:
    """
    One simulated user placing one order for 1 unit of the target medicine.
    Results (status code + response body) are appended to the shared `results`
    list for assertion after all tasks finish.
    """
    headers = {
        "Authorization": f"Bearer {USER_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "items": [
            {
                "medicine_id": MEDICINE_ID,
                "medicine_name": MEDICINE_NAME,
                "quantity": 1,        # Each user tries to buy exactly 1 unit
                "price": 10.0,        # Price does not affect stock logic
                "image_url": None,
            }
        ],
        "delivery_address": DELIVERY_ADDRESS,
        "delivery_latitude": DELIVERY_LATITUDE,
        "delivery_longitude": DELIVERY_LONGITUDE,
        "address_type": "home",
        "address_details": "1",
        "payment_method": "cod",
        "notes": f"Race condition test — user {user_id}",
    }

    try:
        async with session.post(
            f"{BASE_URL}/api/orders/",
            headers=headers,
            json=payload,
        ) as resp:
            body = await resp.json()
            results.append({"user_id": user_id, "status": resp.status, "body": body})
            status_icon = "✅" if resp.status == 201 else "❌"
            print(
                f"  {status_icon} User {user_id:02d}: "
                f"HTTP {resp.status} — "
                f"{body.get('detail', body.get('id', ''))}"
            )
    except Exception as exc:
        results.append({"user_id": user_id, "status": None, "error": str(exc)})
        print(f"  💥 User {user_id:02d}: Exception — {exc}")


async def fetch_current_stock(session: aiohttp.ClientSession) -> int:
    """Fetch the medicine's current stock via the public GET /api/medicines/{id}."""
    async with session.get(f"{BASE_URL}/api/medicines/{MEDICINE_ID}") as resp:
        if resp.status == 200:
            data = await resp.json()
            return data.get("stock", -999)
        return -999


async def run_test() -> None:
    print("=" * 65)
    print("  RACE CONDITION CONCURRENCY TEST")
    print("=" * 65)
    print(f"  Target medicine   : {MEDICINE_NAME} ({MEDICINE_ID})")
    print(f"  Initial stock     : {INITIAL_STOCK}")
    print(f"  Concurrent users  : {CONCURRENT_USERS}")
    print(f"  Started at        : {datetime.now().isoformat()}")
    print("=" * 65)

    results: list = []

    # Use a TCPConnector with a high limit to allow true concurrency.
    connector = aiohttp.TCPConnector(limit=CONCURRENT_USERS + 5)

    async with aiohttp.ClientSession(connector=connector) as session:
        # ── Pre-test: record stock ────────────────────────────────────────────
        stock_before = await fetch_current_stock(session)
        print(f"\n[PRE-TEST]  Stock in DB = {stock_before}")

        if stock_before == -999:
            print("\n  ⚠️  Could not fetch medicine. Check MEDICINE_ID and server.")
            return

        # ── Fire all concurrent requests at the same time ─────────────────────
        print(f"\n[FIRING]  Sending {CONCURRENT_USERS} concurrent requests...\n")
        tasks = [
            place_order(session, user_id=i + 1, results=results)
            for i in range(CONCURRENT_USERS)
        ]
        # asyncio.gather with return_exceptions=True ensures all tasks run even
        # if individual ones raise unhandled exceptions.
        await asyncio.gather(*tasks, return_exceptions=True)

        # ── Post-test: fetch final stock ──────────────────────────────────────
        stock_after = await fetch_current_stock(session)

    # ── Analyse results ───────────────────────────────────────────────────────
    successes = [r for r in results if r.get("status") == 201]
    conflicts = [r for r in results if r.get("status") == 409]
    other_errors = [r for r in results if r.get("status") not in (201, 409, None)]
    exceptions = [r for r in results if r.get("status") is None]

    print("\n" + "=" * 65)
    print("  RESULTS")
    print("=" * 65)
    print(f"  Total requests      : {len(results)}")
    print(f"  ✅ Successful (201) : {len(successes)}")
    print(f"  ❌ Conflicts  (409) : {len(conflicts)}")
    print(f"  ⚠️  Other errors    : {len(other_errors)}")
    print(f"  💥 Exceptions       : {len(exceptions)}")
    print(f"\n  Stock before test   : {stock_before}")
    print(f"  Stock after test    : {stock_after}")
    print("=" * 65)

    # ── Assertions ────────────────────────────────────────────────────────────
    all_passed = True

    def assert_test(condition: bool, message: str) -> None:
        nonlocal all_passed
        icon = "✅ PASS" if condition else "❌ FAIL"
        print(f"  {icon} — {message}")
        if not condition:
            all_passed = False

    print("\n[ASSERTIONS]")

    # 1. Stock must never go below 0.
    assert_test(
        stock_after >= 0,
        f"Stock is non-negative (got {stock_after})",
    )

    # 2. No more orders succeeded than there was stock for.
    assert_test(
        len(successes) <= stock_before,
        f"Successful orders ({len(successes)}) <= initial stock ({stock_before})",
    )

    # 3. The decrease in stock matches the number of successes exactly.
    expected_stock_after = stock_before - len(successes)
    assert_test(
        stock_after == expected_stock_after,
        f"Stock decreased exactly by successes: "
        f"{stock_before} - {len(successes)} = {expected_stock_after} (got {stock_after})",
    )

    # 4. Every failure (beyond the stock limit) returned 409 Conflict, NOT 500.
    expected_failures = CONCURRENT_USERS - len(successes)
    assert_test(
        len(conflicts) == expected_failures,
        f"All failures ({expected_failures}) returned HTTP 409 Conflict",
    )

    # 5. No server-side 500 errors (unhandled exceptions on the backend).
    assert_test(
        len(other_errors) == 0,
        f"No unexpected HTTP errors (5xx / 4xx other than 409)",
    )

    print()
    if all_passed:
        print("  🎉 ALL ASSERTIONS PASSED — Race condition is fully fixed!")
    else:
        print("  🛑 SOME ASSERTIONS FAILED — Review the output above.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_test())
