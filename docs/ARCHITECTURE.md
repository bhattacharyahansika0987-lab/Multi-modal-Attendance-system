# AttendAI — Technical Architecture & Security Specification

## 1. Architectural Overview

AttendAI follows a **local-first, modular edge architecture** designed to operate with zero external cloud dependencies for biometric inference, audio voice activity detection, database persistence, and pedagogical LLM reasoning.

| Layer | Technology | Responsibility |
| :--- | :--- | :--- |
| **Presentation & Role Shell** | Streamlit + Modular CSS (`modules/styles.py`) + Embedded JS Focus Guard | Role-aware UI (`Instructor / Mentor`, `Student`, `Parent / Guardian`), real browser `visibilitychange`/`blur` proctoring, and live Plotly telemetry. |
| **Biometric Identity Layer** | InsightFace (`buffalo_sc`, ONNX Runtime CPU) | Extracts 512-D L2-normalized facial embeddings transiently in RAM; verifies identity via cosine similarity ($\tau_{\text{sim}} = 0.45$). |
| **Engagement Signal Layer** | OpenCV Haar Cascades + WebRTC VAD (`sounddevice`) | Computes rolling visual gaze alignment, centroid motion/inactivity timers, and binary vocal activity ratios without recording audio clips. |
| **Agentic & Reporting Layer** | Ollama (`llama3.2:3b`) + Rule Fallback + Pure-Python PDF 1.4 Compiler | Generates categorized pedagogical recommendations (`Engagement`, `Pacing`, `Comprehension`, `Participation`) and auto-compiles branded PDF session reports on session termination. |
| **Local Storage Layer** | SQLite (`data/classroom.db`) | ACID-compliant local storage for vectors, sustained attendance, proctoring logs, lobbies, Theory/Practical ledgers, dispute tickets, and notifications. |

---

## 2. Database Entity-Relationship Schema (`data/classroom.db`)

```mermaid
erDiagram
    STUDENTS {
        TEXT student_id PK
        TEXT name
        TEXT embedding "512-D JSON float32 vector (0 raw images)"
        TEXT created_at
    }
    ATTENDANCE {
        INT id PK
        TEXT session_id
        TEXT student_id FK
        TEXT name
        TEXT first_seen
        TEXT last_seen
        REAL presence_ratio
        TEXT status
    }
    ENGAGEMENT_LOGS {
        INT id PK
        TEXT session_id
        TEXT timestamp
        REAL gaze_score
        REAL movement_score
        REAL audio_score
        REAL total_engagement
    }
    PROCTOR_INCIDENTS {
        INT id PK
        TEXT session_id
        TEXT student_id FK
        TEXT event_type
        REAL duration_sec
        INT strike_count
        INT max_strikes
        TEXT action_taken
        TEXT timestamp
    }
    SESSION_REPORTS {
        INT id PK
        TEXT session_id
        TEXT lobby_code FK
        TEXT subject_name
        REAL avg_engagement
        INT present_count
        INT total_count
        INT proctor_violations
        TEXT pdf_b64
        TEXT generated_at
    }
    LOBBIES {
        TEXT lobby_code PK
        TEXT name
        TEXT cohort
        TEXT active_host
        TEXT active_subject
    }
    LOBBY_TEACHERS {
        INT id PK
        TEXT lobby_code FK
        TEXT teacher_name
        TEXT subject
        INT is_live
    }
    LOBBY_ASSIGNMENTS {
        INT id PK
        TEXT lobby_code FK
        TEXT subject
        TEXT teacher_name
        TEXT title
        TEXT due_date
        INT submitted_count
        INT total_students
        TEXT status
    }
    SUBJECT_RECORDS {
        INT id PK
        TEXT student_id FK
        TEXT subject_code
        TEXT subject_name
        INT theory_attended
        INT theory_total
        INT practical_attended
        INT practical_total
    }
    DAILY_LOGS {
        INT id PK
        TEXT log_date
        TEXT student_id FK
        TEXT subject_name
        TEXT session_type
        TEXT teacher_name
        TEXT time_slot
        TEXT status
        INT proctor_strikes
    }
    DISPUTE_TICKETS {
        INT id PK
        INT daily_log_id FK
        TEXT student_id FK
        TEXT subject_name
        TEXT session_type
        TEXT routed_to
        TEXT recipient_name
        TEXT reason
        TEXT status
    }
    NOTIFICATIONS {
        INT id PK
        TEXT recipient_role
        TEXT student_id FK
        TEXT category
        TEXT severity
        TEXT title
        TEXT message
        TEXT channels
        INT acknowledged
    }

    STUDENTS ||--o{ ATTENDANCE : logs
    STUDENTS ||--o{ PROCTOR_INCIDENTS : triggers
    STUDENTS ||--o{ SUBJECT_RECORDS : tracks
    STUDENTS ||--o{ DAILY_LOGS : records
    STUDENTS ||--o{ DISPUTE_TICKETS : submits
    STUDENTS ||--o{ NOTIFICATIONS : receives
    DAILY_LOGS ||--o{ DISPUTE_TICKETS : references
    LOBBIES ||--o{ LOBBY_TEACHERS : hosts
    LOBBIES ||--o{ LOBBY_ASSIGNMENTS : shares
    LOBBIES ||--o{ SESSION_REPORTS : archives
```

---

## 3. Multimodal Fusion & Scoring Specifications

| Signal Channel | Weight | Extraction Method | Edge Failure Behavior |
| :--- | :---: | :--- | :--- |
| **Visual Gaze Alignment $G(t)$** | `50%` | OpenCV frontal face + upper-ROI eye cascade detection (`2 eyes = 95%`, `1 eye = 75%`, `face only = 55%`). | Scores `0%` when no face is detected; smoothed via 30-frame rolling `deque`. |
| **Posture & Motion $M(t)$** | `25%` | Inter-frame Euclidean displacement of primary face centroid + inactivity timer (`>15s` static triggers penalty to `35%`). | Prevents passive screen-staring or static photo spoofing from scoring artificially high. |
| **Vocal Interaction $A(t)$** | `25%` | WebRTC VAD (aggressiveness level `2`) over 30 ms PCM frames at 16 kHz. | Falls back gracefully to a neutral `50.0%` baseline when microphone hardware is unavailable (e.g., Linux cloud containers). |

### Internal Attendance Grade Slabs
| Cumulative / Subject % | Internal Grade | Eligibility Status |
| :---: | :---: | :--- |
| $\ge 90.0\%$ | `A+ (5/5 Marks)` | Optimal |
| $85.0\% - 89.9\%$ | `A (4/5 Marks)` | Optimal |
| $75.0\% - 84.9\%$ | `B (3/5 Marks)` | Watch |
| $< 75.0\%$ | `Detained (0/5)` | **At-Risk (Dual Student + Parent Warning Triggered)** |

---

## 4. Privacy & Student Safety Threat Model

| Threat Vector | Architectural Mitigation in AttendAI |
| :--- | :--- |
| **Biometric Photo Leakage** | Raw enrollment frames and live camera buffers remain strictly in volatile RAM and are never written to disk. Only irreversible 512-D L2-normalized float vectors are stored in SQLite. |
| **Cloud Surveillance / Third-Party APIs** |