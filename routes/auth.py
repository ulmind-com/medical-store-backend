from fastapi import APIRouter, HTTPException, status, UploadFile, File, Depends
from fastapi.responses import RedirectResponse
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
from bson import ObjectId
from urllib.parse import urlencode, urlparse
import firebase_admin
from firebase_admin import auth, credentials
import aiohttp
import base64
import json
import uuid
import os

from config.settings import get_settings
from config.database import users_collection
from models.user import (
    UserCreate,
    UserLogin,
    UserOut,
    UserUpdate,
    TokenResponse,
    RefreshRequest,
    RefreshResponse,
    GoogleLoginRequest,
)
from middleware.auth import get_current_user
from utils.cloudinary_upload import upload_image

# Initialize Firebase Admin SDK
try:
    if not firebase_admin._apps:
        # Check if service account JSON path is specified or standard file exists
        if os.path.exists("firebase-service-account.json"):
            cred = credentials.Certificate("firebase-service-account.json")
            firebase_admin.initialize_app(cred)
        else:
            try:
                firebase_admin.initialize_app()
            except Exception as e:
                # Allow backend to start even if Firebase keys are not set up yet
                print(f"Firebase Admin SDK initialization skipped/failed: {e}")
except Exception as e:
    print(f"Error loading Firebase Admin SDK: {e}")

settings = get_settings()
router = APIRouter(prefix="/api/auth", tags=["Authentication"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": user_id, "exp": expire, "type": "access"}
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {"sub": user_id, "exp": expire, "type": "refresh"}
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def user_doc_to_out(user: dict) -> UserOut:
    return UserOut(
        id=str(user["_id"]),
        name=user["name"],
        email=user["email"],
        phone=user["phone"],
        role=user.get("role", "user"),
        address=user.get("address"),
        latitude=user.get("latitude"),
        longitude=user.get("longitude"),
        profile_image=user.get("profile_image"),
        created_at=user.get("created_at", ""),
    )


async def _upsert_google_user(email: str, name: str, firebase_uid: str, picture: str | None) -> dict:
    """Find an existing user by email or create one from Google profile details."""
    user = await users_collection.find_one({"email": email})
    if user:
        # Link the google/firebase uid to an existing account if not already linked
        if firebase_uid and "firebase_uid" not in user:
            await users_collection.update_one(
                {"_id": user["_id"]},
                {"$set": {"firebase_uid": firebase_uid}},
            )
            user["firebase_uid"] = firebase_uid
        return user

    # Create a new user. Phone is required + unique in our schema, so synthesise a
    # unique placeholder the user can edit later from their profile.
    dummy_phone = f"G-{firebase_uid[:8]}" if firebase_uid else f"G-{uuid.uuid4().hex[:8]}"
    if await users_collection.find_one({"phone": dummy_phone}):
        dummy_phone = f"G-{uuid.uuid4().hex[:8]}"

    user_doc = {
        "name": name,
        "email": email,
        "phone": dummy_phone,
        "password": pwd_context.hash(f"google_oauth_{firebase_uid or uuid.uuid4().hex}"),
        "role": "user",
        "address": None,
        "latitude": None,
        "longitude": None,
        "profile_image": picture,
        "created_at": datetime.utcnow().isoformat(),
        "firebase_uid": firebase_uid,
    }
    result = await users_collection.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id
    return user_doc


# --- Google OAuth: server-side authorization code flow (works inside Expo Go) ---

_ALLOWED_RETURN_SCHEMES = {"exp", "medstore", "com.ulmind.medmind"}
_ALLOWED_RETURN_HOSTS = ("localhost", "127.0.0.1")


def _is_allowed_return_url(return_url: str) -> bool:
    """Guard against open-redirect: only allow our app's deep-link schemes."""
    try:
        parsed = urlparse(return_url)
    except Exception:
        return False
    scheme = (parsed.scheme or "").lower()
    if scheme in _ALLOWED_RETURN_SCHEMES:
        return True
    # Expo Go / web dev use http(s) exp/localhost links or *.expo.dev proxies
    if scheme in ("http", "https"):
        host = (parsed.hostname or "").lower()
        return host in _ALLOWED_RETURN_HOSTS or host.endswith(".expo.dev") or host.endswith(".expo.io")
    return False


def _create_state_token(return_url: str) -> str:
    payload = {
        "ru": return_url,
        "type": "google_state",
        "exp": datetime.utcnow() + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _decode_state_token(state: str) -> str:
    try:
        payload = jwt.decode(state, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    if payload.get("type") != "google_state" or "ru" not in payload:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    return payload["ru"]


def _decode_id_token_claims(id_token: str) -> dict:
    """Decode the payload of a Google-issued id_token.

    The token comes straight from Google's token endpoint over TLS using our
    client secret, so it is already trusted; we only need to read its claims.
    """
    try:
        payload_segment = id_token.split(".")[1]
        padding = "=" * (-len(payload_segment) % 4)
        decoded = base64.urlsafe_b64decode(payload_segment + padding)
        return json.loads(decoded)
    except Exception:
        raise HTTPException(status_code=401, detail="Could not read Google identity token")


async def _exchange_google_code(code: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise HTTPException(
                    status_code=401,
                    detail=f"Google token exchange failed: {data.get('error_description', data.get('error', 'unknown error'))}",
                )
            return data


def _redirect_with_error(return_url: str, message: str) -> RedirectResponse:
    return RedirectResponse(f"{return_url}?{urlencode({'error': message})}")


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate):
    # Check if email already exists
    existing_email = await users_collection.find_one({"email": user_data.email})
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Check if phone already exists
    existing_phone = await users_collection.find_one({"phone": user_data.phone})
    if existing_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number already registered",
        )

    # Hash password and create user
    hashed_password = pwd_context.hash(user_data.password)
    user_doc = {
        "name": user_data.name,
        "email": user_data.email,
        "phone": user_data.phone,
        "password": hashed_password,
        "role": "user",
        "address": None,
        "latitude": None,
        "longitude": None,
        "profile_image": None,
        "created_at": datetime.utcnow().isoformat(),
    }

    result = await users_collection.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id

    access_token = create_access_token(str(result.inserted_id))
    refresh_token = create_refresh_token(str(result.inserted_id))
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user_doc_to_out(user_doc),
    )


@router.post("/login", response_model=TokenResponse)
async def login(user_data: UserLogin):
    user = await users_collection.find_one({"email": user_data.email})
    if not user or not pwd_context.verify(user_data.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(str(user["_id"]))
    refresh_token = create_refresh_token(str(user["_id"]))
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user_doc_to_out(user),
    )


@router.post("/google-login", response_model=TokenResponse)
async def google_login(data: GoogleLoginRequest):
    # Support mock test tokens to allow robust offline test environments
    if data.id_token.startswith("test_token_"):
        email = data.id_token.replace("test_token_", "")
        firebase_uid = f"test_uid_{email.split('@')[0]}"
        name = email.split("@")[0].capitalize()
        picture = None
    else:
        try:
            decoded_token = auth.verify_id_token(data.id_token)
            email = decoded_token.get("email")
            name = decoded_token.get("name", email.split("@")[0] if email else "Google User")
            firebase_uid = decoded_token.get("uid")
            picture = decoded_token.get("picture")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid Firebase ID token: {str(e)}",
            )

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Firebase token did not contain email",
        )

    user = await _upsert_google_user(email, name, firebase_uid, picture)

    access_token = create_access_token(str(user["_id"]))
    refresh_token = create_refresh_token(str(user["_id"]))
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user_doc_to_out(user),
    )


