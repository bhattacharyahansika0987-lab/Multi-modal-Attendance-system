import base64
import cv2
import time
import random
import tempfile
import importlib.util
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timedelta

from modules.database import (
    init_db,
    seed_commercial_demo_data,
    load_all_students,
    save_student,
    delete_student,
    seed_sample_roster,
    log_attendance,
    log_engagement,
    get_session_list,
    get_session_data,
    log_proctor_incident,
    get_proctor_incidents,
    save_session_report,
    get_session_reports,
    get_lobbies,
    create_lobby,
    join_lobby_teacher,
    get_lobby_teachers,
    set_lobby_active_host,
    add_lobby_assignment,
    get_lobby_assignments,
    get_student_subject_records,
    compute_student_cumulative_summary,
    compute_internal_grade,
    compute_recovery_classes,
    get_daily_logs,
    create_dispute_ticket,
    get_dispute_tickets,
    resolve_dispute_ticket,
    dispatch_notification,
    dispatch_below_75_warnings,
    get_notifications,
    acknowledge_notification,
)
from modules.attendance import SustainedAttendanceTracker
from modules.engagement import MultimodalEngagementAnalyzer, AUDIO_AVAILABLE
from modules.agent import TeachingAdvisorAgent, check_ollama_status
from modules.styles import (
    SVG_ICONS,
    get_app_css,
    render_top_nav_html,
    render_kpi_html,
    render_seat_card_html,
    render_coach_card_html,
    render_focus_guard_widget,
    render_auto_pdf_download_script,
)

