"""
AttendAI — One-Command Demo Environment Seeder
Initializes the local SQLite database and populates realistic multi-teacher lobbies,
enrolled 512-D L2-normalized student embeddings, Theory/Practical attendance records,
proctoring incidents, student dispute tickets, and parent/safety notifications.
"""

from modules.database import (
    init_db,
    seed_commercial_demo_data,
    load_all_students,
    get_lobbies,
    compute_student_cumulative_summary,
)


def main():
    print("Initializing AttendAI local edge database (data/classroom.db)...")
    init_db()
    seed_commercial_demo_data()

    students = load_all_students()
    lobbies = get_lobbies()
    summary = compute_student_cumulative_summary()
    below_75 = int((summary["cumulative_pct"] < 75.0).sum()) if not summary.empty else 0

    print("\nAttendAI Demo Environment Ready:")
    print(f"  - Enrolled Students (512-D L2 Vectors, 0 Raw Photos): {len(students)}")
    print(f"  - Active Multi-Teacher Classroom Lobbies:             {len(lobbies)}")
    print(f"  - Students Flagged Below 75% (Dual Warnings Sent):    {below_75}")
    print("\nLaunch locally with:\n  streamlit run app.py")


if __name__ == "__main__":
    main()