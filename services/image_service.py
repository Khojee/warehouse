"""Image upload handling for product images and the company logo.

Files are stored under the existing static `images/` mount; only relative
paths (forward slashes) are stored in the database.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from database import SessionLocal
from models import ProductImage, Setting


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRODUCT_IMAGES_DIR = PROJECT_ROOT / "images" / "products"
COMPANY_IMAGES_DIR = PROJECT_ROOT / "images" / "company"

PRODUCT_IMAGES_REL = "images/products"
COMPANY_IMAGES_REL = "images/company"

LOGO_SETTING_KEY = "logo_path"
LOGO_BASENAME = "company_logo"


def extension_of(filename: str) -> str | None:
    """Return the lowercase extension if it is an accepted image format."""
    name = (filename or "").strip().lower()
    if "." not in name:
        return None
    ext = name.rsplit(".", 1)[-1]
    return ext if ext in ALLOWED_EXTENSIONS else None


def sanitize_part(value: str) -> str:
    """Lowercase, spaces -> underscores, strip characters invalid in filenames."""
    part = (value or "").strip().lower()
    part = re.sub(r"\s+", "_", part)
    part = re.sub(r"[^\w\-]", "", part, flags=re.UNICODE)
    return part


def build_product_basename(category: str, size: str, pressure: str) -> str:
    parts = [sanitize_part(category), sanitize_part(size), sanitize_part(pressure)]
    parts = [part for part in parts if part]
    return "_".join(parts) or "product"


def _unique_filename(directory: Path, base: str, ext: str) -> str:
    candidate = f"{base}.{ext}"
    if not (directory / candidate).exists():
        return candidate
    suffix = int(time.time())
    candidate = f"{base}_{suffix}.{ext}"
    counter = 1
    while (directory / candidate).exists():
        candidate = f"{base}_{suffix}_{counter}.{ext}"
        counter += 1
    return candidate


def save_product_image(
    data: bytes,
    *,
    category: str,
    size: str,
    pressure: str,
    ext: str,
) -> str:
    """Write the image to images/products/ and return its relative path."""
    PRODUCT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    base = build_product_basename(category, size, pressure)
    filename = _unique_filename(PRODUCT_IMAGES_DIR, base, ext)
    (PRODUCT_IMAGES_DIR / filename).write_bytes(data)
    return f"{PRODUCT_IMAGES_REL}/{filename}"


def upsert_primary_product_image(product_id: int, file_path: str) -> None:
    """Insert the primary image record, or update it if one already exists."""
    with SessionLocal.begin() as session:
        image = session.scalar(
            select(ProductImage)
            .where(ProductImage.product_id == product_id)
            .where(ProductImage.is_primary.is_(True))
            .limit(1)
        )
        if image is None:
            session.add(
                ProductImage(
                    product_id=product_id,
                    file_path=file_path,
                    is_primary=True,
                    uploaded_at=datetime.utcnow(),
                )
            )
        else:
            image.file_path = file_path
            image.uploaded_at = datetime.utcnow()


def save_company_logo(data: bytes, ext: str) -> str:
    """Write the logo to images/company/, update logo_path, return relative path."""
    COMPANY_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    for stale in COMPANY_IMAGES_DIR.glob(f"{LOGO_BASENAME}.*"):
        stale.unlink(missing_ok=True)
    filename = f"{LOGO_BASENAME}.{ext}"
    (COMPANY_IMAGES_DIR / filename).write_bytes(data)

    relative_path = f"{COMPANY_IMAGES_REL}/{filename}"
    with SessionLocal.begin() as session:
        setting = session.get(Setting, LOGO_SETTING_KEY)
        if setting is None:
            session.add(Setting(key=LOGO_SETTING_KEY, value=relative_path))
        else:
            setting.value = relative_path
    return relative_path


def get_logo_path() -> str | None:
    """Return the stored logo path if the setting and the file both exist."""
    with SessionLocal() as session:
        setting = session.get(Setting, LOGO_SETTING_KEY)
    if setting is None or not (setting.value or "").strip():
        return None
    relative_path = setting.value.strip().replace("\\", "/")
    if not (PROJECT_ROOT / relative_path).exists():
        return None
    return relative_path