# --- Page Configuration ---
st.set_page_config(
    page_title="AttendAI • Commercial Classroom Intelligence",
    page_icon=":material/verified_user:",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
seed_commercial_demo_data()
st.markdown(get_app_css(), unsafe_allow_html=True)

PLOTLY_CFG = {"displayModeBar": False}
PLOTLY_HOVER = dict(
    bgcolor="#141D33",
    bordercolor="rgba(148, 163, 184, 0.28)",
    font=dict(color="#F8FAFC", family="Inter", size=12),
)


@st.cache_resource(show_spinner="Loading local InsightFace (buffalo_sc) model...")
def get_face_analyzer():
    from insightface.app import FaceAnalysis

    face_app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
    face_app.prepare(ctx_id=0, det_size=(320, 320))
    return face_app


@st.cache_data(ttl=30)
def get_diagnostics():
    ollama_ok, ollama_label = check_ollama_status()
    return {
        "ollama_ok": ollama_ok,
        "ollama_label": ollama_label,
        "insightface_ok": importlib.util.find_spec("insightface") is not None,
        "audio_ok": AUDIO_AVAILABLE,
    }


def _init_live_seats() -> list[dict]:
    roster = load_all_students()
    seats = []
    for idx, s in enumerate(roster[:6]):
        is_flagged = s["student_id"] == "S104"
        seats.append({
            "student_id": s["student_id"],
            "name": s["name"],
            "presence": 62.0 if is_flagged else round(86.0 + (idx % 3) * 4.0, 1),
            "focus_state": "Drifting" if is_flagged else "Focused",
            "strikes": 2 if is_flagged else 0,
            "status": "Verifying" if is_flagged else "Verified Present",
        })
    return seats


# --- Session State Initialization ---
defaults = {
    "user_role": "Instructor / Mentor",
    "active_lobby": "LOBBY-ECE301",
    "active_student_id": "S104",  # Pre-selected <75% student to highlight warnings, calculator & disputes
    "session_id": datetime.now().strftime("SESS_%Y%m%d_%H%M%S"),
    "stream_playing": False,
    "stream_speed": "1x",
    "max_strikes": 3,
    "scheduled_minutes": 15,
    "session_remaining_sec": 900,
    "running_video": False,
    "sim_gaze": 86,
    "sim_move": 84,
    "sim_audio": 72,
    "latest_metrics": {
        "total_engagement": 82.0,
        "gaze_score": 86.0,
        "movement_score": 84.0,
        "audio_score": 72.0,
        "inactivity_sec": 1.2,
    },
    "prev_metrics": {
        "total_engagement": 79.5,
        "gaze_score": 83.0,
        "movement_score": 82.0,
        "audio_score": 70.0,
        "inactivity_sec": 1.5,
    },
    "engagement_history": [
        {"Time": "09:30", "Overall": 81.2, "Visual Gaze": 84.0, "Posture & Motion": 82.0, "Vocal Audio": 75.0},
        {"Time": "09:33", "Overall": 79.5, "Visual Gaze": 83.0, "Posture & Motion": 82.0, "Vocal Audio": 70.0},
        {"Time": "09:36", "Overall": 82.0, "Visual Gaze": 86.0, "Posture & Motion": 84.0, "Vocal Audio": 72.0},
    ],
    "suggestion_feed": [
        {
            "category": "Participation",
            "time": "09:36:10",
            "text": "Strong visual focus and Q&A participation across ECE501. Keep Rohan Verma (2/3 Focus Strikes) engaged with a direct concept check.",
            "applied": False,
        }
    ],
    "live_seats": _init_live_seats(),
    "drop_alert": None,
    "auto_pdf_payload": None,
    "last_generated_pdf": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# --- Core Engine Helpers ---
def get_active_lobby_obj() -> dict:
    lobbies = get_lobbies()
    for lb in lobbies:
        if lb["lobby_code"] == st.session_state.active_lobby:
            return lb
    return lobbies[0] if lobbies else {
        "lobby_code": "LOBBY-ECE301",
        "name": "ECE Semester V Core Cohort",
        "cohort": "B.Tech ECE",
        "active_host": "Dr. Vikram Deshmukh",
        "active_subject": "Digital Signal Processing",
    }


def compute_deltas(cur: dict, prev: dict | None) -> dict:
    if not prev:
        return {k: None for k in ["total_engagement", "gaze_score", "movement_score", "audio_score"]}
    return {k: round(cur[k] - prev[k], 1) for k in ["total_engagement", "gaze_score", "movement_score", "audio_score"]}


def record_focus_violation(student_id: str, event_type: str = "Tab Switch / Window Exit", duration_sec: float = 14.2):
    """Applies a proctoring strike; auto-marks ABSENT and alerts Parent/Mentor when limit is reached."""
    max_s = int(st.session_state.max_strikes)
    for seat in st.session_state.live_seats:
        if seat["student_id"] == student_id:
            seat["strikes"] += 1
            if seat["strikes"] >= max_s:
                seat["status"] = "Absent (Focus Violation)"
                seat["focus_state"] = "Focus Breached"
                seat["presence"] = max(20.0, seat["presence"] - 25.0)
                action = f"Marked ABSENT (Limit {max_s}/{max_s}) + Parent & Mentor Alerted"
                for role in ("Parent", "Student", "Instructor"):
                    dispatch_notification(
                        recipient_role=role,
                        student_id=seat["student_id"],
                        student_name=seat["name"],
                        category="Focus Proctoring",
                        severity="Critical",
                        title=f"Absent Override (Tab-Switch Violation) — {seat['name']}",
                        message=(
                            f"{seat['name']} ({seat['student_id']}) exceeded the window-focus limit "
                            f"({seat['strikes']}/{max_s} strikes) in {get_active_lobby_obj()['active_subject']} "
                            f"and was automatically marked ABSENT."
                        ),
                        channels="Portal • SMS • Email",
                    )
            else:
                seat["focus_state"] = "Tab-Switch Warning"
                action = f"Strike Warning Issued ({seat['strikes']}/{max_s})"

            log_proctor_incident(
                session_id=st.session_state.session_id,
                student_id=seat["student_id"],
                student_name=seat["name"],
                event_type=event_type,
                duration_sec=duration_sec,
                strike_count=seat["strikes"],
                max_strikes=max_s,
                action_taken=action,
            )
            return seat["name"], seat["strikes"], action
    return None, 0, ""


def finalize_and_auto_generate_pdf():
    """Concludes scheduled session, persists attendance, compiles PDF, archives it, and triggers auto-download."""
    lobby = get_active_lobby_obj()
    sess_id = st.session_state.session_id
    now_t = datetime.now().strftime("%H:%M:%S")

    # Persist live seat attendance snapshot
    for seat in st.session_state.live_seats:
        log_attendance(
            session_id=sess_id,
            student_id=seat["student_id"],
            name=seat["name"],
            first_seen="09:30:00",
            last_seen=now_t,
            ratio=seat["presence"],
            status="Present" if "Present" in seat["status"] else seat["status"],
        )

    df_att, df_eng, df_sug = get_session_data(sess_id)
    if df_eng.empty and st.session_state.engagement_history:
        for row in st.session_state.engagement_history[-6:]:
            log_engagement(sess_id, row["Visual Gaze"], row["Posture & Motion"], row["Vocal Audio"], row["Overall"])
        df_att, df_eng, df_sug = get_session_data(sess_id)

    df_proctor = get_proctor_incidents(sess_id)
    agent = TeachingAdvisorAgent()
    md_text, pdf_bytes = agent.generate_executive_report(
        session_id=sess_id,
        df_att=df_att,
        df_eng=df_eng,
        df_sug=df_sug,
        df_proctor=df_proctor,
        lobby_code=lobby["lobby_code"],
        subject_name=lobby["active_subject"],
    )

    b64_pdf = base64.b64encode(pdf_bytes).decode("ascii")
    avg_eng = float(df_eng["total_engagement"].mean()) if not df_eng.empty else st.session_state.latest_metrics["total_engagement"]
    present_cnt = sum(1 for s in st.session_state.live_seats if "Present" in s["status"])

    save_session_report(
        session_id=sess_id,
        lobby_code=lobby["lobby_code"],
        subject_name=lobby["active_subject"],
        avg_engagement=avg_eng,
        present_count=present_cnt,
        total_count=len(st.session_state.live_seats),
        proctor_violations=len(df_proctor),
        pdf_b64=b64_pdf,
    )

    filename = f"AttendAI_AutoReport_{sess_id}.pdf"
    st.session_state.auto_pdf_payload = (filename, b64_pdf)
    st.session_state.last_generated_pdf = (filename, pdf_bytes, md_text)
    st.session_state.stream_playing = False
    st.session_state.session_remaining_sec = int(st.session_state.scheduled_minutes) * 60
    st.session_state.session_id = datetime.now().strftime("SESS_%Y%m%d_%H%M%S")


def push_telemetry_step(gaze: float, move: float, audio: float, trigger_ai: bool = False):
    total = round(0.50 * gaze + 0.25 * move + 0.25 * audio, 1)
    st.session_state.prev_metrics = dict(st.session_state.latest_metrics)
    metrics = {
        "total_engagement": total,
        "gaze_score": round(gaze, 1),
        "movement_score": round(move, 1),
        "audio_score": round(audio, 1),
        "inactivity_sec": 18.0 if move < 52 else 1.4,
    }
    st.session_state.latest_metrics = metrics
    st.session_state.engagement_history.append({
        "Time": datetime.now().strftime("%H:%M:%S"),
        "Overall": total,
        "Visual Gaze": metrics["gaze_score"],
        "Posture & Motion": metrics["movement_score"],
        "Vocal Audio": metrics["audio_score"],
    })
    st.session_state.engagement_history = st.session_state.engagement_history[-24:]
    log_engagement(st.session_state.session_id, metrics["gaze_score"], metrics["movement_score"], metrics["audio_score"], total)

    # Update seat attention dynamics smoothly
    for seat in st.session_state.live_seats:
        if seat["strikes"] < int(st.session_state.max_strikes):
            delta_p = 0.8 if total >= 65 else -1.4
            seat["presence"] = round(min(100.0, max(35.0, seat["presence"] + delta_p)), 1)
            seat["focus_state"] = "Focused" if gaze >= 70 else ("Drifting" if gaze >= 50 else "Inactive")
            seat["status"] = "Verified Present" if seat["presence"] >= 60 else "Verifying"

    # Check >15% drop or <55% threshold
    hist = st.session_state.engagement_history
    recent_peak = max(item["Overall"] for item in hist[-5:]) if len(hist) >= 2 else total
    if recent_peak - total >= 15.0:
        st.session_state.drop_alert = f"Engagement dropped -{round(recent_peak - total, 1)}% ({recent_peak}% -> {total}%). Trigger AI Coach for intervention."
    elif total < 55.0:
        st.session_state.drop_alert = f"At-Risk Attention Alert: Class engagement fell to {total}%. Consider a concept check poll."
    else:
        st.session_state.drop_alert = None

    if trigger_ai:
        agent = TeachingAdvisorAgent()
        present_cnt = sum(1 for s in st.session_state.live_seats if "Present" in s["status"])
        adv = agent.generate_advice(st.session_state.session_id, metrics, present_cnt, max(1, len(st.session_state.live_seats)))
        st.session_state.suggestion_feed.insert(
            0,
            {"category": adv["category"], "time": datetime.now().strftime("%H:%M:%S"), "text": adv["text"], "applied": False},
        )


def auto_tick_simulation():
    """Advances auto-streaming simulation and scheduled session timer every 2 seconds."""
    step_sec = 4 if st.session_state.stream_speed == "2x" else 2
    st.session_state.session_remaining_sec = max(0, st.session_state.session_remaining_sec - step_sec)

    g = float(np.clip(st.session_state.sim_gaze + random.uniform(-3.5, 3.5), 25, 98))
    m = float(np.clip(st.session_state.sim_move + random.uniform(-2.8, 2.8), 30, 96))
    a = float(np.clip(st.session_state.sim_audio + random.uniform(-4.5, 4.5), 8, 95))
    st.session_state.sim_gaze, st.session_state.sim_move, st.session_state.sim_audio = int(g), int(m), int(a)
    push_telemetry_step(g, m, a, trigger_ai=False)

    if st.session_state.session_remaining_sec <= 0:
        finalize_and_auto_generate_pdf()


def build_spline_fig(history: list) -> go.Figure:
    df_h = pd.DataFrame(history)
    fig = go.Figure()
    for name, col, w in [("Overall", "#3B82F6", 3), ("Visual Gaze", "#38BDF8", 2), ("Vocal Audio", "#10B981", 2)]:
        if name in df_h.columns:
            fig.add_trace(
                go.Scatter(
                    x=df_h["Time"],
                    y=df_h[name],
                    mode="lines+markers",
                    name=name,
                    line=dict(color=col, width=w, shape="spline"),
                    marker=dict(size=5, line=dict(width=1, color="#060913")),
                    hovertemplate=f"<b>{name}</b>: %{{y:.1f}}%<extra></extra>",
                )
            )
    fig.add_hline(y=60, line_dash="dot", line_color="rgba(245,158,11,0.55)", annotation_text="60% Watch Line", annotation_font=dict(color="#FBBF24", size=11))
    fig.update_layout(
        height=255,
        margin=dict(l=8, r=8, t=12, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#94A3B8", family="Inter", size=11),
        hovermode="x unified",
        hoverlabel=PLOTLY_HOVER,
        yaxis=dict(range=[0, 105], title="Score %", gridcolor="rgba(148,163,184,0.1)", zeroline=False),
        xaxis=dict(title="", gridcolor="rgba(148,163,184,0.05)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


# --- Sidebar: Role Switcher, Lobby Selector, Proctoring Config & Privacy Diagnostics ---
diag = get_diagnostics()
lobbies = get_lobbies()
lobby_codes = [lb["lobby_code"] for lb in lobbies]
all_students = load_all_students()
student_map = {f"{s['student_id']} — {s['name']}": s["student_id"] for s in all_students}

with st.sidebar:
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:9px;margin-bottom:4px;">'
        f'{SVG_ICONS["shield"]}<span style="font-size:1.1rem;font-weight:800;">Attend<span style="color:#3B82F6;">AI</span></span>'
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption("Commercial EdTech & Edge AI Platform")
    st.divider()

    st.markdown("**Role Perspective Switcher**")
    st.session_state.user_role = st.selectbox(
        "Workspace Role",
        ["Instructor / Mentor", "Student", "Parent / Guardian"],
        index=["Instructor / Mentor", "Student", "Parent / Guardian"].index(st.session_state.user_role),
        label_visibility="collapsed",
    )

    if st.session_state.user_role in ("Student", "Parent / Guardian") and student_map:
        st.markdown("**Active Student / Ward Profile**")
        inv_map = {v: k for k, v in student_map.items()}
        default_lbl = inv_map.get(st.session_state.active_student_id, list(student_map.keys())[0])
        chosen_lbl = st.selectbox(
            "Student Profile",
            list(student_map.keys()),
            index=list(student_map.keys()).index(default_lbl),
            label_visibility="collapsed",
        )
        st.session_state.active_student_id = student_map[chosen_lbl]

    st.markdown("**Active Classroom Lobby**")
    if lobby_codes:
        idx_l = lobby_codes.index(st.session_state.active_lobby) if st.session_state.active_lobby in lobby_codes else 0
        st.session_state.active_lobby = st.selectbox("Lobby Room", lobby_codes, index=idx_l, label_visibility="collapsed")

    st.divider()
    st.markdown("**Session & Proctoring Policy**")
    input_mode = st.radio(
        "Live Input Engine",
        ["Auto-Streaming Simulator", "Live Webcam", "Recorded Video (.mp4)"],
        label_visibility="collapsed",
    )
    st.session_state.max_strikes = st.slider("Tab-Switch Absent Limit (Strikes)", 1, 5, int(st.session_state.max_strikes))
    sched_min = st.slider("Scheduled Session Length (min)", 5, 60, int(st.session_state.scheduled_minutes), 5)
    if sched_min != st.session_state.scheduled_minutes:
        st.session_state.scheduled_minutes = sched_min
        st.session_state.session_remaining_sec = sched_min * 60

    st.divider()
    ollama_cls = "dot-ok" if diag["ollama_ok"] else "dot-warn"
    audio_cls = "dot-ok" if diag["audio_ok"] else "dot-warn"
    st.markdown(
        f"""
        <div class="audit-panel">
            <div style="font-weight:700;color:#F8FAFC;margin-bottom:4px;">Edge Privacy &amp; Trust Audit</div>
            <div><span class="dot-ok">&bull;</span>100% On-Device Processing</div>
            <div><span class="dot-ok">&bull;</span>0 Raw Images Stored (512-D)</div>
            <div><span class="dot-ok">&bull;</span>Role-Masked Parent Portal</div>
            <hr style="border:0;border-top:1px solid rgba(148,163,184,0.12);margin:6px 0;">
            <div><span class="dot-ok">&bull;</span>Vision: InsightFace + Cascades</div>
            <div><span class="{audio_cls}">&bull;</span>Audio: {"WebRTC VAD" if diag["audio_ok"] else "Visual-Only (Cloud)"}</div>
            <div><span class="{ollama_cls}">&bull;</span>Coach: {diag["ollama_label"]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# --- Trigger One-Shot Auto-PDF Browser Download if Session Just Completed ---
if st.session_state.auto_pdf_payload:
    fname, b64_data = st.session_state.auto_pdf_payload
    components.html(render_auto_pdf_download_script(fname, b64_data), height=0)
    st.session_state.auto_pdf_payload = None

# --- Top Commercial Navbar ---
role_filter = {"Instructor / Mentor": "Instructor", "Student": "Student", "Parent / Guardian": "Parent"}[st.session_state.user_role]
unread_df = get_notifications(recipient_role=role_filter)
unread_cnt = int((unread_df["acknowledged"] == 0).sum()) if not unread_df.empty else 0
status_badge = "LIVE STREAM ACTIVE" if st.session_state.stream_playing else ("EDGE AI READY" if diag["ollama_ok"] else "CLOUD DEMO READY")
st.markdown(render_top_nav_html(st.session_state.active_lobby, st.session_state.user_role, status_badge, unread_cnt), unsafe_allow_html=True)

if st.session_state.last_generated_pdf:
    pdf_name, pdf_raw, _ = st.session_state.last_generated_pdf
    b_l, b_r = st.columns([3, 1], vertical_alignment="center")
    with b_l:
        st.success(f"Scheduled session completed — **{pdf_name}** was auto-generated, archived, and dispatched for download.")
    with b_r:
        st.download_button("Re-Download Auto PDF", data=pdf_raw, file_name=pdf_name, mime="application/pdf", icon=":material/picture_as_pdf:", type="primary", width="stretch")


# ==============================================================================
# MODULE A: LIVE COMMAND CENTER + PROCTORING + AUTO-PDF (FRAGMENT ENGINE)
# ==============================================================================
def _render_command_center_body():
    lobby = get_active_lobby_obj()
    if st.session_state.drop_alert:
        st.markdown(f'<div class="alert-banner">{SVG_ICONS["alert"]}<span>{st.session_state.drop_alert}</span></div>', unsafe_allow_html=True)

    # Scheduled Session Control & Auto-PDF Strip
    with st.container(border=True):
        sc1, sc2, sc3, sc4, sc5 = st.columns([1.4, 0.9, 0.85, 0.95, 1.35], vertical_alignment="center")
        mins, secs = divmod(int(st.session_state.session_remaining_sec), 60)
        with sc1:
            st.markdown(f'<div class="sec-title">{lobby["active_subject"]}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="sec-sub" style="margin:0;">Host: {lobby["active_host"]} &bull; {lobby["lobby_code"]}</div>', unsafe_allow_html=True)
        with sc2:
            st.markdown(
                f'<div style="text-align:center;"><div style="font-size:0.68rem;color:#94A3B8;text-transform:uppercase;">Scheduled Timer</div>'
                f'<div class="countdown-val" style="font-size:1.35rem;font-weight:700;color:#38BDF8;">{mins:02d}:{secs:02d}</div></div>',
                unsafe_allow_html=True,
            )
        with sc3:
            if st.session_state.stream_playing:
                if st.button("Pause Stream", icon=":material/pause:", width="stretch"):
                    st.session_state.stream_playing = False
                    st.rerun()
            else:
                if st.button("Play Stream", icon=":material/play_arrow:", type="primary", width="stretch"):
                    st.session_state.stream_playing = True
                    st.rerun()
        with sc4:
            st.session_state.stream_speed = st.selectbox("Speed", ["1x", "2x"], index=0 if st.session_state.stream_speed == "1x" else 1, label_visibility="collapsed")
        with sc5:
            if st.button("End Session & Auto-PDF", icon=":material/picture_as_pdf:", width="stretch"):
                finalize_and_auto_generate_pdf()
                st.rerun()

    # 4 Animated KPI Cards with Mini Sparklines
    m = st.session_state.latest_metrics
    d = compute_deltas(m, st.session_state.prev_metrics)
    hist = st.session_state.engagement_history
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(render_kpi_html("Overall Engagement", m["total_engagement"], d["total_engagement"], [x["Overall"] for x in hist]), unsafe_allow_html=True)
    k2.markdown(render_kpi_html("Visual Gaze Focus", m["gaze_score"], d["gaze_score"], [x["Visual Gaze"] for x in hist]), unsafe_allow_html=True)
    k3.markdown(render_kpi_html("Posture & Motion", m["movement_score"], d["movement_score"], [x["Posture & Motion"] for x in hist]), unsafe_allow_html=True)
    k4.markdown(render_kpi_html("Vocal Interaction", m["audio_score"], d["audio_score"], [x["Vocal Audio"] for x in hist]), unsafe_allow_html=True)
    st.write("")

    col_left, col_right = st.columns([1.3, 1], gap="medium")

    with col_left:
        # Scenario Presets + Signal Sliders
        with st.container(border=True):
            st.markdown('<p class="sec-title">Multimodal Telemetry &amp; Scenario Controls</p>', unsafe_allow_html=True)
            p1, p2, p3 = st.columns(3)
            with p1:
                if st.button("Active Q&A", icon=":material/forum:", width="stretch"):
                    st.session_state.sim_gaze, st.session_state.sim_move, st.session_state.sim_audio = 88, 85, 78
                    push_telemetry_step(88, 85, 78, trigger_ai=True)
                    st.rerun(scope="fragment")
            with p2:
                if st.button("Mid-Lecture Drift", icon=":material/trending_down:", width="stretch"):
                    st.session_state.sim_gaze, st.session_state.sim_move, st.session_state.sim_audio = 44, 48, 12
                    push_telemetry_step(44, 48, 12, trigger_ai=True)
                    st.rerun(scope="fragment")
            with p3:
                if st.button("Silent Note-Taking", icon=":material/edit_note:", width="stretch"):
                    st.session_state.sim_gaze, st.session_state.sim_move, st.session_state.sim_audio = 75, 80, 18
                    push_telemetry_step(75, 80, 18, trigger_ai=True)
                    st.rerun(scope="fragment")

            sl1, sl2, sl3 = st.columns(3)
            with sl1:
                g_v = st.slider("Visual Gaze %", 0, 100, int(st.session_state.sim_gaze))
            with sl2:
                m_v = st.slider("Posture %", 0, 100, int(st.session_state.sim_move))
            with sl3:
                a_v = st.slider("Vocal Audio %", 0, 100, int(st.session_state.sim_audio))
            st.session_state.sim_gaze, st.session_state.sim_move, st.session_state.sim_audio = g_v, m_v, a_v

            st.plotly_chart(build_spline_fig(hist), width="stretch", config=PLOTLY_CFG, key=f"spline_{len(hist)}_{m['total_engagement']}")

        # Interactive Classroom Attention Grid + Proctoring Controls
        with st.container(border=True):
            ag1, ag2 = st.columns([1.4, 1], vertical_alignment="center")
            with ag1:
                st.markdown('<p class="sec-title">Live Classroom Attention &amp; Proctoring Grid</p>', unsafe_allow_html=True)
                st.markdown('<p class="sec-sub">Per-student presence verification &amp; tab-switch strike enforcement.</p>', unsafe_allow_html=True)
            with ag2:
                if st.button("Simulate Tab-Switch Strike", icon=":material/tab_unselected:", width="stretch"):
                    target_sid = st.session_state.active_student_id
                    sname, s_cnt, act = record_focus_violation(target_sid, "Tab Switch / Desktop Exit", round(random.uniform(8.0, 22.0), 1))
                    if sname:
                        st.toast(f"{sname}: {act}")
                    st.rerun(scope="fragment")

            g_c1, g_c2 = st.columns(2)
            for idx, seat in enumerate(st.session_state.live_seats):
                target_col = g_c1 if idx % 2 == 0 else g_c2
                target_col.markdown(
                    render_seat_card_html(
                        seat["student_id"],
                        seat["name"],
                        seat["presence"],
                        seat["focus_state"],
                        seat["strikes"],
                        int(st.session_state.max_strikes),
                        seat["status"],
                    ),
                    unsafe_allow_html=True,
                )

    with col_right:
        # Real Browser Window-Focus Proctoring Monitor
        with st.container(border=True):
            st.markdown('<p class="sec-title">Anti-Cheat Window-Focus Proctoring</p>', unsafe_allow_html=True)
            components.html(render_focus_guard_widget(int(st.session_state.max_strikes)), height=145)
            df_inc = get_proctor_incidents()
            if not df_inc.empty:
                st.dataframe(
                    df_inc[["timestamp", "student_name", "strike_count", "action_taken"]].head(4).rename(
                        columns={"timestamp": "Time", "student_name": "Student", "strike_count": "Strikes", "action_taken": "Enforcement"}
                    ),
                    width="stretch",
                    hide_index=True,
                )

        # Actionable AI Teaching Coach
        with st.container(border=True):
            ch1, ch2 = st.columns([1.15, 1], vertical_alignment="center")
            with ch1:
                st.markdown('<p class="sec-title" style="margin:0;">AI Teaching Coach</p>', unsafe_allow_html=True)
            with ch2:
                if st.button("Ask Coach Now", icon=":material/auto_awesome:", type="primary", width="stretch"):
                    push_telemetry_step(st.session_state.sim_gaze, st.session_state.sim_move, st.session_state.sim_audio, trigger_ai=True)
                    st.rerun(scope="fragment")

            for idx, item in enumerate(st.session_state.suggestion_feed[:3]):
                st.markdown(render_coach_card_html(item["category"], item["time"], item["text"]), unsafe_allow_html=True)
                ac1, ac2, _ = st.columns([1, 1, 1.4])
                with ac1:
                    if not item.get("applied") and st.button("Mark Applied", key=f"app_{idx}", width="stretch"):
                        item["applied"] = True
                        st.toast("Intervention marked as applied.")
                        st.rerun(scope="fragment")
                with ac2:
                    if st.button("Dismiss", key=f"dis_{idx}", width="stretch"):
                        st.session_state.suggestion_feed.pop(idx)
                        st.rerun(scope="fragment")

            with st.form("quick_coach_form", clear_on_submit=True, border=False):
                qf1, qf2 = st.columns([3.2, 1])
                with qf1:
                    q_txt = st.text_input("Ask Coach", placeholder="Ask AttendAI Coach...", label_visibility="collapsed")
                with qf2:
                    q_sub = st.form_submit_button("Ask", icon=":material/send:", width="stretch")
                if q_sub and q_txt.strip():
                    agent = TeachingAdvisorAgent()
                    adv = agent.generate_advice(
                        st.session_state.session_id,
                        st.session_state.latest_metrics,
                        sum(1 for s in st.session_state.live_seats if "Present" in s["status"]),
                        len(st.session_state.live_seats),
                        custom_question=q_txt.strip(),
                    )
                    st.session_state.suggestion_feed.insert(
                        0,
                        {"category": adv["category"], "time": datetime.now().strftime("%H:%M:%S"), "text": adv["text"], "applied": False},
                    )
                    st.rerun(scope="fragment")


@st.fragment(run_every=2)
def render_command_center_live():
    if st.session_state.stream_playing:
        auto_tick_simulation()
    _render_command_center_body()


@st.fragment
def render_command_center_paused():
    _render_command_center_body()


# ==============================================================================
# MODULE B: GAME-STYLE MULTI-TEACHER CLASSROOM LOBBIES
# ==============================================================================
@st.fragment
def render_lobbies_module():
    l_top1, l_top2, l_top3 = st.columns([2, 1, 1], vertical_alignment="center")
    with l_top1:
        st.markdown('<p class="sec-title" style="font-size:1.05rem;">Multi-Teacher Classroom Lobbies</p>', unsafe_allow_html=True)
        st.markdown('<p class="sec-sub">Game-style persistent cohort rooms where multiple subject teachers co-host attendance and share assignments.</p>', unsafe_allow_html=True)

    with l_top2:
        with st.popover("Create New Lobby", icon=":material/add_circle:", width="stretch"):
            c_code = st.text_input("Lobby Join Code", placeholder="LOBBY-ME204")
            c_name = st.text_input("Room Name", placeholder="Mechanical Sem IV")
            c_cohort = st.text_input("Cohort", placeholder="B.Tech ME • Sec B")
            c_host = st.text_input("Host Teacher", value="Dr. Vikram Deshmukh")
            c_sub = st.text_input("Primary Subject", placeholder="Thermodynamics")
            if st.button("Launch Lobby Room", type="primary", width="stretch"):
                if c_code.strip() and c_name.strip() and c_sub.strip():
                    if create_lobby(c_code.strip(), c_name.strip(), c_cohort.strip() or "Cohort A", c_host.strip(), c_sub.strip()):
                        st.session_state.active_lobby = c_code.strip().upper()
                        st.toast(f"Created lobby {c_code.strip().upper()}!")
                        st.rerun()
                    else:
                        st.error("Lobby code already exists.")

    with l_top3:
        with st.popover("Join Lobby by Code", icon=":material/login:", width="stretch"):
            j_code = st.text_input("Enter Room Code", value=st.session_state.active_lobby)
            j_teacher = st.text_input("Teacher Name", placeholder="Prof. Kavita Joshi")
            j_sub = st.text_input("Subject Taught", placeholder="Control Systems")
            if st.button("Join Room as Teacher", type="primary", width="stretch"):
                if j_code.strip() and j_teacher.strip() and j_sub.strip():
                    if join_lobby_teacher(j_code.strip(), j_teacher.strip(), j_sub.strip()):
                        st.toast(f"{j_teacher} joined {j_code.upper()}!")
                        st.rerun(scope="fragment")
                    else:
                        st.error("Lobby code not found.")

    active_lb = get_active_lobby_obj()
    col_l, col_r = st.columns([1.05, 1.35], gap="medium")

    with col_l:
        with st.container(border=True):
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
                f'<span class="sec-title">{active_lb["name"]}</span><span class="lobby-code">{active_lb["lobby_code"]}</span>'
                f"</div>",
                unsafe_allow_html=True,
            )
            st.markdown(f'<p class="sec-sub">{active_lb["cohort"]} &bull; Live Host: <strong>{active_lb["active_host"]}</strong> ({active_lb["active_subject"]})</p>', unsafe_allow_html=True)

            teachers = get_lobby_teachers(active_lb["lobby_code"])
            st.markdown("**Connected Subject Teachers in Room**")
            for t in teachers:
                tc1, tc2 = st.columns([2.2, 1], vertical_alignment="center")
                badge = '<span style="color:#34D399;font-weight:700;">● LIVE HOST</span>' if t["is_live"] else '<span style="color:#94A3B8;">● Ready</span>'
                with tc1:
                    st.markdown(f"**{t['teacher_name']}** — {t['subject']} &nbsp; {badge}", unsafe_allow_html=True)
                with tc2:
                    if not t["is_live"] and st.session_state.user_role == "Instructor / Mentor":
                        if st.button("Take Host", key=f"host_{t['id']}", width="stretch"):
                            set_lobby_active_host(active_lb["lobby_code"], t["teacher_name"], t["subject"])
                            st.toast(f"{t['teacher_name']} is now hosting {t['subject']}.")
                            st.rerun()

    with col_r:
        with st.container(border=True):
            ah1, ah2 = st.columns([1.8, 1], vertical_alignment="center")
            with ah1:
                st.markdown('<p class="sec-title">Shared Lobby Assignment Board</p>', unsafe_allow_html=True)
                st.markdown('<p class="sec-sub">Cross-subject tasks shared across all teachers &amp; students in this room.</p>', unsafe_allow_html=True)
            with ah2:
                if st.session_state.user_role == "Instructor / Mentor":
                    with st.popover("Post Assignment", icon=":material/assignment_add:", width="stretch"):
                        a_sub = st.text_input("Subject", value=active_lb["active_subject"])
                        a_teacher = st.text_input("Faculty", value=active_lb["active_host"])
                        a_title = st.text_input("Assignment Title", placeholder="Lab Sheet 4: FFT Analysis")
                        a_due = st.date_input("Due Date", value=datetime.now() + timedelta(days=5))
                        if st.button("Publish to Lobby", type="primary", width="stretch"):
                            if a_title.strip():
                                add_lobby_assignment(active_lb["lobby_code"], a_sub, a_teacher, a_title.strip(), str(a_due))
                                st.toast("Assignment published to lobby!")
                                st.rerun(scope="fragment")

            df_asg = get_lobby_assignments(active_lb["lobby_code"])
            if not df_asg.empty:
                df_asg["Submissions"] = df_asg.apply(lambda r: f"{r['submitted_count']}/{r['total_students']}", axis=1)
                st.dataframe(
                    df_asg[["subject", "title", "teacher_name", "due_date", "Submissions", "status"]].rename(
                        columns={"subject": "Subject", "title": "Assignment", "teacher_name": "Teacher", "due_date": "Due", "status": "Status"}
                    ),
                    width="stretch",
                    hide_index=True,
                )


# ==============================================================================
# MODULE C: THEORY vs PRACTICAL CALCULATOR, <75% WARNINGS, DAILY DIGEST & DISPUTES
# ==============================================================================
@st.fragment
def render_calculator_and_disputes():
    cum_df = compute_student_cumulative_summary()
    if cum_df.empty:
        st.info("No academic records found.")
        return

    # Student selector (Instructors can inspect anyone; Students/Parents see active profile)
    if st.session_state.user_role == "Instructor / Mentor":
        s_opts = {f"{r['student_id']} — {r['student_name']} ({r['cumulative_pct']}%)": r["student_id"] for _, r in cum_df.iterrows()}
        inv_s = {v: k for k, v in s_opts.items()}
        sel_s = st.selectbox("Inspect Student Attendance Calculator", list(s_opts.keys()), index=list(s_opts.keys()).index(inv_s.get(st.session_state.active_student_id, list(s_opts.keys())[0])))
        target_sid = s_opts[sel_s]
    else:
        target_sid = st.session_state.active_student_id

    row_s = cum_df[cum_df["student_id"] == target_sid].iloc[0]

    # Automated <75% Dual Warning Banner
    if row_s["cumulative_pct"] < 75.0:
        st.markdown(
            f'<div class="alert-banner">{SVG_ICONS["alert"]}<span>'
            f'BELOW 75% WARNING ACTIVE — {row_s["student_name"]} ({target_sid}) is at {row_s["cumulative_pct"]}% cumulative attendance. '
            f'Formal shortage alerts have been dispatched to BOTH the Student Dashboard and Parent Portal. ({row_s["recovery"]} consecutive classes needed.)'
            f"</span></div>",
            unsafe_allow_html=True,
        )

    # Top Cumulative & Grade Summary Row
    m1, m2, m3, m4 = st.columns(4)
    m1.markdown(render_kpi_html("Cumulative Attendance", row_s["cumulative_pct"], None, [72, 74, row_s["cumulative_pct"]]), unsafe_allow_html=True)
    m2.markdown(render_kpi_html("Theory Lectures Overall", row_s["theory_pct"], None, [75, 76, row_s["theory_pct"]]), unsafe_allow_html=True)
    m3.markdown(render_kpi_html("Practical Labs Overall", row_s["practical_pct"], None, [78, 79, row_s["practical_pct"]]), unsafe_allow_html=True)
    with m4:
        g_col = "#10B981" if row_s["cumulative_pct"] >= 85 else ("#F59E0B" if row_s["cumulative_pct"] >= 75 else "#EF4444")
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-top"><span class="kpi-label">Internal Grade</span><span class="kpi-pill kpi-{"optimal" if row_s["cumulative_pct"]>=85 else ("watch" if row_s["cumulative_pct"]>=75 else "risk")}">{row_s["risk_tier"]}</span></div>'
            f'<div style="font-size:1.18rem;font-weight:800;color:{g_col};margin-top:6px;">{row_s["internal_grade"]}</div>'
            f'<div class="mono" style="font-size:0.74rem;color:#94A3B8;margin-top:4px;">What-If: {row_s["recovery"]}</div></div>',
            unsafe_allow_html=True,
        )
    st.write("")

    # Subject-Wise Theory vs Practical Breakdown Table
    sub_df = get_student_subject_records(target_sid)
    calc_rows = []
    for _, sr in sub_df.iterrows():
        th_p = round((sr["theory_attended"] / sr["theory_total"]) * 100, 1) if sr["theory_total"] else 0.0
        pr_p = round((sr["practical_attended"] / sr["practical_total"]) * 100, 1) if sr["practical_total"] else 0.0
        comb_att = int(sr["theory_attended"] + sr["practical_attended"])
        comb_tot = int(sr["theory_total"] + sr["practical_total"])
        comb_p = round((comb_att / comb_tot) * 100, 1) if comb_tot else 0.0
        grade, _ = compute_internal_grade(comb_p)
        mode, cnt = compute_recovery_classes(comb_att, comb_tot)
        calc_rows.append({
            "Code": sr["subject_code"],
            "Subject": sr["subject_name"],
            "Theory (Att/Tot)": f"{sr['theory_attended']}/{sr['theory_total']}",
            "Theory %": th_p,
            "Practical (Att/Tot)": f"{sr['practical_attended']}/{sr['practical_total']}",
            "Practical %": pr_p,
            "Subject %": comb_p,
            "Internal Grade": grade,
            "75% Recovery": f"Attend +{cnt}" if mode == "Need" else f"{cnt} buffer",
        })

    with st.container(border=True):
        st.markdown(f'<p class="sec-title">Subject-Wise Attendance Calculator (Theory vs. Practical) — {row_s["student_name"]}</p>', unsafe_allow_html=True)
        st.dataframe(
            pd.DataFrame(calc_rows),
            width="stretch",
            hide_index=True,
            column_config={
                "Theory %": st.column_config.ProgressColumn("Theory %", min_value=0, max_value=100, format="%.1f%%"),
                "Practical %": st.column_config.ProgressColumn("Practical %", min_value=0, max_value=100, format="%.1f%%"),
                "Subject %": st.column_config.NumberColumn("Subject %", format="%.1f%%"),
            },
        )

    # Daily Attendance Summary Digest + Student Dispute / Flag Request Desk
    d_col1, d_col2 = st.columns([1.25, 1], gap="medium")

    with d_col1:
        with st.container(border=True):
            dh1, dh2 = st.columns([1.8, 1], vertical_alignment="center")
            with dh1:
                st.markdown('<p class="sec-title">Daily Attendance Summary Digest</p>', unsafe_allow_html=True)
                st.markdown(f'<p class="sec-sub">End-of-day class timeline for {datetime.now().strftime("%Y-%m-%d")}.</p>', unsafe_allow_html=True)
            df_daily = get_daily_logs(None if st.session_state.user_role == "Instructor / Mentor" else target_sid)
            with dh2:
                if not df_daily.empty:
                    st.download_button(
                        "Export Daily CSV",
                        data=df_daily.to_csv(index=False).encode("utf-8"),
                        file_name=f"AttendAI_DailySummary_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        icon=":material/download:",
                        width="stretch",
                    )

            if not df_daily.empty:
                st.dataframe(
                    df_daily[["time_slot", "student_name", "subject_name", "session_type", "status", "proctor_strikes"]].rename(
                        columns={"time_slot": "Slot", "student_name": "Student", "subject_name": "Subject", "session_type": "Type", "status": "Status", "proctor_strikes": "Strikes"}
                    ),
                    width="stretch",
                    hide_index=True,
                )

    with d_col2:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Attendance Flag &amp; Dispute Resolution Desk</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-sub">Flag missed/incorrect attendance to Mentor or Subject Teacher for real-time recalculation.</p>', unsafe_allow_html=True)

            # Student Flag Submission Form
            if st.session_state.user_role in ("Student", "Instructor / Mentor"):
                with st.expander("Flag / Request Attendance Correction", expanded=(st.session_state.user_role == "Student")):
                    stu_daily = get_daily_logs(target_sid)
                    flag_opts = (
                        {f"#{r['id']} | {r['subject_name']} ({r['session_type']}) — {r['status']}": r for _, r in stu_daily.iterrows()}
                        if not stu_daily.empty
                        else {}
                    )
                    if flag_opts:
                        pick_lbl = st.selectbox("Select Session to Flag", list(flag_opts.keys()))
                        picked = flag_opts[pick_lbl]
                        route_to = st.radio("Route Request Directly To", ["Assigned Mentor", "Subject Teacher"], horizontal=True)
                        recip_name = "Dr. Vikram Deshmukh (Mentor)" if route_to == "Assigned Mentor" else picked["teacher_name"]
                        reason_txt = st.text_area("Reason / Evidence", placeholder="e.g., Present in Lab Bay 2, camera glare, or approved medical duty.")
                        if st.button("Submit Correction Flag", icon=":material/flag:", type="primary", width="stretch"):
                            if reason_txt.strip():
                                create_dispute_ticket(
                                    int(picked["id"]),
                                    target_sid,
                                    row_s["student_name"],
                                    picked["subject_name"],
                                    picked["session_type"],
                                    route_to,
                                    recip_name,
                                    reason_txt.strip(),
                                )
                                st.toast(f"Flag sent to {recip_name}!")
                                st.rerun(scope="fragment")

            # Ticket Queue (Faculty can Approve & Recalculate in real time)
            tickets_df = get_dispute_tickets(None if st.session_state.user_role == "Instructor / Mentor" else target_sid)
            if tickets_df.empty:
                st.caption("No active attendance correction tickets.")
            else:
                for _, tk in tickets_df.head(5).iterrows():
                    st.markdown(
                        f'<div class="notif-card notif-{"warning" if tk["status"]=="Pending Review" else "info"}">'
                        f'<div style="display:flex;justify-content:space-between;font-size:0.78rem;margin-bottom:4px;">'
                        f'<strong>{tk["student_name"]} &bull; {tk["subject_name"]} ({tk["session_type"]})</strong>'
                        f'<span class="mono" style="color:#38BDF8;">{tk["status"]}</span></div>'
                        f'<div style="font-size:0.80rem;color:#CBD5E1;">To: {tk["routed_to"]} ({tk["recipient_name"]}) — {tk["reason"]}</div></div>',
                        unsafe_allow_html=True,
                    )
                    if tk["status"] == "Pending Review" and st.session_state.user_role == "Instructor / Mentor":
                        rb1, rb2 = st.columns(2)
                        with rb1:
                            if st.button("Approve & Recalculate", key=f"appr_{tk['id']}", type="primary", width="stretch"):
                                resolve_dispute_ticket(int(tk["id"]), True, "Verified by faculty; attendance recalculated.")
                                st.toast("Approved! Theory/Practical % & Cumulative Grade recalculated.")
                                st.rerun(scope="fragment")
                        with rb2:
                            if st.button("Reject Flag", key=f"rej_{tk['id']}", width="stretch"):
                                resolve_dispute_ticket(int(tk["id"]), False, "Unable to verify physical presence.")
                                st.toast("Dispute rejected.")
                                st.rerun(scope="fragment")


# ==============================================================================
# MODULE D: PARENT ENGAGEMENT & STUDENT SAFETY CENTER
# ==============================================================================
@st.fragment
def render_parent_safety_center():
    cum_df = compute_student_cumulative_summary()
    target_sid = st.session_state.active_student_id
    ward_row = cum_df[cum_df["student_id"] == target_sid].iloc[0] if not cum_df.empty and target_sid in cum_df["student_id"].values else None

    p_left, p_right = st.columns([1.25, 1], gap="medium")

    with p_left:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Parent &amp; Guardian Communication Hub</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-sub">Real-time dispatch feed for &lt;75% warnings, daily attendance digests, and unexpected exit safety checks.</p>', unsafe_allow_html=True)

            if ward_row is not None:
                st.markdown(
                    f'<div class="lobby-card">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                    f'<strong>Ward Overview: {ward_row["student_name"]} ({ward_row["student_id"]})</strong>'
                    f'<span class="lobby-code">Cumulative: {ward_row["cumulative_pct"]}%</span></div>'
                    f'<div style="font-size:0.82rem;color:#CBD5E1;margin-top:6px;">Theory: <strong>{ward_row["theory_pct"]}%</strong> &bull; Practical: <strong>{ward_row["practical_pct"]}%</strong> &bull; Grade: <strong>{ward_row["internal_grade"]}</strong></div>'
                    f"</div>",
                    unsafe_allow_html=True,
                )

            if st.button("Run <75% Dual Warning Audit Now", icon=":material/notifications_active:", width="stretch"):
                cnt = dispatch_below_75_warnings()
                st.toast(f"Dispatched {cnt} new <75% warning(s) to Student & Parent portals." if cnt else "All <75% warnings already dispatched.")
                st.rerun(scope="fragment")

            parent_notifs = get_notifications(recipient_role="Parent" if st.session_state.user_role == "Parent / Guardian" else None)
            if parent_notifs.empty:
                st.caption("No parent notifications dispatched yet.")
            else:
                for _, nf in parent_notifs.head(6).iterrows():
                    sev_cls = "critical" if nf["severity"] == "Critical" else ("warning" if nf["severity"] == "Warning" else "info")
                    ack_txt = "Acknowledged" if nf["acknowledged"] else "Pending Ack"
                    st.markdown(
                        f'<div class="notif-card notif-{sev_cls}">'
                        f'<div style="display:flex;justify-content:space-between;font-size:0.78rem;margin-bottom:4px;">'
                        f'<strong>{nf["title"]}</strong><span class="mono" style="color:#94A3B8;">{nf["created_at"]}</span></div>'
                        f'<div style="font-size:0.80rem;color:#CBD5E1;">{nf["message"]}</div>'
                        f'<div style="font-size:0.71rem;color:#38BDF8;margin-top:5px;">To: {nf["recipient_role"]} &bull; Channels: {nf["channels"]} &bull; {ack_txt}</div>'
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    if not nf["acknowledged"]:
                        if st.button("Mark Acknowledged", key=f"ack_{nf['id']}", width="stretch"):
                            acknowledge_notification(int(nf["id"]))
                            st.rerun(scope="fragment")

    with p_right:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Student Safety &amp; Safeguarding Protocols</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-sub">Presence verification during scheduled hours, discreet SOS check-in, and zero-image biometric privacy.</p>', unsafe_allow_html=True)

            # Discreet Student Safety Check-In / SOS Trigger
            st.markdown("**Discreet Student Safety / Well-Being Check-In**")
            sos_note = st.text_input("Optional Private Message to Mentor / Campus Safety", placeholder="e.g., Feeling unwell in Lab Block B, requesting mentor check-in.")
            if st.button("Send Private Safety Check-In to Mentor", icon=":material/health_and_safety:", type="primary", width="stretch"):
                w_name = ward_row["student_name"] if ward_row is not None else "Student"
                msg = sos_note.strip() or f"{w_name} requested a discreet safety / well-being check-in during scheduled hours."
                for r_role in ("Instructor", "Parent"):
                    dispatch_notification(
                        recipient_role=r_role,
                        student_id=target_sid,
                        student_name=w_name,
                        category="Student Safety SOS",
                        severity="Critical",
                        title=f"Safety Check-In Alert — {w_name}",
                        message=msg,
                        channels="Urgent Mentor Desk • SMS",
                    )
                st.success("Private safety alert delivered to Assigned Mentor and Campus Safety Desk.")
                st.rerun(scope="fragment")

            st.divider()
            st.markdown("**Message Assigned Mentor (Parent Quick-Connect)**")
            with st.form("parent_mentor_msg", clear_on_submit=True, border=False):
                pm_txt = st.text_input("Parent Note", placeholder="e.g., Rohan had a doctor appointment this morning.")
                if st.form_submit_button("Send Note to Mentor", icon=":material/mail:", width="stretch") and pm_txt.strip():
                    w_name = ward_row["student_name"] if ward_row is not None else "Student"
                    dispatch_notification(
                        recipient_role="Instructor",
                        student_id=target_sid,
                        student_name=w_name,
                        category="Parent Message",
                        severity="Info",
                        title=f"Parent Note regarding {w_name}",
                        message=pm_txt.strip(),
                        channels="Parent Portal -> Mentor",
                    )
                    st.toast("Message delivered to Assigned Mentor.")
                    st.rerun(scope="fragment")

            st.divider()
            st.markdown(
                '<div class="audit-panel">'
                '<div style="font-weight:700;color:#F8FAFC;margin-bottom:4px;">Safeguarding &amp; Privacy Guarantees</div>'
                '<div><span class="dot-ok">&bull;</span>Mid-session disappearances auto-trigger mentor safety checks.</div>'
                '<div><span class="dot-ok">&bull;</span>Role-masked portal: parents only view their linked ward.</div>'
                '<div><span class="dot-ok">&bull;</span>0 raw photos stored; 512-D L2 vectors only.</div>'
                "</div>",
                unsafe_allow_html=True,
            )


# ==============================================================================
# MODULE E: BIOMETRIC ROSTER, AUTO-PDF ARCHIVE & ANALYTICS
# ==============================================================================
@st.fragment
def render_roster_and_reports():
    sub_tab1, sub_tab2 = st.tabs([":material/fingerprint: Biometric Roster & Privacy Vault", ":material/analytics: Auto-PDF Archive & Analytics"])

    with sub_tab1:
        r_l, r_r = st.columns([1, 1.35], gap="medium")
        with r_l:
            with st.container(border=True):
                st.markdown('<p class="sec-title">Enroll Student (Zero-Image Vault)</p>', unsafe_allow_html=True)
                st.markdown('<p class="sec-sub">Extracts a normalized 512-D vector in RAM and permanently discards the photo.</p>', unsafe_allow_html=True)
                nid = st.text_input("Student ID", placeholder="S107")
                nname = st.text_input("Full Name", placeholder="Priya Deshmukh")
                src_mode = st.radio("Capture Method", ["Upload Portrait", "Live Camera Snapshot"], horizontal=True)
                img_file = st.file_uploader("Front-Facing Photo", type=["jpg", "jpeg", "png"]) if src_mode == "Upload Portrait" else st.camera_input("Take Snapshot")

                if st.button("Extract & Save 512-D Vector", icon=":material/person_add:", type="primary", width="stretch"):
                    if not nid.strip() or not nname.strip() or img_file is None:
                        st.error("Provide Student ID, Full Name, and a facial photo.")
                    else:
                        arr = np.asarray(bytearray(img_file.read()), dtype=np.uint8)
                        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                        if img is not None:
                            fapp = get_face_analyzer()
                            faces = fapp.get(img)
                            if len(faces) == 1:
                                emb = faces[0].embedding / np.linalg.norm(faces[0].embedding)
                                save_student(nid.strip(), nname.strip(), emb)
                                st.success(f"Enrolled {nname.strip()} ({nid.strip()}). Raw Image Permanently Discarded (0 Bytes Saved).")
                                st.rerun(scope="fragment")
                            else:
                                st.error("Ensure exactly 1 clear face is visible.")

        with r_r:
            with st.container(border=True):
                rh1, rh2 = st.columns([1.6, 1], vertical_alignment="center")
                with rh1:
                    st.markdown('<p class="sec-title">Enrolled Biometric Directory</p>', unsafe_allow_html=True)
                with rh2:
                    if st.button("Load Sample Roster", icon=":material/group_add:", width="stretch"):
                        seed_sample_roster()
                        st.rerun(scope="fragment")

                roster = load_all_students()
                rdf = pd.DataFrame([
                    {
                        "Student ID": r["student_id"],
                        "Full Name": r["name"],
                        "Storage Proof": "512-D L2 Vector (0 Raw Bytes)",
                        "L2 Norm": round(float(np.linalg.norm(r["embedding"])), 4),
                        "Enrolled": r["created_at"],
                    }
                    for r in roster
                ])
                st.dataframe(rdf, width="stretch", hide_index=True)

                if roster:
                    i1, i2, i3 = st.columns([2, 1, 1], vertical_alignment="center")
                    opts = [f"{r['student_id']} — {r['name']}" for r in roster]
                    with i1:
                        picked = st.selectbox("Select Student", opts, label_visibility="collapsed")
                    tid = picked.split(" — ")[0]
                    tobj = next(r for r in roster if r["student_id"] == tid)
                    with i2:
                        with st.popover("Inspect Vector", icon=":material/fingerprint:", width="stretch"):
                            st.markdown(f"**{tobj['name']}** (`{tid}`)")
                            st.caption("Raw Image Stored: 0 Bytes")
                            vals = ", ".join(f"{v:+.4f}" for v in tobj["embedding"][:10])
                            st.code(f"[{vals}, ... ] (512-D, L2=1.0000)", language="text")
                    with i3:
                        if st.button("Remove", icon=":material/delete:", width="stretch"):
                            delete_student(tid)
                            st.rerun(scope="fragment")

    with sub_tab2:
        # Auto-Generated Session PDF Archive
        with st.container(border=True):
            st.markdown('<p class="sec-title">Auto-Generated Session PDF Archive</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-sub">Compiled automatically at the conclusion of every scheduled classroom session.</p>', unsafe_allow_html=True)
            rep_df = get_session_reports()
            if rep_df.empty:
                st.caption("End a scheduled session in the Live Command Center to auto-generate and archive your first PDF report.")
            else:
                for _, rr in rep_df.head(5).iterrows():
                    rc1, rc2 = st.columns([3, 1], vertical_alignment="center")
                    with rc1:
                        st.markdown(
                            f"**{rr['subject_name']}** (`{rr['session_id']}` • {rr['lobby_code']}) — "
                            f"Engagement: **{rr['avg_engagement']}%** | Present: **{rr['present_count']}/{rr['total_count']}** | "
                            f"Proctor Alerts: **{rr['proctor_violations']}** | _{rr['generated_at']}_"
                        )
                    with rc2:
                        st.download_button(
                            "Download PDF",
                            data=base64.b64decode(rr["pdf_b64"]),
                            file_name=f"AttendAI_AutoReport_{rr['session_id']}.pdf",
                            mime="application/pdf",
                            icon=":material/picture_as_pdf:",
                            key=f"dl_rep_{rr['id']}",
                            width="stretch",
                        )

        # Multimodal Analytics Charts
        sessions = get_session_list()
        sel_sess = st.selectbox("Filter Historical Session", ["ALL"] + sessions, format_func=lambda x: "All Archived Sessions" if x == "ALL" else x)
        df_att, df_eng, df_sug = get_session_data(sel_sess)

        if not df_eng.empty:
            c1, c2 = st.columns([1.5, 1], gap="medium")
            with c1:
                with st.container(border=True):
                    st.markdown('<p class="sec-title">Multimodal Engagement Breakdown</p>', unsafe_allow_html=True)
                    df_p = df_eng.tail(18).rename(columns={"gaze_score": "Visual Gaze", "movement_score": "Posture & Motion", "audio_score": "Vocal Audio"})
                    fig_b = go.Figure()
                    for nm, cl in [("Visual Gaze", "#3B82F6"), ("Posture & Motion", "#38BDF8"), ("Vocal Audio", "#10B981")]:
                        fig_b.add_trace(go.Bar(x=df_p["timestamp"], y=df_p[nm], name=nm, marker_color=cl))
                    fig_b.update_layout(
                        barmode="group",
                        height=280,
                        margin=dict(l=8, r=8, t=10, b=8),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#94A3B8", family="Inter", size=11),
                        hoverlabel=PLOTLY_HOVER,
                        yaxis=dict(range=[0, 105], gridcolor="rgba(148,163,184,0.1)"),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    )
                    st.plotly_chart(fig_b, width="stretch", config=PLOTLY_CFG)

            with c2:
                with st.container(border=True):
                    st.markdown('<p class="sec-title">Composite Modality Balance</p>', unsafe_allow_html=True)
                    comp = round(float(df_eng["total_engagement"].mean()), 1)
                    fig_d = go.Figure(
                        data=[
                            go.Pie(
                                labels=["Visual Gaze", "Posture & Motion", "Vocal Audio"],
                                values=[round(float(df_eng["gaze_score"].mean()), 1), round(float(df_eng["movement_score"].mean()), 1), round(float(df_eng["audio_score"].mean()), 1)],
                                hole=0.66,
                                marker=dict(colors=["#3B82F6", "#38BDF8", "#10B981"], line=dict(color="#060913", width=2)),
                            )
                        ]
                    )
                    fig_d.update_layout(
                        height=280,
                        margin=dict(l=12, r=12, t=12, b=28),
                        paper_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#94A3B8", family="Inter", size=11),
                        legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.08),
                        annotations=[dict(text=f"<b>{comp:.1f}%</b><br><span style='font-size:11px;color:#94A3B8;'>Composite</span>", x=0.5, y=0.5, font=dict(size=20, color="#F8FAFC"), showarrow=False)],
                    )
                    st.plotly_chart(fig_d, width="stretch", config=PLOTLY_CFG)


# --- Main Role-Aware Navigation Tabs ---
tabs = st.tabs([
    ":material/sensors: Live Command & Proctoring",
    ":material/sports_esports: Classroom Lobbies",
    ":material/calculate: Attendance Calculator & Disputes",
    ":material/family_restroom: Parent & Student Safety",
    ":material/verified_user: Biometric Vault & Auto-PDFs",
])

with tabs[0]:
    if st.session_state.stream_playing:
        render_command_center_live()
    else:
        render_command_center_paused()

with tabs[1]:
    render_lobbies_module()

with tabs[2]:
    render_calculator_and_disputes()

with tabs[3]:
    render_parent_safety_center()

with tabs[4]:
    render_roster_and_reports()