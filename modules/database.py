import sqlite3
import json
import math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path("data/classroom.db")


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    """Creates all original biometric/telemetry tables plus commercial AttendAI tables."""
    conn = get_connection()
    cur = conn.cursor()

    # --- Original Core Tables (Unchanged Schema) ---
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

    # --- Commercial Module Tables ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lobbies (
            lobby_code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            cohort TEXT NOT NULL,
            created_by TEXT NOT NULL,
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
            is_live INTEGER NOT NULL DEFAULT 0
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
            submitted_count INTEGER NOT NULL DEFAULT 0,
            total_students INTEGER NOT NULL DEFAULT 6,
            status TEXT NOT NULL DEFAULT 'Active'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS subject_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            subject_code TEXT NOT NULL,
            subject_name TEXT NOT NULL,
            teacher_name TEXT NOT NULL,
            theory_attended INTEGER NOT NULL,
            theory_total INTEGER NOT NULL,
            practical_attended INTEGER NOT NULL,
            practical_total INTEGER NOT NULL
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
            proctor_strikes INTEGER NOT NULL DEFAULT 0
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
            status TEXT NOT NULL DEFAULT 'Pending Review',
            faculty_remark TEXT DEFAULT '',
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
            acknowledged INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
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
            generated_at TEXT NOT NULL,
            avg_engagement REAL NOT NULL,
            present_count INTEGER NOT NULL,
            total_count INTEGER NOT NULL,
            proctor_violations INTEGER NOT NULL,
            pdf_b64 TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# --- Biometric Roster Functions ---
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
    init_db()
    sample_students = [
        ("S101", "Hansika Bhattacharya", 101),
        ("S102", "Aarav Sharma", 102),
        ("S103", "Meera Nair", 103),
        ("S104", "Rohan Verma", 104),
        ("S105", "Ananya Gupta", 105),
        ("S106", "Kabir Malhotra", 106),
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


# --- Core Logging Functions ---
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


# --- Proctoring & Auto-PDF Archive ---
def log_proctor_incident(
    session_id: str,
    student_id: str,
    student_name: str,
    event_type: str,
    duration_sec: float,
    strike_count: int,
    max_strikes: int,
    action_taken: str,
):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO proctor_incidents
           (session_id, student_id, student_name, event_type, duration_sec, strike_count, max_strikes, action_taken, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            student_id,
            student_name,
            event_type,
            round(duration_sec, 1),
            strike_count,
            max_strikes,
            action_taken,
            datetime.now().strftime("%H:%M:%S"),
        ),
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
):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO session_reports
           (session_id, lobby_code, subject_name, generated_at, avg_engagement, present_count, total_count, proctor_violations, pdf_b64)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            lobby_code,
            subject_name,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            round(avg_engagement, 1),
            present_count,
            total_count,
            proctor_violations,
            pdf_b64,
        ),
    )
    conn.commit()
    conn.close()


def get_session_reports() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM session_reports ORDER BY id DESC", conn)
    conn.close()
    return df


# --- Game-Style Multi-Teacher Lobbies ---
def get_lobbies() -> list[dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT lobby_code, name, cohort, created_by, active_host, active_subject, created_at FROM lobbies ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "lobby_code": r[0],
            "name": r[1],
            "cohort": r[2],
            "created_by": r[3],
            "active_host": r[4],
            "active_subject": r[5],
            "created_at": r[6],
        }
        for r in rows
    ]


