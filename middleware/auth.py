"""
middleware/auth.py
──────────────────────────────────────────────────────────────────────────────
Clerk JWT verification middleware using JWKS public key.

Fixed issues:
  - python-jose requires the RSA public key object, NOT the raw JWKS dict
  - Proper key matching by kid (key ID) from JWT header
  - get_clerk_payload: returns raw claims (no MongoDB lookup)
  - get_current_user: returns MongoDB user doc
"""
import os
import requests
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, jwk
from jose.exceptions import JWTError
from config.database import users_collection
from config.settings import get_settings

settings = get_settings()
security = HTTPBearer()


# ── JWKS URL ───────────────────────────────────────────────────────────────
# Always use the hardcoded domain from the publishable key.
# pk_test_YWRhcHRlZC1zb2xlLTMuY2xlcmsuYWNjb3VudHMuZGV2JA
# → domain: adapted-sole-3.clerk.accounts.dev
CLERK_JWKS_URL = "https://adapted-sole-3.clerk.accounts.dev/.well-known/jwks.json"

# Simple in-memory cache — keyed by kid → RSA public key
_jwks_key_cache: dict = {}
_jwks_loaded = False


def _load_jwks() -> bool:
    """
    Fetch JWKS from Clerk and populate the key cache.
    Returns True on success.
    """
    global _jwks_loaded
    try:
        resp = requests.get(CLERK_JWKS_URL, timeout=10)
        if resp.status_code != 200:
            print(f"[Auth] JWKS fetch failed: HTTP {resp.status_code}")
            return False

        data = resp.json()
        for key_data in data.get("keys", []):
            kid = key_data.get("kid")
            if kid:
                # Construct the public key object from JWK
                rsa_key = jwk.construct(key_data)
                _jwks_key_cache[kid] = rsa_key

        _jwks_loaded = True
        print(f"[Auth] Loaded {len(_jwks_key_cache)} JWKS key(s) from Clerk")
        return True
    except Exception as e:
        print(f"[Auth] Error loading JWKS: {e}")
        return False


def _get_public_key(token: str):
    """
    Extract the kid from the JWT header and return the matching RSA key.
    Reloads JWKS if the key is not found (handles key rotation).
    """
    global _jwks_loaded

    # Decode header without verification to get kid
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token header: {e}",
        )

    kid = header.get("kid")

    # Load JWKS if not loaded yet
    if not _jwks_loaded or (kid and kid not in _jwks_key_cache):
        _load_jwks()

    if not _jwks_key_cache:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable (JWKS unavailable)",
        )

    # Match key by kid, or fall back to first available key
    if kid and kid in _jwks_key_cache:
        return _jwks_key_cache[kid]
    elif _jwks_key_cache:
        # Fallback: use first key (handles cases where kid is missing)
        return next(iter(_jwks_key_cache.values()))
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No matching signing key found",
        )


def _decode_token(token: str) -> dict:
    """
    Verify and decode a JWT. Supports both Clerk RS256 and custom HS256.
    Returns the payload dict on success, raises HTTPException on failure.
    """
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token header: {e}",
        )

    alg = header.get("alg")

    if alg == "HS256":
        # Custom JWT
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
            return payload
        except JWTError as e:
            print(f"[Auth] Custom HS256 JWT decode failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token verification failed",
                headers={"WWW-Authenticate": "Bearer"},
            )
    else:
        # Clerk JWT (RS256)
        public_key = _get_public_key(token)
        try:
            payload = jwt.decode(
                token,
                public_key.public_key(),  # RSA public key object
                algorithms=["RS256"],
                options={"verify_aud": False},
            )
            return payload
        except JWTError as e:
            print(f"[Auth] Clerk RS256 JWT decode failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token verification failed",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e:
            print(f"[Auth] Unexpected error decoding token: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )


# ── FastAPI Dependencies ───────────────────────────────────────────────────

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
    Dependency: verify JWT (either Clerk or Custom) and return the MongoDB user document.
    """
    payload = _decode_token(credentials.credentials)

    sub: str = payload.get("sub", "")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing subject",
        )

    # Check if the token is a custom JWT
    is_custom = payload.get("type") == "custom"

    if is_custom:
        try:
            from bson import ObjectId
            user = await users_collection.find_one({"_id": ObjectId(sub)})
        except Exception:
            user = None
    else:
        # Primary lookup by clerk_id
        user = await users_collection.find_one({"clerk_id": sub})

        if user is None:
            # Fallback: find by email and link clerk_id
            email = (
                payload.get("email")
                or payload.get("primary_email_address")
                or ""
            ).lower()

            if email:
                user = await users_collection.find_one({"email": email})
                if user:
                    await users_collection.update_one(
                        {"_id": user["_id"]},
                        {"$set": {"clerk_id": sub}}
                    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
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
