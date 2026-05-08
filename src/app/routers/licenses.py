import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import CurrentUser, get_current_user
from ..models import License, LicenseStatus, LicenseType, User
from ..schemas import LicenseOut, LicenseStatusUpdate
from ..utils.storage import delete_upload, save_upload

router = APIRouter(prefix="/licenses", tags=["licenses"])


@router.post("/", response_model=LicenseOut, status_code=status.HTTP_201_CREATED)
async def upload_license(
    license_type: LicenseType = Form(...),
    license_number: str | None = Form(None),
    issuing_authority: str | None = Form(None),
    jurisdiction: str | None = Form(None),
    notes: str | None = Form(None),
    issued_at: str | None = Form(None),
    expires_at: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> License:
    try:
        relative_path, file_hash = save_upload(file.file, file.filename or "upload", current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    license_ = License(
        owner_id=current_user.id,
        license_type=license_type,
        license_number=license_number,
        issuing_authority=issuing_authority,
        jurisdiction=jurisdiction,
        file_path=relative_path,
        original_filename=file.filename,
        file_hash=file_hash,
        notes=notes,
        issued_at=datetime.fromisoformat(issued_at) if issued_at else None,
        expires_at=datetime.fromisoformat(expires_at) if expires_at else None,
    )
    db.add(license_)
    db.commit()
    db.refresh(license_)
    return license_


@router.get("/", response_model=list[LicenseOut])
def list_licenses(
    owner_id: str | None = None,
    license_type: LicenseType | None = None,
    status: LicenseStatus | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[License]:
    q = db.query(License)
    # non-owners can only see their own licenses unless explicitly filtering by another owner
    target_owner = owner_id or current_user.id
    q = q.filter(License.owner_id == target_owner)
    if license_type:
        q = q.filter(License.license_type == license_type)
    if status:
        q = q.filter(License.status == status)
    return q.order_by(License.created_at.desc()).all()


@router.get("/{license_id}", response_model=LicenseOut)
def get_license(
    license_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> License:
    license_ = db.get(License, license_id)
    if not license_:
        raise HTTPException(status_code=404, detail="License not found")
    return license_


@router.patch("/{license_id}/status", response_model=LicenseOut)
def update_license_status(
    license_id: str,
    body: LicenseStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> License:
    license_ = db.get(License, license_id)
    if not license_:
        raise HTTPException(status_code=404, detail="License not found")
    license_.status = body.status
    db.commit()
    db.refresh(license_)
    return license_


@router.delete("/{license_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_license(
    license_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    license_ = db.get(License, license_id)
    if not license_:
        raise HTTPException(status_code=404, detail="License not found")
    if license_.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot delete another party's license")
    if license_.file_path:
        delete_upload(license_.file_path)
    db.delete(license_)
    db.commit()
