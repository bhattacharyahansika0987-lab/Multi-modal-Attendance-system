import sqlite3
import json
import math
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

DB_PATH = Path("data/classroom.db")


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    """Creates all local SQLite tables with zero pre-filled demo records."""
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
            generated_at TEXT NOT NULL
        )
    """)

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

    conn.commit()
    conn.close()


def clear_all_data():
    """Deletes all records from every table so the teacher can start with a blank slate."""
    conn = get_connection()
    cur = conn.cursor()
    tables = [
        "students",
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
    ]
    for tbl in tables:
        cur.execute(f"DELETE FROM {tbl}")
    conn.commit()
    conn.close()


def save_student(student_id: str, name: str, embedding: np.ndarray | None = None):
    if embedding is None:
        rng = np.random.default_rng(abs(hash(student_id)) % (2**32))
        vec = rng.standard_normal(512).astype(np.float32)
        embedding = vec / np.linalg.norm(vec)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO students (student_id, name, embedding, created_at) VALUES (?, ?, ?, ?)",
        (student_id.strip(), name.strip(), json.dumps(embedding.tolist()), datetime.now().strftime("%Y-%m-%d %H:%M")),
    )
    conn.commit()
    conn.close()


def delete_student(student_id: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM students WHERE student_id = ?", (student_id,))
    cur.execute("DELETE FROM subject_records WHERE student_id = ?", (student_id,))
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


def log_attendance(session_id: str, student_id: str, name: str, first_seen: str, last_seen: str, ratio: float, status: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO attendance (session_id, student_id, name, first_seen, last_seen, presence_ratio, status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (session_id, student_id, name, first_seen, last_seen, round(ratio, 1), status),
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
           (session_id, lobby_code, subject_name, avg_engagement, present_count, total_count, proctor_violations, pdf_b64, generated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            lobby_code,
            subject_name,
            round(avg_engagement, 1),
            present_count,
            total_count,
            proctor_violations,
            pdf_b64,
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


def get_lobbies() -> list[dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT lobby_code, name, cohort, active_host, active_subject, created_at FROM lobbies ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "lobby_code": r[0],
            "name": r[1],
            "cohort": r[2],
            "active_host": r[3],
            "active_subject": r[4],
            "created_at": r[5],
        }
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


def get_lobby_teachers(lobby_code: str) -> list[dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, teacher_name, subject, is_live FROM lobby_teachers WHERE lobby_code = ? ORDER BY is_live DESC, id ASC",
        (lobby_code,),
    )
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
    df = pd.read_sql_query(
        "SELECT * FROM lobby_assignments WHERE lobby_code = ? ORDER BY id DESC",
        conn,
        params=(lobby_code,),
    )
    conn.close()
    return df


def add_or_update_subject_record(
    student_id: str,
    student_name: str,
    subject_code: str,
    subject_name: str,
    theory_attended: int,
    theory_total: int,
    practical_attended: int,
    practical_total: int,
):
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
        (
            student_id.strip(),
            student_name.strip(),
            subject_code.strip().upper(),
            subject_name.strip(),
            int(theory_attended),
            int(theory_total),
            int(practical_attended),
            int(practical_total),
        ),
    )
    conn.commit()
    conn.close()


def compute_internal_grade(pct: float, min_threshold: float = 75.0, slabs: dict | None = None) -> tuple[str, str]:
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
    df = pd.read_sql_query(
        "SELECT * FROM subject_records WHERE student_id = ? ORDER BY subject_code ASC",
        conn,
        params=(student_id,),
    )
    conn.close()
    return df


def compute_student_cumulative_summary(min_threshold: float = 75.0, slabs: dict | None = None) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM subject_records", conn)
    conn.close()
    if df.empty:
        return pd.DataFrame()

    rows = []
    for (sid, sname), grp in df.groupby(["student_id", "student_name"]):
        th_att = int(grp["theory_attended"].sum())
        th_tot = int(grp["theory_total"].sum())
        pr_att = int(grp["practical_attended"].sum())
        pr_tot = int(grp["practical_total"].sum())

        th_pct = round((th_att / th_tot) * 100, 1) if th_tot else 0.0
        pr_pct = round((pr_att / pr_tot) * 100, 1) if pr_tot else 0.0
        cum_att = th_att + pr_att
        cum_tot = th_tot + pr_tot
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


def add_daily_log(
    student_id: str,
    student_name: str,
    subject_name: str,
    session_type: str,
    teacher_name: str,
    time_slot: str,
    status: str,
    proctor_strikes: int = 0,
):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO daily_logs
           (log_date, student_id, student_name, subject_name, session_type, teacher_name, time_slot, status, proctor_strikes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().strftime("%Y-%m-%d"),
            student_id.strip(),
            student_name.strip(),
            subject_name.strip(),
            session_type,
            teacher_name.strip(),
            time_slot.strip(),
            status,
            int(proctor_strikes),
        ),
    )
    conn.commit()
    conn.close()


def get_daily_logs(student_id: str | None = None) -> pd.DataFrame:
    conn = get_connection()
    if student_id:
        df = pd.read_sql_query(
            "SELECT * FROM daily_logs WHERE student_id = ? ORDER BY id DESC",
            conn,
            params=(student_id,),
        )
    else:
        df = pd.read_sql_query("SELECT * FROM daily_logs ORDER BY id DESC", conn)
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
            reason.strip(),
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ),
    )
    conn.commit()
    conn.close()
    dispatch_notification(
        recipient_role="Instructor",
        student_id=student_id,
        student_name=student_name,
        category="Correction Request",
        severity="Warning",
        title=f"Attendance Flag from {student_name} ({subject_name})",
        message=f"Routed to {routed_to} ({recipient_name}): {reason.strip()}",
        channels="Instructor Portal",
    )


def get_dispute_tickets(student_id: str | None = None) -> pd.DataFrame:
    conn = get_connection()
    if student_id:
        df = pd.read_sql_query(
            "SELECT * FROM dispute_tickets WHERE student_id = ? ORDER BY id DESC",
            conn,
            params=(student_id,),
        )
    else:
        df = pd.read_sql_query("SELECT * FROM dispute_tickets ORDER BY id DESC", conn)
    conn.close()
    return df


def resolve_dispute_ticket(ticket_id: int, approve: bool, resolution_note: str):
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
    new_status = "Approved & Updated" if approve else "Declined"
    cur.execute(
        "UPDATE dispute_tickets SET status = ?, resolution_note = ? WHERE id = ?",
        (new_status, resolution_note, ticket_id),
    )

    if approve:
        if daily_log_id:
            cur.execute("UPDATE daily_logs SET status = 'Present (Verified)' WHERE id = ?", (daily_log_id,))
        if stype.lower() == "practical":
            cur.execute(
                """UPDATE subject_records
                   SET practical_attended = MIN(practical_total, practical_attended + 1)
                   WHERE student_id = ? AND subject_name = ?""",
                (sid, subj),
            )
        else:
            cur.execute(
                """UPDATE subject_records
                   SET theory_attended = MIN(theory_total, theory_attended + 1)
                   WHERE student_id = ? AND subject_name = ?""",
                (sid, subj),
            )

    conn.commit()
    conn.close()

    dispatch_notification(
        recipient_role="Student",
        student_id=sid,
        student_name=sname,
        category="Correction Update",
        severity="Info" if approve else "Warning",
        title=f"Attendance Flag {new_status} — {subj}",
        message=resolution_note or f"Your request for {subj} ({stype}) was marked {new_status}.",
        channels="Student & Guardian Portal",
    )


def dispatch_notification(
    recipient_role: str,
    student_id: str,
    student_name: str,
    category: str,
    severity: str,
    title: str,
    message: str,
    channels: str = "Portal · Email · SMS",
):
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
        sid = row["student_id"]
        sname = row["student_name"]
        pct = row["cumulative_pct"]
        for role in ("Student", "Parent"):
            cur.execute(
                "SELECT 1 FROM notifications WHERE recipient_role = ? AND student_id = ? AND category = 'Attendance Warning'",
                (role, sid),
            )
            if not cur.fetchone():
                msg = (
                    f"{sname} ({sid}) is at {pct}% cumulative attendance, below the {min_threshold:.0f}% minimum "
                    f"(Theory: {row['theory_pct']}% | Practical: {row['practical_pct']}%). Recovery: {row['recovery']}."
                )
                cur.execute(
                    """INSERT INTO notifications
                       (recipient_role, student_id, student_name, category, severity, title, message, channels, acknowledged, created_at)
                       VALUES (?, ?, ?, 'Attendance Warning', 'Critical', ?, ?, 'Portal · Email · SMS', 0, ?)""",
                    (
                        role,
                        sid,
                        sname,
                        f"Below {min_threshold:.0f}% Attendance Warning — {sname} ({pct}%)",
                        msg,
                        datetime.now().strftime("%Y-%m-%d %H:%M"),
                    ),
                )
                dispatched += 1
    conn.commit()
    conn.close()
    return dispatched


def get_notifications(recipient_role: str | None = None, student_id: str | None = None) -> pd.DataFrame:
    conn = get_connection()
    query = "SELECT * FROM notifications WHERE 1=1"
    params = []
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