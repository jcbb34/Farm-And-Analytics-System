from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.workforce import TaskEvidence


ALLOWED_IMAGE_FORMATS = {
    "JPEG": {"extensions": {".jpg", ".jpeg"}, "mime": "image/jpeg"},
    "PNG": {"extensions": {".png"}, "mime": "image/png"},
    "WEBP": {"extensions": {".webp"}, "mime": "image/webp"},
}
SIGNATURE_CHECKS = {
    "JPEG": lambda data: data.startswith(b"\xff\xd8\xff"),
    "PNG": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
    "WEBP": lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
}


class EvidenceValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ProcessedEvidenceImage:
    content: bytes
    thumbnail: bytes
    content_type: str
    extension: str
    width: int
    height: int
    sha256_hex: str


class LocalEvidenceStorage:
    """Filesystem storage used for the capstone WLAN deployment.

    Callers only work with random storage identifiers.  Physical server paths
    never leave this class and are never returned by API responses.  A future
    object-storage adapter can implement the same small interface.
    """

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, identifier: str, payload: bytes) -> None:
        target = self._path(identifier)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)

    def path_for_response(self, identifier: str) -> Path:
        target = self._path(identifier)
        if not target.is_file():
            raise FileNotFoundError(identifier)
        return target

    def delete(self, identifier: str | None) -> None:
        if not identifier:
            return
        self._path(identifier).unlink(missing_ok=True)

    def _path(self, identifier: str) -> Path:
        safe_name = Path(str(identifier)).name
        if safe_name != identifier or not safe_name:
            raise ValueError("Invalid evidence storage identifier")
        return self.root / safe_name


def get_evidence_storage():
    backend = str(settings.workforce_evidence_storage_backend or "local").strip().lower()
    if backend != "local":
        raise RuntimeError(
            f"Unsupported workforce evidence storage backend: {backend}. "
            "Configure 'local' or install an object-storage adapter."
        )
    configured = Path(settings.workforce_evidence_local_dir)
    root = configured if configured.is_absolute() else Path(__file__).resolve().parents[2] / configured
    return LocalEvidenceStorage(root)


def _safe_display_name(filename: str | None) -> str:
    value = Path(str(filename or "evidence-image")).name.strip()
    return (value or "evidence-image")[:255]


def validate_and_reencode_image(
    payload: bytes,
    *,
    original_filename: str | None,
    browser_content_type: str | None,
) -> ProcessedEvidenceImage:
    if not payload:
        raise EvidenceValidationError("The selected evidence photo is empty.")
    if len(payload) > settings.workforce_evidence_max_bytes:
        raise EvidenceValidationError(
            f"Evidence photo must be {settings.workforce_evidence_max_bytes // (1024 * 1024)} MB or smaller."
        )

    extension = Path(_safe_display_name(original_filename)).suffix.lower()
    if extension not in {ext for item in ALLOWED_IMAGE_FORMATS.values() for ext in item["extensions"]}:
        raise EvidenceValidationError("Evidence photo must use a JPG, JPEG, PNG, or WEBP extension.")

    claimed_mime = str(browser_content_type or "").split(";", 1)[0].strip().lower()
    if claimed_mime not in {item["mime"] for item in ALLOWED_IMAGE_FORMATS.values()}:
        raise EvidenceValidationError("Evidence photo MIME type must be image/jpeg, image/png, or image/webp.")

    try:
        with Image.open(BytesIO(payload)) as probe:
            actual_format = str(probe.format or "").upper()
            probe.verify()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise EvidenceValidationError("The uploaded file is not a valid decodable image.") from exc

    metadata = ALLOWED_IMAGE_FORMATS.get(actual_format)
    signature_check = SIGNATURE_CHECKS.get(actual_format)
    if metadata is None or signature_check is None or not signature_check(payload):
        raise EvidenceValidationError("The uploaded file signature is not an allowed image format.")
    if extension not in metadata["extensions"]:
        raise EvidenceValidationError("The file extension does not match the actual image format.")
    if claimed_mime != metadata["mime"]:
        raise EvidenceValidationError("The browser MIME type does not match the actual image format.")

    try:
        with Image.open(BytesIO(payload)) as source:
            width, height = source.size
            if width < settings.workforce_evidence_min_dimension or height < settings.workforce_evidence_min_dimension:
                raise EvidenceValidationError(
                    f"Evidence photo dimensions must be at least {settings.workforce_evidence_min_dimension}x{settings.workforce_evidence_min_dimension} pixels."
                )
            if width > settings.workforce_evidence_max_dimension or height > settings.workforce_evidence_max_dimension:
                raise EvidenceValidationError(
                    f"Evidence photo dimensions must not exceed {settings.workforce_evidence_max_dimension} pixels on either side."
                )
            if width * height > settings.workforce_evidence_max_pixels:
                raise EvidenceValidationError("Evidence photo contains too many pixels.")

            # Only decode pixels after the dimension/pixel-count limits pass.
            source.load()
            normalized = ImageOps.exif_transpose(source)
            has_alpha = normalized.mode in {"RGBA", "LA"} or (
                normalized.mode == "P" and "transparency" in normalized.info
            )
            if has_alpha:
                normalized = normalized.convert("RGBA")
                output_format = "PNG"
                output_extension = ".png"
                output_mime = "image/png"
            else:
                normalized = normalized.convert("RGB")
                output_format = "JPEG"
                output_extension = ".jpg"
                output_mime = "image/jpeg"

            output = BytesIO()
            if output_format == "JPEG":
                normalized.save(output, format="JPEG", quality=88, optimize=True)
            else:
                normalized.save(output, format="PNG", optimize=True)
            safe_bytes = output.getvalue()

            thumbnail_image = normalized.copy()
            thumbnail_image.thumbnail(
                (settings.workforce_evidence_thumbnail_pixels, settings.workforce_evidence_thumbnail_pixels)
            )
            thumb_output = BytesIO()
            if has_alpha:
                thumbnail_image.save(thumb_output, format="PNG", optimize=True)
            else:
                thumbnail_image.save(thumb_output, format="JPEG", quality=82, optimize=True)
            thumbnail_bytes = thumb_output.getvalue()
            final_width, final_height = normalized.size
    except EvidenceValidationError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise EvidenceValidationError("The uploaded image could not be decoded safely.") from exc

    return ProcessedEvidenceImage(
        content=safe_bytes,
        thumbnail=thumbnail_bytes,
        content_type=output_mime,
        extension=output_extension,
        width=final_width,
        height=final_height,
        sha256_hex=sha256(safe_bytes).hexdigest(),
    )


