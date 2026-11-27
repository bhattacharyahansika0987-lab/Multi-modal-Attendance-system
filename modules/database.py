from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DB_PATH = Path("data/classroom.db")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def _ensure_column(cur: sqlite3.Cursor, table: str, column: str, definition: str) -> None:
    cur.execute(f"PRAGMA table_info({table})")
    existing = {row[1] for row in cur.fetchall()}
    if column not in existing:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _iso_duration_sec(left_at: str, returned_at: str | None) -> float | None:
    if not left_at or not returned_at:
        return None
    try:
        t0 = datetime.fromisoformat(left_at.replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(returned_at.replace("Z", "+00:00"))
        return round(max(0.0, (t1 - t0).total_seconds()), 1)
    except ValueError:
        return None


def init_db() -> None:
    """Creates and safely migrates all local SQLite tables with zero pre-filled demo data."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            embedding TEXT,
            biometric_enrolled INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    _ensure_column(cur, "students", "biometric_enrolled", "INTEGER NOT NULL DEFAULT 0")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS student_embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            embedding TEXT NOT NULL,
            det_score REAL,
            face_size_px REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS session_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            snapshot_index INTEGER NOT NULL,
            captured_at TEXT NOT NULL,
            total_faces INTEGER NOT NULL,
            is_demo INTEGER NOT NULL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS snapshot_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            snapshot_index INTEGER NOT NULL,
            student_id TEXT,
            student_name TEXT,
            state TEXT NOT NULL,
            similarity REAL NOT NULL,
            second_student_id TEXT,
            second_similarity REAL NOT NULL,
            margin REAL NOT NULL,
            det_score REAL NOT NULL,
            face_size_px REAL NOT NULL,
            reason TEXT NOT NULL,
            is_demo INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    # Phase 2: Real head-pose attention telemetry (audio explicitly marked Not measured)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attention_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            snapshot_index INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            faces_evaluated INTEGER NOT NULL,
            faces_facing_front INTEGER NOT NULL,
            facing_front_ratio REAL,
            head_alignment_score REAL,
            mean_abs_yaw_deg REAL,
            mean_abs_pitch_deg REAL,
            audio_measured INTEGER NOT NULL DEFAULT 0,
            audio_status TEXT NOT NULL DEFAULT 'Not measured',
            combined_attention_score REAL,
            active_weights TEXT NOT NULL DEFAULT '{}',
            is_demo INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Phase 2: Real bidirectional student window-focus events (never auto-marks Absent)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS focus_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_uid TEXT UNIQUE NOT NULL,
            session_id TEXT NOT NULL,
            lobby_code TEXT NOT NULL,
            student_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            event_type TEXT NOT NULL,
            status TEXT NOT NULL,
            left_at TEXT NOT NULL,
            returned_at TEXT,
            duration_sec REAL,
            is_demo INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS review_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            snapshot_index INTEGER NOT NULL,
            student_id TEXT,
            student_name TEXT,
            candidate_student_id TEXT,
            candidate_student_name TEXT,
            flag_state TEXT NOT NULL,
            detail TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            resolved_state TEXT DEFAULT '',
            override_reason TEXT DEFAULT '',
            resolved_by TEXT DEFAULT '',
            is_demo INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            resolved_at TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            student_id TEXT NOT NULL,
            name TEXT NOT NULL,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            presence_ratio REAL NOT NULL,
            status TEXT NOT NULL,
            observed_snapshots INTEGER NOT NULL DEFAULT 0,
            total_snapshots INTEGER NOT NULL DEFAULT 0,
            override_reason TEXT DEFAULT '',
            is_demo INTEGER NOT NULL DEFAULT 0
        )
    """)
    _ensure_column(cur, "attendance", "observed_snapshots", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(cur, "attendance", "total_snapshots", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(cur, "attendance", "override_reason", "TEXT DEFAULT ''")
    _ensure_column(cur, "attendance", "is_demo", "INTEGER NOT NULL DEFAULT 0")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS engagement_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            gaze_score REAL NOT NULL,
            movement_score REAL NOT NULL,
            audio_score REAL NOT NULL,
            total_engagement REAL NOT NULL,
            is_demo INTEGER NOT NULL DEFAULT 0
        )
    """)
    _ensure_column(cur, "engagement_logs", "is_demo", "INTEGER NOT NULL DEFAULT 0")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS agent_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            engagement_level REAL NOT NULL,
            suggestion TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS proctor_incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            student_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            event_type TEXT NOT NULL,
            duration_sec REAL NOT NULL,
            strike_count INTEGER NOT NULL,
            max_strikes INTEGER NOT NULL,
            action_taken TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS session_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            lobby_code TEXT NOT NULL,
            subject_name TEXT NOT NULL,
            avg_engagement REAL NOT NULL,
            present_count INTEGER NOT NULL,
            total_count INTEGER NOT NULL,
            proctor_violations INTEGER NOT NULL,
            pdf_b64 TEXT NOT NULL,
            is_demo INTEGER NOT NULL DEFAULT 0,
            generated_at TEXT NOT NULL
        )
    """)
    _ensure_column(cur, "session_reports", "is_demo", "INTEGER NOT NULL DEFAULT 0")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lobbies (
            lobby_code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            cohort TEXT NOT NULL,
            active_host TEXT NOT NULL,
            active_subject TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lobby_teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lobby_code TEXT NOT NULL,
            teacher_name TEXT NOT NULL,
            subject TEXT NOT NULL,
            is_live INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS lobby_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lobby_code TEXT NOT NULL,
            subject TEXT NOT NULL,
            teacher_name TEXT NOT NULL,
            title TEXT NOT NULL,
            due_date TEXT NOT NULL,
            submitted_count INTEGER DEFAULT 0,
            total_students INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Active'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS subject_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            subject_code TEXT NOT NULL,
            subject_name TEXT NOT NULL,
            theory_attended INTEGER NOT NULL,
            theory_total INTEGER NOT NULL,
            practical_attended INTEGER NOT NULL,
            practical_total INTEGER NOT NULL,
            UNIQUE(student_id, subject_code)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_date TEXT NOT NULL,
            student_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            subject_name TEXT NOT NULL,
            session_type TEXT NOT NULL,
            teacher_name TEXT NOT NULL,
            time_slot TEXT NOT NULL,
            status TEXT NOT NULL,
            proctor_strikes INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS dispute_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            daily_log_id INTEGER,
            student_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            subject_name TEXT NOT NULL,
            session_type TEXT NOT NULL,
            routed_to TEXT NOT NULL,
            recipient_name TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL,
            resolution_note TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_role TEXT NOT NULL,
            student_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            channels TEXT NOT NULL,
            acknowledged INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    # Migrate legacy single-embedding rows into student_embeddings if not yet copied
    cur.execute(
        """SELECT student_id, embedding, created_at FROM students
           WHERE embedding IS NOT NULL AND TRIM(embedding) != ''"""
    )
    for sid, emb_json, created_at in cur.fetchall():
        cur.execute("SELECT COUNT(*) FROM student_embeddings WHERE student_id = ?", (sid,))
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO student_embeddings (student_id, embedding, created_at) VALUES (?, ?, ?)",
                (sid, emb_json, created_at),
            )
            cur.execute("UPDATE students SET biometric_enrolled = 1 WHERE student_id = ?", (sid,))

    conn.commit()
    conn.close()


