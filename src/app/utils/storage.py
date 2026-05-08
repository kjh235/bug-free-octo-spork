import hashlib
import shutil
import uuid
from pathlib import Path

UPLOADS_ROOT = Path(__file__).parent.parent.parent.parent / "uploads"
UPLOADS_ROOT.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".webp"}
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB


def save_upload(file_obj, original_filename: str, owner_id: str) -> tuple[str, str]:
    """
    Persist an uploaded file and return (relative_path, sha256_hex).
    Raises ValueError for disallowed extensions or oversized files.
    """
    suffix = Path(original_filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File type '{suffix}' not allowed. Accepted: {ALLOWED_EXTENSIONS}")

    dest_dir = UPLOADS_ROOT / owner_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_name = f"{uuid.uuid4()}{suffix}"
    dest_path = dest_dir / dest_name

    hasher = hashlib.sha256()
    total = 0
    with dest_path.open("wb") as out:
        while chunk := file_obj.read(8192):
            total += len(chunk)
            if total > MAX_FILE_SIZE_BYTES:
                dest_path.unlink(missing_ok=True)
                raise ValueError(f"File exceeds {MAX_FILE_SIZE_BYTES // (1024*1024)} MB limit")
            hasher.update(chunk)
            out.write(chunk)

    relative = str(dest_path.relative_to(UPLOADS_ROOT))
    return relative, hasher.hexdigest()


def delete_upload(relative_path: str) -> None:
    target = UPLOADS_ROOT / relative_path
    target.unlink(missing_ok=True)
