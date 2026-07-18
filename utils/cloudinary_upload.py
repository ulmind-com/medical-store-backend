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
    try:
        cloudinary.uploader.destroy(public_id)
    except Exception as e:
        print(f"Error deleting image from Cloudinary: {e}")

def extract_public_id(url: str) -> str:
    """Extract public_id from a Cloudinary URL."""
    if not url:
        return ""
    try:
        parts = url.split("/upload/")
        if len(parts) > 1:
            path = parts[1]
            if path.startswith("v") and "/" in path:
                version_end = path.find("/")
                if path[1:version_end].isdigit():
                    path = path[version_end+1:]
            return path.rsplit(".", 1)[0]
    except Exception:
        pass
    return ""