def clear_all_data() -> None:
    conn = get_connection()
    cur = conn.cursor()
    for tbl in (
        "student_embeddings",
        "students",
        "session_snapshots",
        "snapshot_observations",
        "attention_snapshots",
        "focus_events",
        "review_queue",
        "attendance",
        "engagement_logs",
        "agent_suggestions",
        "proctor_incidents",
        "session_reports",
        "lobbies",
        "lobby_teachers",
        "lobby_assignments",
        "subject_records",
        "daily_logs",
        "dispute_tickets",
        "notifications",
    ):
        cur.execute(f"DELETE FROM {tbl}")
    conn.commit()
    conn.close()


# --- Biometric & Roster Management ---
def save_student(
    student_id: str,
    name: str,
    embedding: np.ndarray | None = None,
    det_score: float | None = None,
    face_size_px: float | None = None,
) -> None:
    sid = student_id.strip()
    sname = name.strip()
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = get_connection()
    cur = conn.cursor()
    if embedding is None:
        cur.execute("SELECT biometric_enrolled, embedding FROM students WHERE student_id = ?", (sid,))
        existing = cur.fetchone()
        if existing:
            cur.execute("UPDATE students SET name = ? WHERE student_id = ?", (sname, sid))
        else:
            cur.execute(
                "INSERT INTO students (student_id, name, embedding, biometric_enrolled, created_at) VALUES (?, ?, NULL, 0, ?)",
                (sid, sname, now_ts),
            )
    else:
        arr = np.asarray(embedding, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(arr))
        if norm <= 1e-12:
            conn.close()
            raise ValueError("Cannot store zero-norm embedding.")
        arr = arr / norm
        emb_json = json.dumps(arr.tolist())
        cur.execute(
            """INSERT INTO students (student_id, name, embedding, biometric_enrolled, created_at)
               VALUES (?, ?, ?, 1, ?)
               ON CONFLICT(student_id) DO UPDATE SET
                   name = excluded.name,
                   embedding = excluded.embedding,
                   biometric_enrolled = 1""",
            (sid, sname, emb_json, now_ts),
        )
        cur.execute(
            "INSERT INTO student_embeddings (student_id, embedding, det_score, face_size_px, created_at) VALUES (?, ?, ?, ?, ?)",
            (sid, emb_json, det_score, face_size_px, now_ts),
        )
    conn.commit()
    conn.close()


