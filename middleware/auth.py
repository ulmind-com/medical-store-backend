import os
import requests
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt
from jose.exceptions import JWTError
from config.database import users_collection

security = HTTPBearer()

# Derive JWKS URL from the publishable key's domain
# pk_test_YWRhcHRlZC1zb2xlLTMuY2xlcmsuYWNjb3VudHMuZGV2JA
# → base64 decode middle segment → adapted-sole-3.clerk.accounts.dev
def _derive_jwks_url() -> str:
    import base64
    pk = os.environ.get("CLERK_PUBLISHABLE_KEY", "")
    if not pk:
        # Fallback: hardcoded from .env publishable key domain
        return "https://adapted-sole-3.clerk.accounts.dev/.well-known/jwks.json"
    try:
        # pk_test_<base64-encoded-domain> → decode to get the instance domain
        encoded = pk.split("_", 2)[-1]
        # Add padding
        padded = encoded + "=" * (-len(encoded) % 4)
        domain = base64.b64decode(padded).decode("utf-8").rstrip("$")
        return f"https://{domain}/.well-known/jwks.json"
    except Exception:
        return "https://adapted-sole-3.clerk.accounts.dev/.well-known/jwks.json"

CLERK_JWKS_URL = _derive_jwks_url()
_jwks_cache = None


def get_jwks():
    global _jwks_cache
    if _jwks_cache is None:
        try:
            resp = requests.get(CLERK_JWKS_URL, timeout=10)
            if resp.status_code == 200:
                _jwks_cache = resp.json()
                print(f"[Auth] Loaded JWKS from {CLERK_JWKS_URL}")
            else:
                print(f"[Auth] JWKS fetch failed: {resp.status_code}")
        except Exception as e:
            print(f"[Auth] Error fetching Clerk JWKS: {e}")
    return _jwks_cache


def _decode_token(token: str) -> dict:
    """Decode and verify a Clerk RS256 JWT. Returns the payload dict."""
    jwks = get_jwks()
    if not jwks:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable",
        )
    try:
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        return payload
    except JWTError as e:
        print(f"[Auth] JWT verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_clerk_payload(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Dependency: verify Clerk JWT and return raw payload claims.
    Does NOT require the user to exist in MongoDB.
    Used by /upsert which creates the user if missing.
    """
    return _decode_token(credentials.credentials)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Dependency: verify Clerk JWT and return the MongoDB user document.
    Returns 401 if user not found in DB (call /upsert first).
    """
    token = credentials.credentials
    payload = _decode_token(token)

    clerk_id: str = payload.get("sub")
    if not clerk_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing subject",
        )

    # Find user by clerk_id
    user = await users_collection.find_one({"clerk_id": clerk_id})

    if user is None:
        # Fallback: try to find by email claim
        email = (payload.get("email") or payload.get("primary_email_address") or "").lower()
        if email:
            user = await users_collection.find_one({"email": email})
            if user:
                # Link clerk_id going forward
                await users_collection.update_one(
                    {"_id": user["_id"]},
                    {"$set": {"clerk_id": clerk_id}}
                )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User profile not found. Please call /api/auth/upsert first.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user["id"] = str(user["_id"])
    return user


async def get_admin_user(current_user: dict = Depends(get_current_user)):
    """Ensure the current user is an admin."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user

