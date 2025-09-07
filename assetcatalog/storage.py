import hashlib
import os
import mimetypes
from pathlib import Path
from typing import Tuple, Dict, Any

from django.conf import settings
from django.core.files.storage import FileSystemStorage

# Lazy/optional Pillow import so runserver doesn't crash if not installed yet
try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover
    Image = None

BLOB_BASE = "assets/blobs"
THUMB_BASE = "assets/thumbs"

_storage = FileSystemStorage(location=getattr(settings, "MEDIA_ROOT", None),
                             base_url=getattr(settings, "MEDIA_URL", None))


def _hash_file_and_size(file_obj) -> Tuple[str, int]:
    sha = hashlib.sha256()
    total = 0
    for chunk in file_obj.chunks():
        sha.update(chunk)
        total += len(chunk)
    file_obj.seek(0)
    return sha.hexdigest(), total


def _hash_to_path(sha256: str) -> str:
    return os.path.join(BLOB_BASE, sha256[:2], sha256[2:4], sha256)


def store_blob(uploaded_file) -> Dict[str, Any]:
    sha, size = _hash_file_and_size(uploaded_file)
    blob_rel = _hash_to_path(sha)

    existed = _storage.exists(blob_rel)
    if not existed:
        abs_dir = Path(_storage.path(blob_rel)).parent
        abs_dir.mkdir(parents=True, exist_ok=True)
        _storage.save(blob_rel, uploaded_file)
    else:
        uploaded_file.seek(0)

    ctype = getattr(uploaded_file, "content_type", None) or mimetypes.guess_type(uploaded_file.name or "")[0] or "application/octet-stream"

    return {
        "sha256": sha,
        "size_bytes": size,
        "content_type": ctype,
        "blob_path": blob_rel,
        "existed": existed,
    }


def thumbnail_path_for_sha(sha256: str, ext: str = "jpg") -> str:
    return os.path.join(THUMB_BASE, f"{sha256}.{ext}")


def ensure_image_thumbnail(sha256: str, blob_rel: str, max_size=(600, 600)) -> str | None:
    if Image is None:
        return None  # Pillow not installed; skip
    thumb_rel = thumbnail_path_for_sha(sha256)
    if _storage.exists(thumb_rel):
        return thumb_rel

    abs_thumb = Path(_storage.path(thumb_rel))
    abs_thumb.parent.mkdir(parents=True, exist_ok=True)

    with _storage.open(blob_rel, "rb") as f:
        img = Image.open(f)
        img.thumbnail(max_size)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(abs_thumb, format="JPEG", optimize=True, quality=82)

    return thumb_rel