def add_student_embedding(
    student_id: str,
    embedding: np.ndarray,
    det_score: float | None = None,
    face_size_px: float | None = None,
    max_embeddings: int = 5,
) -> int:
    sid = student_id.strip()
    arr = np.asarray(embedding, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(arr))
    if norm <= 1e-12:
        raise ValueError("Cannot store zero-norm embedding.")
    arr = arr / norm
    emb_json = json.dumps(arr.tolist())
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM students WHERE student_id = ?", (sid,))
    if not cur.fetchone():
        conn.close()
        raise KeyError(f"Student '{sid}' does not exist.")

    cur.execute("SELECT id FROM student_embeddings WHERE student_id = ? ORDER BY id ASC", (sid,))
    existing_ids = [row[0] for row in cur.fetchall()]
    while len(existing_ids) >= max_embeddings:
        oldest_id = existing_ids.pop(0)
        cur.execute("DELETE FROM student_embeddings WHERE id = ?", (oldest_id,))

    cur.execute(
        "INSERT INTO student_embeddings (student_id, embedding, det_score, face_size_px, created_at) VALUES (?, ?, ?, ?, ?)",
        (sid, emb_json, det_score, face_size_px, now_ts),
    )
    cur.execute(
        "UPDATE students SET embedding = ?, biometric_enrolled = 1 WHERE student_id = ?",
        (emb_json, sid),
    )
    cur.execute("SELECT COUNT(*) FROM student_embeddings WHERE student_id = ?", (sid,))
    total_cnt = int(cur.fetchone()[0])
    conn.commit()
    conn.close()
    return total_cnt


