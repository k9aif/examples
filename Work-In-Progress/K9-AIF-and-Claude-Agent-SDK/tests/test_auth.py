"""Auth service -- registration, login, sessions. Runs against the live Postgres
database configured in .env (same pattern as test_deterministic_purity.py's
sibling data tests) since this isn't a pure in-memory concern like GateRegistry."""

from __future__ import annotations

import uuid

import pytest

from petstore.services import auth


def _unique_email() -> str:
    return f"test-{uuid.uuid4().hex[:8]}@example.com"


def _unique_username() -> str:
    return f"admin-test-{uuid.uuid4().hex[:8]}"


def test_register_and_login_user():
    email = _unique_email()
    user_id = auth.register_user(email, "correct-horse-battery-staple", "Test User")
    assert user_id

    token = auth.login_user(email, "correct-horse-battery-staple")
    assert token is not None

    principal = auth.get_session(token)
    assert principal == ("user", user_id)


def test_login_rejects_wrong_password():
    email = _unique_email()
    auth.register_user(email, "correct-password", "Test User")
    assert auth.login_user(email, "wrong-password") is None


def test_login_rejects_unknown_email():
    assert auth.login_user("nobody-here@example.com", "whatever") is None


def test_duplicate_registration_rejected():
    email = _unique_email()
    auth.register_user(email, "pw1", "First")
    with pytest.raises(ValueError):
        auth.register_user(email, "pw2", "Second")


def test_password_hash_never_stores_plaintext():
    hashed = auth.hash_password("hunter2")
    assert "hunter2" not in hashed
    assert hashed.startswith("pbkdf2_sha256$")


def test_logout_invalidates_session():
    email = _unique_email()
    auth.register_user(email, "pw", "Test User")
    token = auth.login_user(email, "pw")
    assert auth.get_session(token) is not None

    auth.logout(token)
    assert auth.get_session(token) is None


def test_admin_register_and_login():
    username = _unique_username()
    admin_id = auth.register_admin(username, "admin-password")
    token = auth.login_admin(username, "admin-password")
    assert token is not None
    assert auth.get_session(token) == ("admin", admin_id)


def test_user_and_admin_sessions_are_distinguishable():
    email = _unique_email()
    username = _unique_username()
    auth.register_user(email, "pw", "Test User")
    auth.register_admin(username, "pw")

    user_token = auth.login_user(email, "pw")
    admin_token = auth.login_admin(username, "pw")

    assert auth.get_session(user_token)[0] == "user"
    assert auth.get_session(admin_token)[0] == "admin"