def create_lobby(lobby_code: str, name: str, cohort: str, host_teacher: str, subject: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO lobbies (lobby_code, name, cohort, created_by, active_host, active_subject, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (lobby_code.upper(), name, cohort, host_teacher, host_teacher, subject, datetime.now().strftime("%Y-%m-%d %H:%M")),
        )
        cur.execute(
            "INSERT INTO lobby_teachers (lobby_code, teacher_name, subject, is_live) VALUES (?, ?, ?, 1)",
            (lobby_code.upper(), host_teacher, subject),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def join_lobby_teacher(lobby_code: str, teacher_name: str, subject: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT lobby_code FROM lobbies WHERE lobby_code = ?", (lobby_code.upper(),))
    if not cur.fetchone():
        conn.close()
        return False
    cur.execute(
        "INSERT INTO lobby_teachers (lobby_code, teacher_name, subject, is_live) VALUES (?, ?, ?, 0)",
        (lobby_code.upper(), teacher_name, subject),
    )
    conn.commit()
    conn.close()
    return True


def get_lobby_teachers(lobby_code: str) -> list[dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, teacher_name, subject, is_live FROM lobby_teachers WHERE lobby_code = ?", (lobby_code,))
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "teacher_name": r[1], "subject": r[2], "is_live": bool(r[3])} for r in rows]


def set_lobby_active_host(lobby_code: str, teacher_name: str, subject: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE lobby_teachers SET is_live = 0 WHERE lobby_code = ?", (lobby_code,))
    cur.execute(
        "UPDATE lobby_teachers SET is_live = 1 WHERE lobby_code = ? AND teacher_name = ? AND subject = ?",
        (lobby_code, teacher_name, subject),
    )
    cur.execute(
        "UPDATE lobbies SET active_host = ?, active_subject = ? WHERE lobby_code = ?",
        (teacher_name, subject, lobby_code),
    )
    conn.commit()
    conn.close()


def add_lobby_assignment(lobby_code: str, subject: str, teacher_name: str, title: str, due_date: str):
    conn = get_connection()
    cur = conn.cursor()
    total_stu = max(6, len(load_all_students()))
    cur.execute(
        """INSERT INTO lobby_assignments (lobby_code, subject, teacher_name, title, due_date, submitted_count, total_students, status)
           VALUES (?, ?, ?, ?, ?, 0, ?, 'Active')""",
        (lobby_code, subject, teacher_name, title, due_date, total_stu),
    )
    conn.commit()
    conn.close()


def get_lobby_assignments(lobby_code: str) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM lobby_assignments WHERE lobby_code = ? ORDER BY id DESC", conn, params=(lobby_code,))
    conn.close()
    return df


# --- Subject-Wise Calculator (Theory vs. Practical), Grade & Recovery ---
def compute_internal_grade(pct: float) -> tuple[str, str]:
    if pct >= 90.0:
        return "A+ (5/5 Marks)", "Optimal"
    if pct >= 85.0:
        return "A (4/5 Marks)", "Optimal"
    if pct >= 75.0:
        return "B (3/5 Marks)", "Watch"
    return "Detained (0/5 Marks)", "At-Risk"


def compute_recovery_classes(attended: int, total: int, target: float = 0.75) -> tuple[str, int]:
    """Calculates classes needed to hit 75% or safe buffer classes if already >= 75%."""
    if total == 0:
        return "On Track", 0
    if (attended / total) < target:
        needed = max(1, math.ceil((target * total - attended) / (1.0 - target)))
        return "Need", needed
    safe_skip = max(0, math.floor((attended / target) - total))
    return "Buffer", safe_skip


def get_student_subject_records(student_id: str | None = None) -> pd.DataFrame:
    conn = get_connection()
    if student_id:
        df = pd.read_sql_query("SELECT * FROM subject_records WHERE student_id = ? ORDER BY subject_code ASC", conn, params=(student_id,))
    else:
        df = pd.read_sql_query("SELECT * FROM subject_records ORDER BY student_id ASC, subject_code ASC", conn)
    conn.close()
    return df


def compute_student_cumulative_summary() -> pd.DataFrame:
    """Computes cumulative Theory %, Practical %, Overall %, Grade, and 75% risk for every student."""
    df = get_student_subject_records()
    if df.empty:
        return pd.DataFrame()

    rows = []
    for (sid, sname), grp in df.groupby(["student_id", "student_name"]):
        th_att = int(grp["theory_attended"].sum())
        th_tot = int(grp["theory_total"].sum())
        pr_att = int(grp["practical_attended"].sum())
        pr_tot = int(grp["practical_total"].sum())
        all_att = th_att + pr_att
        all_tot = th_tot + pr_tot

        th_pct = round((th_att / th_tot) * 100, 1) if th_tot else 0.0
        pr_pct = round((pr_att / pr_tot) * 100, 1) if pr_tot else 0.0
        cum_pct = round((all_att / all_tot) * 100, 1) if all_tot else 0.0
        grade, tier = compute_internal_grade(cum_pct)
        mode, count = compute_recovery_classes(all_att, all_tot)
        rec_str = f"Attend next {count}" if mode == "Need" else f"{count} safe skips"

        rows.append({
            "student_id": sid,
            "student_name": sname,
            "theory_attended": th_att,
            "theory_total": th_tot,
            "theory_pct": th_pct,
            "practical_attended": pr_att,
            "practical_total": pr_tot,
            "practical_pct": pr_pct,
            "cumulative_pct": cum_pct,
            "internal_grade": grade,
            "risk_tier": tier,
            "recovery": rec_str,
        })
    return pd.DataFrame(rows).sort_values("student_id")


# --- Daily Summary, Dispute Desk & Dual Notifications ---
def get_daily_logs(student_id: str | None = None) -> pd.DataFrame:
    conn = get_connection()
    if student_id:
        df = pd.read_sql_query("SELECT * FROM daily_logs WHERE student_id = ? ORDER BY id ASC", conn, params=(student_id,))
    else:
        df = pd.read_sql_query("SELECT * FROM daily_logs ORDER BY id ASC", conn)
    conn.close()
    return df


def create_dispute_ticket(
    daily_log_id: int | None,
    student_id: str,
    student_name: str,
    subject_name: str,
    session_type: str,
    routed_to: str,
    recipient_name: str,
    reason: str,
):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO dispute_tickets
           (daily_log_id, student_id, student_name, subject_name, session_type, routed_to, recipient_name, reason, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending Review', ?)""",
        (
            daily_log_id,
            student_id,
            student_name,
            subject_name,
            session_type,
            routed_to,
            recipient_name,
            reason,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ),
    )
    conn.commit()
    conn.close()

    dispatch_notification(
        recipient_role="Instructor",
        student_id=student_id,
        student_name=student_name,
        category="Attendance Dispute",
        severity="Warning",
        title=f"Correction Flag from {student_name} ({subject_name})",
        message=f"Routed to {routed_to} ({recipient_name}) for {session_type}: {reason}",
        channels="Instructor Desk",
    )


def get_dispute_tickets(student_id: str | None = None) -> pd.DataFrame:
    conn = get_connection()
    if student_id:
        df = pd.read_sql_query("SELECT * FROM dispute_tickets WHERE student_id = ? ORDER BY id DESC", conn, params=(student_id,))
    else:
        df = pd.read_sql_query("SELECT * FROM dispute_tickets ORDER BY id DESC", conn)
    conn.close()
    return df


def resolve_dispute_ticket(ticket_id: int, approve: bool, remark: str):
    """Approves/rejects a student flag and dynamically recalculates Theory/Practical attendance."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT daily_log_id, student_id, student_name, subject_name, session_type FROM dispute_tickets WHERE id = ?",
        (ticket_id,),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return

    daily_log_id, sid, sname, subj, stype = row
    new_status = "Approved & Recalculated" if approve else "Rejected"

    cur.execute(
        "UPDATE dispute_tickets SET status = ?, faculty_remark = ? WHERE id = ?",
        (new_status, remark or ("Verified and updated." if approve else "Evidence insufficient."), ticket_id),
    )

    if approve:
        if daily_log_id:
            cur.execute("UPDATE daily_logs SET status = 'Present (Corrected)', proctor_strikes = 0 WHERE id = ?", (daily_log_id,))
        if stype == "Theory":
            cur.execute(
                """UPDATE subject_records
                   SET theory_attended = MIN(theory_total, theory_attended + 1)
                   WHERE student_id = ? AND subject_name = ?""",
                (sid, subj),
            )
        else:
            cur.execute(
                """UPDATE subject_records
                   SET practical_attended = MIN(practical_total, practical_attended + 1)
                   WHERE student_id = ? AND subject_name = ?""",
                (sid, subj),
            )

    conn.commit()
    conn.close()

    # Notify both Student and Parent of resolution
    msg = (
        f"Your attendance flag for {subj} ({stype}) was {new_status}. Remark: {remark or 'Updated in ledger.'}"
    )
    for role in ("Student", "Parent"):
        dispatch_notification(
            recipient_role=role,
            student_id=sid,
            student_name=sname,
            category="Dispute Resolved",
            severity="Info" if approve else "Warning",
            title=f"Attendance Flag {new_status} — {subj}",
            message=msg,
            channels="Portal • Email",
        )


def dispatch_notification(
    recipient_role: str,
    student_id: str,
    student_name: str,
    category: str,
    severity: str,
    title: str,
    message: str,
    channels: str = "Portal • Email • SMS",
):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO notifications
           (recipient_role, student_id, student_name, category, severity, title, message, channels, acknowledged, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
        (
            recipient_role,
            student_id,
            student_name,
            category,
            severity,
            title,
            message,
            channels,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ),
    )
    conn.commit()
    conn.close()


def dispatch_below_75_warnings() -> int:
    """Checks all students and dispatches <75% alerts to both Student and Parent if not already sent."""
    summary = compute_student_cumulative_summary()
    if summary.empty:
        return 0

    conn = get_connection()
    cur = conn.cursor()
    sent_count = 0

    for _, row in summary[summary["cumulative_pct"] < 75.0].iterrows():
        sid = row["student_id"]
        sname = row["student_name"]
        pct = row["cumulative_pct"]
        for role in ("Student", "Parent"):
            cur.execute(
                "SELECT COUNT(*) FROM notifications WHERE recipient_role = ? AND student_id = ? AND category = 'Below 75% Warning'",
                (role, sid),
            )
            if cur.fetchone()[0] == 0:
                msg = (
                    f"Cumulative attendance for {sname} ({sid}) has dropped to {pct}% "
                    f"(Theory: {row['theory_pct']}%, Practical: {row['practical_pct']}%). "
                    f"Action Required: {row['recovery']} consecutive classes to avoid detention."
                )
                cur.execute(
                    """INSERT INTO notifications
                       (recipient_role, student_id, student_name, category, severity, title, message, channels, acknowledged, created_at)
                       VALUES (?, ?, ?, 'Below 75% Warning', 'Critical', ?, ?, 'Portal • Email • SMS', 0, ?)""",
                    (
                        role,
                        sid,
                        sname,
                        f"Attendance Shortage Warning (<75%): {sname} at {pct}%",
                        msg,
                        datetime.now().strftime("%Y-%m-%d %H:%M"),
                    ),
                )
                sent_count += 1

    conn.commit()
    conn.close()
    return sent_count


def get_notifications(recipient_role: str | None = None, student_id: str | None = None) -> pd.DataFrame:
    conn = get_connection()
    query = "SELECT * FROM notifications WHERE 1=1"
    params: list = []
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


def acknowledge_notification(notif_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE notifications SET acknowledged = 1 WHERE id = ?", (notif_id,))
    conn.commit()
    conn.close()


# --- Unified Commercial Demo Seeder ---
def seed_commercial_demo_data():
    """Seeds realistic lobbies, subjects (Theory/Practical), daily logs, disputes, and telemetry on fresh DB."""
    init_db()
    seed_sample_roster()
    conn = get_connection()
    cur = conn.cursor()

    # 1. Seed Lobbies & Multi-Subject Teachers
    cur.execute("SELECT COUNT(*) FROM lobbies")
    if cur.fetchone()[0] == 0:
        now_s = datetime.now().strftime("%Y-%m-%d %H:%M")
        cur.executemany(
            """INSERT INTO lobbies (lobby_code, name, cohort, created_by, active_host, active_subject, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                ("LOBBY-ECE301", "ECE Semester V Core Cohort", "B.Tech ECE • Sec A", "Dr. Vikram Deshmukh", "Dr. Vikram Deshmukh", "Digital Signal Processing", now_s),
                ("LOBBY-CS402", "AI & Embedded Systems Track", "B.Tech Hon. • Batch 2", "Prof. Neha Kulkarni", "Prof. Neha Kulkarni", "Embedded Systems & IoT", now_s),
            ],
        )
        cur.executemany(
            "INSERT INTO lobby_teachers (lobby_code, teacher_name, subject, is_live) VALUES (?, ?, ?, ?)",
            [
                ("LOBBY-ECE301", "Dr. Vikram Deshmukh", "Digital Signal Processing", 1),
                ("LOBBY-ECE301", "Prof. Neha Kulkarni", "Embedded Systems & IoT", 0),
                ("LOBBY-ECE301", "Dr. Rajesh Iyer", "Network Theory & Lines", 0),
                ("LOBBY-ECE301", "Prof. Sunita Rao", "VLSI Design Lab", 0),
                ("LOBBY-CS402", "Prof. Neha Kulkarni", "Embedded Systems & IoT", 1),
                ("LOBBY-CS402", "Dr. Arjun Menon", "Edge Computer Vision", 0),
            ],
        )
        cur.executemany(
            """INSERT INTO lobby_assignments (lobby_code, subject, teacher_name, title, due_date, submitted_count, total_students, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                ("LOBBY-ECE301", "Digital Signal Processing", "Dr. Vikram Deshmukh", "FIR vs. IIR Filter Design in MATLAB", "2026-11-29", 5, 6, "Active"),
                ("LOBBY-ECE301", "Network Theory & Lines", "Dr. Rajesh Iyer", "Passive LC Filter Impedance Analysis", "2026-12-01", 4, 6, "Active"),
                ("LOBBY-ECE301", "VLSI Design Lab", "Prof. Sunita Rao", "CMOS Inverter Transient Simulation", "2026-12-03", 6, 6, "Graded"),
                ("LOBBY-CS402", "Edge Computer Vision", "Dr. Arjun Menon", "ONNX Quantization Benchmark Report", "2026-12-02", 4, 6, "Active"),
            ],
        )

    # 2. Seed Subject-Wise Attendance (Theory vs Practical)
    cur.execute("SELECT COUNT(*) FROM subject_records")
    if cur.fetchone()[0] == 0:
        subjects = [
            ("ECE501", "Digital Signal Processing", "Dr. Vikram Deshmukh"),
            ("ECE502", "Embedded Systems & IoT", "Prof. Neha Kulkarni"),
            ("ECE503", "Network Theory & Lines", "Dr. Rajesh Iyer"),
            ("ECE504", "VLSI Design", "Prof. Sunita Rao"),
        ]
        # Deliberately give Rohan Verma (S104) and Kabir Malhotra (S106) <75% to showcase dual warning engine
        student_profiles = {
            "S101": ("Hansika Bhattacharya", [(23, 24, 11, 12), (21, 22, 10, 10), (20, 22, 9, 10), (19, 20, 10, 10)]),
            "S102": ("Aarav Sharma",         [(21, 24, 10, 12), (19, 22, 9, 10),  (19, 22, 8, 10), (17, 20, 9, 10)]),
            "S103": ("Meera Nair",           [(20, 24, 10, 12), (18, 22, 8, 10),  (17, 22, 8, 10), (16, 20, 8, 10)]),
            "S104": ("Rohan Verma",          [(15, 24, 7, 12),  (14, 22, 6, 10),  (15, 22, 6, 10), (13, 20, 6, 10)]),
            "S105": ("Ananya Gupta",         [(24, 24, 12, 12), (21, 22, 10, 10), (21, 22, 10, 10), (20, 20, 10, 10)]),
            "S106": ("Kabir Malhotra",       [(16, 24, 8, 12),  (15, 22, 7, 10),  (14, 22, 7, 10), (14, 20, 7, 10)]),
        }
        recs = []
        for sid, (sname, counts) in student_profiles.items():
            for (code, s_title, teacher), (ta, tt, pa, pt) in zip(subjects, counts):
                recs.append((sid, sname, code, s_title, teacher, ta, tt, pa, pt))
        cur.executemany(
            """INSERT INTO subject_records
               (student_id, student_name, subject_code, subject_name, teacher_name, theory_attended, theory_total, practical_attended, practical_total)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            recs,
        )

    # 3. Seed Daily Attendance Summary Logs
    cur.execute("SELECT COUNT(*) FROM daily_logs")
    if cur.fetchone()[0] == 0:
        today_s = datetime.now().strftime("%Y-%m-%d")
        daily_rows = [
            (today_s, "S101", "Hansika Bhattacharya", "Digital Signal Processing", "Theory", "Dr. Vikram Deshmukh", "09:30 - 10:20", "Present", 0),
            (today_s, "S101", "Hansika Bhattacharya", "Embedded Systems & IoT", "Practical", "Prof. Neha Kulkarni", "10:30 - 12:10", "Present", 0),
            (today_s, "S101", "Hansika Bhattacharya", "Network Theory & Lines", "Theory", "Dr. Rajesh Iyer", "13:00 - 13:50", "Present", 0),
            (today_s, "S101", "Hansika Bhattacharya", "VLSI Design", "Practical", "Prof. Sunita Rao", "14:00 - 15:40", "Present", 0),

            (today_s, "S104", "Rohan Verma", "Digital Signal Processing", "Theory", "Dr. Vikram Deshmukh", "09:30 - 10:20", "Absent (Focus Violation)", 3),
            (today_s, "S104", "Rohan Verma", "Embedded Systems & IoT", "Practical", "Prof. Neha Kulkarni", "10:30 - 12:10", "Absent", 0),
            (today_s, "S104", "Rohan Verma", "Network Theory & Lines", "Theory", "Dr. Rajesh Iyer", "13:00 - 13:50", "Present", 1),
            (today_s, "S104", "Rohan Verma", "VLSI Design", "Practical", "Prof. Sunita Rao", "14:00 - 15:40", "Absent", 0),

            (today_s, "S102", "Aarav Sharma", "Digital Signal Processing", "Theory", "Dr. Vikram Deshmukh", "09:30 - 10:20", "Present", 0),
            (today_s, "S103", "Meera Nair", "Digital Signal Processing", "Theory", "Dr. Vikram Deshmukh", "09:30 - 10:20", "Present", 1),
            (today_s, "S105", "Ananya Gupta", "Digital Signal Processing", "Theory", "Dr. Vikram Deshmukh", "09:30 - 10:20", "Present", 0),
            (today_s, "S106", "Kabir Malhotra", "Digital Signal Processing", "Theory", "Dr. Vikram Deshmukh", "09:30 - 10:20", "Absent", 0),
        ]
        cur.executemany(
            """INSERT INTO daily_logs
               (log_date, student_id, student_name, subject_name, session_type, teacher_name, time_slot, status, proctor_strikes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            daily_rows,
        )

    # 4. Seed One Pending Student Dispute Flag
    cur.execute("SELECT COUNT(*) FROM dispute_tickets")
    if cur.fetchone()[0] == 0:
        cur.execute("SELECT id FROM daily_logs WHERE student_id = 'S104' AND subject_name = 'Embedded Systems & IoT' LIMIT 1")
        row = cur.fetchone()
        log_id = row[0] if row else None
        cur.execute(
            """INSERT INTO dispute_tickets
               (daily_log_id, student_id, student_name, subject_name, session_type, routed_to, recipient_name, reason, status, created_at)
               VALUES (?, 'S104', 'Rohan Verma', 'Embedded Systems & IoT', 'Practical', 'Subject Teacher', 'Prof. Neha Kulkarni',
                       'Was assisting in hardware oscilloscope calibration in Lab Bay 2 outside main webcam angle.', 'Pending Review', ?)""",
            (log_id, datetime.now().strftime("%Y-%m-%d %H:%M")),
        )

    # 5. Seed Historical Telemetry & Proctoring Incident
    cur.execute("SELECT COUNT(*) FROM engagement_logs")
    if cur.fetchone()[0] == 0:
        demo_sess = "LOBBY-ECE301_DEMO"
        base_t = datetime.now() - timedelta(minutes=30)
        cur.executemany(
            """INSERT INTO attendance (session_id, student_id, name, first_seen, last_seen, presence_ratio, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (demo_sess, "S101", "Hansika Bhattacharya", "09:30:08", "10:19:50", 97.2, "Present"),
                (demo_sess, "S102", "Aarav Sharma", "09:31:12", "10:19:42", 91.5, "Present"),
                (demo_sess, "S103", "Meera Nair", "09:30:45", "10:19:15", 85.0, "Present"),
                (demo_sess, "S104", "Rohan Verma", "09:32:10", "09:58:14", 44.0, "Absent (Focus Violation)"),
                (demo_sess, "S105", "Ananya Gupta", "09:30:05", "10:19:55", 98.4, "Present"),
                (demo_sess, "S106", "Kabir Malhotra", "09:34:00", "10:02:10", 52.0, "Absent"),
            ],
        )
        curve = [
            (87.0, 85.0, 64.0),
            (84.0, 82.0, 56.0),
            (78.0, 79.0, 42.0),
            (66.0, 70.0, 24.0),
            (51.0, 56.0, 14.0),
            (46.0, 48.0, 11.0),
            (64.0, 68.0, 46.0),
            (83.0, 86.0, 76.0),
            (90.0, 88.0, 82.0),
            (86.0, 84.0, 69.0),
        ]
        for idx, (g, m, a) in enumerate(curve):
            ts = (base_t + timedelta(minutes=idx * 3)).strftime("%H:%M:%S")
            tot = round(0.50 * g + 0.25 * m + 0.25 * a, 1)
            cur.execute(
                """INSERT INTO engagement_logs (session_id, timestamp, gaze_score, movement_score, audio_score, total_engagement)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (demo_sess, ts, g, m, a, tot),
            )
        cur.execute(
            """INSERT INTO proctor_incidents
               (session_id, student_id, student_name, event_type, duration_sec, strike_count, max_strikes, action_taken, timestamp)
               VALUES (?, 'S104', 'Rohan Verma', 'Tab Switch / Window Exit', 24.5, 3, 3, 'Marked ABSENT (Focus Violation) + Parent Alerted', '09:58:14')""",
            (demo_sess,),
        )
        cur.execute(
            """INSERT INTO agent_suggestions (session_id, timestamp, engagement_level, suggestion)
               VALUES (?, '09:45:00', 40.8, '[Engagement] Attention and vocal activity dipped sharply—run a 60-second concept check poll before advancing slides.')""",
            (demo_sess,),
        )

    # 6. Seed Safety / Parent Digest Notification
    cur.execute("SELECT COUNT(*) FROM notifications")
    if cur.fetchone()[0] == 0:
        cur.execute(
            """INSERT INTO notifications
               (recipient_role, student_id, student_name, category, severity, title, message, channels, acknowledged, created_at)
               VALUES ('Parent', 'S104', 'Rohan Verma', 'Safety & Proctoring', 'Critical',
                       'Unexpected Window Exit / Focus Violation — Rohan Verma',
                       'Rohan Verma exited the live Digital Signal Processing session 3 times (limit 3/3) and was marked Absent. Mentor notified for safety check-in.',
                       'Portal • SMS • Email', 0, ?)""",
            (datetime.now().strftime("%Y-%m-%d %H:%M"),),
        )

    conn.commit()
    conn.close()
    dispatch_below_75_warnings()


def seed_demo_sessions():
    """Backward-compatible helper."""
    seed_commercial_demo_data()
    return True