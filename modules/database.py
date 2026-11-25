import sqlite3
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path("data/classroom.db")


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    """Creates the 4 core tables for 100% offline local storage."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            embedding TEXT NOT NULL,
            created_at TEXT NOT NULL
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
            status TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS engagement_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            gaze_score REAL NOT NULL,
            movement_score REAL NOT NULL,
            audio_score REAL NOT NULL,
            total_engagement REAL NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS agent_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            engagement_level REAL NOT NULL,
            suggestion TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def save_student(student_id: str, name: str, embedding: np.ndarray):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO students (student_id, name, embedding, created_at) VALUES (?, ?, ?, ?)",
        (student_id, name, json.dumps(embedding.tolist()), datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()


def delete_student(student_id: str):
    """Deletes an enrolled student embedding from local storage."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM students WHERE student_id = ?", (student_id,))
    conn.commit()
    conn.close()


def load_all_students():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT student_id, name, embedding, created_at FROM students ORDER BY student_id ASC")
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "student_id": r[0],
            "name": r[1],
            "embedding": np.array(json.loads(r[2]), dtype=np.float32),
            "created_at": r[3],
        }
        for r in rows
    ]


def seed_sample_roster() -> int:
    """Seeds 5 realistic students with deterministic L2-normalized 512-D embeddings."""
    init_db()
    sample_students = [
        ("S101", "Hansika Bhattacharya", 101),
        ("S102", "Aarav Sharma", 102),
        ("S103", "Meera Nair", 103),
        ("S104", "Rohan Verma", 104),
        ("S105", "Ananya Gupta", 105),
    ]
    existing_ids = {s["student_id"] for s in load_all_students()}
    added = 0
    for sid, name, seed_val in sample_students:
        if sid not in existing_ids:
            rng = np.random.default_rng(seed_val)
            vec = rng.standard_normal(512).astype(np.float32)
            vec = vec / np.linalg.norm(vec)
            save_student(sid, name, vec)
            added += 1
    return added


def log_attendance(session_id: str, student_id: str, name: str, first_seen: str, last_seen: str, ratio: float, status: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO attendance (session_id, student_id, name, first_seen, last_seen, presence_ratio, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (session_id, student_id, name, first_seen, last_seen, round(ratio, 2), status),
    )
    conn.commit()
    conn.close()


def log_engagement(session_id: str, gaze: float, movement: float, audio: float, total: float):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO engagement_logs (session_id, timestamp, gaze_score, movement_score, audio_score, total_engagement)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (session_id, datetime.now().strftime("%H:%M:%S"), round(gaze, 1), round(movement, 1), round(audio, 1), round(total, 1)),
    )
    conn.commit()
    conn.close()


def log_suggestion(session_id: str, engagement_level: float, suggestion: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO agent_suggestions (session_id, timestamp, engagement_level, suggestion)
           VALUES (?, ?, ?, ?)""",
        (session_id, datetime.now().strftime("%H:%M:%S"), round(engagement_level, 1), suggestion),
    )
    conn.commit()
    conn.close()


def get_session_list():
    """Returns distinct session IDs ordered from newest to oldest."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT session_id FROM (
            SELECT session_id FROM engagement_logs
            UNION
            SELECT session_id FROM attendance
            UNION
            SELECT session_id FROM agent_suggestions
        ) ORDER BY session_id DESC
    """)
    sessions = [row[0] for row in cur.fetchall()]
    conn.close()
    return sessions


def get_session_data(session_id: str = "ALL"):
    """Fetches attendance, engagement, and AI suggestion DataFrames."""
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


def seed_demo_sessions():
    """Populates realistic historical demo records for cloud & evaluator previews."""
    init_db()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM engagement_logs")
    if cur.fetchone()[0] > 0:
        conn.close()
        return False

    demo_session = "DEMO_ECE301_LECTURE"
    base_time = datetime.now() - timedelta(minutes=35)

    sample_att = [
        (demo_session, "S101", "Hansika Bhattacharya", "10:00:12", "10:44:50", 96.4, "Present"),
        (demo_session, "S102", "Aarav Sharma", "10:01:05", "10:44:42", 91.2, "Present"),
        (demo_session, "S103", "Meera Nair", "10:00:30", "10:44:10", 84.5, "Present"),
        (demo_session, "S104", "Rohan Verma", "10:05:18", "10:22:14", 41.0, "Absent"),
        (demo_session, "S105", "Ananya Gupta", "10:00:08", "10:44:55", 98.1, "Present"),
    ]
    cur.executemany(
        """INSERT INTO attendance (session_id, student_id, name, first_seen, last_seen, presence_ratio, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        sample_att,
    )

    eng_curve = [
        (86.0, 84.0, 62.0),
        (84.0, 82.0, 58.0),
        (79.0, 80.0, 40.0),
        (68.0, 72.0, 22.0),
        (52.0, 58.0, 14.0),
        (46.0, 49.0, 10.0),
        (61.0, 66.0, 45.0),
        (82.0, 85.0, 74.0),
        (89.0, 88.0, 82.0),
        (85.0, 84.0, 68.0),
    ]
    for idx, (g, m, a) in enumerate(eng_curve):
        ts = (base_time + timedelta(minutes=idx * 3)).strftime("%H:%M:%S")
        tot = round(0.50 * g + 0.25 * m + 0.25 * a, 1)
        cur.execute(
            """INSERT INTO engagement_logs (session_id, timestamp, gaze_score, movement_score, audio_score, total_engagement)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (demo_session, ts, g, m, a, tot),
        )

    sample_sugs = [
        (
            demo_session,
            (base_time + timedelta(minutes=15)).strftime("%H:%M:%S"),
            40.8,
            "Attention and vocal interaction dropped sharply—pause the derivation for a 60-second concept check poll.\n"
            "Ask an open-ended question linking the current circuit model to a practical lab example.",
        ),
        (
            demo_session,
            (base_time + timedelta(minutes=24)).strftime("%H:%M:%S"),
            87.0,
            "High visual focus and active Q&A detected—allow 2 additional minutes for peer discussion before advancing.\n"
            "Summarize key student questions on the board to consolidate understanding.",
        ),
    ]
    cur.executemany(
        """INSERT INTO agent_suggestions (session_id, timestamp, engagement_level, suggestion)
           VALUES (?, ?, ?, ?)""",
        sample_sugs,
    )

    conn.commit()
    conn.close()
    return True