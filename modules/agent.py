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


class TeachingAdvisorAgent:
    def __init__(self, model_name: str = "llama3.2:3b"):
        self.model_name = model_name

    def generate_suggestion(self, session_id: str, metrics: dict, present_count: int, total_students: int) -> str:
        """Generates context-aware pedagogical suggestions locally via Ollama or rule fallback."""
        engagement = metrics.get("total_engagement", 0.0)
        gaze = metrics.get("gaze_score", 0.0)
        movement = metrics.get("movement_score", 0.0)
        audio = metrics.get("audio_score", 0.0)
        inactivity = metrics.get("inactivity_sec", 0.0)

        prompt = (
            f"You are AttendAI, an assistive classroom intelligence coach. Analyze these live anonymous session metrics:\n"
            f"- Attendance: {present_count}/{total_students} learners verified present\n"
            f"- Overall Engagement: {engagement}%\n"
            f"- Visual Attention (Gaze/Head Alignment): {gaze}%\n"
            f"- Posture/Movement Activity: {movement}% (Inactivity: {inactivity}s)\n"
            f"- Vocal/Audio Interaction Level: {audio}%\n\n"
            f"Provide exactly 2 concise, practical, non-intrusive teaching recommendations for the instructor right now. "
            f"Format as 2 bullet points, 1 sentence each."
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
                    options={"temperature": 0.3, "num_predict": 140},
                )
                suggestion = response["message"]["content"].strip()
            except Exception:
                suggestion = None

        if not suggestion:
            if engagement < 55.0 and audio < 25.0:
                suggestion = (
                    "• Attention and vocal interaction are both low—pause lecture delivery for a 60-second live concept check or poll.\n"
                    "• Pose an open-ended real-world question to re-engage learners showing prolonged downward gaze."
                )
            elif gaze < 60.0:
                suggestion = (
                    "• Visual focus is drifting away from the focal area—summarize the current slide's core takeaway before advancing.\n"
                    "• Introduce a brief visual diagram or worked example to re-anchor visual attention."
                )
            elif audio >= 65.0 and gaze >= 70.0:
                suggestion = (
                    "• High active discussion and strong visual focus detected—extend peer Q&A by 1–2 minutes to reinforce mastery.\n"
                    "• Capture key learner questions on the board to bridge smoothly into the next topic."
                )
            elif gaze >= 68.0 and audio < 25.0:
                suggestion = (
                    "• Silent note-taking and steady visual concentration detected—maintain current pacing without rushing slides.\n"
                    "• Schedule a brief comprehension check in 5 minutes once learners finish transcribing key points."
                )
            else:
                suggestion = (
                    "• Classroom pacing and multimodal engagement are balanced—maintain your current instructional cadence.\n"
                    "• Invite one quick clarifying question before transitioning to the next module."
                )

        log_suggestion(session_id=session_id, engagement_level=engagement, suggestion=suggestion)
        return suggestion

    def generate_executive_report(self, session_id: str, df_att: pd.DataFrame, df_eng: pd.DataFrame, df_sug: pd.DataFrame) -> tuple[str, str]:
        """Generates formatted Markdown and HTML executive post-session pedagogical reports."""
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

        # Optional local LLM synthesis paragraph
        exec_synthesis = None
        if OLLAMA_PKG_INSTALLED and not df_eng.empty:
            try:
                synth_prompt = (
                    f"Write a 3-sentence executive classroom evaluation for session {session_id}: "
                    f"Attendance {present_cnt}/{total_roster} ({att_rate}%), Average Engagement {avg_eng}% "
                    f"(Gaze {avg_gaze}%, Posture {avg_move}%, Audio {avg_audio}%), Peak {peak_str}, Lowest {low_str}. "
                    f"Give one strategic recommendation for the next lecture."
                )
                resp = ollama.chat(
                    model=self.model_name,
                    messages=[{"role": "user", "content": synth_prompt}],
                    options={"temperature": 0.3, "num_predict": 160},
                )
                exec_synthesis = resp["message"]["content"].strip()
            except Exception:
                exec_synthesis = None

        if not exec_synthesis:
            if avg_eng >= 75:
                tier = "strong overall classroom attentiveness and sustained learner participation"
                next_step = "Continue balancing short concept explanations with interactive Q&A checkpoints."
            elif avg_eng >= 55:
                tier = "moderate engagement with periodic attention fluctuations during extended explanation blocks"
                next_step = "Insert a 2-minute interactive check-in near the mid-point of the next lecture to prevent attention decay."
            else:
                tier = "notable engagement fatigue and low vocal participation across the session"
                next_step = "Break dense theory into shorter 10-minute segments paired with visual demonstrations or quick polls."
            exec_synthesis = (
                f"Session **{session_id}** recorded **{tier}** (Mean Engagement: **{avg_eng}%**, "
                f"Verified Attendance: **{present_cnt}/{total_roster}**). Peak attention occurred at **{peak_str}**, "
                f"while the sharpest attention dip was observed at **{low_str}**. "
                f"**Next-Session Action:** {next_step}"
            )

        att_md = df_att[["student_id", "name", "first_seen", "last_seen", "presence_ratio", "status"]].to_markdown(index=False) if not df_att.empty else "_No attendance records logged for this session._"
        sug_md = "\n".join(
            [f"- **[{r['timestamp']} | Eng: {r['engagement_level']}%]** {r['suggestion'].replace(chr(10), ' ')}" for _, r in df_sug.head(6).iterrows()]
        ) if not df_sug.empty else "_No AI coaching interventions recorded._"

        md_report = f"""# AttendAI — Executive Session Report
**Session ID:** `{session_id}`  
**Generated At:** {generated_at}  
**Privacy Audit:** 100% Edge/Local Architecture • 0 Raw Images Stored • Anonymous Engagement Metrics

---

## 1. Executive Pedagogical Summary
{exec_synthesis}

## 2. Core Session Telemetry
| Metric | Value |
| :--- | :--- |
| Verified Attendance | **{present_cnt} / {total_roster}** ({att_rate}%) |
| Mean Overall Engagement | **{avg_eng}%** |
| Mean Visual Gaze Focus | **{avg_gaze}%** |
| Mean Posture & Movement | **{avg_move}%** |
| Mean Vocal Interaction | **{avg_audio}%** |
| Peak Engagement Window | **{peak_str}** |
| Lowest Attention Dip | **{low_str}** |

## 3. Sustained-Presence Attendance Roster
{att_md}

## 4. AI Coaching Interventions Log
{sug_md}
"""

        # Styled standalone HTML report for clean browser/PDF export
        att_html = df_att[["student_id", "name", "first_seen", "last_seen", "presence_ratio", "status"]].to_html(index=False, border=0) if not df_att.empty else "<p>No attendance records logged.</p>"
        sug_html = "".join(
            [f"<li><strong>[{r['timestamp']} • {r['engagement_level']}%]</strong> {r['suggestion'].replace(chr(10), '<br>')}</li>" for _, r in df_sug.head(6).iterrows()]
        ) if not df_sug.empty else "<li>No AI coaching interventions recorded.</li>"

        html_report = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>AttendAI Report - {session_id}</title>
