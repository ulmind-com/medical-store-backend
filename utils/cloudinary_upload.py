import cloudinary.uploader
from fastapi import UploadFile
import config.cloudinary_config  # noqa: F401 — triggers Cloudinary initialization


async def upload_image(file: UploadFile, folder: str = "medical_store") -> str:
    """Upload an image to Cloudinary and return the secure URL."""
    contents = await file.read()
    result = cloudinary.uploader.upload(
        contents,
        folder=folder,
        resource_type="auto",
    )
    return result.get("secure_url", "")


async def upload_image_bytes(file_bytes: bytes, folder: str = "medical_store") -> str:
    """Upload raw bytes to Cloudinary and return the secure URL."""
    result = cloudinary.uploader.upload(
        file_bytes,
        folder=folder,
        resource_type="auto",
    )
    return result.get("secure_url", "")


def delete_image(public_id: str):
    """Delete an image from Cloudinary by its public_id."""
    cloudinary.uploader.destroy(public_id)
