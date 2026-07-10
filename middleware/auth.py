import requests
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt
from jose.exceptions import JWTError
from config.settings import get_settings
from config.database import users_collection

settings = get_settings()
security = HTTPBearer()

# Clerk JWKS URL derived from public key domain: adapted-sole-3.clerk.accounts.dev
CLERK_JWKS_URL = "https://adapted-sole-3.clerk.accounts.dev/.well-known/jwks.json"
_jwks_cache = None

def get_jwks():
    global _jwks_cache
    if _jwks_cache is None:
        try:
            resp = requests.get(CLERK_JWKS_URL, timeout=10)
            if resp.status_code == 200:
                _jwks_cache = resp.json()
        except Exception as e:
            print(f"Error fetching Clerk JWKS: {e}")
    return _jwks_cache

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Extract and verify Clerk RS256 JWT token, returning the database user profile."""
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    jwks = get_jwks()
    if not jwks:
        raise credentials_exception

    try:
        # RS256 algorithm verification using JWKS keys
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )
        clerk_id: str = payload.get("sub")
        if clerk_id is None:
            raise credentials_exception
    except JWTError as e:
        print(f"JWT Verification failed: {e}")
        raise credentials_exception

    # Find user by clerk_id
    user = await users_collection.find_one({"clerk_id": clerk_id})
    if user is None:
        # Fallback to finding by email address if email is in token claims
        email = payload.get("email")
        if not email:
            # Check for standard clerk email claims
            email = payload.get("primary_email_address")
            
        if email:
            user = await users_collection.find_one({"email": email})
            if user:
                # Link clerk_id to existing user record
                await users_collection.update_one(
                    {"_id": user["_id"]},
                    {"$set": {"clerk_id": clerk_id}}
                )

    if user is None:
        # If user doesn't exist yet, we raise 401 (webhook is handling sync)
        raise credentials_exception

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
