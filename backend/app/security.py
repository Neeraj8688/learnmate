import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except (ValueError, TypeError):
        return False


def make_token(secret: str, user_id: int, days: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=days)
    return jwt.encode({"sub": str(user_id), "exp": exp}, secret, algorithm="HS256")


def decode_token(secret: str, token: str) -> int | None:
    try:
        return int(jwt.decode(token, secret, algorithms=["HS256"])["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def load_or_create_secret(configured: str, path: Path, maker) -> str:
    """Use the env-provided secret, else a generated one persisted in the data volume."""
    if configured:
        return configured
    if path.exists():
        return path.read_text().strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    value = maker()
    path.write_text(value)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return value


def new_jwt_secret() -> str:
    return secrets.token_urlsafe(48)