def delete_student(student_id: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM student_embeddings WHERE student_id = ?", (student_id,))
    cur.execute("DELETE FROM students WHERE student_id = ?", (student_id,))
    cur.execute("DELETE FROM subject_records WHERE student_id = ?", (student_id,))
    conn.commit()
    conn.close()


def load_all_students() -> list[dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.student_id, s.name, s.embedding, s.biometric_enrolled, s.created_at,
               COUNT(e.id) AS emb_count
        FROM students s
        LEFT JOIN student_embeddings e ON s.student_id = e.student_id
        GROUP BY s.student_id
        ORDER BY s.student_id ASC
    """)
    rows = cur.fetchall()
    conn.close()
    result: list[dict[str, Any]] = []
    for r in rows:
        emb = np.array(json.loads(r[2]), dtype=np.float32) if r[2] else None
        emb_count = int(r[5])
        enrolled = bool(r[3]) and emb_count > 0
        result.append(
            {
                "student_id": r[0],
                "name": r[1],
                "embedding": emb,
                "biometric_enrolled": enrolled,
                "embedding_count": emb_count,
                "created_at": r[4],
            }
        )
    return result


def load_roster_embeddings() -> tuple[list[dict[str, Any]], dict[str, list[np.ndarray]]]:
    roster_meta = load_all_students()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT student_id, embedding FROM student_embeddings ORDER BY id ASC")
    emb_map: dict[str, list[np.ndarray]] = {}
    for sid, emb_json in cur.fetchall():
        emb_map.setdefault(sid, []).append(np.array(json.loads(emb_json), dtype=np.float32))
    conn.close()
    return roster_meta, emb_map


# --- Phase 1 Snapshots, Observations & Review Queue ---
def log_snapshot(session_id: str, snapshot_index: int, total_faces: int, is_demo: bool = False) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO session_snapshots (session_id, snapshot_index, captured_at, total_faces, is_demo) VALUES (?, ?, ?, ?, ?)",
        (session_id, int(snapshot_index), datetime.now().strftime("%H:%M:%S"), int(total_faces), int(bool(is_demo))),
    )
    conn.commit()
    conn.close()


def log_snapshot_observation(
    session_id: str,
    snapshot_index: int,
    student_id: str | None,
    student_name: str | None,
    state: str,
    similarity: float,
    second_student_id: str | None,
    second_similarity: float,
    margin: float,
    det_score: float,
    face_size_px: float,
    reason: str,
    is_demo: bool = False,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO snapshot_observations
           (session_id, snapshot_index, student_id, student_name, state, similarity,
            second_student_id, second_similarity, margin, det_score, face_size_px, reason, is_demo, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            int(snapshot_index),
            student_id,
            student_name,
            state,
            round(float(similarity), 4),
            second_student_id,
            round(float(second_similarity), 4),
            round(float(margin), 4),
            round(float(det_score), 3),
            round(float(face_size_px), 1),
            reason,
            int(bool(is_demo)),
            datetime.now().strftime("%H:%M:%S"),
        ),
    )
    conn.commit()
    conn.close()


def get_snapshot_observations(session_id: str) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM snapshot_observations WHERE session_id = ? ORDER BY id DESC",
        conn,
        params=(session_id,),
    )
    conn.close()
    return df


# --- Phase 2: Real Head-Pose Attention & Bidirectional Focus Events ---
def log_attention_snapshot(
    session_id: str,
    snapshot_index: int,
    faces_evaluated: int,
    faces_facing_front: int,
    facing_front_ratio: float | None,
    head_alignment_score: float | None,
    mean_abs_yaw_deg: float | None,
    mean_abs_pitch_deg: float | None,
    combined_attention_score: float | None,
    active_weights: dict[str, float],
    audio_measured: bool = False,
    audio_status: str = "Not measured",
    is_demo: bool = False,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO attention_snapshots
           (session_id, snapshot_index, timestamp, faces_evaluated, faces_facing_front,
            facing_front_ratio, head_alignment_score, mean_abs_yaw_deg, mean_abs_pitch_deg,
            audio_measured, audio_status, combined_attention_score, active_weights, is_demo)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            int(snapshot_index),
            datetime.now().strftime("%H:%M:%S"),
            int(faces_evaluated),
            int(faces_facing_front),
            facing_front_ratio,
            head_alignment_score,
            mean_abs_yaw_deg,
            mean_abs_pitch_deg,
            int(bool(audio_measured)),
            audio_status,
            combined_attention_score,
            json.dumps(active_weights),
            int(bool(is_demo)),
        ),
    )
    conn.commit()
    conn.close()


def get_attention_snapshots(session_id: str) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM attention_snapshots WHERE session_id = ? ORDER BY id ASC",
        conn,
        params=(session_id,),
    )
    conn.close()
    return df


def record_focus_event(
    *,
    event_uid: str,
    session_id: str,
    lobby_code: str,
    student_id: str,
    student_name: str,
    event_type: str,
    status: str,
    left_at: str,
    returned_at: str | None = None,
    duration_sec: float | None = None,
    review_threshold: int = 1,
    is_demo: bool = False,
) -> dict[str, Any]:
    """
    Stores a real student browser focus event (deduplicated by event_uid).
    Computes duration_sec from real ISO timestamps whenever returned_at is set.
    NEVER auto-marks Absent: once a student reaches review_threshold exits,
    creates or updates a NEEDS REVIEW item for the instructor to decide.
    """
    computed_dur = _iso_duration_sec(left_at, returned_at)
    final_dur = computed_dur if computed_dur is not None else duration_sec
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO focus_events
           (event_uid, session_id, lobby_code, student_id, student_name, event_type,
            status, left_at, returned_at, duration_sec, is_demo, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(event_uid) DO UPDATE SET
               status = excluded.status,
               returned_at = COALESCE(excluded.returned_at, focus_events.returned_at),
               duration_sec = COALESCE(excluded.duration_sec, focus_events.duration_sec)""",
        (
            event_uid.strip(),
            session_id.strip(),
            lobby_code.strip().upper(),
            student_id.strip(),
            student_name.strip(),
            event_type.strip(),
            status.strip(),
            left_at.strip(),
            returned_at.strip() if returned_at else None,
            round(float(final_dur), 1) if final_dur is not None else None,
            int(bool(is_demo)),
            now_str,
        ),
    )

    cur.execute(
        "SELECT COUNT(*), COALESCE(SUM(duration_sec), 0.0) FROM focus_events WHERE session_id = ? AND student_id = ?",
        (session_id.strip(), student_id.strip()),
    )
    total_exits, total_away = cur.fetchone()
    total_exits = int(total_exits)
    total_away = round(float(total_away or 0.0), 1)

    review_queued = False
    if total_exits >= max(1, int(review_threshold)):
        detail = (
            f"Real browser focus monitor logged {total_exits} window exit(s) "
            f"(total measured away time: {total_away}s; latest: {event_type}). "
            f"Instructor decision required (never auto-marked Absent)."
        )
        cur.execute(
            """SELECT id FROM review_queue
               WHERE session_id = ? AND student_id = ? AND flag_state = 'NEEDS REVIEW'
                 AND status = 'PENDING' AND detail LIKE 'Real browser focus monitor%'""",
            (session_id.strip(), student_id.strip()),
        )
        existing_rq = cur.fetchone()
        if existing_rq:
            cur.execute("UPDATE review_queue SET detail = ? WHERE id = ?", (detail, existing_rq[0]))
        else:
            cur.execute(
                """INSERT INTO review_queue
                   (session_id, snapshot_index, student_id, student_name, flag_state,
                    detail, status, is_demo, created_at)
                   VALUES (?, 0, ?, ?, 'NEEDS REVIEW', ?, 'PENDING', ?, ?)""",
                (session_id.strip(), student_id.strip(), student_name.strip(), detail, int(bool(is_demo)), now_str),
            )
        review_queued = True

    conn.commit()
    conn.close()
    return {
        "event_uid": event_uid,
        "total_exits": total_exits,
        "total_away_sec": total_away,
        "duration_sec": final_dur,
        "review_queued": review_queued,
    }


def get_focus_events(
    session_id: str | None = None,
    lobby_code: str | None = None,
    student_id: str | None = None,
) -> pd.DataFrame:
    conn = get_connection()
    query = "SELECT * FROM focus_events WHERE 1=1"
    params: list[Any] = []
    if session_id:
        query += " AND session_id = ?"
        params.append(session_id)
    if lobby_code:
        query += " AND lobby_code = ?"
        params.append(lobby_code.strip().upper())
    if student_id:
        query += " AND student_id = ?"
        params.append(student_id.strip())
    query += " ORDER BY id DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def enqueue_review_item(
    session_id: str,
    snapshot_index: int,
    student_id: str | None,
    student_name: str | None,
    flag_state: str,
    detail: str,
    candidate_student_id: str | None = None,
    candidate_student_name: str | None = None,
    is_demo: bool = False,
) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO review_queue
           (session_id, snapshot_index, student_id, student_name, candidate_student_id,
            candidate_student_name, flag_state, detail, status, is_demo, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)""",
        (
            session_id,
            int(snapshot_index),
            student_id,
            student_name,
            candidate_student_id,
            candidate_student_name,
            flag_state,
            detail,
            int(bool(is_demo)),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    item_id = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return item_id


def get_review_queue(session_id: str | None = None, pending_only: bool = False) -> pd.DataFrame:
    conn = get_connection()
    query = "SELECT * FROM review_queue WHERE 1=1"
    params: list[Any] = []
    if session_id:
        query += " AND session_id = ?"
        params.append(session_id)
    if pending_only:
        query += " AND status = 'PENDING'"
    query += " ORDER BY id DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def resolve_review_item(
    item_id: int,
    resolved_state: str,
    override_reason: str,
    resolved_by: str = "Instructor",
) -> None:
    if not override_reason or not override_reason.strip():
        raise ValueError("An override reason is required to resolve a review item.")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """UPDATE review_queue
           SET status = 'RESOLVED',
               resolved_state = ?,
               override_reason = ?,
               resolved_by = ?,
               resolved_at = ?
           WHERE id = ?""",
        (
            resolved_state,
            override_reason.strip(),
            resolved_by.strip() or "Instructor",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            int(item_id),
        ),
    )
    conn.commit()
    conn.close()


# --- Session Attendance, Telemetry & Reports ---
def log_attendance(
    session_id: str,
    student_id: str,
    name: str,
    first_seen: str,
    last_seen: str,
    ratio: float,
    status: str,
    observed_snapshots: int = 0,
    total_snapshots: int = 0,
    override_reason: str = "",
    is_demo: bool = False,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO attendance
           (session_id, student_id, name, first_seen, last_seen, presence_ratio, status,
            observed_snapshots, total_snapshots, override_reason, is_demo)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            student_id,
            name,
            first_seen,
            last_seen,
            round(float(ratio), 1),
            status,
            int(observed_snapshots),
            int(total_snapshots),
            override_reason,
            int(bool(is_demo)),
        ),
    )
    conn.commit()
    conn.close()


def log_engagement(session_id: str, gaze: float, movement: float, audio: float, total: float, is_demo: bool = False) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO engagement_logs
           (session_id, timestamp, gaze_score, movement_score, audio_score, total_engagement, is_demo)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (session_id, datetime.now().strftime("%H:%M:%S"), round(gaze, 1), round(movement, 1), round(audio, 1), round(total, 1), int(bool(is_demo))),
    )
    conn.commit()
    conn.close()


def log_suggestion(session_id: str, engagement_level: float, suggestion: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO agent_suggestions (session_id, timestamp, engagement_level, suggestion) VALUES (?, ?, ?, ?)",
        (session_id, datetime.now().strftime("%H:%M:%S"), round(engagement_level, 1), suggestion),
    )
    conn.commit()
    conn.close()


def get_session_list() -> list[str]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT session_id FROM (
            SELECT session_id FROM engagement_logs
            UNION SELECT session_id FROM attendance
            UNION SELECT session_id FROM agent_suggestions
            UNION SELECT session_id FROM session_snapshots
            UNION SELECT session_id FROM attention_snapshots
            UNION SELECT session_id FROM focus_events
        ) ORDER BY session_id DESC
    """)
    sessions = [row[0] for row in cur.fetchall()]
    conn.close()
    return sessions


