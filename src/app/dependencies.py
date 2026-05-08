"""
Auth dependencies using pure-Python HMAC tokens (no cryptography C-extension needed).
Token format: base64url(json_payload) + "." + base64url(hmac_sha256_signature)
"""
import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .schemas import TokenData

SECRET_KEY = b"change-me-in-production"   # override via env var in prod
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8      # 8 hours

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padded = s + "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(padded)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    payload["exp"] = expire.timestamp()
    encoded = _b64url_encode(json.dumps(payload).encode())
    sig = hmac.new(SECRET_KEY, encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{sig}"


def _decode_token(token: str) -> dict:
    try:
        encoded, sig = token.rsplit(".", 1)
    except ValueError:
        raise ValueError("Malformed token")
    expected = hmac.new(SECRET_KEY, encoded.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise ValueError("Invalid signature")
    payload = json.loads(_b64url_decode(encoded))
    if payload.get("exp", 0) < datetime.now(timezone.utc).timestamp():
        raise ValueError("Token expired")
    return payload


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = _decode_token(token)
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exc
        token_data = TokenData(user_id=user_id)
    except (ValueError, KeyError):
        raise credentials_exc

    user = db.get(User, token_data.user_id)
    if user is None or not user.is_active:
        raise credentials_exc
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
