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
    """Checks if local Ollama daemon is reachable without blocking startup."""
    if not OLLAMA_PKG_INSTALLED:
        return False, "Rule-Based Fallback (Cloud Mode)"
    try:
        ollama.list()
        return True, f"Ollama Local ({model_name})"
    except Exception:
        return False, "Rule-Based Fallback (Ollama Offline)"


def _build_pdf_bytes(title: str, subtitle: str, lines: list[tuple[str, str]]) -> bytes:
    """Pure-Python minimal PDF 1.4 builder with zero external dependencies."""
    def esc(text: str) -> str:
        safe = text.encode("latin-1", "replace").decode("latin-1")
        return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    # Paginate into chunks of 46 lines
    wrapped_lines: list[tuple[str, str]] = []
    for style, raw_line in lines:
        if not raw_line.strip():
            wrapped_lines.append(("body", ""))
            continue
        width = 74 if style == "h2" else 88
        for chunk in textwrap.wrap(raw_line, width=width) or [""]:
            wrapped_lines.append((style, chunk))

    pages_content: list[bytes] = []
    per_page = 44
    total_chunks = max(1, (len(wrapped_lines) + per_page - 1) // per_page)

    for page_idx in range(total_chunks):
        chunk = wrapped_lines[page_idx * per_page : (page_idx + 1) * per_page]
        cmds = ["BT"]
        y = 752
        if page_idx == 0:
            cmds.append(f"/F2 17 Tf 48 {y} Td ({esc(title)}) Tj")
            y -= 18
            cmds.append(f"/F1 9.5 Tf 0 -18 Td ({esc(subtitle)}) Tj")
            y -= 26
            cmds.append("ET")
            cmds.append("0.75 0.78 0.85 RG 0.8 w 48 720 m 564 720 l S")
            cmds.append("BT")
            cmds.append(f"/F1 10 Tf 48 {y} Td")
        else:
            cmds.append(f"/F1 10 Tf 48 {y} Td")

        for style, line in chunk:
            if style == "h2":
                cmds.append(f"/F2 12 Tf 0 -18 Td ({esc(line)}) Tj /F1 10 Tf")
            elif style == "bold":
                cmds.append(f"/F2 10 Tf 0 -14 Td ({esc(line)}) Tj /F1 10 Tf")
            else:
                cmds.append(f"0 -14 Td ({esc(line)}) Tj")

        cmds.append("ET")
        cmds.append(f"BT /F1 8.5 Tf 48 28 Td (AttendAI Edge Classroom Intelligence - Page {page_idx + 1} of {total_chunks}) Tj ET")
        pages_content.append("\n".join(cmds).encode("latin-1"))

    # Assemble PDF objects: 1=Catalog, 2=Pages, 3=Helvetica, 4=Helvetica-Bold, then Page+Stream pairs
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

    trailer = (
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode("latin-1")
    buf.extend(trailer)
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
        """Generates categorized pedagogical advice locally via Ollama or rule fallback."""
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
                f"Respond in 2 concise, practical sentences tailored to the live classroom metrics."
            )
        else:
            prompt = (
                f"You are AttendAI, an assistive classroom intelligence coach. Analyze these live anonymous session metrics:\n"
                f"- Attendance: {present_count}/{total_students} learners verified present\n"
                f"- Overall Engagement: {engagement}%\n"
                f"- Visual Attention (Gaze/Head Alignment): {gaze}%\n"
                f"- Posture/Movement Activity: {movement}% (Inactivity: {inactivity}s)\n"
                f"- Vocal/Audio Interaction Level: {audio}%\n\n"
                f"Provide exactly 2 concise, practical teaching recommendations (1 sentence each)."
            )

        suggestion = None
        if OLLAMA_PKG_INSTALLED:
            try:
                response = ollama.chat(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": "You provide concise, supportive, evidence-based pedagogical guidance."},
                        {"role": "user", "content": prompt},
                    ],
                    options={"temperature": 0.3, "num_predict": 150},
                )
                suggestion = response["message"]["content"].strip()
            except Exception:
                suggestion = None

        if not suggestion:
            if custom_question:
                q_low = custom_question.lower()
                if any(k in q_low for k in ["poll", "quiz", "question", "engage", "attention", "bored", "dip"]):
                    suggestion = (
                        f"With current engagement at {engagement}% (Gaze {gaze}%, Audio {audio}%), run a 60-second multiple-choice concept check on the last slide. "
                        f"Pair learners for 45 seconds to compare answers before calling on one group to explain."
                    )
                elif any(k in q_low for k in ["pace", "fast", "slow", "break", "time"]):
                    suggestion = (
                        f"Current visual focus ({gaze}%) and posture activity ({movement}%) indicate learners benefit from chunked transitions. "
                        f"Pause for a 90-second recap of the core formula before advancing to the next section."
                    )
                else:
                    suggestion = (
                        f"Based on live telemetry (Engagement {engagement}%, Gaze {gaze}%, Vocal {audio}%), anchor your next point with a concrete worked example. "
                        f"Follow immediately with one open-ended prompt to verify comprehension across the room."
                    )
            elif engagement < 55.0 and audio < 25.0:
                suggestion = (
                    "Attention and vocal interaction are both low—pause lecture delivery for a 60-second live concept check or poll.\n"
                    "Pose an open-ended real-world question to re-engage learners showing prolonged downward gaze."
                )
            elif gaze < 60.0:
                suggestion = (
                    "Visual focus is drifting away from the focal area—summarize the current slide's core takeaway before advancing.\n"
                    "Introduce a brief visual diagram or worked example to re-anchor visual attention."
                )
            elif audio >= 65.0 and gaze >= 70.0:
                suggestion = (
                    "High active discussion and strong visual focus detected—extend peer Q&A by 1-2 minutes to reinforce mastery.\n"
                    "Capture key learner questions on the board to bridge smoothly into the next module."
                )
            elif gaze >= 68.0 and audio < 25.0:
                suggestion = (
                    "Silent note-taking and steady visual concentration detected—maintain current pacing without rushing slides.\n"
                    "Schedule a brief comprehension check in 5 minutes once learners finish transcribing key points."
                )
            else:
                suggestion = (
                    "Classroom pacing and multimodal engagement are balanced—maintain your current instructional cadence.\n"
                    "Invite one quick clarifying question before transitioning to the next topic."
                )

        log_suggestion(session_id=session_id, engagement_level=engagement, suggestion=f"[{category}] {suggestion}")
        return {"category": category, "text": suggestion}

    def generate_suggestion(self, session_id: str, metrics: dict, present_count: int, total_students: int) -> str:
        """Backward-compatible wrapper returning plain suggestion text."""
        return self.generate_advice(session_id, metrics, present_count, total_students)["text"]

    def generate_executive_report(
        self,
        session_id: str,
        df_att: pd.DataFrame,
        df_eng: pd.DataFrame,
        df_sug: pd.DataFrame,
    ) -> tuple[str, bytes]:
        """Generates formatted Markdown summary and a downloadable PDF report."""
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_roster = len(df_att)
        present_cnt = int((df_att["status"] == "Present").sum()) if not df_att.empty else 0
        att_rate = round((present_cnt / total_roster) * 100, 1) if total_roster > 0 else 0.0

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
            tier = "strong overall classroom attentiveness and sustained learner participation"
            next_step = "Continue balancing short concept explanations with interactive Q&A checkpoints."
        elif avg_eng >= 55:
            tier = "moderate engagement with periodic attention fluctuations during extended explanation blocks"
            next_step = "Insert a 2-minute interactive check-in near the mid-point of the next lecture to prevent attention decay."
        else:
            tier = "notable engagement fatigue and low vocal participation across the session"
            next_step = "Break dense theory into 10-minute segments paired with visual demonstrations or quick polls."

        exec_synthesis = (
            f"Session {session_id} recorded {tier} (Mean Engagement: {avg_eng}%, "
            f"Verified Attendance: {present_cnt}/{total_roster}). Peak attention occurred at {peak_str}, "
            f"while the sharpest dip occurred at {low_str}. Next-Session Action: {next_step}"
        )

        att_md = (
            df_att[["student_id", "name", "first_seen", "last_seen", "presence_ratio", "status"]].to_markdown(index=False)
            if not df_att.empty
            else "_No attendance records logged for this session._"
        )
        sug_md = (
            "\n".join(
                [
                    f"- **[{r['timestamp']} | Eng: {r['engagement_level']}%]** {r['suggestion'].replace(chr(10), ' ')}"
                    for _, r in df_sug.head(8).iterrows()
                ]
            )
            if not df_sug.empty
            else "_No AI coaching interventions recorded._"
        )

        md_report = f"""# AttendAI — Executive Session Report
**Session ID:** `{session_id}`  
**Generated At:** {generated_at}  
**Privacy Audit:** 100% Edge/Local Architecture • 0 Raw Images Stored • Anonymous Engagement Telemetry

---

## 1. Executive Pedagogical Summary
{exec_synthesis}

## 2. Core Session Telemetry
| Metric | Value |
| :--- | :--- |
| Verified Attendance | **{present_cnt} / {total_roster}** ({att_rate}%) |
| Mean Overall Engagement | **{avg_eng}%** |
| Mean Visual Gaze Focus | **{avg_gaze}%** |
| Mean Posture & Motion | **{avg_move}%** |
| Mean Vocal Interaction | **{avg_audio}%** |
| Peak Engagement Window | **{peak_str}** |
| Lowest Attention Dip | **{low_str}** |

## 3. Sustained-Presence Attendance Roster
{att_md}

## 4. AI Coaching Interventions Log
{sug_md}
"""

        pdf_lines: list[tuple[str, str]] = [
            ("h2", "1. Executive Pedagogical Summary"),
            ("body", exec_synthesis),
            ("body", ""),
            ("h2", "2. Core Session Telemetry"),
            ("bold", f"Verified Attendance: {present_cnt}/{total_roster} ({att_rate}%)  |  Mean Engagement: {avg_eng}%"),
            ("body", f"Visual Gaze: {avg_gaze}%  |  Posture & Motion: {avg_move}%  |  Vocal Audio: {avg_audio}%"),
            ("body", f"Peak Window: {peak_str}  |  Lowest Attention Dip: {low_str}"),
            ("body", ""),
            ("h2", "3. Sustained-Presence Attendance Roster"),
        ]
        if not df_att.empty:
            for _, row in df_att.iterrows():
                pdf_lines.append(
                    (
                        "body",
                        f"{row['student_id']} | {row['name']} | {row['presence_ratio']}% | {row['status']} ({row['first_seen']} - {row['last_seen']})",
                    )
                )
        else:
            pdf_lines.append(("body", "No attendance records logged for this session."))

        pdf_lines.append(("body", ""))
        pdf_lines.append(("h2", "4. AI Teaching Coach Interventions"))
        if not df_sug.empty:
            for _, row in df_sug.head(8).iterrows():
                clean_sug = str(row["suggestion"]).replace("\n", " ")
                pdf_lines.append(("body", f"[{row['timestamp']} | {row['engagement_level']}%] {clean_sug}"))
        else:
            pdf_lines.append(("body", "No AI coaching interventions recorded."))

        pdf_bytes = _build_pdf_bytes(
            title="AttendAI - Executive Session Report",
            subtitle=f"Session: {session_id}  |  Generated: {generated_at}  |  Privacy: 0 Raw Images Stored",
            lines=pdf_lines,
        )
        return md_report, pdf_bytes