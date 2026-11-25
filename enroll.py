import cv2
import numpy as np
from insightface.app import FaceAnalysis
from modules.database import init_db, save_student


def enroll_student():
    init_db()

    student_id = input("Enter Student ID (e.g., S101): ").strip()
    name = input("Enter Student Full Name: ").strip()

    if not student_id or not name:
        print("Student ID and Name cannot be empty.")
        return

    print("\nLoading offline face recognition model (first run downloads ~280 MB locally)...")
    app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(320, 320))

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not access webcam.")
        return

    embeddings = []
    print(f"\nWebcam active for {name}. Look at the camera.")
    print("Press SPACEBAR to capture a sample (need 5 samples) or Q to quit.\n")

    while len(embeddings) < 5:
        ret, frame = cap.read()
        if not ret:
            break

        display = frame.copy()
        faces = app.get(frame)

        for face in faces:
            x1, y1, x2, y2 = face.bbox.astype(int)
            cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)

        cv2.putText(
            display,
            f"Captured: {len(embeddings)}/5 | Press SPACE to capture",
            (15, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
        )
        cv2.imshow("Student Enrollment (Privacy-Preserving)", display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord(" "):
            if len(faces) == 1:
                # Normalize embedding vector
                emb = faces[0].embedding
                emb = emb / np.linalg.norm(emb)
                embeddings.append(emb)
                print(f"Sample {len(embeddings)}/5 captured!")
            elif len(faces) == 0:
                print("No face detected. Center your face and try again.")
            else:
                print("Multiple faces detected. Ensure only one person is in frame.")
        elif key == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

    if len(embeddings) == 5:
        # Average the 5 samples and re-normalize for reliable matching
        avg_embedding = np.mean(embeddings, axis=0)
        avg_embedding = avg_embedding / np.linalg.norm(avg_embedding)
        save_student(student_id, name, avg_embedding)
        print(f"\nSuccess! {name} ({student_id}) enrolled locally. Raw images were discarded.")
    else:
        print("\nEnrollment cancelled before 5 samples were captured.")


if __name__ == "__main__":
    enroll_student()