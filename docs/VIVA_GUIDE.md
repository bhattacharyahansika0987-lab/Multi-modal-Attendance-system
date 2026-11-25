# AttendAI — Final Project Demo Script & Viva Preparation Guide

## 1. Structured 5-Minute Live Evaluation Script

Use this exact sequence during your B.Tech major project presentation. Open **`https://multi-modal-attendance-system-cjbidvpaux4ulfw4y9zyxo.streamlit.app/`** (or `http://localhost:8501` if presenting locally with Ollama and webcam).

### Minute 0:00 – 0:45 | Architecture & Privacy Hook
* Point to the **Edge Privacy & Trust Audit** card in the sidebar.
* Highlight the core differentiator: *"Unlike cloud surveillance tools, AttendAI processes vision, audio, and LLM reasoning locally—storing zero raw student photos, only 512-D normalized vectors."*

### Minute 0:45 – 2:00 | Live Command Center, Focus Proctoring & Auto-PDF
1. Click **Play Stream** to show real-time animated telemetry, sparkline KPIs, and per-student attention cards.
2. Click **Mid-Lecture Drift** to trigger the crimson engagement-drop banner and show the **AI Teaching Coach** issuing an immediate pedagogical intervention.
3. Demonstrate **Anti-Cheat Focus Proctoring:** Switch browser tabs briefly (or click **Simulate Tab-Switch Strike**) until strikes hit `3/3`—show the student automatically overridden to **`Absent (Focus Violation)`** with an immediate alert dispatched to the Parent and Mentor.
4. Click **End Session & Auto-PDF**—show the system automatically compiling, downloading, and archiving the complete PDF session dossier without manual formatting.

### Minute 2:00 – 2:50 | Game-Style Multi-Teacher Classroom Lobbies
1. Open the **Classroom Lobbies** tab (`LOBBY-ECE301`).
2. Click **Join Lobby by Code** to add a second subject teacher into the same cohort room, click **Take Host** to switch live control, and publish a quick assignment on the shared Lobby Assignment Board.

### Minute 2:50 – 4:10 | Theory vs. Practical Calculator, `<75%` Warnings & Dispute Recalculation
1. Open **Attendance Calculator & Disputes** and select **`S104 — Rohan Verma`** (below `75%`).
2. Point out the separate **Theory %** and **Practical %** columns, **Internal Attendance Grade**, **75% Recovery Calculator**, and active **`<75%` Dual Warning Banner**.
3. Switch the sidebar Role to **Student**, expand **Flag / Request Attendance Correction**, and route a dispute to the Subject Teacher.
4. Switch back to **Instructor / Mentor** and click **Approve & Recalculate**—show the student's Theory/Practical % and Cumulative % updating live.

### Minute 4:10 – 5:00 | Parent Portal, Student Safety & Biometric Vault
1. Switch the sidebar Role to **Parent / Guardian** and open **Parent & Student Safety**.
2. Show the ward's attendance summary, acknowledge a `<75%` warning, and demonstrate the discreet **Student Safety Check-In (SOS)** to the Mentor.
3. Close in **Biometric Vault & Auto-PDFs** by clicking **Inspect Vector** on any student to prove only a 512-D float array (`L2 = 1.0000`) is stored—zero raw images.

---

## 2. Top 10 Expected Viva Questions & Crisp Answers

### Q1. Why did you use sustained-presence tracking instead of standard one-shot facial recognition?
**Answer:** One-shot recognition is vulnerable to brief doorway check-ins or proxy attendance. By evaluating the ratio $P_i = N_{i,\text{verified}} / N_{\text{total}}$ across the lecture duration against a threshold (default `60%`) and coupling it with window-focus proctoring strikes, AttendAI verifies continuous physical and digital presence.