def create_task_evidence(
    db: Session,
    *,
    task_id: int,
    uploader_user_id: int,
    original_filename: str | None,
    browser_content_type: str | None,
    payload: bytes,
) -> TaskEvidence:
    now = datetime.now()
    active_assets = list(
        db.scalars(
            select(TaskEvidence).where(
                TaskEvidence.activity_id == task_id,
                TaskEvidence.submission_id.is_(None),
                TaskEvidence.status == "Temporary",
                (TaskEvidence.expires_at.is_(None) | (TaskEvidence.expires_at > now)),
            )
        ).all()
    )
    if len(active_assets) >= settings.workforce_evidence_max_files_per_submission:
        raise EvidenceValidationError(
            f"A task submission may contain at most {settings.workforce_evidence_max_files_per_submission} evidence photos."
        )

    processed = validate_and_reencode_image(
        payload,
        original_filename=original_filename,
        browser_content_type=browser_content_type,
    )
    pending_total = sum(int(item.size_bytes or 0) for item in active_assets)
    if pending_total + len(processed.content) > settings.workforce_evidence_max_total_bytes_per_submission:
        raise EvidenceValidationError(
            f"Total evidence for one submission must be {settings.workforce_evidence_max_total_bytes_per_submission // (1024 * 1024)} MB or smaller."
        )

    public_id = uuid4().hex
    storage_identifier = f"{uuid4().hex}{processed.extension}"
    thumbnail_identifier = f"{uuid4().hex}.thumb{processed.extension}"
    storage = get_evidence_storage()
    storage.put(storage_identifier, processed.content)
    try:
        storage.put(thumbnail_identifier, processed.thumbnail)
    except Exception:
        storage.delete(storage_identifier)
        raise

    evidence = TaskEvidence(
        public_id=public_id,
        activity_id=task_id,
        submission_id=None,
        uploader_user_id=uploader_user_id,
        original_display_name=_safe_display_name(original_filename),
        content_type=processed.content_type,
        storage_identifier=storage_identifier,
        thumbnail_storage_identifier=thumbnail_identifier,
        size_bytes=len(processed.content),
        sha256=processed.sha256_hex,
        width=processed.width,
        height=processed.height,
        status="Temporary",
        expires_at=now + timedelta(hours=settings.workforce_evidence_temporary_hours),
        created_at=now,
    )
    db.add(evidence)
    try:
        db.flush()
    except Exception:
        storage.delete(storage_identifier)
        storage.delete(thumbnail_identifier)
        raise
    return evidence


def cleanup_expired_task_evidence(db: Session, *, now: datetime | None = None, commit: bool = True) -> int:
    cutoff = now or datetime.now()
    expired = list(
        db.scalars(
            select(TaskEvidence).where(
                TaskEvidence.submission_id.is_(None),
                TaskEvidence.status == "Temporary",
                TaskEvidence.expires_at.is_not(None),
                TaskEvidence.expires_at <= cutoff,
            )
        ).all()
    )
    if not expired:
        if commit:
            db.commit()
        return 0

    storage = get_evidence_storage()
    for evidence in expired:
        storage.delete(evidence.storage_identifier)
        storage.delete(evidence.thumbnail_storage_identifier)
        evidence.status = "Deleted"
        evidence.deleted_at = cutoff
        evidence.expires_at = None
    if commit:
        db.commit()
    else:
        db.flush()
    return len(expired)


def evidence_url(public_id: str) -> str:
    return f"/workforce/evidence-assets/{public_id}"


def evidence_thumbnail_url(public_id: str) -> str:
    return f"/workforce/evidence-assets/{public_id}/thumbnail"