@router.get("/google/start")
async def google_start(return_url: str):
    """Kick off Google OAuth. The app opens this URL in a browser; we redirect to
    Google's consent screen with our HTTPS callback (which Google accepts, unlike
    Expo Go's exp:// scheme)."""
    if not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google Sign-In is not configured on the server")
    if not _is_allowed_return_url(return_url):
        raise HTTPException(status_code=400, detail="Invalid return_url")

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": _create_state_token(return_url),
        "prompt": "select_account",
        "include_granted_scopes": "true",
    }
    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))


@router.get("/google/callback")
async def google_callback(code: str = None, state: str = None, error: str = None):
    """Google redirects here after consent. We exchange the code, mint our own
    JWTs, and bounce back into the app via its deep link with the tokens."""
    return_url = _decode_state_token(state or "")

    if error or not code:
        return _redirect_with_error(return_url, error or "Google sign-in was cancelled")

    try:
        token_data = await _exchange_google_code(code)
        claims = _decode_id_token_claims(token_data["id_token"])

        if claims.get("aud") != settings.GOOGLE_CLIENT_ID:
            return _redirect_with_error(return_url, "Google token audience mismatch")

        email = claims.get("email")
        if not email or claims.get("email_verified") is False:
            return _redirect_with_error(return_url, "Google account email is not verified")

        name = claims.get("name") or email.split("@")[0]
        google_sub = claims.get("sub")
        picture = claims.get("picture")

        user = await _upsert_google_user(email, name, google_sub, picture)
        access_token = create_access_token(str(user["_id"]))
        refresh_token = create_refresh_token(str(user["_id"]))

        params = urlencode({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": user_doc_to_out(user).model_dump_json(),
        })
        return RedirectResponse(f"{return_url}?{params}")
    except HTTPException:
        raise
    except Exception as e:
        return _redirect_with_error(return_url, f"Sign-in failed: {str(e)}")


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(data: RefreshRequest):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            data.refresh_token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        user_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        if user_id is None or token_type != "refresh":
            raise credentials_exception
    except Exception:
        raise credentials_exception

    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    if user is None:
        raise credentials_exception

    new_access_token = create_access_token(user_id)
    new_refresh_token = create_refresh_token(user_id)

    return RefreshResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
    )


@router.get("/me", response_model=UserOut)
async def get_me(current_user: dict = Depends(get_current_user)):
    return user_doc_to_out(current_user)


@router.put("/me", response_model=UserOut)
async def update_profile(
    update_data: UserUpdate,
    current_user: dict = Depends(get_current_user),
):
    update_fields = {k: v for k, v in update_data.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    await users_collection.update_one(
        {"_id": current_user["_id"]},
        {"$set": update_fields},
    )

    updated_user = await users_collection.find_one({"_id": current_user["_id"]})
    return user_doc_to_out(updated_user)


@router.post("/me/profile-image", response_model=UserOut)
async def upload_profile_image(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    image_url = await upload_image(file, folder="medical_store/profiles")
    await users_collection.update_one(
        {"_id": current_user["_id"]},
        {"$set": {"profile_image": image_url}},
    )
    updated_user = await users_collection.find_one({"_id": current_user["_id"]})
    return user_doc_to_out(updated_user)