def get_session_data(session_id: str = "ALL") -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    conn = get_connection()
    if session_id == "ALL":
        df_att = pd.read_sql_query("SELECT * FROM attendance ORDER BY id DESC", conn)
        df_eng = pd.read_sql_query("SELECT * FROM engagement_logs ORDER BY id ASC", conn)
        df_sug = pd.read_sql_query("SELECT * FROM agent_suggestions ORDER BY id DESC", conn)
    else:
        df_att = pd.read_sql_query("SELECT * FROM attendance WHERE session_id = ? ORDER BY id DESC", conn, params=(session_id,))
        df_eng = pd.read_sql_query("SELECT * FROM engagement_logs WHERE session_id = ? ORDER BY id ASC", conn, params=(session_id,))
        df_sug = pd.read_sql_query("SELECT * FROM agent_suggestions WHERE session_id = ? ORDER BY id DESC", conn, params=(session_id,))
    conn.close()
    return df_att, df_eng, df_sug


def log_proctor_incident(
    session_id: str,
    student_id: str,
    student_name: str,
    event_type: str,
    duration_sec: float,
    strike_count: int,
    max_strikes: int,
    action_taken: str,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO proctor_incidents
           (session_id, student_id, student_name, event_type, duration_sec, strike_count, max_strikes, action_taken, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (session_id, student_id, student_name, event_type, round(duration_sec, 1), strike_count, max_strikes, action_taken, datetime.now().strftime("%H:%M:%S")),
    )
    conn.commit()
    conn.close()


def get_proctor_incidents(session_id: str = "ALL") -> pd.DataFrame:
    conn = get_connection()
    if session_id == "ALL":
        df = pd.read_sql_query("SELECT * FROM proctor_incidents ORDER BY id DESC", conn)
    else:
        df = pd.read_sql_query("SELECT * FROM proctor_incidents WHERE session_id = ? ORDER BY id DESC", conn, params=(session_id,))
    conn.close()
    return df


def save_session_report(
    session_id: str,
    lobby_code: str,
    subject_name: str,
    avg_engagement: float,
    present_count: int,
    total_count: int,
    proctor_violations: int,
    pdf_b64: str,
    is_demo: bool = False,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO session_reports
           (session_id, lobby_code, subject_name, avg_engagement, present_count, total_count,
            proctor_violations, pdf_b64, is_demo, generated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            lobby_code,
            subject_name,
            round(avg_engagement, 1),
            present_count,
            total_count,
            proctor_violations,
            pdf_b64,
            int(bool(is_demo)),
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ),
    )
    conn.commit()
    conn.close()


def get_session_reports() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM session_reports ORDER BY id DESC", conn)
    conn.close()
    return df


# --- Course Rooms ---
def get_lobbies() -> list[dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT lobby_code, name, cohort, active_host, active_subject, created_at FROM lobbies ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [
        {"lobby_code": r[0], "name": r[1], "cohort": r[2], "active_host": r[3], "active_subject": r[4], "created_at": r[5]}
        for r in rows
    ]


def create_lobby(lobby_code: str, name: str, cohort: str, host_teacher: str, subject: str) -> bool:
    code = lobby_code.strip().upper()
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO lobbies (lobby_code, name, cohort, active_host, active_subject, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (code, name.strip(), cohort.strip(), host_teacher.strip(), subject.strip(), datetime.now().strftime("%Y-%m-%d %H:%M")),
        )
        cur.execute(
            "INSERT INTO lobby_teachers (lobby_code, teacher_name, subject, is_live) VALUES (?, ?, ?, 1)",
            (code, host_teacher.strip(), subject.strip()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def join_lobby_teacher(lobby_code: str, teacher_name: str, subject: str) -> bool:
    code = lobby_code.strip().upper()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM lobbies WHERE lobby_code = ?", (code,))
    if not cur.fetchone():
        conn.close()
        return False
    cur.execute(
        "INSERT INTO lobby_teachers (lobby_code, teacher_name, subject, is_live) VALUES (?, ?, ?, 0)",
        (code, teacher_name.strip(), subject.strip()),
    )
    conn.commit()
    conn.close()
    return True


def get_lobby_teachers(lobby_code: str) -> list[dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, teacher_name, subject, is_live FROM lobby_teachers WHERE lobby_code = ? ORDER BY is_live DESC, id ASC", (lobby_code,))
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "teacher_name": r[1], "subject": r[2], "is_live": bool(r[3])} for r in rows]


def set_lobby_active_host(lobby_code: str, teacher_name: str, subject: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE lobby_teachers SET is_live = 0 WHERE lobby_code = ?", (lobby_code,))
    cur.execute("UPDATE lobby_teachers SET is_live = 1 WHERE lobby_code = ? AND teacher_name = ? AND subject = ?", (lobby_code, teacher_name, subject))
    cur.execute("UPDATE lobbies SET active_host = ?, active_subject = ? WHERE lobby_code = ?", (teacher_name, subject, lobby_code))
    conn.commit()
    conn.close()


def add_lobby_assignment(lobby_code: str, subject: str, teacher_name: str, title: str, due_date: str) -> None:
    roster_len = max(1, len(load_all_students()))
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO lobby_assignments
           (lobby_code, subject, teacher_name, title, due_date, submitted_count, total_students, status)
           VALUES (?, ?, ?, ?, ?, 0, ?, 'Active')""",
        (lobby_code, subject.strip(), teacher_name.strip(), title.strip(), due_date, roster_len),
    )
    conn.commit()
    conn.close()


def get_lobby_assignments(lobby_code: str) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM lobby_assignments WHERE lobby_code = ? ORDER BY id DESC", conn, params=(lobby_code,))
    conn.close()
    return df


# --- Theory vs Practical Attendance Calculator & Grades ---
def add_or_update_subject_record(
    student_id: str,
    student_name: str,
    subject_code: str,
    subject_name: str,
    theory_attended: int,
    theory_total: int,
    practical_attended: int,
    practical_total: int,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO subject_records
           (student_id, student_name, subject_code, subject_name, theory_attended, theory_total, practical_attended, practical_total)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(student_id, subject_code) DO UPDATE SET
               student_name = excluded.student_name,
               subject_name = excluded.subject_name,
               theory_attended = excluded.theory_attended,
               theory_total = excluded.theory_total,
               practical_attended = excluded.practical_attended,
               practical_total = excluded.practical_total""",
        (student_id.strip(), student_name.strip(), subject_code.strip().upper(), subject_name.strip(), int(theory_attended), int(theory_total), int(practical_attended), int(practical_total)),
    )
    conn.commit()
    conn.close()


def compute_internal_grade(pct: float, min_threshold: float = 75.0, slabs: dict[str, Any] | None = None) -> tuple[str, str]:
    s = slabs or {"a_plus": 90, "a": 85, "max_marks": 5}
    max_m = int(s.get("max_marks", 5))
    a_plus = float(s.get("a_plus", 90))
    a_grade = float(s.get("a", 85))
    if pct >= a_plus:
        return f"A+ ({max_m}/{max_m})", "On Track"
    if pct >= a_grade:
        return f"A ({max(1, max_m - 1)}/{max_m})", "On Track"
    if pct >= min_threshold:
        return f"B ({max(1, max_m - 2)}/{max_m})", "Watch"
    return f"Below Min (0/{max_m})", "Flagged"


def compute_recovery_classes(attended: int, total: int, target_pct: float = 75.0) -> tuple[str, int]:
    t = target_pct / 100.0
    if total <= 0:
        return "Safe", 0
    if (attended / total) >= t:
        buffer_cnt = int(math.floor((attended / t) - total)) if t > 0 else 0
        return "Safe", max(0, buffer_cnt)
    if t >= 1.0:
        return "Need", 99
    needed = math.ceil((t * total - attended) / (1.0 - t))
    return "Need", max(1, needed)


def get_student_subject_records(student_id: str) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM subject_records WHERE student_id = ? ORDER BY subject_code ASC", conn, params=(student_id,))
    conn.close()
    return df


def compute_student_cumulative_summary(min_threshold: float = 75.0, slabs: dict[str, Any] | None = None) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM subject_records", conn)
    conn.close()
    if df.empty:
        return pd.DataFrame()
    rows = []
    for (sid, sname), grp in df.groupby(["student_id", "student_name"]):
        th_att, th_tot = int(grp["theory_attended"].sum()), int(grp["theory_total"].sum())
        pr_att, pr_tot = int(grp["practical_attended"].sum()), int(grp["practical_total"].sum())
        th_pct = round((th_att / th_tot) * 100, 1) if th_tot else 0.0
        pr_pct = round((pr_att / pr_tot) * 100, 1) if pr_tot else 0.0
        cum_att, cum_tot = th_att + pr_att, th_tot + pr_tot
        cum_pct = round((cum_att / cum_tot) * 100, 1) if cum_tot else 0.0
        grade, risk = compute_internal_grade(cum_pct, min_threshold=min_threshold, slabs=slabs)
        rec_mode, rec_cnt = compute_recovery_classes(cum_att, cum_tot, target_pct=min_threshold)
        rows.append({
            "student_id": sid,
            "student_name": sname,
            "theory_pct": th_pct,
            "practical_pct": pr_pct,
            "cumulative_pct": cum_pct,
            "internal_grade": grade,
            "risk_tier": risk,
            "recovery": f"Attend +{rec_cnt}" if rec_mode == "Need" else f"{rec_cnt} class buffer",
        })
    return pd.DataFrame(rows).sort_values("cumulative_pct", ascending=True).reset_index(drop=True)


# --- Daily Logs, Disputes & Notifications ---
def add_daily_log(student_id: str, student_name: str, subject_name: str, session_type: str, teacher_name: str, time_slot: str, status: str, proctor_strikes: int = 0) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO daily_logs
           (log_date, student_id, student_name, subject_name, session_type, teacher_name, time_slot, status, proctor_strikes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (datetime.now().strftime("%Y-%m-%d"), student_id.strip(), student_name.strip(), subject_name.strip(), session_type, teacher_name.strip(), time_slot.strip(), status, int(proctor_strikes)),
    )
    conn.commit()
    conn.close()


def get_daily_logs(student_id: str | None = None) -> pd.DataFrame:
    conn = get_connection()
    if student_id:
        df = pd.read_sql_query("SELECT * FROM daily_logs WHERE student_id = ? ORDER BY id DESC", conn, params=(student_id,))
    else:
        df = pd.read_sql_query("SELECT * FROM daily_logs ORDER BY id DESC", conn)
    conn.close()
    return df


def create_dispute_ticket(daily_log_id: int | None, student_id: str, student_name: str, subject_name: str, session_type: str, routed_to: str, recipient_name: str, reason: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO dispute_tickets
           (daily_log_id, student_id, student_name, subject_name, session_type, routed_to, recipient_name, reason, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending Review', ?)""",
        (daily_log_id, student_id, student_name, subject_name, session_type, routed_to, recipient_name, reason.strip(), datetime.now().strftime("%Y-%m-%d %H:%M")),
    )
    conn.commit()
    conn.close()
    dispatch_notification("Instructor", student_id, student_name, "Correction Request", "Warning", f"Attendance Flag from {student_name} ({subject_name})", f"Routed to {routed_to} ({recipient_name}): {reason.strip()}", "Portal")


def get_dispute_tickets(student_id: str | None = None) -> pd.DataFrame:
    conn = get_connection()
    if student_id:
        df = pd.read_sql_query("SELECT * FROM dispute_tickets WHERE student_id = ? ORDER BY id DESC", conn, params=(student_id,))
    else:
        df = pd.read_sql_query("SELECT * FROM dispute_tickets ORDER BY id DESC", conn)
    conn.close()
    return df


def resolve_dispute_ticket(ticket_id: int, approve: bool, resolution_note: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT daily_log_id, student_id, student_name, subject_name, session_type FROM dispute_tickets WHERE id = ?", (ticket_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return
    daily_log_id, sid, sname, subj, stype = row
    new_status = "Approved & Updated" if approve else "Declined"
    cur.execute("UPDATE dispute_tickets SET status = ?, resolution_note = ? WHERE id = ?", (new_status, resolution_note, ticket_id))
    if approve:
        if daily_log_id:
            cur.execute("UPDATE daily_logs SET status = 'Present (Verified)' WHERE id = ?", (daily_log_id,))
        col = "practical_attended" if stype.lower() == "practical" else "theory_attended"
        tot = "practical_total" if stype.lower() == "practical" else "theory_total"
        cur.execute(f"UPDATE subject_records SET {col} = MIN({tot}, {col} + 1) WHERE student_id = ? AND subject_name = ?", (sid, subj))
    conn.commit()
    conn.close()
    dispatch_notification("Student", sid, sname, "Correction Update", "Info" if approve else "Warning", f"Attendance Flag {new_status} — {subj}", resolution_note or f"Marked {new_status}.", "Portal")


def dispatch_notification(recipient_role: str, student_id: str, student_name: str, category: str, severity: str, title: str, message: str, channels: str = "Portal") -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO notifications
           (recipient_role, student_id, student_name, category, severity, title, message, channels, acknowledged, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
        (recipient_role, student_id, student_name, category, severity, title, message, channels, datetime.now().strftime("%Y-%m-%d %H:%M")),
    )
    conn.commit()
    conn.close()


def dispatch_below_threshold_warnings(min_threshold: float = 75.0) -> int:
    summary = compute_student_cumulative_summary(min_threshold=min_threshold)
    if summary.empty:
        return 0
    conn = get_connection()
    cur = conn.cursor()
    dispatched = 0
    for _, row in summary[summary["cumulative_pct"] < min_threshold].iterrows():
        sid, sname, pct = row["student_id"], row["student_name"], row["cumulative_pct"]
        for role in ("Student", "Parent"):
            cur.execute("SELECT 1 FROM notifications WHERE recipient_role = ? AND student_id = ? AND category = 'Attendance Warning'", (role, sid))
            if not cur.fetchone():
                msg = f"{sname} ({sid}) is at {pct}% cumulative attendance, below {min_threshold:.0f}% (Theory: {row['theory_pct']}% | Practical: {row['practical_pct']}%). Recovery: {row['recovery']}."
                cur.execute(
                    """INSERT INTO notifications
                       (recipient_role, student_id, student_name, category, severity, title, message, channels, acknowledged, created_at)
                       VALUES (?, ?, ?, 'Attendance Warning', 'Critical', ?, ?, 'Portal', 0, ?)""",
                    (role, sid, sname, f"Below {min_threshold:.0f}% Attendance Warning — {sname} ({pct}%)", msg, datetime.now().strftime("%Y-%m-%d %H:%M")),
                )
                dispatched += 1
    conn.commit()
    conn.close()
    return dispatched


def get_notifications(recipient_role: str | None = None, student_id: str | None = None) -> pd.DataFrame:
    conn = get_connection()
    query = "SELECT * FROM notifications WHERE 1=1"
    params: list[Any] = []
    if recipient_role:
        query += " AND recipient_role = ?"
        params.append(recipient_role)
    if student_id:
        query += " AND student_id = ?"
        params.append(student_id)
    query += " ORDER BY id DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def acknowledge_notification(notif_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE notifications SET acknowledged = 1 WHERE id = ?", (notif_id,))
    conn.commit()
    conn.close()