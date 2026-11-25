import cv2
import numpy as np
from datetime import datetime
from insightface.app import FaceAnalysis
from modules.database import load_all_students, log_attendance


class SustainedAttendanceTracker:
    def __init__(self, similarity_threshold: float = 0.45, presence_threshold: float = 0.60):
        self.similarity_threshold = similarity_threshold
        self.presence_threshold = presence_threshold
        self.students = load_all_students()
        self.total_checks = 0
        self.records = {}

        # Initialize tracking state for each enrolled student
        for s in self.students:
            self.records[s["student_id"]] = {
                "name": s["name"],
                "seen_count": 0,
                "first_seen": None,
                "last_seen": None,
            }

        self.app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
        self.app.prepare(ctx_id=0, det_size=(320, 320))

    def process_frame(self, frame: np.ndarray):
        """Detects faces, matches against enrolled embeddings, and annotates the frame."""
        self.total_checks += 1
        now_str = datetime.now().strftime("%H:%M:%S")
        annotated = frame.copy()
        faces = self.app.get(frame)

        for face in faces:
            x1, y1, x2, y2 = face.bbox.astype(int)
            emb = face.embedding / np.linalg.norm(face.embedding)

            best_id = None
            best_name = "Unknown"
            best_score = -1.0

            # Compare detected face against all enrolled student embeddings
            for s in self.students:
                score = float(np.dot(emb, s["embedding"]))
                if score > best_score:
                    best_score = score
                    best_id = s["student_id"]
                    best_name = s["name"]

            if best_score >= self.similarity_threshold and best_id is not None:
                rec = self.records[best_id]
                rec["seen_count"] += 1
                if rec["first_seen"] is None:
                    rec["first_seen"] = now_str
                rec["last_seen"] = now_str

                ratio = rec["seen_count"] / max(1, self.total_checks)
                status = "PRESENT" if ratio >= self.presence_threshold else "VERIFYING..."
                color = (0, 255, 0) if status == "PRESENT" else (0, 215, 255)
                label = f"{best_name} | {status} ({int(ratio * 100)}%)"
            else:
                color = (0, 0, 255)
                label = "Unknown"

            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            cv2.putText(annotated, label, (x1, max(20, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        return annotated

    def get_summary(self):
        """Returns current attendance status table for all enrolled students."""
        summary = []
        for sid, rec in self.records.items():
            ratio = rec["seen_count"] / max(1, self.total_checks)
            status = "Present" if ratio >= self.presence_threshold else "Absent"
            summary.append({
                "Student ID": sid,
                "Name": rec["name"],
                "First Seen": rec["first_seen"] or "-",
                "Last Seen": rec["last_seen"] or "-",
                "Presence %": round(ratio * 100, 1),
                "Status": status,
            })
        return summary

    def finalize_session(self, session_id: str):
        """Saves final timestamped attendance records into SQLite."""
        summary = self.get_summary()
        for row in summary:
            log_attendance(
                session_id=session_id,
                student_id=row["Student ID"],
                name=row["Name"],
                first_seen=row["First Seen"],
                last_seen=row["Last Seen"],
                ratio=row["Presence %"],
                status=row["Status"],
            )
        return summary


if __name__ == "__main__":
    tracker = SustainedAttendanceTracker()
    cap = cv2.VideoCapture(0)
    print("Testing Sustained Attendance! Look at the webcam. Press Q to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        out = tracker.process_frame(frame)
        cv2.imshow("Scenario 1: Sustained Attendance Test", out)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("\nSession Summary:", tracker.get_summary())