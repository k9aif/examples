"""
Account auth -- registration, login, session tokens, for both the user
and admin portals. Pure stdlib (hashlib.pbkdf2_hmac + secrets) -- no new
dependency, no LLM/agent/SDK imports, same purity constraint as the
rest of petstore/services/.

Real password hashing (PBKDF2-HMAC-SHA256, 390000 iterations, random
per-user salt) since the user explicitly asked for real accounts, not
a lightweight session-only stand-in.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from petstore.services.db import get_cursor

_PBKDF2_ITERATIONS = 390_000
_SESSION_TTL = timedelta(hours=24)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    return secrets.compare_digest(dk.hex(), hash_hex)


# ── Users ──────────────────────────────────────────────────────────────────

def register_user(email: str, password: str, name: str) -> str:
    with get_cursor() as cur:
        cur.execute("SELECT 1 FROM users WHERE email = %s", (email,))
        if cur.fetchone() is not None:
            raise ValueError(f"An account with email {email} already exists")

    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO users (email, password_hash, name) VALUES (%s, %s, %s) RETURNING user_id",
            (email, hash_password(password), name),
        )
        return str(cur.fetchone()[0])


def login_user(email: str, password: str) -> Optional[str]:
    with get_cursor() as cur:
        cur.execute("SELECT user_id, password_hash FROM users WHERE email = %s", (email,))
        row = cur.fetchone()
    if row is None or not verify_password(password, row[1]):
        return None
    return _create_session("user", str(row[0]))


def get_user(user_id: str) -> Optional[dict]:
    with get_cursor() as cur:
        cur.execute("SELECT user_id, email, name, created_at FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
    if row is None:
        return None
    return {"user_id": str(row[0]), "email": row[1], "name": row[2], "created_at": row[3]}


# ── Admin ──────────────────────────────────────────────────────────────────

def register_admin(username: str, password: str) -> str:
    """Not exposed via any public form -- see demo/seed_admin.py. Admin
    accounts are provisioned out-of-band, never via self-registration."""
    with get_cursor() as cur:
        cur.execute("SELECT 1 FROM admin WHERE username = %s", (username,))
        if cur.fetchone() is not None:
            raise ValueError(f"An admin account with username {username} already exists")

    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO admin (username, password_hash) VALUES (%s, %s) RETURNING admin_id",
            (username, hash_password(password)),
        )
        return str(cur.fetchone()[0])


def login_admin(username: str, password: str) -> Optional[str]:
    with get_cursor() as cur:
        cur.execute("SELECT admin_id, password_hash FROM admin WHERE username = %s", (username,))
        row = cur.fetchone()
    if row is None or not verify_password(password, row[1]):
        return None
    return _create_session("admin", str(row[0]))


# ── Sessions ─────────────────────────────────────────────────────────────

def _create_session(principal_type: str, principal_id: str) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + _SESSION_TTL
    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO sessions (session_token, principal_type, principal_id, expires_at) "
            "VALUES (%s, %s, %s, %s)",
            (token, principal_type, principal_id, expires_at),
        )
    return token


def get_session(token: str) -> Optional[Tuple[str, str]]:
    """Returns (principal_type, principal_id) if the session is valid and unexpired, else None."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT principal_type, principal_id, expires_at FROM sessions WHERE session_token = %s",
            (token,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    if row[2] < datetime.now(timezone.utc):
        logout(token)
        return None
    return row[0], str(row[1])


def logout(token: str) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM sessions WHERE session_token = %s", (token,))
