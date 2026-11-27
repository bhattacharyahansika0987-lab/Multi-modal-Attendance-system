

import base64
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import streamlit as st

try:
    import bcrypt as _bcrypt
except ImportError:  # pragma: no cover
    _bcrypt = None

try:
    from cryptography.fernet import Fernet as _Fernet, InvalidToken as _InvalidToken
except ImportError:  # pragma: no cover
    _Fernet = None
    _InvalidToken = Exception

DEFAULT_ORG_ID = "default_org"
CURRENT_POLICY_VERSION = "1.0-biometric-v1"
SANDBOX_DIR = Path("data/sandboxes")


def get_secret_or_env(key: str, default: str = "") -> str:
    try:
        if key in st.secrets and st.secrets[key]:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.environ.get(key, default)


def resolve_database_url() -> str:
    """Returns DATABASE_URL from st.secrets/env (Postgres/Supabase) or local SQLite fallback."""
    url = get_secret_or_env("DATABASE_URL", "").strip()
    if url:
        return url
    db_path = Path("data/classroom.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path.resolve().as_posix()}"


def _sandbox_db_path(session_token: str) -> Path:
    safe = "".join(ch for ch in session_token if ch.isalnum())[:24] or "guest"
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    return SANDBOX_DIR / f"sandbox_{safe}.db"


def get_scoped_sqlite_connection(
    default_db_path: Path,
    *,
    authenticated: bool = False,
    session_token: str = "guest",
) -> sqlite3.Connection:
    """
    Returns an isolated per-session sandbox SQLite DB for unauthenticated visitors,
    or the shared DB for authenticated users.
    """
    if not authenticated:
        target = _sandbox_db_path(session_token)
        is_new = not target.exists()
        conn = sqlite3.connect(target, check_same_thread=False)
        if is_new:
            _init_sandbox_schema(conn)
        return conn

    default_db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(default_db_path, check_same_thread=False)


def _init_sandbox_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY, name TEXT NOT NULL, embedding TEXT,
            biometric_enrolled INTEGER NOT NULL DEFAULT 0, org_id TEXT NOT NULL DEFAULT 'sandbox',
            consent_given INTEGER NOT NULL DEFAULT 0, consent_version TEXT DEFAULT '',
            consent_at TEXT DEFAULT '', created_at TEXT NOT NULL
        )"""
    )
    cur.execute(
        """INSERT OR IGNORE INTO students
           (student_id, name, embedding, biometric_enrolled, org_id, created_at)
           VALUES ('DEMO-S1', 'Sandbox Student One (Fake)', NULL, 0, 'sandbox', ?)""",
        (datetime.now().strftime("%Y-%m-%d %H:%M"),),
    )
    conn.commit()


# --- Fernet Embedding Encryption at Rest ---
def _get_fernet() -> Any | None:
    if _Fernet is None:
        return None
    raw_key = get_secret_or_env("EMBEDDING_ENCRYPTION_KEY", "").strip()
    if not raw_key:
        return None
    try:
        key_bytes = raw_key.encode("utf-8") if len(raw_key) == 44 else base64.urlsafe_b64encode(hashlib.sha256(raw_key.encode("utf-8")).digest())
        return _Fernet(key_bytes)
    except Exception:
        return None


def encrypt_embedding_payload(emb: np.ndarray) -> str:
    arr = np.asarray(emb, dtype=np.float32).reshape(-1)
    raw_json = json.dumps(arr.tolist())
    fernet = _get_fernet()
    if fernet is None:
        return raw_json
    token = fernet.encrypt(raw_json.encode("utf-8")).decode("utf-8")
    return f"FERNET::{token}"


def decrypt_embedding_payload(payload: str | None) -> np.ndarray | None:
    if not payload or not str(payload).strip():
        return None
    text = str(payload).strip()
    if text.startswith("FERNET::"):
        fernet = _get_fernet()
        if fernet is None:
            raise RuntimeError("Encrypted embedding found, but EMBEDDING_ENCRYPTION_KEY is not configured.")
        try:
            raw_json = fernet.decrypt(text[len("FERNET::") :].encode("utf-8")).decode("utf-8")
        except _InvalidToken as exc:
            raise ValueError("Failed to decrypt student embedding: invalid key or corrupted ciphertext.") from exc
    else:
        raw_json = text
    return np.array(json.loads(raw_json), dtype=np.float32)


# --- Passwords, Users, Roles & Row-Level Query Enforcement ---
def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password cannot be empty.")
    if _bcrypt is not None:
        return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return f"pbkdf2${salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    if password_hash.startswith("pbkdf2$"):
        _, salt, expected = password_hash.split("$", 2)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
        return actual == expected
    if _bcrypt is not None:
        try:
            return _bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except ValueError:
            return False
    return False


def init_auth_privacy_tables(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            org_id TEXT NOT NULL DEFAULT 'default_org',
            student_id TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS guardian_student_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guardian_username TEXT NOT NULL,
            student_id TEXT NOT NULL,
            org_id TEXT NOT NULL DEFAULT 'default_org',
            UNIQUE(guardian_username, student_id, org_id)
        )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL DEFAULT 'default_org',
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            target_table TEXT NOT NULL,
            target_id TEXT NOT NULL,
            before_json TEXT,
            after_json TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    for tbl in ("students", "attendance", "lobbies", "notifications", "review_queue"):
        cur.execute(f"PRAGMA table_info({tbl})")
        cols = {r[1] for r in cur.fetchall()}
        if "org_id" not in cols:
            cur.execute(f"ALTER TABLE {tbl} ADD COLUMN org_id TEXT NOT NULL DEFAULT 'default_org'")
    cur.execute("PRAGMA table_info(students)")
    scols = {r[1] for r in cur.fetchall()}
    for col, defn in [
        ("consent_given", "INTEGER NOT NULL DEFAULT 0"),
        ("consent_version", "TEXT DEFAULT ''"),
        ("consent_at", "TEXT DEFAULT ''"),
    ]:
        if col not in scols:
            cur.execute(f"ALTER TABLE students ADD COLUMN {col} {defn}")
    conn.commit()


def create_user(
    conn: sqlite3.Connection,
    username: str,
    password: str,
    role: str,
    *,
    org_id: str = DEFAULT_ORG_ID,
    student_id: str | None = None,
) -> bool:
    role_clean = role.strip().lower()
    if role_clean not in {"admin", "instructor", "student", "guardian"}:
        raise ValueError("Invalid role.")
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO users (username, password_hash, role, org_id, student_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (username.strip(), hash_password(password), role_clean, org_id, student_id, datetime.now().strftime("%Y-%m-%d %H:%M")),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def authenticate_user(conn: sqlite3.Connection, username: str, password: str) -> dict[str, Any] | None:
    cur = conn.cursor()
    cur.execute("SELECT id, username, password_hash, role, org_id, student_id FROM users WHERE username = ?", (username.strip(),))
    row = cur.fetchone()
    if not row or not verify_password(password, row[2]):
        return None
    return {"id": row[0], "username": row[1], "role": row[3], "org_id": row[4], "student_id": row[5]}


def link_guardian_to_student(conn: sqlite3.Connection, guardian_username: str, student_id: str, org_id: str = DEFAULT_ORG_ID) -> None:
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO guardian_student_links (guardian_username, student_id, org_id) VALUES (?, ?, ?)",
        (guardian_username.strip(), student_id.strip(), org_id),
    )
    conn.commit()


def list_accessible_students(conn: sqlite3.Connection, user: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Enforces role and org_id permissions in the database query layer."""
    if not user:
        return []
    role = user.get("role", "")
    org_id = user.get("org_id", DEFAULT_ORG_ID)
    cur = conn.cursor()
    if role in {"admin", "instructor"}:
        cur.execute(
            "SELECT student_id, name, biometric_enrolled, consent_given, consent_version, created_at FROM students WHERE org_id = ? ORDER BY student_id",
            (org_id,),
        )
        rows = cur.fetchall()
    elif role == "student" and user.get("student_id"):
        cur.execute(
            "SELECT student_id, name, biometric_enrolled, consent_given, consent_version, created_at FROM students WHERE org_id = ? AND student_id = ?",
            (org_id, user["student_id"]),
        )
        rows = cur.fetchall()
    elif role == "guardian":
        cur.execute(
            """SELECT s.student_id, s.name, s.biometric_enrolled, s.consent_given, s.consent_version, s.created_at
               FROM students s
               INNER JOIN guardian_student_links g
                 ON s.student_id = g.student_id AND s.org_id = g.org_id
               WHERE g.guardian_username = ? AND s.org_id = ?
               ORDER BY s.student_id""",
            (user["username"], org_id),
        )
        rows = cur.fetchall()
    else:
        rows = []
    return [
        {
            "student_id": r[0],
            "name": r[1],
            "biometric_enrolled": bool(r[2]),
            "consent_given": bool(r[3]),
            "consent_version": r[4] or "",
            "created_at": r[5],
        }
        for r in rows
    ]