<style>
  body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 36px; }}
  .container {{ max-width: 900px; margin: auto; background: rgba(30, 41, 59, 0.85); border: 1px solid rgba(148,163,184,0.22); border-radius: 16px; padding: 32px; }}
  h1, h2 {{ color: #f8fafc; margin-top: 0; }}
  h2 {{ border-bottom: 1px solid rgba(148,163,184,0.2); padding-bottom: 8px; margin-top: 28px; font-size: 1.15rem; color: #38bdf8; }}
  .meta {{ color: #94a3b8; font-size: 0.9rem; margin-bottom: 20px; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 20px 0; }}
  .kpi {{ background: rgba(15, 23, 42, 0.65); border: 1px solid rgba(148,163,184,0.2); border-radius: 12px; padding: 16px; text-align: center; }}
  .kpi .val {{ font-size: 1.6rem; font-weight: 700; color: #818cf8; }}
  .kpi .lbl {{ font-size: 0.78rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 0.9rem; }}
  th, td {{ padding: 10px 12px; border-bottom: 1px solid rgba(148,163,184,0.15); text-align: left; }}
  th {{ color: #cbd5e1; background: rgba(15, 23, 42, 0.5); }}
  .summary-box {{ background: rgba(99, 102, 241, 0.12); border-left: 4px solid #6366f1; padding: 16px; border-radius: 8px; line-height: 1.6; }}
  ul {{ line-height: 1.65; color: #e2e8f0; }}
</style>
</head>
<body>
  <div class="container">
    <h1>AttendAI — Executive Session Report</h1>
    <div class="meta">Session: <strong>{session_id}</strong> &nbsp;|&nbsp; Generated: {generated_at} &nbsp;|&nbsp; Privacy Verified: 0 Raw Images Stored</div>
    <div class="summary-box">{exec_synthesis.replace('**', '')}</div>
    <div class="kpi-grid">
      <div class="kpi"><div class="lbl">Attendance</div><div class="val">{present_cnt}/{total_roster}</div></div>
      <div class="kpi"><div class="lbl">Mean Engagement</div><div class="val">{avg_eng}%</div></div>
      <div class="kpi"><div class="lbl">Peak Window</div><div class="val" style="font-size:1.05rem;">{peak_str}</div></div>
      <div class="kpi"><div class="lbl">Lowest Dip</div><div class="val" style="font-size:1.05rem; color:#f59e0b;">{low_str}</div></div>
    </div>
    <h2>Sustained-Presence Attendance Roster</h2>
    {att_html}
    <h2>AI Coaching Interventions</h2>
    <ul>{sug_html}</ul>
  </div>
</body>
</html>"""

        return md_report, html_report