from __future__ import annotations

import hmac
import secrets
from datetime import UTC, datetime, timedelta
from functools import wraps

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from flask import Blueprint, current_app, g, jsonify, request, session

from .db import audit, get_db, new_id, now, row_dict

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")
hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _public_user(row) -> dict:
    user = row_dict(row)
    return {key: user[key] for key in ("id", "username", "full_name", "registration_number", "role")}


def init_auth(app) -> None:
    @app.before_request
    def load_user_and_enforce_session():
        g.user = None
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("Origin")
            expected_origin = current_app.config.get("PUBLIC_ORIGIN", "").rstrip("/")
            if origin and expected_origin and origin.rstrip("/") != expected_origin:
                return jsonify({"error": "invalid_origin"}), 403
        user_id = session.get("user_id")
        if not user_id:
            return None
        row = get_db().execute("SELECT * FROM users WHERE id=? AND active=1", (user_id,)).fetchone()
        if not row:
            session.clear()
            return None
        current = datetime.now(UTC)
        started = _parse(session.get("started_at"))
        last_seen = _parse(session.get("last_seen"))
        if (not started or current - started > timedelta(hours=8) or not last_seen
                or (current - last_seen).total_seconds() > current_app.config["SESSION_IDLE_SECONDS"]):
            session.clear()
            return jsonify({"error": "session_expired"}), 401
        session["last_seen"] = current.isoformat()
        g.user = row

        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.endpoint != "auth.login":
            supplied = request.headers.get("X-CSRF-Token", "")
            expected = session.get("csrf_token", "")
            if not expected or not hmac.compare_digest(supplied, expected):
                return jsonify({"error": "invalid_csrf_token"}), 403
        return None


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            return jsonify({"error": "authentication_required"}), 401
        return fn(*args, **kwargs)
    return wrapped


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user["role"] != "admin":
            return jsonify({"error": "admin_required"}), 403
        return fn(*args, **kwargs)
    return wrapped


@auth_bp.post("/login")
def login():
    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip().lower()
    password = str(body.get("password", ""))
    row = get_db().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    generic = {"error": "invalid_credentials"}
    if not row or not row["active"]:
        return jsonify(generic), 401

    current = datetime.now(UTC)
    locked_until = _parse(row["locked_until"])
    if locked_until and locked_until > current:
        return jsonify({"error": "account_locked", "retry_after": int((locked_until-current).total_seconds())}), 429

    try:
        valid = hasher.verify(row["password_hash"], password)
    except VerifyMismatchError:
        valid = False
    except Exception:
        valid = False
    if not valid:
        first = _parse(row["first_failed_at"])
        window = current_app.config["LOGIN_WINDOW_SECONDS"]
        attempts = row["failed_attempts"] + 1 if first and (current-first).total_seconds() <= window else 1
        first_value = first.isoformat() if attempts > 1 else current.isoformat()
        lock = None
        if attempts >= current_app.config["LOGIN_MAX_FAILURES"]:
            lock = (current + timedelta(seconds=current_app.config["LOGIN_LOCK_SECONDS"])).isoformat()
        get_db().execute(
            "UPDATE users SET failed_attempts=?,first_failed_at=?,locked_until=? WHERE id=?",
            (attempts, first_value, lock, row["id"]),
        )
        get_db().commit()
        audit("auth.login_failed", row["id"], metadata={"locked": bool(lock)})
        return jsonify(generic), 401

    if hasher.check_needs_rehash(row["password_hash"]):
        get_db().execute("UPDATE users SET password_hash=? WHERE id=?", (hasher.hash(password), row["id"]))
    get_db().execute(
        "UPDATE users SET failed_attempts=0,first_failed_at=NULL,locked_until=NULL WHERE id=?", (row["id"],)
    )
    get_db().commit()
    session.clear()
    session.permanent = True
    session["user_id"] = row["id"]
    session["started_at"] = current.isoformat()
    session["last_seen"] = current.isoformat()
    session["csrf_token"] = secrets.token_urlsafe(32)
    audit("auth.login", row["id"])
    return jsonify({"user": _public_user(row), "csrf_token": session["csrf_token"]})


@auth_bp.post("/logout")
@login_required
def logout():
    user_id = g.user["id"]
    audit("auth.logout", user_id)
    session.clear()
    return "", 204


@auth_bp.get("/session")
@login_required
def get_session():
    return jsonify({"user": _public_user(g.user), "csrf_token": session["csrf_token"]})


def validate_password(password: str) -> str | None:
    if len(password) < 14:
        return "Password must contain at least 14 characters."
    if password.lower() == password or password.upper() == password or not any(c.isdigit() for c in password):
        return "Password must include upper-case, lower-case, and numeric characters."
    return None


@auth_bp.post("/users")
@admin_required
def create_user():
    body = request.get_json(silent=True) or {}
    password = str(body.get("password", ""))
    error = validate_password(password)
    if error:
        return jsonify({"error": "invalid_password", "message": error}), 400
    username = str(body.get("username", "")).strip().lower()
    full_name = str(body.get("full_name", "")).strip()
    if not username or not full_name:
        return jsonify({"error": "username_and_full_name_required"}), 400
    user_id = new_id()
    try:
        get_db().execute(
            "INSERT INTO users(id,username,full_name,registration_number,password_hash,role,created_at) VALUES(?,?,?,?,?,?,?)",
            (user_id, username, full_name, str(body.get("registration_number", "")).strip(),
             hasher.hash(password), body.get("role", "clinician"), now()),
        )
        get_db().commit()
    except Exception:
        return jsonify({"error": "username_unavailable"}), 409
    audit("user.created", g.user["id"], target_id=user_id, metadata={"role": body.get("role", "clinician")})
    return jsonify({"id": user_id, "username": username, "full_name": full_name}), 201


def bootstrap_admin(username: str, password: str, full_name: str, registration_number: str = "") -> str:
    error = validate_password(password)
    if error:
        raise ValueError(error)
    db = get_db()
    if db.execute("SELECT 1 FROM users").fetchone():
        raise ValueError("A user already exists; create subsequent accounts through the admin API.")
    user_id = new_id()
    db.execute(
        "INSERT INTO users(id,username,full_name,registration_number,password_hash,role,created_at) VALUES(?,?,?,?,?,'admin',?)",
        (user_id, username.strip().lower(), full_name.strip(), registration_number.strip(), hasher.hash(password), now()),
    )
    db.commit()
    return user_id
