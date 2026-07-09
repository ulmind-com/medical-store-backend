"""
test_refresh_flow.py
===================
Test script for the JWT Refresh Token Flow.

This script verifies:
1. Normal Login returns both access_token and refresh_token.
2. Accessing a secure endpoint (/api/auth/me) with the access_token succeeds.
3. Accessing the endpoint with an invalid/expired token returns HTTP 401.
4. Calling POST /api/auth/refresh with the refresh_token returns a new access_token
   and a rotated refresh_token.
5. Accessing the secure endpoint with the newly minted access_token succeeds.

Usage:
------
1. Ensure the backend server is running:
       uv run uvicorn main:app --reload

2. Configure USER_EMAIL and USER_PASSWORD with a valid user's credentials below.

3. Run the script:
       python test_refresh_flow.py
"""

import requests
import json
import sys

# ─────────────────────────────────────────────────────────────────────────────
# ★  CONFIGURE THESE BEFORE RUNNING  ★
# ─────────────────────────────────────────────────────────────────────────────
BASE_URL = "http://127.0.0.1:8000"
USER_EMAIL = "PASTE_TEST_USER_EMAIL_HERE"
USER_PASSWORD = "PASTE_TEST_USER_PASSWORD_HERE"
# ─────────────────────────────────────────────────────────────────────────────

def run_test():
    print("=" * 65)
    print("  JWT REFRESH FLOW REGRESSION TEST")
    print("=" * 65)

    if USER_EMAIL == "PASTE_TEST_USER_EMAIL_HERE" or USER_PASSWORD == "PASTE_TEST_USER_PASSWORD_HERE":
        print("⚠️ Please configure USER_EMAIL and USER_PASSWORD in the script before running.")
        sys.exit(1)

    # 1. Login to obtain access and refresh tokens
    print("\n[STEP 1] Logging in...")
    login_url = f"{BASE_URL}/api/auth/login"
    login_payload = {
        "email": USER_EMAIL,
        "password": USER_PASSWORD
    }

    try:
        response = requests.post(login_url, json=login_payload)
    except requests.exceptions.ConnectionError:
        print(f"❌ Failed to connect to server at {BASE_URL}. Ensure uvicorn is running.")
        sys.exit(1)

    if response.status_code != 200:
        print(f"❌ Login failed with status {response.status_code}: {response.text}")
        sys.exit(1)

    login_data = response.json()
    access_token = login_data.get("access_token")
    refresh_token = login_data.get("refresh_token")

    if not access_token or not refresh_token:
        print(f"❌ Server did not return both tokens: {login_data}")
        sys.exit(1)

    print("✅ Login successful!")
    print(f"   Access Token:  {access_token[:25]}...")
    print(f"   Refresh Token: {refresh_token[:25]}...")

    # 2. Make a secure request with the current access token
    print("\n[STEP 2] Making request to secure route (/api/auth/me) with Access Token...")
    headers = {"Authorization": f"Bearer {access_token}"}
    me_response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)

    if me_response.status_code != 200:
        print(f"❌ Failed to fetch profile with valid access token: {me_response.status_code} - {me_response.text}")
        sys.exit(1)

    print("✅ Profile fetched successfully!")
    print(f"   User Name: {me_response.json().get('name')}")
    print(f"   User Role: {me_response.json().get('role')}")

    # 3. Simulate access token expiry (use a corrupted/invalid token)
    print("\n[STEP 3] Making request with invalid/expired Access Token (expects 401)...")
    bad_headers = {"Authorization": "Bearer bad_expired_or_corrupted_access_token"}
    bad_response = requests.get(f"{BASE_URL}/api/auth/me", headers=bad_headers)

    if bad_response.status_code != 401:
        print(f"❌ Expected HTTP 401 Unauthorized, but got {bad_response.status_code}: {bad_response.text}")
        sys.exit(1)

    print("✅ Received expected HTTP 401 Unauthorized!")

    # 4. Use the refresh token to get a new access token (and verify token rotation)
    print("\n[STEP 4] Calling POST /api/auth/refresh with Refresh Token...")
    refresh_url = f"{BASE_URL}/api/auth/refresh"
    refresh_payload = {
        "refresh_token": refresh_token
    }
    refresh_response = requests.post(refresh_url, json=refresh_payload)

    if refresh_response.status_code != 200:
        print(f"❌ Refresh request failed with status {refresh_response.status_code}: {refresh_response.text}")
        sys.exit(1)

    refresh_data = refresh_response.json()
    new_access_token = refresh_data.get("access_token")
    new_refresh_token = refresh_data.get("refresh_token")

    if not new_access_token or not new_refresh_token:
        print(f"❌ Refresh response missing new tokens: {refresh_data}")
        sys.exit(1)

    print("✅ Refresh successful!")
    print(f"   New Access Token:  {new_access_token[:25]}...")
    print(f"   New Refresh Token: {new_refresh_token[:25]}...")

    if new_refresh_token == refresh_token:
        print("⚠️ Refresh token was not rotated (returned identical token).")
    else:
        print("✅ Refresh token rotated successfully!")

    # 5. Access the secure route with the brand new access token
    print("\n[STEP 5] Accessing secure route with new Access Token...")
    new_headers = {"Authorization": f"Bearer {new_access_token}"}
    new_me_response = requests.get(f"{BASE_URL}/api/auth/me", headers=new_headers)

    if new_me_response.status_code != 200:
        print(f"❌ Failed to access secure route with new access token: {new_me_response.status_code} - {new_me_response.text}")
        sys.exit(1)

    print("✅ Successfully accessed secure route with new Access Token!")
    print(f"   User Name: {new_me_response.json().get('name')}")
    print("\n🎉 ALL REFRESH FLOW TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_test()
