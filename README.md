# 🛡️ AttendAI — Privacy-Preserving Multimodal Attendance, Engagement & Safeguarding Suite

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Streamlit%20Cloud-3B82F6?style=for-the-badge&logo=streamlit&logoColor=white)](https://multi-modal-attendance-system-cjbidvpaux4ulfw4y9zyxo.streamlit.app/)
[![Python](https://img.shields.io/badge/Python-3.10%2B-10B981?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Edge Privacy](https://img.shields.io/badge/Privacy-Zero%20Raw%20Images%20Stored-0EA5E9?style=for-the-badge)](#privacy-by-design-architecture)
[![LLM Engine](https://img.shields.io/badge/Local%20AI-Ollama%20Llama%203.2-6366F1?style=for-the-badge)](https://ollama.com/)

**AttendAI** is an offline-first, edge-deployed classroom intelligence platform engineered for B.Tech academic institutions. It unifies **sustained-presence biometric attendance**, **multimodal visual-audio engagement analytics**, **anti-cheat window-focus proctoring**, **game-style multi-teacher cohort lobbies**, **Theory vs. Practical attendance grading**, and **parent-student safety communication** inside a single privacy-preserving application.

> **Live Deployment:** [https://multi-modal-attendance-system-cjbidvpaux4ulfw4y9zyxo.streamlit.app/](https://multi-modal-attendance-system-cjbidvpaux4ulfw4y9zyxo.streamlit.app/)  
> **Repository:** [https://github.com/bhattacharyahansika0987-lab/Multi-modal-Attendance-system](https://github.com/bhattacharyahansika0987-lab/Multi-modal-Attendance-system)

---

## 📌 Problem Statement

Conventional classroom attendance and monitoring tools suffer from four structural failures:
1. **Single-Frame Proxy Spoofing:** Roll calls and one-shot face scans fail to verify whether a student actually remained attentive across the lecture.
2. **Privacy & Surveillance Risks:** Cloud-hosted vision platforms transmit student video feeds and raw facial images to third-party servers.
3. **Zero Pedagogical Feedback Loop:** Instructors lack real-time visibility into attention drops, silent fatigue, or browser tab-switching during hybrid/digital lectures.
4. **Fragmented Academic & Safety Communication:** Theory vs. Practical attendance calculations, `<75%` detention warnings, student attendance disputes, and parent safety alerts are scattered across disconnected spreadsheets and notice boards.

**AttendAI** solves all four issues locally on edge hardware—storing **0 raw images** and executing vision, voice activity, and LLM reasoning entirely offline (with cloud-safe demo fallback for instant browser evaluation).

---

## ✨ Key Platform Capabilities

| Module | Core Capabilities |
| :--- | :--- |
| **Live Command Center & Proctoring** | Sustained-presence verification (InsightFace `buffalo_sc`), real-time gaze/posture/audio fusion, live browser `visibilitychange`/`window.blur` tab-switch strike enforcement (auto-marks `ABSENT` on breach), and **automatic PDF report generation** upon scheduled session completion. |
| **Multi-Teacher Classroom Lobbies** | Game-style persistent cohort rooms (`LOBBY-ECE301`, `LOBBY-CS402`) with shareable join codes where multiple subject teachers co-host live sessions, track unified attendance, and publish cross-subject assignments. |
| **Attendance Calculator & Dispute Desk** | Separates **Theory Lectures** and **Practical Labs** per subject, calculates **Internal Attendance Grades** + **Total Cumulative %**, provides a 75% recovery calculator, generates **Daily Attendance Digests**, and allows students to flag/route attendance disputes directly to their **Mentor** or **Subject Teacher** with live recalculation upon approval. |
| **Parent Portal & Student Safety** | Automated dual dispatch of **`<75%` attendance warnings** and unexpected exit alerts to both Students and Parents, discreet **Student Safety / Well-Being Check-In (SOS)** to Mentors, and strict role-based data masking. |
| **Biometric Privacy Vault & Auto-PDF Archive** | Transient RAM-only 512-D L2-normalized embedding extraction, inspectable vector fingerprints (`0 Raw Bytes Stored`), auto-archived session PDFs, and multimodal Plotly analytics. |

---

## 🏗️ System Architecture & Multimodal Pipeline

```mermaid
flowchart LR
    subgraph Input["Edge / Browser Input Layer"]
        CAM[Webcam / Video / Simulator]
        MIC[Microphone Audio Stream]
        TAB[Browser Focus Guard<br/>visibilitychange / blur]
    end

    subgraph VisionAudio["Offline Multimodal Processing"]
        IF[InsightFace buffalo_sc<br/>512-D L2 Embeddings]
        HC[OpenCV Haar Cascades<br/>Gaze, Posture & Inactivity]
        VAD[WebRTC VAD<br/>Speech Activity Ratio]
    end

    subgraph Intelligence["Fusion, Proctoring & Agentic Layer"]
        ATT[Sustained-Presence Engine]
        FUS[Weighted Multimodal Fusion<br/>0.50 Gaze + 0.25 Motion + 0.25 Audio]
        PRO[Strike Enforcer<br/>3-Strike Absent Override]
        LLM[Teaching Advisor Agent<br/>Local Ollama llama3.2:3b + Fallback]
    end

    subgraph StorageUI["Local Persistence & Role-Based UI"]
        DB[(SQLite classroom.db<br/>0 Raw Images Stored)]
        PDF[Auto-PDF Session Compiler]
        UI[AttendAI Command Suite<br/>Instructor • Student • Parent Views]
    end

    CAM --> IF --> ATT --> DB
    CAM --> HC --> FUS
    MIC --> VAD --> FUS
    TAB --> PRO --> DB
    FUS --> DB
    FUS --> LLM --> DB
    DB --> PDF --> UI
    DB --> UI