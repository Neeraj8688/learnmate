import re

from ..db import Database

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email)) and len(email) <= 254


def get_by_email(db: Database, email: str) -> dict | None:
    rows = db.query("SELECT * FROM users WHERE email=?", (email,))
    return rows[0] if rows else None


def get_by_id(db: Database, user_id: int) -> dict | None:
    rows = db.query("SELECT * FROM users WHERE id=?", (user_id,))
    return rows[0] if rows else None


def create_user(db: Database, email: str, password_hash: str) -> int:
    return db.execute("INSERT INTO users (email, password_hash) VALUES (?,?)", (email, password_hash))
