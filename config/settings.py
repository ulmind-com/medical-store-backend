from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    MONGODB_URL: str
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    CLOUDINARY_CLOUD_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str

    RAZORPAY_KEY_ID: str
    RAZORPAY_KEY_SECRET: str

    # Google OAuth (server-side authorization code flow — works in Expo Go)
    GOOGLE_CLIENT_ID: str = "94751380370-j7lqf6pt5ptv7fiv6h2pt8k9i12n8e22.apps.googleusercontent.com"
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "https://medical-store-backend-qklg.onrender.com/api/auth/google/callback"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()
