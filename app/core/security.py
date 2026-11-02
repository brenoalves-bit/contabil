import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

_hasher = PasswordHash.recommended()  # argon2id


def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return _hasher.verify(raw, hashed)
    except Exception:  # noqa: BLE001 — hash inválido/corrompido conta como senha errada
        return False


def create_access_token(usuario_id: UUID, admin_escritorio: bool) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(usuario_id),
        "adm": admin_escritorio,
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(minutes=s.access_token_minutes),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    s = get_settings()
    payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("tipo de token inválido")
    return payload


def new_refresh_token() -> tuple[str, str]:
    """Retorna (token em claro para o cliente, hash sha256 para persistir)."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
