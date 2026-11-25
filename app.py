import base64
import cv2
import random
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
from modules.engagement import AUDIO_AVAILABLE
from modules.agent import TeachingAdvisorAgent, check_ollama_status
from modules.styles import (
    SVG_ICONS,
    get_app_css,
    render_top_nav_html,
    render_faculty_card_html,
    render_kpi_html,
    render_seat_card_html,
    render_coach_card_html,
    render_focus_guard_widget,
    render_auto_pdf_download_script,
)

# --- Page Configuration ---
st.set_page_config(
    page_title="AttendAI — Classroom Intelligence",
    page_icon=":material/verified_user:",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
seed_commercial_demo_data()
st.markdown(get_app_css(), unsafe_allow_html=True)

PLOTLY_CFG = {"displayModeBar": False}
PLOTLY_HOVER = dict(
    bgcolor="#1E293B",
    bordercolor="#334155",
    font=dict(color="#F8FAFC", family="Inter", size=12),
)


@st.cache_resource(show_spinner="Preparing identity verification engine...")
def get_face_analyzer():
    from insightface.app import FaceAnalysis

    face_app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
    face_app.prepare(ctx_id=0, det_size=(320, 320))
    return face_app


@st.cache_data(ttl=30)
def get_diagnostics():
    ollama_ok, _ = check_ollama_status()
    return {
        "ai_local": ollama_ok,
        "vision_ok": importlib.util.find_spec("insightface") is not None,
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
            "focus_state": "Distracted" if is_flagged else "Engaged",
            "strikes": 2 if is_flagged else 0,
            "status": "Checking" if is_flagged else "Present",
        })
    return seats


# --- Session State ---
defaults = {
    "user_role": "Instructor / Mentor",
    "active_lobby": "LOBBY-ECE301",
    "active_student_id": "S104",
    "session_id": datetime.now().strftime("SESS_%Y%m%d_%H%M%S"),
    "stream_playing": False,
    "stream_speed": "1x",
    "max_strikes": 3,
    "scheduled_minutes": 15,
    "session_remaining_sec": 900,
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
        {"Time": "09:30", "Overall": 81.2, "Visual Attention": 84.0, "Posture & Activity": 82.0, "Class Discussion": 75.0},
        {"Time": "09:33", "Overall": 79.5, "Visual Attention": 83.0, "Posture & Activity": 82.0, "Class Discussion": 70.0},
        {"Time": "09:36", "Overall": 82.0, "Visual Attention": 86.0, "Posture & Activity": 84.0, "Class Discussion": 72.0},
    ],
    "suggestion_feed": [
        {
            "category": "Participation",
            "time": "09:36",
            "text": "Class attention is strong across the room. Consider checking in with Rohan Verma (2/3 focus alerts) using a quick concept question.",
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


# --- Core Helpers ---
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


def record_focus_violation(student_id: str, event_type: str = "Left Classroom Window", duration_sec: float = 14.2):
    max_s = int(st.session_state.max_strikes)
    for seat in st.session_state.live_seats:
        if seat["student_id"] == student_id:
            seat["strikes"] += 1
            if seat["strikes"] >= max_s:
                seat["status"] = "Absent (Focus Limit)"
                seat["focus_state"] = "Out of Window"
                seat["presence"] = max(20.0, seat["presence"] - 25.0)
                action = f"Marked Absent ({max_s}/{max_s} alerts) · Guardian & Mentor Notified"
                for role in ("Parent", "Student", "Instructor"):
                    dispatch_notification(
                        recipient_role=role,
                        student_id=seat["student_id"],
                        student_name=seat["name"],
                        category="Focus Alert",
                        severity="Critical",
                        title=f"Attendance Updated to Absent — {seat['name']}",
                        message=(
                            f"{seat['name']} reached the window-focus limit "
                            f"({seat['strikes']}/{max_s} alerts) during {get_active_lobby_obj()['active_subject']} "
                            f"and was automatically marked Absent."
                        ),
                        channels="Portal · SMS · Email",
                    )
            else:
                seat["focus_state"] = "Focus Warning"
                action = f"Focus Alert Recorded ({seat['strikes']}/{max_s})"

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
    lobby = get_active_lobby_obj()
    sess_id = st.session_state.session_id
    now_t = datetime.now().strftime("%H:%M:%S")

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
            log_engagement(sess_id, row["Visual Attention"], row["Posture & Activity"], row["Class Discussion"], row["Overall"])
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

    filename = f"AttendAI_Session_Report_{sess_id}.pdf"
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
        "Visual Attention": metrics["gaze_score"],
        "Posture & Activity": metrics["movement_score"],
        "Class Discussion": metrics["audio_score"],
    })
    st.session_state.engagement_history = st.session_state.engagement_history[-24:]
    log_engagement(st.session_state.session_id, metrics["gaze_score"], metrics["movement_score"], metrics["audio_score"], total)

    for seat in st.session_state.live_seats:
        if seat["strikes"] < int(st.session_state.max_strikes):
            delta_p = 0.8 if total >= 65 else -1.4
            seat["presence"] = round(min(100.0, max(35.0, seat["presence"] + delta_p)), 1)
            seat["focus_state"] = "Engaged" if gaze >= 70 else ("Distracted" if gaze >= 50 else "Inactive")
            seat["status"] = "Present" if seat["presence"] >= 60 else "Checking"

    hist = st.session_state.engagement_history
    recent_peak = max(item["Overall"] for item in hist[-5:]) if len(hist) >= 2 else total
    if recent_peak - total >= 15.0:
        st.session_state.drop_alert = f"Class attention dipped by {round(recent_peak - total, 1)}% ({recent_peak}% to {total}%). Check the Teaching Assistant for a quick reset idea."
    elif total < 55.0:
        st.session_state.drop_alert = f"Low class engagement detected ({total}%). Consider pausing for a brief concept check."
    else:
        st.session_state.drop_alert = None

    if trigger_ai:
        agent = TeachingAdvisorAgent()
        present_cnt = sum(1 for s in st.session_state.live_seats if "Present" in s["status"])
        adv = agent.generate_advice(st.session_state.session_id, metrics, present_cnt, max(1, len(st.session_state.live_seats)))
        st.session_state.suggestion_feed.insert(
            0,
            {"category": adv["category"], "time": datetime.now().strftime("%H:%M"), "text": adv["text"], "applied": False},
        )