# --- Consent, Audit Log, Delete-My-Data & Retention Purge ---
def record_biometric_consent(
    conn: sqlite3.Connection,
    student_id: str,
    *,
    consent_given: bool,
    policy_version: str = CURRENT_POLICY_VERSION,
    org_id: str = DEFAULT_ORG_ID,
    actor: str = "system",
) -> None:
    if not consent_given:
        raise ValueError("Explicit consent is required before biometric enrollment.")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.cursor()
    cur.execute(
        "SELECT consent_given, consent_version FROM students WHERE student_id = ? AND org_id = ?",
        (student_id, org_id),
    )
    before = cur.fetchone()
    cur.execute(
        "UPDATE students SET consent_given = 1, consent_version = ?, consent_at = ? WHERE student_id = ? AND org_id = ?",
        (policy_version, now_str, student_id, org_id),
    )
    log_audit_event(
        conn,
        org_id=org_id,
        actor=actor,
        action="RECORD_CONSENT",
        target_table="students",
        target_id=student_id,
        before_data={"consent_given": bool(before[0]), "consent_version": before[1]} if before else None,
        after_data={"consent_given": True, "consent_version": policy_version, "consent_at": now_str},
    )
    conn.commit()


def log_audit_event(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    actor: str,
    action: str,
    target_table: str,
    target_id: str,
    before_data: dict[str, Any] | None,
    after_data: dict[str, Any] | None,
) -> None:
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO audit_log
           (org_id, actor, action, target_table, target_id, before_json, after_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            org_id,
            actor,
            action,
            target_table,
            target_id,
            json.dumps(before_data) if before_data is not None else None,
            json.dumps(after_data) if after_data is not None else None,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()


def delete_student_my_data(
    conn: sqlite3.Connection,
    student_id: str,
    *,
    org_id: str = DEFAULT_ORG_ID,
    actor: str = "self_service",
) -> None:
    cur = conn.cursor()
    cur.execute("SELECT student_id, name, biometric_enrolled FROM students WHERE student_id = ? AND org_id = ?", (student_id, org_id))
    row = cur.fetchone()
    for tbl in ("student_embeddings", "attendance", "subject_records", "daily_logs", "dispute_tickets", "notifications", "guardian_student_links"):
        cur.execute(f"DELETE FROM {tbl} WHERE student_id = ?", (student_id,))
    cur.execute("DELETE FROM students WHERE student_id = ? AND org_id = ?", (student_id, org_id))
    log_audit_event(
        conn,
        org_id=org_id,
        actor=actor,
        action="DELETE_MY_DATA",
        target_table="students",
        target_id=student_id,
        before_data={"student_id": row[0], "name": row[1]} if row else None,
        after_data=None,
    )
    conn.commit()


def purge_expired_records(conn: sqlite3.Connection, retention_days: int = 90, org_id: str = DEFAULT_ORG_ID) -> int:
    cutoff = (datetime.now() - timedelta(days=max(1, int(retention_days)))).strftime("%Y-%m-%d")
    cur = conn.cursor()
    cur.execute("DELETE FROM daily_logs WHERE log_date < ?", (cutoff,))
    deleted = cur.rowcount
    log_audit_event(
        conn,
        org_id=org_id,
        actor="retention_job",
        action="PURGE_EXPIRED",
        target_table="daily_logs",
        target_id=f"before_{cutoff}",
        before_data={"retention_days": retention_days, "cutoff": cutoff},
        after_data={"deleted_rows": deleted},
    )
    conn.commit()
    return max(0, int(deleted))