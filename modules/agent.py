import textwrap
from datetime import datetime
import pandas as pd
from modules.database import log_suggestion

try:
    import ollama
    OLLAMA_PKG_INSTALLED = True
except Exception:
    ollama = None
    OLLAMA_PKG_INSTALLED = False


def check_ollama_status(model_name: str = "llama3.2:3b") -> tuple[bool, str]:
    if not OLLAMA_PKG_INSTALLED:
        return False, "Rule-Based Fallback (Cloud Mode)"
    try:
        ollama.list()
        return True, f"Ollama Local ({model_name})"
    except Exception:
        return False, "Rule-Based Fallback (Ollama Offline)"


def _build_pdf_bytes(title: str, subtitle: str, lines: list[tuple[str, str]]) -> bytes:
    """Zero-dependency pure-Python PDF 1.4 generator for automatic session reports."""
    def esc(text: str) -> str:
        safe = str(text).encode("latin-1", "replace").decode("latin-1")
        return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    wrapped_lines: list[tuple[str, str]] = []
    for style, raw_line in lines:
        if not str(raw_line).strip():
            wrapped_lines.append(("body", ""))
            continue
        width = 72 if style == "h2" else 88
        for chunk in textwrap.wrap(str(raw_line), width=width) or [""]:
            wrapped_lines.append((style, chunk))

    pages_content: list[bytes] = []
    per_page = 44
    total_pages = max(1, (len(wrapped_lines) + per_page - 1) // per_page)

    for page_idx in range(total_pages):
        chunk = wrapped_lines[page_idx * per_page : (page_idx + 1) * per_page]
        cmds = ["BT"]
        y = 752
        if page_idx == 0:
            cmds.append(f"/F2 16 Tf 48 {y} Td ({esc(title)}) Tj")
            y -= 18
            cmds.append(f"/F1 9 Tf 0 -18 Td ({esc(subtitle)}) Tj")
            y -= 26
            cmds.append("ET")
            cmds.append("0.23 0.51 0.96 RG 1.2 w 48 720 m 564 720 l S")
            cmds.append("BT")
            cmds.append(f"/F1 10 Tf 48 {y} Td")
        else:
            cmds.append(f"/F1 10 Tf 48 {y} Td")

        for style, line in chunk:
            if style == "h2":
                cmds.append(f"/F2 11.5 Tf 0 -18 Td ({esc(line)}) Tj /F1 9.5 Tf")
            elif style == "bold":
                cmds.append(f"/F2 9.5 Tf 0 -14 Td ({esc(line)}) Tj /F1 9.5 Tf")
            else:
                cmds.append(f"0 -14 Td ({esc(line)}) Tj")

        cmds.append("ET")
        cmds.append(
            f"BT /F1 8 Tf 48 28 Td (AttendAI Automated Session Dossier | Privacy Verified: 0 Raw Images Stored | Page {page_idx + 1}/{total_pages}) Tj ET"
        )
        pages_content.append("\n".join(cmds).encode("latin-1"))

    objs: list[bytes] = []
    page_obj_ids = [5 + i * 2 for i in range(len(pages_content))]
    kids_str = " ".join(f"{pid} 0 R" for pid in page_obj_ids)

    objs.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objs.append(f"2 0 obj\n<< /Type /Pages /Kids [{kids_str}] /Count {len(pages_content)} >>\nendobj\n".encode("latin-1"))
    objs.append(b"3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
    objs.append(b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>\nendobj\n")

    for i, stream in enumerate(pages_content):
        page_id = 5 + i * 2
        stream_id = page_id + 1
        page_obj = (
            f"{page_id} 0 obj\n"
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            f"/Contents {stream_id} 0 R >>\nendobj\n"
        ).encode("latin-1")
        stream_obj = (
            f"{stream_id} 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
            + stream
            + b"\nendstream\nendobj\n"
        )
        objs.append(page_obj)
        objs.append(stream_obj)

    buf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objs:
        offsets.append(len(buf))
        buf.extend(obj)

    xref_pos = len(buf)
    buf.extend(f"xref\n0 {len(offsets)}\n".encode("latin-1"))
    buf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        buf.extend(f"{off:010d} 00000 n \n".encode("latin-1"))

    buf.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("latin-1"))
    return bytes(buf)


class TeachingAdvisorAgent:
    def __init__(self, model_name: str = "llama3.2:3b"):
        self.model_name = model_name

    @staticmethod
    def _classify_category(metrics: dict, custom_question: str | None = None) -> str:
        if custom_question:
            return "Instructor Query"
        eng = metrics.get("total_engagement", 0.0)
        gaze = metrics.get("gaze_score", 0.0)
        audio = metrics.get("audio_score", 0.0)
        if eng < 55.0 and audio < 25.0:
            return "Engagement"
        if gaze < 60.0:
            return "Pacing"
        if audio >= 65.0 and gaze >= 70.0:
            return "Participation"
        if gaze >= 68.0 and audio < 25.0:
            return "Comprehension"
        return "Pacing"

    def generate_advice(
        self,
        session_id: str,
        metrics: dict,
        present_count: int,
        total_students: int,
        custom_question: str | None = None,
    ) -> dict:
        engagement = metrics.get("total_engagement", 0.0)
        gaze = metrics.get("gaze_score", 0.0)
        movement = metrics.get("movement_score", 0.0)
        audio = metrics.get("audio_score", 0.0)
        inactivity = metrics.get("inactivity_sec", 0.0)
        category = self._classify_category(metrics, custom_question)

        if custom_question:
            prompt = (
                f"You are AttendAI, an assistive classroom coach. Live anonymous metrics: "
                f"Engagement {engagement}%, Gaze {gaze}%, Posture {movement}%, Vocal {audio}%, "
                f"Attendance {present_count}/{total_students}.\n"
                f"Instructor Question: {custom_question}\n"
                f"Respond in 2 concise, actionable sentences."
            )
        else:
            prompt = (
                f"You are AttendAI, an assistive classroom coach. Live anonymous metrics:\n"
                f"- Attendance: {present_count}/{total_students} verified present\n"
                f"- Overall Engagement: {engagement}% (Gaze {gaze}%, Posture {movement}%, Audio {audio}%, Inactivity {inactivity}s)\n"
                f"Provide exactly 2 short, practical teaching recommendations (1 sentence each)."
            )

        suggestion = None
        if OLLAMA_PKG_INSTALLED:
            try:
                resp = ollama.chat(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "You give concise, evidence-based pedagogical guidance."},
                        {"role": "user", "content": prompt},
                    ],
                    options={"temperature": 0.3, "num_predict": 140},
                )
                suggestion = resp["message"]["content"].strip()
            except Exception:
                suggestion = None

        if not suggestion:
            if custom_question:
                q_low = custom_question.lower()
                if any(k in q_low for k in ["tab", "cheat", "proctor", "focus", "absent"]):
                    suggestion = (
                        "Remind students that the AttendAI Focus Guard enforces a 3-strike window-exit limit before marking an automatic absence. "
                        "Use a quick 45-second live verbal question to verify active presence across flagged seats."
                    )
                elif any(k in q_low for k in ["poll", "quiz", "engage", "attention", "dip"]):
                    suggestion = (
                        f"With engagement at {engagement}% (Gaze {gaze}%, Audio {audio}%), launch a 60-second conceptual poll on the current derivation. "
                        f"Have learners discuss in pairs for 30 seconds before revealing the solution."
                    )
                else:
                    suggestion = (
                        f"Based on live telemetry (Engagement {engagement}%, Gaze {gaze}%, Vocal {audio}%), anchor the next concept with a real-world hardware example. "
                        f"Check comprehension with one targeted open-ended prompt."
                    )
            elif engagement < 55.0 and audio < 25.0:
                suggestion = (
                    "Attention and vocal interaction dropped sharply—pause lecture delivery for a 60-second live concept check poll.\n"
                    "Pose an open-ended applied question to re-engage learners showing downward gaze."
                )
            elif gaze < 60.0:
                suggestion = (
                    "Visual focus is drifting from the screen—summarize the key takeaway of the current slide before advancing.\n"
                    "Use a visual schematic or quick whiteboard example to re-anchor classroom attention."
                )
            elif audio >= 65.0 and gaze >= 70.0:
                suggestion = (
                    "Strong active discussion and visual focus detected—extend peer Q&A by 2 minutes to consolidate mastery.\n"
                    "Capture top student questions in the Lobby board for exam revision."
                )
            elif gaze >= 68.0 and audio < 25.0:
                suggestion = (
                    "Steady silent note-taking detected—maintain current pacing without rushing complex equations.\n"
                    "Run a brief comprehension check in 5 minutes once learners finish transcribing notes."
                )
            else:
                suggestion = (
                    "Classroom pacing and multimodal engagement are balanced—maintain current instructional cadence.\n"
                    "Invite one clarifying question before transitioning to the next subtopic."
                )

        log_suggestion(session_id=session_id, engagement_level=engagement, suggestion=f"[{category}] {suggestion}")
        return {"category": category, "text": suggestion}

    def generate_suggestion(self, session_id: str, metrics: dict, present_count: int, total_students: int) -> str:
        return self.generate_advice(session_id, metrics, present_count, total_students)["text"]

    def generate_executive_report(
        self,
        session_id: str,
        df_att: pd.DataFrame,
        df_eng: pd.DataFrame,
        df_sug: pd.DataFrame,
        df_proctor: pd.DataFrame | None = None,
        lobby_code: str = "LOBBY-ECE301",
        subject_name: str = "Digital Signal Processing",
    ) -> tuple[str, bytes]:
        """Compiles Markdown + Branded Auto-Session PDF including attendance, proctoring & telemetry."""
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_roster = len(df_att)
        present_cnt = int(df_att["status"].astype(str).str.startswith("Present").sum()) if not df_att.empty else 0
        att_rate = round((present_cnt / total_roster) * 100, 1) if total_roster > 0 else 0.0
        proctor_cnt = len(df_proctor) if df_proctor is not None and not df_proctor.empty else 0

        if not df_eng.empty:
            avg_eng = round(float(df_eng["total_engagement"].mean()), 1)
            avg_gaze = round(float(df_eng["gaze_score"].mean()), 1)
            avg_move = round(float(df_eng["movement_score"].mean()), 1)
            avg_audio = round(float(df_eng["audio_score"].mean()), 1)
            peak_row = df_eng.loc[df_eng["total_engagement"].idxmax()]
            low_row = df_eng.loc[df_eng["total_engagement"].idxmin()]
            peak_str = f"{peak_row['total_engagement']}% at {peak_row['timestamp']}"
            low_str = f"{low_row['total_engagement']}% at {low_row['timestamp']}"
        else:
            avg_eng = avg_gaze = avg_move = avg_audio = 0.0
            peak_str = low_str = "No telemetry recorded"

        if avg_eng >= 75:
            tier = "strong sustained learner attentiveness and healthy multimodal participation"
            next_step = "Continue pairing short derivations with active Q&A checkpoints."
        elif avg_eng >= 55:
            tier = "moderate engagement with periodic mid-lecture attention fluctuations"
            next_step = "Insert a 90-second concept poll at the 20-minute mark in the next session."
        else:
            tier = "elevated attention fatigue and low vocal participation"
            next_step = "Chunk theoretical proofs into 10-minute modules with worked visual examples."

        exec_summary = (
            f"Session {session_id} ({subject_name} | {lobby_code}) recorded {tier}. "
            f"Verified Attendance: {present_cnt}/{total_roster} ({att_rate}%). Mean Engagement: {avg_eng}% "
            f"(Peak: {peak_str}; Lowest Dip: {low_str}). Window-Focus Proctoring logged {proctor_cnt} incident(s). "
            f"Recommended Next Action: {next_step}"
        )

        att_md = (
            df_att[["student_id", "name", "presence_ratio", "status"]].to_markdown(index=False)
            if not df_att.empty
            else "_No attendance entries recorded._"
        )
        proctor_md = (
            df_proctor[["timestamp", "student_name", "event_type", "strike_count", "action_taken"]].to_markdown(index=False)
            if df_proctor is not None and not df_proctor.empty
            else "_Zero tab-switch or window-exit violations recorded._"
        )

        md_report = f"""# AttendAI — Automated Session Report
**Session ID:** `{session_id}`  
**Lobby / Subject:** `{lobby_code}` • {subject_name}  
**Generated At:** {generated_at}  
**Privacy & Safety:** 100% Edge Processing • 0 Raw Images Stored • Proctoring Active

---

## 1. Executive Pedagogical Summary
{exec_summary}

## 2. Multimodal Session Telemetry
| Metric | Value |
| :--- | :--- |
| Verified Attendance | **{present_cnt} / {total_roster}** ({att_rate}%) |
| Mean Overall Engagement | **{avg_eng}%** |
| Visual Gaze / Posture / Audio | **{avg_gaze}% / {avg_move}% / {avg_audio}%** |
| Peak / Lowest Window | **{peak_str}** / **{low_str}** |
| Focus Proctoring Incidents | **{proctor_cnt}** |

## 3. Verified Attendance Roster
{att_md}

## 4. Tab-Switch & Window-Exit Proctoring Audit
{proctor_md}
"""

        pdf_lines: list[tuple[str, str]] = [
            ("h2", "1. Executive Pedagogical Summary"),
            ("body", exec_summary),
            ("body", ""),
            ("h2", "2. Multimodal Session Telemetry"),
            ("bold", f"Attendance: {present_cnt}/{total_roster} ({att_rate}%)  |  Mean Engagement: {avg_eng}%  |  Proctor Alerts: {proctor_cnt}"),
            ("body", f"Visual Gaze: {avg_gaze}%  |  Posture & Motion: {avg_move}%  |  Vocal Audio: {avg_audio}%"),
            ("body", f"Peak Engagement: {peak_str}  |  Lowest Dip: {low_str}"),
            ("body", ""),
            ("h2", "3. Verified Sustained-Presence Attendance Roster"),
        ]
        if not df_att.empty:
            for _, row in df_att.iterrows():
                pdf_lines.append(
                    ("body", f"{row['student_id']} | {row['name']} | Presence: {row['presence_ratio']}% | Status: {row['status']}")
                )
        else:
            pdf_lines.append(("body", "No attendance entries recorded."))

        pdf_lines.append(("body", ""))
        pdf_lines.append(("h2", "4. Tab-Switch & Window-Exit Proctoring Log"))
        if df_proctor is not None and not df_proctor.empty:
            for _, row in df_proctor.head(10).iterrows():
                pdf_lines.append(
                    (
                        "body",
                        f"[{row['timestamp']}] {row['student_name']} ({row['student_id']}) - {row['event_type']} "
                        f"({row['duration_sec']}s) | Strikes: {row['strike_count']}/{row['max_strikes']} -> {row['action_taken']}",
                    )
                )
        else:
            pdf_lines.append(("body", "Zero tab-switch or window-exit violations recorded."))

        pdf_lines.append(("body", ""))
        pdf_lines.append(("h2", "5. AI Teaching Coach Interventions"))
        if not df_sug.empty:
            for _, row in df_sug.head(8).iterrows():
                pdf_lines.append(("body", f"[{row['timestamp']} | Eng: {row['engagement_level']}%] {str(row['suggestion']).replace(chr(10), ' ')}"))
        else:
            pdf_lines.append(("body", "No AI interventions triggered."))

        pdf_bytes = _build_pdf_bytes(
            title=f"AttendAI Session Report - {subject_name}",
            subtitle=f"Session: {session_id} | Lobby: {lobby_code} | Generated: {generated_at}",
            lines=pdf_lines,
        )
        return md_report, pdf_bytes