### Q2. How do you guarantee student privacy if you are using facial recognition?
**Answer:** During enrollment and live verification, frames exist strictly in transient RAM. InsightFace extracts an irreversible 512-dimensional L2-normalized embedding vector, which is stored in local SQLite (`data/classroom.db`), and the raw image buffer is immediately discarded. You cannot reconstruct a student's photograph from the stored vector.

### Q3. Why did you replace MediaPipe with OpenCV Haar Cascades for gaze and posture tracking?
**Answer:** Newer Python and MediaPipe releases introduced breaking API changes in `mediapipe.solutions` and heavier Linux cloud dependencies. OpenCV Haar Cascades (`haarcascade_frontalface_default.xml` + `haarcascade_eye.xml`) run in under 15 ms on standard CPUs, work 100% offline, and deploy reliably across Windows and headless Linux servers.

### Q4. How does your multimodal engagement fusion formula work, and why those specific weights?
**Answer:** $E(t) = 0.50 \cdot G(t) + 0.25 \cdot M(t) + 0.25 \cdot A(t)$. Visual gaze ($50\%$) is the primary indicator of screen/board attention during lectures, while posture/movement ($25\%$) distinguishes active alertness from prolonged static drowsiness (`>15s` inactivity penalty), and WebRTC VAD vocal activity ($25\%$) captures classroom Q&A without recording speech.

### Q5. What happens if the microphone or local Ollama LLM is unavailable (such as on Streamlit Cloud)?
**Answer:** Every hardware-dependent subsystem is built with fault-tolerant graceful degradation. If `sounddevice`/`webrtcvad` is unavailable, audio defaults to a neutral `50%` baseline so visual tracking continues uninterrupted. If Ollama (`llama3.2:3b`) is offline, `TeachingAdvisorAgent` automatically engages a deterministic pedagogical rule engine mapped to live engagement thresholds.

### Q6. How does the browser tab-switch proctoring prevent students from minimizing or leaving the session?
**Answer:** An embedded JavaScript Focus Guard listens to native browser DOM events (`document.visibilityState` and `window.blur`). Every exit logs a timestamped strike and away-duration. Once a student reaches the configured strike limit (default `3/3`), the backend overrides their status to `Absent (Focus Violation)` and dispatches an incident alert to the Mentor and Parent Portal.

### Q7. How are Theory and Practical lectures calculated differently in the Attendance Calculator?
**Answer:** `subject_records` tracks `theory_attended/theory_total` and `practical_attended/practical_total` independently per subject. The calculator displays separate Theory % and Practical % progress bars, derives the subject's Internal Attendance Grade slab (`A+`, `A`, `B`, or `Detained`), computes the overall cumulative percentage across all sessions, and calculates the exact recovery classes needed (`ceil(3*total - 4*attended)`) to regain `75%`.

### Q8. How does the Student Attendance Dispute system maintain audit integrity?
**Answer:** Students cannot edit their own attendance. Flagging a session creates a tracked ticket in `dispute_tickets` routed specifically to their Assigned Mentor or Subject Teacher. Only the `Instructor / Mentor` role can click **Approve & Recalculate**, which atomically updates both `daily_logs` and `subject_records` while preserving the ticket decision audit trail.

### Q9. How did you implement automatic PDF generation without fragile third-party binaries like wkhtmltopdf?
**Answer:** `modules/agent.py` includes a custom, pure-Python PDF 1.4 binary writer (`_build_pdf_bytes`) that formats multi-page reports (pedagogical summary, multimodal telemetry, attendance roster, proctoring logs, and AI interventions) in under 35 ms with zero external C-library dependencies—ensuring 100% compatibility on both Windows and Linux cloud containers.

### Q10. Why did you choose SQLite over a cloud database like Firebase or MongoDB Atlas?
**Answer:** Using embedded SQLite (`data/classroom.db`) directly enforces our privacy-first edge mandate: biometric vectors and student attendance records remain physically on the institution's local machine with zero network latency, zero recurring cloud storage cost, and full offline resilience during campus Wi-Fi outages.