import sqlite3
import json
import numpy as np
from datetime import datetime
from pathlib import Path

DB_PATH = Path("data/classroom.db")


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    """Creates the 4 core tables for offline storage."""
    conn = get_connection()
    cur = conn.cursor()

    # 1. Enrolled students (stores 512-D facial vector, never raw photos)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            embedding TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # 2. Sustained-presence attendance logs (Scenario 1)
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

    # 3. Time-windowed multimodal engagement scores (Scenario 2)
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

    # 4. Offline AI teaching suggestions (Scenario 3)
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
        (student_id, name, json.dumps(embedding.tolist()), datetime.now().isoformat(timespec="seconds"))
    )
    conn.commit()
    conn.close()


def load_all_students():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT student_id, name, embedding FROM students")
    rows = cur.fetchall()
    conn.close()
    return [
        {"student_id": r[0], "name": r[1], "embedding": np.array(json.loads(r[2]), dtype=np.float32)}
        for r in rows
    ]


def log_attendance(session_id: str, student_id: str, name: str, first_seen: str, last_seen: str, ratio: float, status: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO attendance (session_id, student_id, name, first_seen, last_seen, presence_ratio, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (session_id, student_id, name, first_seen, last_seen, round(ratio, 2), status)
    )
    conn.commit()
    conn.close()


def log_engagement(session_id: str, gaze: float, movement: float, audio: float, total: float):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO engagement_logs (session_id, timestamp, gaze_score, movement_score, audio_score, total_engagement)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (session_id, datetime.now().strftime("%H:%M:%S"), round(gaze, 1), round(movement, 1), round(audio, 1), round(total, 1))
    )
    conn.commit()
    conn.close()


def log_suggestion(session_id: str, engagement_level: float, suggestion: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO agent_suggestions (session_id, timestamp, engagement_level, suggestion)
           VALUES (?, ?, ?, ?)""",
        (session_id, datetime.now().strftime("%H:%M:%S"), round(engagement_level, 1), suggestion)
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at data/classroom.db!")