def auto_tick_simulation():
    step_sec = 4 if st.session_state.stream_speed == "2x" else 2
    st.session_state.session_remaining_sec = max(0, st.session_state.session_remaining_sec - step_sec)

    g = float(np.clip(st.session_state.sim_gaze + random.uniform(-3.0, 3.0), 25, 98))
    m = float(np.clip(st.session_state.sim_move + random.uniform(-2.5, 2.5), 30, 96))
    a = float(np.clip(st.session_state.sim_audio + random.uniform(-4.0, 4.0), 8, 95))
    st.session_state.sim_gaze, st.session_state.sim_move, st.session_state.sim_audio = int(g), int(m), int(a)
    push_telemetry_step(g, m, a, trigger_ai=False)

    if st.session_state.session_remaining_sec <= 0:
        finalize_and_auto_generate_pdf()


def build_spline_fig(history: list) -> go.Figure:
    df_h = pd.DataFrame(history)
    fig = go.Figure()
    series = [
        ("Overall", "#818CF8", 2.8),
        ("Visual Attention", "#38BDF8", 2.0),
        ("Class Discussion", "#10B981", 2.0),
    ]
    for name, col, w in series:
        if name in df_h.columns:
            fig.add_trace(
                go.Scatter(
                    x=df_h["Time"],
                    y=df_h[name],
                    mode="lines+markers",
                    name=name,
                    line=dict(color=col, width=w, shape="spline"),
                    marker=dict(size=5, line=dict(width=1.5, color="#0F172A")),
                    hovertemplate=f"<b>{name}</b>: %{{y:.1f}}%<extra></extra>",
                )
            )
    fig.add_hline(
        y=60,
        line_dash="dot",
        line_color="#F59E0B",
        annotation_text="Target Minimum (60%)",
        annotation_position="bottom right",
        annotation_font=dict(color="#FCD34D", size=11),
    )
    fig.update_layout(
        height=270,
        margin=dict(l=8, r=8, t=12, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#CBD5E1", family="Inter", size=11),
        hovermode="x unified",
        hoverlabel=PLOTLY_HOVER,
        yaxis=dict(range=[0, 105], title="Score %", gridcolor="rgba(148,163,184,0.12)", zeroline=False),
        xaxis=dict(title="", gridcolor="rgba(148,163,184,0.06)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="#CBD5E1")),
    )
    return fig


# --- Sidebar: Workspace Navigation, Collapsible Demo Controls & Privacy ---
diag = get_diagnostics()
lobbies = get_lobbies()
lobby_codes = [lb["lobby_code"] for lb in lobbies]
all_students = load_all_students()
student_map = {f"{s['name']} ({s['student_id']})": s["student_id"] for s in all_students}

with st.sidebar:
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:2px;">'
        f'<div class="brand-mark" style="width:28px;height:28px;">{SVG_ICONS["brand"]}</div>'
        f'<span style="font-size:1.05rem;font-weight:700;letter-spacing:-0.02em;color:#F8FAFC;">AttendAI</span>'
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption("Classroom Intelligence Workspace")
    st.divider()

    st.markdown("**View As**")
    st.session_state.user_role = st.selectbox(
        "View As",
        ["Instructor / Mentor", "Student", "Parent / Guardian"],
        index=["Instructor / Mentor", "Student", "Parent / Guardian"].index(st.session_state.user_role),
        label_visibility="collapsed",
    )

    if st.session_state.user_role in ("Student", "Parent / Guardian") and student_map:
        st.markdown("**Student Profile**")
        inv_map = {v: k for k, v in student_map.items()}
        default_lbl = inv_map.get(st.session_state.active_student_id, list(student_map.keys())[0])
        chosen_lbl = st.selectbox(
            "Student Profile",
            list(student_map.keys()),
            index=list(student_map.keys()).index(default_lbl),
            label_visibility="collapsed",
        )
        st.session_state.active_student_id = student_map[chosen_lbl]

    st.markdown("**Active Course Room**")
    if lobby_codes:
        idx_l = lobby_codes.index(st.session_state.active_lobby) if st.session_state.active_lobby in lobby_codes else 0
        st.session_state.active_lobby = st.selectbox("Course Room", lobby_codes, index=idx_l, label_visibility="collapsed")

    st.divider()

    with st.expander("Demo Controls", expanded=False):
        st.caption("Preview classroom scenarios without a live camera.")

        if st.button("Active Discussion", icon=":material/forum:", width="stretch"):
            st.session_state.sim_gaze, st.session_state.sim_move, st.session_state.sim_audio = 88, 85, 78
            push_telemetry_step(88, 85, 78, trigger_ai=True)
            st.rerun()

        if st.button("Attention Drop", icon=":material/trending_down:", width="stretch"):
            st.session_state.sim_gaze, st.session_state.sim_move, st.session_state.sim_audio = 44, 48, 12
            push_telemetry_step(44, 48, 12, trigger_ai=True)
            st.rerun()

        if st.button("Quiet Note-Taking", icon=":material/edit_note:", width="stretch"):
            st.session_state.sim_gaze, st.session_state.sim_move, st.session_state.sim_audio = 75, 80, 18
            push_telemetry_step(75, 80, 18, trigger_ai=True)
            st.rerun()

        st.markdown("---")
        g_v = st.slider("Visual Attention (%)", 0, 100, int(st.session_state.sim_gaze))
        m_v = st.slider("Posture & Activity (%)", 0, 100, int(st.session_state.sim_move))
        a_v = st.slider("Class Discussion (%)", 0, 100, int(st.session_state.sim_audio))
        st.session_state.sim_gaze, st.session_state.sim_move, st.session_state.sim_audio = g_v, m_v, a_v

        if st.button("Update Live Metrics", icon=":material/tune:", type="primary", width="stretch"):
            push_telemetry_step(g_v, m_v, a_v, trigger_ai=False)
            st.rerun()

        if st.button("Test Focus Alert", icon=":material/tab_unselected:", width="stretch"):
            sname, _, act = record_focus_violation(
                st.session_state.active_student_id,
                "Left Classroom Window",
                round(random.uniform(8.0, 22.0), 1),
            )
            if sname:
                st.toast(f"{sname}: {act}")
            st.rerun()

    with st.expander("Session Settings", expanded=False):
        st.session_state.max_strikes = st.slider("Focus Alert Limit", 1, 5, int(st.session_state.max_strikes))
        sched_min = st.slider("Session Duration (min)", 5, 60, int(st.session_state.scheduled_minutes), 5)
        if sched_min != st.session_state.scheduled_minutes:
            st.session_state.scheduled_minutes = sched_min
            st.session_state.session_remaining_sec = sched_min * 60

    st.write("")
    st.markdown(
        f"""
        <div class="privacy-box">
            <div style="display:flex;align-items:center;gap:6px;font-weight:600;color:#F8FAFC;margin-bottom:4px;">
                {SVG_ICONS["lock"]}<span>Privacy &amp; Compliance</span>
            </div>
            <div><span class="dot-ok">&bull;</span>On-device processing active</div>
            <div><span class="dot-ok">&bull;</span>Zero student photos stored</div>
            <div><span class="dot-ok">&bull;</span>Guardian data isolation enabled</div>
            <div><span class="{'dot-ok' if diag['ai_local'] else 'dot-muted'}">&bull;</span>Teaching Assistant: {'Local AI' if diag['ai_local'] else 'Smart Mode'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# Trigger automatic PDF download when a scheduled session completes
if st.session_state.auto_pdf_payload:
    fname, b64_data = st.session_state.auto_pdf_payload
    components.html(render_auto_pdf_download_script(fname, b64_data), height=0)
    st.session_state.auto_pdf_payload = None

# Top Workspace Bar
role_filter = {"Instructor / Mentor": "Instructor", "Student": "Student", "Parent / Guardian": "Parent"}[st.session_state.user_role]
unread_df = get_notifications(recipient_role=role_filter)
unread_cnt = int((unread_df["acknowledged"] == 0).sum()) if not unread_df.empty else 0
status_badge = "Session Live" if st.session_state.stream_playing else "Ready"
st.markdown(render_top_nav_html(st.session_state.active_lobby, st.session_state.user_role, status_badge, unread_cnt), unsafe_allow_html=True)

if st.session_state.last_generated_pdf:
    pdf_name, pdf_raw, _ = st.session_state.last_generated_pdf
    b_l, b_r = st.columns([3.2, 1], vertical_alignment="center")
    with b_l:
        st.success(f"Session completed — **{pdf_name}** was automatically generated and saved to your Reports archive.")
    with b_r:
        st.download_button("Download PDF", data=pdf_raw, file_name=pdf_name, mime="application/pdf", icon=":material/picture_as_pdf:", type="primary", width="stretch")


# ==============================================================================
# TAB 1: LIVE SESSION
# ==============================================================================
def _render_live_session_body():
    lobby = get_active_lobby_obj()
    if st.session_state.drop_alert:
        st.markdown(f'<div class="alert-banner">{SVG_ICONS["alert"]}<span>{st.session_state.drop_alert}</span></div>', unsafe_allow_html=True)

    with st.container(border=True):
        sc1, sc2, sc3, sc4, sc5 = st.columns([1.8, 0.9, 0.85, 0.7, 1.25], vertical_alignment="center")
        mins, secs = divmod(int(st.session_state.session_remaining_sec), 60)
        with sc1:
            st.markdown(f'<div class="sec-title" style="font-size:1.05rem;">{lobby["active_subject"]}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="sec-sub" style="margin:0;">{lobby["active_host"]} &middot; {lobby["name"]}</div>', unsafe_allow_html=True)
        with sc2:
            st.markdown(
                f'<div style="text-align:center;">'
                f'<div style="font-size:0.70rem;font-weight:500;color:#94A3B8;">Time Remaining</div>'
                f'<div class="timer-val" style="font-size:1.45rem;font-weight:700;letter-spacing:-0.02em;color:#F8FAFC;">{mins:02d}:{secs:02d}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
        with sc3:
            if st.session_state.stream_playing:
                if st.button("Pause", icon=":material/pause:", width="stretch"):
                    st.session_state.stream_playing = False
                    st.rerun()
            else:
                if st.button("Start Live", icon=":material/play_arrow:", type="primary", width="stretch"):
                    st.session_state.stream_playing = True
                    st.rerun()
        with sc4:
            st.session_state.stream_speed = st.selectbox("Speed", ["1x", "2x"], index=0 if st.session_state.stream_speed == "1x" else 1, label_visibility="collapsed")
        with sc5:
            if st.button("End & Export PDF", icon=":material/picture_as_pdf:", width="stretch"):
                finalize_and_auto_generate_pdf()
                st.rerun()

    m = st.session_state.latest_metrics
    d = compute_deltas(m, st.session_state.prev_metrics)
    hist = st.session_state.engagement_history
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(render_kpi_html("Overall Engagement", m["total_engagement"], d["total_engagement"], [x["Overall"] for x in hist]), unsafe_allow_html=True)
    k2.markdown(render_kpi_html("Visual Attention", m["gaze_score"], d["gaze_score"], [x["Visual Attention"] for x in hist]), unsafe_allow_html=True)
    k3.markdown(render_kpi_html("Posture & Activity", m["movement_score"], d["movement_score"], [x["Posture & Activity"] for x in hist]), unsafe_allow_html=True)
    k4.markdown(render_kpi_html("Class Discussion", m["audio_score"], d["audio_score"], [x["Class Discussion"] for x in hist]), unsafe_allow_html=True)
    st.write("")

    col_left, col_right = st.columns([1.35, 1], gap="medium")

    with col_left:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Engagement Trends</p>', unsafe_allow_html=True)
            st.markdown(
                '<p class="sec-sub">Real-time class attention across visual focus, posture, and discussion. Open <strong>Demo Controls</strong> in the sidebar to test scenarios.</p>',
                unsafe_allow_html=True,
            )
            st.plotly_chart(build_spline_fig(hist), width="stretch", config=PLOTLY_CFG, theme=None, key=f"spline_{len(hist)}_{m['total_engagement']}")

        with st.container(border=True):
            st.markdown('<p class="sec-title">Live Classroom Attendance</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-sub">Continuous attendance verification and window focus status for enrolled students.</p>', unsafe_allow_html=True)
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
        with st.container(border=True):
            ch1, ch2 = st.columns([1.2, 1], vertical_alignment="center")
            with ch1:
                st.markdown('<p class="sec-title" style="margin:0;">Teaching Assistant</p>', unsafe_allow_html=True)
            with ch2:
                if st.button("Get Insights", icon=":material/auto_awesome:", type="primary", width="stretch"):
                    push_telemetry_step(st.session_state.sim_gaze, st.session_state.sim_move, st.session_state.sim_audio, trigger_ai=True)
                    st.rerun(scope="fragment")
            st.markdown('<p class="sec-sub" style="margin-top:4px;">Actionable pacing and engagement recommendations for this session.</p>', unsafe_allow_html=True)

            for idx, item in enumerate(st.session_state.suggestion_feed[:3]):
                st.markdown(render_coach_card_html(item["category"], item["time"], item["text"]), unsafe_allow_html=True)
                ac1, ac2, _ = st.columns([1, 1, 1.3])
                with ac1:
                    if not item.get("applied") and st.button("Mark Applied", key=f"app_{idx}", width="stretch"):
                        item["applied"] = True
                        st.toast("Marked as applied.")
                        st.rerun(scope="fragment")
                with ac2:
                    if st.button("Dismiss", key=f"dis_{idx}", width="stretch"):
                        st.session_state.suggestion_feed.pop(idx)
                        st.rerun(scope="fragment")

            with st.form("quick_coach_form", clear_on_submit=True, border=False):
                qf1, qf2 = st.columns([3.3, 1])
                with qf1:
                    q_txt = st.text_input("Ask Assistant", placeholder="Ask for a quick class activity or pacing tip...", label_visibility="collapsed")
                with qf2:
                    q_sub = st.form_submit_button("Send", icon=":material/send:", width="stretch")
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
                        {"category": adv["category"], "time": datetime.now().strftime("%H:%M"), "text": adv["text"], "applied": False},
                    )
                    st.rerun(scope="fragment")

        with st.container(border=True):
            st.markdown('<p class="sec-title">Window Focus Integrity</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-sub">Flags repeated tab switches and updates attendance automatically once the limit is reached.</p>', unsafe_allow_html=True)
            components.html(render_focus_guard_widget(int(st.session_state.max_strikes)), height=142)
            df_inc = get_proctor_incidents()
            if not df_inc.empty:
                st.dataframe(
                    df_inc[["timestamp", "student_name", "strike_count", "action_taken"]].head(4).rename(
                        columns={"timestamp": "Time", "student_name": "Student", "strike_count": "Alerts", "action_taken": "Status"}
                    ),
                    width="stretch",
                    hide_index=True,
                )


@st.fragment(run_every=2)
def render_live_session_streaming():
    if st.session_state.stream_playing:
        auto_tick_simulation()
    _render_live_session_body()


@st.fragment
def render_live_session_paused():
    _render_live_session_body()


# ==============================================================================
# TAB 2: COURSE ROOMS (UPGRADED FACULTY CARDS + FULL-WIDTH ASSIGNMENTS TABLE)
# ==============================================================================
@st.fragment
def render_course_rooms():
    l_top1, l_top2, l_top3 = st.columns([2.2, 0.9, 0.9], vertical_alignment="center")
    with l_top1:
        st.markdown('<p class="sec-title" style="font-size:1.08rem;">Course Rooms</p>', unsafe_allow_html=True)
        st.markdown('<p class="sec-sub">Shared cohort rooms where subject faculty co-host live attendance and post assignments together.</p>', unsafe_allow_html=True)

    with l_top2:
        with st.popover("New Room", icon=":material/add:", width="stretch"):
            c_code = st.text_input("Room Code", placeholder="ROOM-ME204")
            c_name = st.text_input("Room Name", placeholder="Mechanical Semester IV")
            c_cohort = st.text_input("Cohort", placeholder="B.Tech ME · Section B")
            c_host = st.text_input("Lead Instructor", value="Dr. Vikram Deshmukh")
            c_sub = st.text_input("Subject", placeholder="Thermodynamics")
            if st.button("Create Room", type="primary", width="stretch"):
                if c_code.strip() and c_name.strip() and c_sub.strip():
                    if create_lobby(c_code.strip(), c_name.strip(), c_cohort.strip() or "Cohort A", c_host.strip(), c_sub.strip()):
                        st.session_state.active_lobby = c_code.strip().upper()
                        st.toast(f"Created {c_code.strip().upper()}.")
                        st.rerun()
                    else:
                        st.error("A room with that code already exists.")

    with l_top3:
        with st.popover("Join Room", icon=":material/login:", width="stretch"):
            j_code = st.text_input("Room Code", value=st.session_state.active_lobby)
            j_teacher = st.text_input("Instructor Name", placeholder="Prof. Kavita Joshi")
            j_sub = st.text_input("Subject", placeholder="Control Systems")
            if st.button("Join as Instructor", type="primary", width="stretch"):
                if j_code.strip() and j_teacher.strip() and j_sub.strip():
                    if join_lobby_teacher(j_code.strip(), j_teacher.strip(), j_sub.strip()):
                        st.toast(f"{j_teacher} joined {j_code.upper()}.")
                        st.rerun(scope="fragment")
                    else:
                        st.error("Room code not found.")

    active_lb = get_active_lobby_obj()
    col_l, col_r = st.columns([1.0, 1.45], gap="medium")

    with col_l:
        with st.container(border=True):
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">'
                f'<span class="sec-title" style="font-size:1.0rem;">{active_lb["name"]}</span><span class="room-code">{active_lb["lobby_code"]}</span>'
                f"</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<p class="sec-sub">{active_lb["cohort"]} &middot; Active Host: <strong style="color:#F8FAFC;">{active_lb["active_host"]}</strong></p>',
                unsafe_allow_html=True,
            )

            st.markdown('<p style="font-size:0.80rem;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;color:#94A3B8;margin:10px 0 8px 0;">Faculty in Room</p>', unsafe_allow_html=True)
            teachers = get_lobby_teachers(active_lb["lobby_code"])
            for t in teachers:
                if t["is_live"] or st.session_state.user_role != "Instructor / Mentor":
                    st.markdown(render_faculty_card_html(t["teacher_name"], t["subject"], bool(t["is_live"])), unsafe_allow_html=True)
                else:
                    fc1, fc2 = st.columns([2.6, 1.0], vertical_alignment="center")
                    with fc1:
                        st.markdown(render_faculty_card_html(t["teacher_name"], t["subject"], False), unsafe_allow_html=True)
                    with fc2:
                        if st.button("Host Next", key=f"host_{t['id']}", width="stretch"):
                            set_lobby_active_host(active_lb["lobby_code"], t["teacher_name"], t["subject"])
                            st.toast(f"{t['teacher_name']} is now hosting {t['subject']}.")
                            st.rerun()

    with col_r:
        with st.container(border=True):
            ah1, ah2 = st.columns([1.9, 1.0], vertical_alignment="center")
            with ah1:
                st.markdown('<p class="sec-title" style="font-size:1.0rem;">Shared Assignments</p>', unsafe_allow_html=True)
                st.markdown('<p class="sec-sub">Coursework and deadlines shared across all subjects in this cohort.</p>', unsafe_allow_html=True)
            with ah2:
                if st.session_state.user_role == "Instructor / Mentor":
                    with st.popover("New Assignment", icon=":material/assignment_add:", width="stretch"):
                        a_sub = st.text_input("Subject", value=active_lb["active_subject"])
                        a_teacher = st.text_input("Instructor", value=active_lb["active_host"])
                        a_title = st.text_input("Title", placeholder="Lab Sheet 4: FFT Analysis")
                        a_due = st.date_input("Due Date", value=datetime.now() + timedelta(days=5))
                        if st.button("Publish", type="primary", width="stretch"):
                            if a_title.strip():
                                add_lobby_assignment(active_lb["lobby_code"], a_sub, a_teacher, a_title.strip(), str(a_due))
                                st.toast("Assignment published.")
                                st.rerun(scope="fragment")

            df_asg = get_lobby_assignments(active_lb["lobby_code"])
            if not df_asg.empty:
                df_disp = pd.DataFrame({
                    "Subject": df_asg["subject"],
                    "Assignment": df_asg["title"],
                    "Instructor": df_asg["teacher_name"],
                    "Due": df_asg["due_date"].astype(str).str.slice(5),
                    "Submitted": df_asg.apply(lambda r: f"{r['submitted_count']}/{r['total_students']}", axis=1),
                })
                st.dataframe(
                    df_disp,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Subject": st.column_config.TextColumn("Subject", width="medium"),
                        "Assignment": st.column_config.TextColumn("Assignment", width="medium"),
                        "Instructor": st.column_config.TextColumn("Instructor", width="small"),
                        "Due": st.column_config.TextColumn("Due", width="small"),
                        "Submitted": st.column_config.TextColumn("Submitted", width="small"),
                    },
                )


# ==============================================================================
# TAB 3: ATTENDANCE & GRADES
# ==============================================================================
@st.fragment
def render_attendance_and_grades():
    cum_df = compute_student_cumulative_summary()
    if cum_df.empty:
        st.info("No attendance records available yet.")
        return

    if st.session_state.user_role == "Instructor / Mentor":
        s_opts = {f"{r['student_name']} ({r['student_id']}) — {r['cumulative_pct']}%": r["student_id"] for _, r in cum_df.iterrows()}
        inv_s = {v: k for k, v in s_opts.items()}
        sel_s = st.selectbox("Select Student", list(s_opts.keys()), index=list(s_opts.keys()).index(inv_s.get(st.session_state.active_student_id, list(s_opts.keys())[0])))
        target_sid = s_opts[sel_s]
    else:
        target_sid = st.session_state.active_student_id

    row_s = cum_df[cum_df["student_id"] == target_sid].iloc[0]

    if row_s["cumulative_pct"] < 75.0:
        st.markdown(
            f'<div class="alert-banner">{SVG_ICONS["alert"]}<span>'
            f'Attendance Below 75% — {row_s["student_name"]} is currently at {row_s["cumulative_pct"]}%. '
            f'Automatic warnings have been sent to both the Student and Guardian portals ({row_s["recovery"]} needed to restore eligibility).'
            f"</span></div>",
            unsafe_allow_html=True,
        )

    m1, m2, m3, m4 = st.columns(4)
    m1.markdown(render_kpi_html("Cumulative Attendance", row_s["cumulative_pct"], None, [72, 74, row_s["cumulative_pct"]]), unsafe_allow_html=True)
    m2.markdown(render_kpi_html("Theory Lectures", row_s["theory_pct"], None, [75, 76, row_s["theory_pct"]]), unsafe_allow_html=True)
    m3.markdown(render_kpi_html("Practical Labs", row_s["practical_pct"], None, [78, 79, row_s["practical_pct"]]), unsafe_allow_html=True)
    with m4:
        b_cls = "badge-optimal" if row_s["cumulative_pct"] >= 85 else ("badge-watch" if row_s["cumulative_pct"] >= 75 else "badge-risk")
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-top"><span class="kpi-label">Attendance Grade</span><span class="kpi-badge {b_cls}">{row_s["risk_tier"]}</span></div>'
            f'<div style="font-size:1.15rem;font-weight:700;color:#F8FAFC;margin-top:6px;">{row_s["internal_grade"]}</div>'
            f'<div style="font-size:0.74rem;color:#94A3B8;margin-top:4px;">Recovery target: {row_s["recovery"]}</div></div>',
            unsafe_allow_html=True,
        )
    st.write("")

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
            "Theory": f"{sr['theory_attended']}/{sr['theory_total']}",
            "Theory %": th_p,
            "Practical": f"{sr['practical_attended']}/{sr['practical_total']}",
            "Practical %": pr_p,
            "Overall %": comb_p,
            "Internal Grade": grade,
            "75% Goal": f"Attend +{cnt}" if mode == "Need" else f"{cnt} buffer",
        })

    with st.container(border=True):
        st.markdown(f'<p class="sec-title">Subject Breakdown — {row_s["student_name"]}</p>', unsafe_allow_html=True)
        st.markdown('<p class="sec-sub">Separate tracking for Theory lectures and Practical lab sessions with internal grade calculation.</p>', unsafe_allow_html=True)
        st.dataframe(
            pd.DataFrame(calc_rows),
            width="stretch",
            hide_index=True,
            column_config={
                "Theory %": st.column_config.ProgressColumn("Theory %", min_value=0, max_value=100, format="%.1f%%"),
                "Practical %": st.column_config.ProgressColumn("Practical %", min_value=0, max_value=100, format="%.1f%%"),
                "Overall %": st.column_config.NumberColumn("Overall %", format="%.1f%%"),
            },
        )

    d_col1, d_col2 = st.columns([1.25, 1], gap="medium")

    with d_col1:
        with st.container(border=True):
            dh1, dh2 = st.columns([1.8, 1], vertical_alignment="center")
            with dh1:
                st.markdown('<p class="sec-title">Daily Attendance Summary</p>', unsafe_allow_html=True)
                st.markdown(f'<p class="sec-sub">Session log for {datetime.now().strftime("%B %d, %Y")}.</p>', unsafe_allow_html=True)
            df_daily = get_daily_logs(None if st.session_state.user_role == "Instructor / Mentor" else target_sid)
            with dh2:
                if not df_daily.empty:
                    st.download_button(
                        "Export CSV",
                        data=df_daily.to_csv(index=False).encode("utf-8"),
                        file_name=f"AttendAI_DailySummary_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        icon=":material/download:",
                        width="stretch",
                    )

            if not df_daily.empty:
                st.dataframe(
                    df_daily[["time_slot", "student_name", "subject_name", "session_type", "status", "proctor_strikes"]].rename(
                        columns={"time_slot": "Time", "student_name": "Student", "subject_name": "Subject", "session_type": "Type", "status": "Status", "proctor_strikes": "Focus Alerts"}
                    ),
                    width="stretch",
                    hide_index=True,
                )

    with d_col2:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Attendance Correction Requests</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-sub">Students can flag missed or incorrect attendance directly to their Mentor or Subject Instructor.</p>', unsafe_allow_html=True)

            if st.session_state.user_role in ("Student", "Instructor / Mentor"):
                with st.expander("Flag a Session for Review", expanded=(st.session_state.user_role == "Student")):
                    stu_daily = get_daily_logs(target_sid)
                    flag_opts = (
                        {f"{r['subject_name']} ({r['session_type']}) · {r['status']} [#{r['id']}]": r for _, r in stu_daily.iterrows()}
                        if not stu_daily.empty
                        else {}
                    )
                    if flag_opts:
                        pick_lbl = st.selectbox("Session", list(flag_opts.keys()))
                        picked = flag_opts[pick_lbl]
                        route_to = st.radio("Send Request To", ["Assigned Mentor", "Subject Instructor"], horizontal=True)
                        recip_name = "Dr. Vikram Deshmukh (Mentor)" if route_to == "Assigned Mentor" else picked["teacher_name"]
                        reason_txt = st.text_area("Reason", placeholder="Briefly explain why this attendance record should be reviewed.")
                        if st.button("Submit Request", icon=":material/flag:", type="primary", width="stretch"):
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
                                st.toast(f"Request routed to {recip_name}.")
                                st.rerun(scope="fragment")

            tickets_df = get_dispute_tickets(None if st.session_state.user_role == "Instructor / Mentor" else target_sid)
            if tickets_df.empty:
                st.caption("No open attendance correction requests.")
            else:
                for _, tk in tickets_df.head(5).iterrows():
                    st.markdown(
                        f'<div class="notif-card notif-{"warning" if tk["status"]=="Pending Review" else "info"}">'
                        f'<div style="display:flex;justify-content:space-between;font-size:0.80rem;margin-bottom:4px;">'
                        f'<strong style="color:#F8FAFC;">{tk["student_name"]} &middot; {tk["subject_name"]} ({tk["session_type"]})</strong>'
                        f'<span style="color:#A5B4FC;font-weight:600;font-size:0.74rem;">{tk["status"]}</span></div>'
                        f'<div style="font-size:0.80rem;color:#CBD5E1;">Sent to {tk["recipient_name"]} — {tk["reason"]}</div></div>',
                        unsafe_allow_html=True,
                    )
                    if tk["status"] == "Pending Review" and st.session_state.user_role == "Instructor / Mentor":
                        rb1, rb2 = st.columns(2)
                        with rb1:
                            if st.button("Approve & Update", key=f"appr_{tk['id']}", type="primary", width="stretch"):
                                resolve_dispute_ticket(int(tk["id"]), True, "Verified by instructor; attendance recalculated.")
                                st.toast("Approved and recalculated.")
                                st.rerun(scope="fragment")
                        with rb2:
                            if st.button("Decline", key=f"rej_{tk['id']}", width="stretch"):
                                resolve_dispute_ticket(int(tk["id"]), False, "Unable to verify session attendance.")
                                st.toast("Request declined.")
                                st.rerun(scope="fragment")


# ==============================================================================
# TAB 4: GUARDIAN & STUDENT SAFETY
# ==============================================================================
@st.fragment
def render_guardian_and_safety():
    cum_df = compute_student_cumulative_summary()
    target_sid = st.session_state.active_student_id
    ward_row = cum_df[cum_df["student_id"] == target_sid].iloc[0] if not cum_df.empty and target_sid in cum_df["student_id"].values else None

    p_left, p_right = st.columns([1.25, 1], gap="medium")

    with p_left:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Guardian Portal &amp; Alerts</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-sub">Automatic attendance summaries, below-75% warnings, and unexpected exit notifications for families.</p>', unsafe_allow_html=True)

            if ward_row is not None:
                st.markdown(
                    f'<div class="room-summary">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                    f'<strong style="color:#F8FAFC;">{ward_row["student_name"]} ({ward_row["student_id"]})</strong>'
                    f'<span class="room-code">Overall: {ward_row["cumulative_pct"]}%</span></div>'
                    f'<div style="font-size:0.81rem;color:#CBD5E1;margin-top:6px;">Theory: <strong>{ward_row["theory_pct"]}%</strong> &middot; Practical: <strong>{ward_row["practical_pct"]}%</strong> &middot; Grade: <strong>{ward_row["internal_grade"]}</strong></div>'
                    f"</div>",
                    unsafe_allow_html=True,
                )

            if st.button("Check & Send Below-75% Warnings", icon=":material/notifications_active:", width="stretch"):
                cnt = dispatch_below_75_warnings()
                st.toast(f"Sent {cnt} new attendance warning(s)." if cnt else "All below-75% warnings are up to date.")
                st.rerun(scope="fragment")

            parent_notifs = get_notifications(recipient_role="Parent" if st.session_state.user_role == "Parent / Guardian" else None)
            if parent_notifs.empty:
                st.caption("No guardian alerts sent yet.")
            else:
                for _, nf in parent_notifs.head(6).iterrows():
                    sev_cls = "critical" if nf["severity"] == "Critical" else ("warning" if nf["severity"] == "Warning" else "info")
                    ack_txt = "Acknowledged" if nf["acknowledged"] else "Unread"
                    st.markdown(
                        f'<div class="notif-card notif-{sev_cls}">'
                        f'<div style="display:flex;justify-content:space-between;font-size:0.80rem;margin-bottom:4px;">'
                        f'<strong style="color:#F8FAFC;">{nf["title"]}</strong><span style="color:#94A3B8;font-size:0.73rem;">{nf["created_at"]}</span></div>'
                        f'<div style="font-size:0.80rem;color:#CBD5E1;">{nf["message"]}</div>'
                        f'<div style="font-size:0.72rem;color:#94A3B8;margin-top:5px;">Recipient: {nf["recipient_role"]} &middot; {nf["channels"]} &middot; <strong style="color:#E2E8F0;">{ack_txt}</strong></div>'
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    if not nf["acknowledged"]:
                        if st.button("Mark as Read", key=f"ack_{nf['id']}", width="stretch"):
                            acknowledge_notification(int(nf["id"]))
                            st.rerun(scope="fragment")

    with p_right:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Student Safety &amp; Well-Being</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-sub">Private safety check-ins during class hours and direct family-to-mentor communication.</p>', unsafe_allow_html=True)

            st.markdown("**Private Safety Check-In**")
            sos_note = st.text_input("Optional note for Mentor", placeholder="e.g., Feeling unwell in Lab Block B, need assistance.")
            if st.button("Alert Mentor Privately", icon=":material/health_and_safety:", type="primary", width="stretch"):
                w_name = ward_row["student_name"] if ward_row is not None else "Student"
                msg = sos_note.strip() or f"{w_name} requested a private well-being check-in during scheduled hours."
                for r_role in ("Instructor", "Parent"):
                    dispatch_notification(
                        recipient_role=r_role,
                        student_id=target_sid,
                        student_name=w_name,
                        category="Student Safety",
                        severity="Critical",
                        title=f"Safety Check-In — {w_name}",
                        message=msg,
                        channels="Mentor Desk · SMS",
                    )
                st.success("Your private safety check-in has been sent to your Mentor.")
                st.rerun(scope="fragment")

            st.divider()
            st.markdown("**Message Assigned Mentor**")
            with st.form("parent_mentor_msg", clear_on_submit=True, border=False):
                pm_txt = st.text_input("Message", placeholder="Share a note regarding absence or well-being...")
                if st.form_submit_button("Send Message", icon=":material/mail:", width="stretch") and pm_txt.strip():
                    w_name = ward_row["student_name"] if ward_row is not None else "Student"
                    dispatch_notification(
                        recipient_role="Instructor",
                        student_id=target_sid,
                        student_name=w_name,
                        category="Guardian Note",
                        severity="Info",
                        title=f"Note from Guardian ({w_name})",
                        message=pm_txt.strip(),
                        channels="Guardian Portal",
                    )
                    st.toast("Note delivered to Mentor.")
                    st.rerun(scope="fragment")


# ==============================================================================
# TAB 5: STUDENT ROSTER & SESSION REPORTS
# ==============================================================================
@st.fragment
def render_roster_and_reports():
    sub_tab1, sub_tab2 = st.tabs([":material/group: Student Roster", ":material/description: Session Reports & Analytics"])

    with sub_tab1:
        r_l, r_r = st.columns([1, 1.35], gap="medium")
        with r_l:
            with st.container(border=True):
                st.markdown('<p class="sec-title">Enroll Student</p>', unsafe_allow_html=True)
                st.markdown('<p class="sec-sub">Generates an encrypted identity signature on-device and discards the photo immediately.</p>', unsafe_allow_html=True)
                nid = st.text_input("Student ID", placeholder="S107")
                nname = st.text_input("Full Name", placeholder="Priya Deshmukh")
                src_mode = st.radio("Photo Source", ["Upload Photo", "Camera Snapshot"], horizontal=True)
                img_file = st.file_uploader("Front-facing portrait", type=["jpg", "jpeg", "png"]) if src_mode == "Upload Photo" else st.camera_input("Take Snapshot")

                if st.button("Save Student Profile", icon=":material/person_add:", type="primary", width="stretch"):
                    if not nid.strip() or not nname.strip() or img_file is None:
                        st.error("Enter Student ID, Full Name, and provide a clear photo.")
                    else:
                        arr = np.asarray(bytearray(img_file.read()), dtype=np.uint8)
                        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                        if img is not None:
                            fapp = get_face_analyzer()
                            faces = fapp.get(img)
                            if len(faces) == 1:
                                emb = faces[0].embedding / np.linalg.norm(faces[0].embedding)
                                save_student(nid.strip(), nname.strip(), emb)
                                st.success(f"Enrolled {nname.strip()}. Original photo permanently discarded.")
                                st.rerun(scope="fragment")
                            else:
                                st.error("Please ensure exactly one clear face is visible.")

        with r_r:
            with st.container(border=True):
                rh1, rh2 = st.columns([1.6, 1], vertical_alignment="center")
                with rh1:
                    st.markdown('<p class="sec-title">Enrolled Directory</p>', unsafe_allow_html=True)
                with rh2:
                    if st.button("Load Sample Roster", icon=":material/group_add:", width="stretch"):
                        seed_sample_roster()
                        st.rerun(scope="fragment")

                roster = load_all_students()
                rdf = pd.DataFrame([
                    {
                        "Student ID": r["student_id"],
                        "Name": r["name"],
                        "Privacy Status": "Encrypted Signature · No Photo",
                        "Added": r["created_at"],
                    }
                    for r in roster
                ])
                st.dataframe(rdf, width="stretch", hide_index=True)

                if roster:
                    i1, i2, i3 = st.columns([2, 1, 1], vertical_alignment="center")
                    opts = [f"{r['name']} ({r['student_id']})" for r in roster]
                    with i1:
                        picked = st.selectbox("Manage Student", opts, label_visibility="collapsed")
                    tid = picked.split("(")[-1].rstrip(")")
                    tobj = next(r for r in roster if r["student_id"] == tid)
                    with i2:
                        with st.popover("Privacy Proof", icon=":material/verified_user:", width="stretch"):
                            st.markdown(f"**{tobj['name']}** (`{tid}`)")
                            st.caption("Stored Images: 0 files (0 bytes)")
                            vals = ", ".join(f"{v:+.4f}" for v in tobj["embedding"][:8])
                            st.code(f"Signature Preview: [{vals}, ...]", language="text")
                    with i3:
                        if st.button("Remove", icon=":material/delete:", width="stretch"):
                            delete_student(tid)
                            st.rerun(scope="fragment")

    with sub_tab2:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Automated Session PDF Archive</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-sub">Generated automatically whenever a scheduled session concludes.</p>', unsafe_allow_html=True)
            rep_df = get_session_reports()
            if rep_df.empty:
                st.caption("Click End & Export PDF in the Live Session tab to archive your first session report.")
            else:
                for _, rr in rep_df.head(5).iterrows():
                    rc1, rc2 = st.columns([3, 1], vertical_alignment="center")
                    with rc1:
                        st.markdown(
                            f"**{rr['subject_name']}** ({rr['lobby_code']}) &middot; "
                            f"Engagement: **{rr['avg_engagement']}%** &middot; Present: **{rr['present_count']}/{rr['total_count']}** &middot; "
                            f"Focus Alerts: **{rr['proctor_violations']}** &middot; _{rr['generated_at']}_"
                        )
                    with rc2:
                        st.download_button(
                            "Download PDF",
                            data=base64.b64decode(rr["pdf_b64"]),
                            file_name=f"AttendAI_Session_Report_{rr['session_id']}.pdf",
                            mime="application/pdf",
                            icon=":material/picture_as_pdf:",
                            key=f"dl_rep_{rr['id']}",
                            width="stretch",
                        )

        sessions = get_session_list()
        sel_sess = st.selectbox("Session History", ["ALL"] + sessions, format_func=lambda x: "All Sessions" if x == "ALL" else x)
        _, df_eng, _ = get_session_data(sel_sess)

        if not df_eng.empty:
            c1, c2 = st.columns([1.5, 1], gap="medium")
            with c1:
                with st.container(border=True):
                    st.markdown('<p class="sec-title">Engagement Breakdown</p>', unsafe_allow_html=True)
                    df_p = df_eng.tail(18).rename(columns={"gaze_score": "Visual Attention", "movement_score": "Posture & Activity", "audio_score": "Class Discussion"})
                    fig_b = go.Figure()
                    for nm, cl in [("Visual Attention", "#818CF8"), ("Posture & Activity", "#38BDF8"), ("Class Discussion", "#10B981")]:
                        fig_b.add_trace(go.Bar(x=df_p["timestamp"], y=df_p[nm], name=nm, marker_color=cl))
                    fig_b.update_layout(
                        barmode="group",
                        height=280,
                        margin=dict(l=8, r=8, t=10, b=8),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#CBD5E1", family="Inter", size=11),
                        hoverlabel=PLOTLY_HOVER,
                        yaxis=dict(range=[0, 105], gridcolor="rgba(148,163,184,0.12)"),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="#CBD5E1")),
                    )
                    st.plotly_chart(fig_b, width="stretch", config=PLOTLY_CFG, theme=None)

            with c2:
                with st.container(border=True):
                    st.markdown('<p class="sec-title">Engagement Mix</p>', unsafe_allow_html=True)
                    comp = round(float(df_eng["total_engagement"].mean()), 1)
                    fig_d = go.Figure(
                        data=[
                            go.Pie(
                                labels=["Visual Attention", "Posture & Activity", "Class Discussion"],
                                values=[round(float(df_eng["gaze_score"].mean()), 1), round(float(df_eng["movement_score"].mean()), 1), round(float(df_eng["audio_score"].mean()), 1)],
                                hole=0.68,
                                marker=dict(colors=["#818CF8", "#38BDF8", "#10B981"], line=dict(color="#0F172A", width=2)),
                            )
                        ]
                    )
                    fig_d.update_layout(
                        height=280,
                        margin=dict(l=12, r=12, t=12, b=28),
                        paper_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#CBD5E1", family="Inter", size=11),
                        hoverlabel=PLOTLY_HOVER,
                        legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.08, font=dict(color="#CBD5E1")),
                        annotations=[dict(text=f"<b>{comp:.1f}%</b><br><span style='font-size:11px;color:#94A3B8;'>Overall</span>", x=0.5, y=0.5, font=dict(size=20, color="#F8FAFC"), showarrow=False)],
                    )
                    st.plotly_chart(fig_d, width="stretch", config=PLOTLY_CFG, theme=None)


# --- Primary Navigation ---
tabs = st.tabs([
    ":material/sensors: Live Session",
    ":material/meeting_room: Course Rooms",
    ":material/calculate: Attendance & Grades",
    ":material/family_restroom: Guardian & Safety",
    ":material/folder_shared: Roster & Reports",
])

with tabs[0]:
    if st.session_state.stream_playing:
        render_live_session_streaming()
    else:
        render_live_session_paused()

with tabs[1]:
    render_course_rooms()

with tabs[2]:
    render_attendance_and_grades()

with tabs[3]:
    render_guardian_and_safety()

with tabs[4]:
    render_roster_and_reports()