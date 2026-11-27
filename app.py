

import base64
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from modules.agent import TeachingAdvisorAgent
from modules.attendance import STATE_NEEDS_REVIEW, STATE_PRESENT
from modules.database import (
    acknowledge_notification,
    add_daily_log,
    add_lobby_assignment,
    add_or_update_subject_record,
    clear_all_data,
    compute_internal_grade,
    compute_recovery_classes,
    compute_student_cumulative_summary,
    create_dispute_ticket,
    create_lobby,
    dispatch_below_threshold_warnings,
    dispatch_notification,
    get_attention_snapshots,
    get_daily_logs,
    get_dispute_tickets,
    get_lobbies,
    get_lobby_assignments,
    get_lobby_teachers,
    get_notifications,
    get_session_reports,
    get_student_subject_records,
    init_db,
    join_lobby_teacher,
    load_all_students,
    log_engagement,
    resolve_dispute_ticket,
    set_lobby_active_host,
)
from modules.live_attendance_ui import (
    ensure_phase1_state,
    finalize_real_session_and_export_pdf,
    get_or_build_tracker,
    render_demo_mode_banner,
    render_honest_kpi_card,
    render_instructor_focus_feed,
    render_live_face_capture_section,
    render_phase1_roster_enrollment,
    render_real_attention_section,
    render_student_live_focus_view,
)
from modules.styles import (
    SVG_ICONS,
    get_app_css,
    render_auto_pdf_download_script,
    render_faculty_card_html,
    render_kpi_html,
    render_top_nav_html,
)

# --- Page Config ---
st.set_page_config(
    page_title="AttendAI — Classroom Workspace",
    page_icon=":material/verified_user:",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
ensure_phase1_state()

DURATION_OPTIONS = {
    "45 minutes": 45,
    "1 hour": 60,
    "1 hour 15 minutes": 75,
    "1 hour 30 minutes": 90,
    "1 hour 45 minutes": 105,
    "2 hours": 120,
}

ACCENT_PRESETS = {
    "Crimson Flag": "#C81E1E",
    "Cobalt Royal": "#1D4ED8",
    "Forest Emerald": "#047857",
    "Burnt Amber": "#B45309",
    "Deep Plum": "#6D28D9",
}

defaults = {
    "org_name": "Campus Workspace",
    "accent_color": "#C81E1E",
    "user_role": "Instructor / Mentor",
    "active_lobby": None,
    "active_student_id": None,
    "session_subject": "",
    "session_id": datetime.now().strftime("SESS_%Y%m%d_%H%M%S"),
    "class_duration_label": "45 minutes",
    "session_remaining_sec": 45 * 60,
    "stream_playing": False,
    "stream_speed": "1x",
    "min_attendance_pct": 75,
    "grade_a_plus": 90,
    "grade_a": 85,
    "grade_max_marks": 5,
    "w_gaze": 50,
    "w_move": 25,
    "w_audio": 25,
    "sim_gaze": 0,
    "sim_move": 0,
    "sim_audio": 0,
    "latest_metrics": {
        "total_engagement": 0.0,
        "gaze_score": 0.0,
        "movement_score": 0.0,
        "audio_score": 0.0,
        "inactivity_sec": 0.0,
    },
    "engagement_history": [],
    "suggestion_feed": [],
    "auto_pdf_payload": None,
    "last_generated_pdf": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

ACCENT = st.session_state.accent_color
st.markdown(get_app_css(ACCENT), unsafe_allow_html=True)

PLOTLY_CFG = {"displayModeBar": False}
PLOTLY_HOVER = dict(bgcolor="#FFFFFF", bordercolor="#E2E8F0", font=dict(color="#0F172A", family="Inter", size=12))


def get_grade_slabs() -> dict:
    return {
        "a_plus": st.session_state.grade_a_plus,
        "a": st.session_state.grade_a,
        "max_marks": st.session_state.grade_max_marks,
    }


def get_active_room() -> dict | None:
    lobbies = get_lobbies()
    if not lobbies:
        st.session_state.active_lobby = None
        return None
    for lb in lobbies:
        if lb["lobby_code"] == st.session_state.active_lobby:
            return lb
    st.session_state.active_lobby = lobbies[0]["lobby_code"]
    return lobbies[0]


def record_demo_engagement_step(front_ratio: float, alignment: float) -> None:
    """DEMO MODE ONLY: logs simulated visual sliders (audio explicitly Not measured)."""
    w_sum = max(1, st.session_state.w_gaze + st.session_state.w_move)
    total = round(
        front_ratio * (st.session_state.w_gaze / w_sum)
        + alignment * (st.session_state.w_move / w_sum),
        1,
    )
    st.session_state.latest_metrics = {
        "total_engagement": total,
        "gaze_score": round(front_ratio, 1),
        "movement_score": round(alignment, 1),
        "audio_score": 0.0,
        "inactivity_sec": 0.0,
    }
    st.session_state.engagement_history.append({
        "Time": datetime.now().strftime("%H:%M:%S"),
        "Combined Attention (SIMULATED)": total,
        "Facing-Front Ratio (SIMULATED)": round(front_ratio, 1),
        "Head Alignment (SIMULATED)": round(alignment, 1),
    })
    st.session_state.engagement_history = st.session_state.engagement_history[-24:]
    log_engagement(st.session_state.session_id, front_ratio, alignment, 0.0, total, is_demo=True)


def auto_tick_timer() -> None:
    step_sec = 4 if st.session_state.stream_speed == "2x" else 2
    st.session_state.session_remaining_sec = max(0, st.session_state.session_remaining_sec - step_sec)
    if st.session_state.session_remaining_sec <= 0:
        finalize_real_session_and_export_pdf(active_room, DURATION_OPTIONS[st.session_state.class_duration_label])


def build_demo_trend_chart(history: list) -> go.Figure:
    df_h = pd.DataFrame(history)
    fig = go.Figure()
    styles = [
        ("Combined Attention (SIMULATED)", "#0F172A", 2.8, "solid"),
        ("Facing-Front Ratio (SIMULATED)", "#4F46E5", 1.8, "dash"),
        ("Head Alignment (SIMULATED)", ACCENT, 1.8, "dot"),
    ]
    for name, col, w, dash in styles:
        if name in df_h.columns:
            fig.add_trace(
                go.Scatter(
                    x=df_h["Time"],
                    y=df_h[name],
                    mode="lines+markers",
                    name=name,
                    line=dict(color=col, width=w, dash=dash, shape="spline"),
                    marker=dict(size=5, color=col),
                )
            )
    fig.update_layout(
        height=230,
        margin=dict(l=8, r=8, t=12, b=8),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font=dict(color="#0F172A", family="Inter", size=11),
        hovermode="x unified",
        hoverlabel=PLOTLY_HOVER,
        yaxis=dict(range=[0, 105], title="Score (%)", gridcolor="#E2E8F0", zeroline=False),
        xaxis=dict(title="", gridcolor="#F1F5F9"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


lobbies = get_lobbies()
all_students = load_all_students()
active_room = get_active_room()

# --- Sidebar ---
with st.sidebar:
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:2px;">'
        f'<div class="brand-mark" style="width:28px;height:28px;">{SVG_ICONS["brand"]}</div>'
        f'<span style="font-size:1.05rem;font-weight:800;color:#0F172A;">AttendAI</span>'
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(st.session_state.org_name)
    st.divider()

    st.session_state.demo_mode = st.toggle(
        "Demo Mode (Simulated Data)",
        value=bool(st.session_state.demo_mode),
        help="Off by default. Turn on only to demonstrate flows without a live camera.",
    )

    st.markdown("**View As**")
    st.session_state.user_role = st.selectbox(
        "View As",
        ["Instructor / Mentor", "Student", "Parent / Guardian"],
        index=["Instructor / Mentor", "Student", "Parent / Guardian"].index(st.session_state.user_role),
        label_visibility="collapsed",
    )

    if st.session_state.user_role in ("Student", "Parent / Guardian"):
        st.markdown("**Student Profile**")
        if all_students:
            s_map = {f"{s['name']} ({s['student_id']})": s["student_id"] for s in all_students}
            inv = {v: k for k, v in s_map.items()}
            def_k = inv.get(st.session_state.active_student_id, list(s_map.keys())[0])
            pick = st.selectbox("Student Profile", list(s_map.keys()), index=list(s_map.keys()).index(def_k), label_visibility="collapsed")
            st.session_state.active_student_id = s_map[pick]
        else:
            st.caption("No students enrolled yet. Add students in Roster & Reports.")

    st.markdown("**Active Course Room**")
    if lobbies:
        codes = [lb["lobby_code"] for lb in lobbies]
        idx_c = codes.index(st.session_state.active_lobby) if st.session_state.active_lobby in codes else 0
        st.session_state.active_lobby = st.selectbox("Active Room", codes, index=idx_c, label_visibility="collapsed")
    else:
        st.caption("No course room yet. Create one in Course Rooms.")

    st.markdown("**Lecture Duration**")
    dur_labels = list(DURATION_OPTIONS.keys())
    new_dur = st.selectbox(
        "Lecture Duration",
        dur_labels,
        index=dur_labels.index(st.session_state.class_duration_label),
        label_visibility="collapsed",
    )
    if new_dur != st.session_state.class_duration_label:
        st.session_state.class_duration_label = new_dur
        st.session_state.session_remaining_sec = DURATION_OPTIONS[new_dur] * 60
        st.session_state.snapshot_schedule = []
        st.rerun()

    # Sliders exist strictly inside Demo Mode only (zero sliders in Live Mode)
    if st.session_state.demo_mode:
        st.divider()
        with st.expander("Demo Controls (Simulated)", expanded=True):
            st.caption("Simulated visual sliders only (Audio: Not measured; does NOT fake attendance).")
            g_val = st.slider("Facing-Front Ratio (%)", 0, 100, int(st.session_state.sim_gaze))
            m_val = st.slider("Head Alignment (%)", 0, 100, int(st.session_state.sim_move))
            st.session_state.sim_gaze, st.session_state.sim_move = g_val, m_val
            if st.button("Record Simulated Trend Point", icon=":material/add_chart:", type="primary", use_container_width=True):
                record_demo_engagement_step(g_val, m_val)
                st.rerun()

    st.divider()
    st.markdown("**Flag / Highlight Color**")
    chosen_color = st.color_picker(
        "Pick Flag Color",
        value=st.session_state.accent_color,
        help="Color used for warnings, flags, and highlights.",
    )
    if chosen_color != st.session_state.accent_color:
        st.session_state.accent_color = chosen_color
        st.rerun()

# Trigger Auto-PDF download when session completes
if st.session_state.auto_pdf_payload:
    fname, b64_data = st.session_state.auto_pdf_payload
    components.html(render_auto_pdf_download_script(fname, b64_data), height=0)
    st.session_state.auto_pdf_payload = None

# Top Header & Demo Mode Banner
role_key = {"Instructor / Mentor": "Instructor", "Student": "Student", "Parent / Guardian": "Parent"}[st.session_state.user_role]
unread_df = get_notifications(recipient_role=role_key)
unread_cnt = int((unread_df["acknowledged"] == 0).sum()) if not unread_df.empty else 0
room_tag = active_room["lobby_code"] if active_room else "No Room Selected"
status_tag = "Live" if st.session_state.stream_playing else "Standby"
st.markdown(render_top_nav_html(st.session_state.org_name, room_tag, st.session_state.user_role, status_tag, unread_cnt), unsafe_allow_html=True)
render_demo_mode_banner()

if st.session_state.last_generated_pdf:
    pdf_name, pdf_raw, _ = st.session_state.last_generated_pdf
    bl, br = st.columns([3.2, 1], vertical_alignment="center")
    with bl:
        st.info(f"Session report **{pdf_name}** was automatically generated and saved under Roster & Reports.")
    with br:
        st.download_button("Download PDF", data=pdf_raw, file_name=pdf_name, mime="application/pdf", icon=":material/picture_as_pdf:", type="primary", use_container_width=True)


# ==============================================================================
# TAB 1: LIVE SESSION (PHASE 1 REAL ATTENDANCE + PHASE 2 HEAD-POSE & FOCUS SYNC)
# ==============================================================================
def _render_live_session() -> None:
    # Student Mode gets the dedicated bidirectional Window Focus Monitor join flow
    if st.session_state.user_role == "Student":
        render_student_live_focus_view(active_room, ACCENT)
        return

    tracker = get_or_build_tracker()
    summaries = tracker.get_student_summaries()
    total_students = len(summaries)
    present_cnt = sum(1 for s in summaries if s.state == STATE_PRESENT)
    review_cnt = sum(1 for s in summaries if s.state == STATE_NEEDS_REVIEW)

    df_pose = get_attention_snapshots(st.session_state.session_id)
    measured_pose = df_pose[df_pose["facing_front_ratio"].notna()] if not df_pose.empty else pd.DataFrame()
    latest_pose = measured_pose.iloc[-1] if not measured_pose.empty else None

    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns([1.85, 0.95, 0.85, 0.7, 1.25], vertical_alignment="center")
        mins, secs = divmod(int(st.session_state.session_remaining_sec), 60)
        subj_title = active_room["active_subject"] if active_room else (st.session_state.session_subject or "New Lecture Session")
        host_sub = (
            f"{active_room['active_host']} · {active_room['name']}"
            if active_room
            else "Create a room in Course Rooms to attach faculty and assignments."
        )
        with c1:
            st.markdown(f'<div class="sec-title" style="font-size:1.05rem;">{subj_title}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="sec-sub" style="margin:0;">{host_sub}</div>', unsafe_allow_html=True)
        with c2:
            st.markdown(
                f'<div style="text-align:center;">'
                f'<div style="font-size:0.70rem;font-weight:600;color:#64748B;text-transform:uppercase;">{st.session_state.class_duration_label}</div>'
                f'<div class="timer-val" style="font-size:1.55rem;font-weight:800;color:#0F172A;">{mins:02d}:{secs:02d}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
        with c3:
            if st.session_state.stream_playing:
                if st.button("Pause", icon=":material/pause:", use_container_width=True):
                    st.session_state.stream_playing = False
                    st.rerun()
            else:
                if st.button("Start Class", icon=":material/play_arrow:", type="primary", use_container_width=True):
                    st.session_state.stream_playing = True
                    st.rerun()
        with c4:
            st.session_state.stream_speed = st.selectbox("Speed", ["1x", "2x"], index=0 if st.session_state.stream_speed == "1x" else 1, label_visibility="collapsed")
        with c5:
            if st.button("End & Auto-PDF", icon=":material/picture_as_pdf:", use_container_width=True):
                finalize_real_session_and_export_pdf(active_room, DURATION_OPTIONS[st.session_state.class_duration_label])
                st.rerun()

    # Four Honest Live KPIs (Renamed to exactly what is measured; Audio explicitly Not measured)
    present_pct = round((present_cnt / total_students) * 100.0, 1) if total_students else 0.0
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(
        render_honest_kpi_card(
            "Verified Present",
            f"{present_pct:.1f}%",
            f"{present_cnt}/{total_students} students ({review_cnt} review)",
            flagged=(review_cnt > 0),
            tag="Real Tracker" if tracker.total_snapshots else "Standby",
        ),
        unsafe_allow_html=True,
    )
    if latest_pose is not None:
        ff_val = float(latest_pose["facing_front_ratio"])
        al_val = float(latest_pose["head_alignment_score"])
        k2.markdown(
            render_honest_kpi_card(
                "Facing-Front Ratio",
                f"{ff_val:.1f}%",
                f"{int(latest_pose['faces_facing_front'])}/{int(latest_pose['faces_evaluated'])} faces front-aligned",
                flagged=(ff_val < 60.0),
                tag="Flagged" if ff_val < 60.0 else "Measured",
            ),
            unsafe_allow_html=True,
        )
        k3.markdown(
            render_honest_kpi_card(
                "Head Alignment",
                f"{al_val:.1f}%",
                f"Avg |yaw| {latest_pose['mean_abs_yaw_deg']}° · |pitch| {latest_pose['mean_abs_pitch_deg']}°",
                flagged=(al_val < 60.0),
                tag="Flagged" if al_val < 60.0 else "Measured",
            ),
            unsafe_allow_html=True,
        )
    else:
        k2.markdown(render_honest_kpi_card("Facing-Front Ratio", "Not measured", "Capture a snapshot to compute", tag="Standby"), unsafe_allow_html=True)
        k3.markdown(render_honest_kpi_card("Head Alignment", "Not measured", "Derived from 5-pt facial keypoints", tag="Standby"), unsafe_allow_html=True)

    k4.markdown(
        render_honest_kpi_card(
            "Audio Activity",
            "Not measured",
            "No live mic capture · visual weights renormalized",
            flagged=False,
            tag="Unmeasured",
        ),
        unsafe_allow_html=True,
    )
    st.write("")

    col_l, col_r = st.columns([1.35, 1], gap="medium")

    with col_l:
        render_live_face_capture_section(DURATION_OPTIONS[st.session_state.class_duration_label], active_room=active_room)

    with col_r:
        render_real_attention_section(ACCENT)

        if st.session_state.demo_mode and st.session_state.engagement_history:
            with st.container(border=True):
                st.markdown('<p class="sec-title">Simulated Trend Chart (Demo Mode)</p>', unsafe_allow_html=True)
                st.plotly_chart(build_demo_trend_chart(st.session_state.engagement_history), use_container_width=True, config=PLOTLY_CFG, theme=None)

        render_instructor_focus_feed(active_room)

        with st.container(border=True):
            h1, h2 = st.columns([1.2, 1], vertical_alignment="center")
            with h1:
                st.markdown('<p class="sec-title" style="margin:0;">Teaching Assistant</p>', unsafe_allow_html=True)
            with h2:
                if st.button("Generate Tip", icon=":material/auto_awesome:", type="primary", use_container_width=True):
                    agent = TeachingAdvisorAgent()
                    adv = agent.generate_advice(
                        st.session_state.session_id,
                        st.session_state.latest_metrics,
                        present_cnt,
                        max(1, total_students),
                    )
                    st.session_state.suggestion_feed.insert(0, {"category": adv["category"], "time": datetime.now().strftime("%H:%M"), "text": adv["text"]})
                    st.rerun(scope="fragment")
            st.markdown('<p class="sec-sub" style="margin-top:4px;">Ask for pacing suggestions or classroom activities.</p>', unsafe_allow_html=True)

            if not st.session_state.suggestion_feed:
                st.caption("No suggestions generated yet. Click Generate Tip or ask a question below.")
            else:
                for item in st.session_state.suggestion_feed[:3]:
                    st.markdown(
                        f'<div class="ink-card"><div class="row-between"><span class="kpi-tag">{item["category"]}</span>'
                        f'<span class="card-meta">{item["time"]}</span></div>'
                        f'<div style="font-size:0.83rem;margin-top:6px;line-height:1.5;">{item["text"]}</div></div>',
                        unsafe_allow_html=True,
                    )

            with st.form("assistant_ask_form", clear_on_submit=True, border=False):
                q1, q2 = st.columns([3.2, 1])
                with q1:
                    q_text = st.text_input(
                        "Ask Teaching Assistant",
                        placeholder="Example: Suggest a 2-minute concept check for today's lecture",
                        label_visibility="collapsed",
                    )
                with q2:
                    q_send = st.form_submit_button("Ask", icon=":material/send:", use_container_width=True)
                if q_send and q_text.strip():
                    agent = TeachingAdvisorAgent()
                    adv = agent.generate_advice(
                        st.session_state.session_id,
                        st.session_state.latest_metrics,
                        present_cnt,
                        max(1, total_students),
                        custom_question=q_text.strip(),
                    )
                    st.session_state.suggestion_feed.insert(0, {"category": adv["category"], "time": datetime.now().strftime("%H:%M"), "text": adv["text"]})
                    st.rerun(scope="fragment")


@st.fragment(run_every=2)
def render_live_streaming() -> None:
    if st.session_state.stream_playing:
        auto_tick_timer()
    _render_live_session()


@st.fragment
def render_live_paused() -> None:
    _render_live_session()


# ==============================================================================
# TAB 2: COURSE ROOMS
# ==============================================================================
@st.fragment
def render_course_rooms() -> None:
    t1, t2, t3 = st.columns([2.1, 0.95, 0.95], vertical_alignment="center")
    with t1:
        st.markdown('<p class="sec-title" style="font-size:1.05rem;">Course Rooms</p>', unsafe_allow_html=True)
        st.markdown('<p class="sec-sub">Create a shared cohort room where multiple subject teachers track attendance and share assignments together.</p>', unsafe_allow_html=True)

    with t2:
        with st.popover("New Room", icon=":material/add:", use_container_width=True):
            c_code = st.text_input("Room Code", placeholder="Example: ECE-301")
            c_name = st.text_input("Room Name", placeholder="Example: B.Tech ECE Semester V")
            c_cohort = st.text_input("Section / Batch", placeholder="Example: Section A (2026-27)")
            c_host = st.text_input("Lead Instructor", placeholder="Example: Dr. Vikram Deshmukh")
            c_sub = st.text_input("Primary Subject", placeholder="Example: Digital Signal Processing")
            if st.button("Create Room", type="primary", use_container_width=True):
                if c_code.strip() and c_name.strip() and c_host.strip() and c_sub.strip():
                    if create_lobby(c_code, c_name, c_cohort or "General Batch", c_host, c_sub):
                        st.session_state.active_lobby = c_code.strip().upper()
                        st.toast(f"Created room {c_code.strip().upper()}.")
                        st.rerun()
                    else:
                        st.error("A room with this code already exists.")
                else:
                    st.error("Please fill in Room Code, Room Name, Lead Instructor, and Primary Subject.")

    with t3:
        with st.popover("Join Room", icon=":material/login:", use_container_width=True):
            j_code = st.text_input("Room Code to Join", placeholder="Example: ECE-301")
            j_teacher = st.text_input("Your Name", placeholder="Example: Prof. Neha Kulkarni")
            j_sub = st.text_input("Your Subject", placeholder="Example: Embedded Systems")
            if st.button("Join as Instructor", type="primary", use_container_width=True):
                if j_code.strip() and j_teacher.strip() and j_sub.strip():
                    if join_lobby_teacher(j_code, j_teacher, j_sub):
                        st.session_state.active_lobby = j_code.strip().upper()
                        st.toast(f"{j_teacher} joined {j_code.strip().upper()}.")
                        st.rerun()
                    else:
                        st.error("Room code not found. Create the room first.")
                else:
                    st.error("Fill in Room Code, Your Name, and Your Subject.")

    room = get_active_room()
    if not room:
        st.markdown(
            '<div class="empty-box"><h4>No Course Rooms Created Yet</h4>'
            '<p>Click <strong>New Room</strong> in the top right to create your first cohort room, then invite subject faculty using <strong>Join Room</strong>.</p></div>',
            unsafe_allow_html=True,
        )
        return

    col_l, col_r = st.columns([1.0, 1.45], gap="medium")

    with col_l:
        with st.container(border=True):
            st.markdown(
                f'<div class="row-between" style="margin-bottom:4px;">'
                f'<span class="sec-title">{room["name"]}</span><span class="kpi-tag">{room["lobby_code"]}</span></div>'
                f'<p class="sec-sub">{room["cohort"]} &middot; Hosting Now: <strong>{room["active_host"]}</strong></p>',
                unsafe_allow_html=True,
            )
            st.markdown("**Faculty in Room**")
            teachers = get_lobby_teachers(room["lobby_code"])
            for t in teachers:
                if t["is_live"] or st.session_state.user_role != "Instructor / Mentor":
                    st.markdown(render_faculty_card_html(t["teacher_name"], t["subject"], t["is_live"]), unsafe_allow_html=True)
                else:
                    fc1, fc2 = st.columns([2.4, 1.0], vertical_alignment="center")
                    with fc1:
                        st.markdown(render_faculty_card_html(t["teacher_name"], t["subject"], False), unsafe_allow_html=True)
                    with fc2:
                        if st.button("Host Next", key=f"host_{t['id']}", use_container_width=True):
                            set_lobby_active_host(room["lobby_code"], t["teacher_name"], t["subject"])
                            st.toast(f"{t['teacher_name']} is now hosting {t['subject']}.")
                            st.rerun()

    with col_r:
        with st.container(border=True):
            ah1, ah2 = st.columns([1.8, 1.0], vertical_alignment="center")
            with ah1:
                st.markdown('<p class="sec-title">Shared Assignments</p>', unsafe_allow_html=True)
                st.markdown('<p class="sec-sub">Assignments and deadlines shared across all subjects in this room.</p>', unsafe_allow_html=True)
            with ah2:
                if st.session_state.user_role == "Instructor / Mentor":
                    with st.popover("New Assignment", icon=":material/assignment_add:", use_container_width=True):
                        a_sub = st.text_input("Subject", placeholder=f"Example: {room['active_subject']}")
                        a_teacher = st.text_input("Instructor", placeholder=f"Example: {room['active_host']}")
                        a_title = st.text_input("Assignment Title", placeholder="Example: Lab 4 — FIR Filter Design")
                        a_due = st.date_input("Due Date", value=datetime.now() + timedelta(days=7))
                        if st.button("Publish Assignment", type="primary", use_container_width=True):
                            if a_title.strip():
                                add_lobby_assignment(
                                    room["lobby_code"],
                                    a_sub.strip() or room["active_subject"],
                                    a_teacher.strip() or room["active_host"],
                                    a_title.strip(),
                                    str(a_due),
                                )
                                st.toast("Assignment published.")
                                st.rerun(scope="fragment")
                            else:
                                st.error("Enter an assignment title.")

            df_asg = get_lobby_assignments(room["lobby_code"])
            if df_asg.empty:
                st.markdown(
                    '<div class="empty-box"><h4>No Assignments Posted</h4>'
                    '<p>Click <strong>New Assignment</strong> above to share coursework with this room.</p></div>',
                    unsafe_allow_html=True,
                )
            else:
                df_disp = pd.DataFrame({
                    "Subject": df_asg["subject"],
                    "Assignment": df_asg["title"],
                    "Instructor": df_asg["teacher_name"],
                    "Due Date": df_asg["due_date"],
                    "Submitted": df_asg.apply(lambda r: f"{r['submitted_count']}/{r['total_students']}", axis=1),
                })
                st.dataframe(df_disp, use_container_width=True, hide_index=True)


# ==============================================================================
# TAB 3: ATTENDANCE & GRADES
# ==============================================================================
@st.fragment
def render_attendance_and_grades() -> None:
    min_req = float(st.session_state.min_attendance_pct)
    slabs = get_grade_slabs()
    students = load_all_students()

    if st.session_state.user_role == "Instructor / Mentor":
        act1, act2, act3 = st.columns([1.2, 1.2, 1.6], vertical_alignment="center")
        with act1:
            with st.popover("Record Subject Attendance", icon=":material/add_box:", use_container_width=True):
                if not students:
                    st.warning("Enroll at least one student in Roster & Reports first.")
                else:
                    s_opts = {f"{s['name']} ({s['student_id']})": s for s in students}
                    sel_stu = s_opts[st.selectbox("Student", list(s_opts.keys()), key="rec_stu")]
                    sc = st.text_input("Subject Code", placeholder="Example: EC501")
                    sn = st.text_input("Subject Name", placeholder="Example: Digital Signal Processing")
                    c_th1, c_th2 = st.columns(2)
                    with c_th1:
                        th_att = st.number_input("Theory Attended", min_value=0, max_value=200, value=0)
                    with c_th2:
                        th_tot = st.number_input("Theory Total", min_value=0, max_value=200, value=1)
                    c_pr1, c_pr2 = st.columns(2)
                    with c_pr1:
                        pr_att = st.number_input("Practical Attended", min_value=0, max_value=200, value=0)
                    with c_pr2:
                        pr_tot = st.number_input("Practical Total", min_value=0, max_value=200, value=0)
                    if st.button("Save Subject Record", type="primary", use_container_width=True):
                        if sc.strip() and sn.strip():
                            add_or_update_subject_record(
                                sel_stu["student_id"],
                                sel_stu["name"],
                                sc,
                                sn,
                                min(th_att, th_tot),
                                th_tot,
                                min(pr_att, pr_tot),
                                pr_tot,
                            )
                            dispatch_below_threshold_warnings(min_threshold=min_req)
                            st.toast(f"Saved {sn} for {sel_stu['name']}.")
                            st.rerun(scope="fragment")
                        else:
                            st.error("Enter both Subject Code and Subject Name.")

        with act2:
            with st.popover("Log Daily Class Entry", icon=":material/today:", use_container_width=True):
                if not students:
                    st.warning("Enroll at least one student in Roster & Reports first.")
                else:
                    s_opts = {f"{s['name']} ({s['student_id']})": s for s in students}
                    sel_d = s_opts[st.selectbox("Student", list(s_opts.keys()), key="daily_stu")]
                    d_subj = st.text_input("Subject", placeholder="Example: Embedded Systems")
                    d_type = st.radio("Session Type", ["Theory", "Practical"], horizontal=True)
                    d_teacher = st.text_input("Instructor Name", placeholder="Example: Prof. Neha Kulkarni")
                    d_slot = st.text_input("Time Slot", placeholder="Example: 10:30 - 11:15")
                    d_status = st.selectbox("Status", ["Present", "Absent", "Needs Review"])
                    if st.button("Add to Daily Summary", type="primary", use_container_width=True):
                        if d_subj.strip() and d_teacher.strip() and d_slot.strip():
                            add_daily_log(sel_d["student_id"], sel_d["name"], d_subj, d_type, d_teacher, d_slot, d_status)
                            st.toast("Added to today's summary.")
                            st.rerun(scope="fragment")
                        else:
                            st.error("Fill in Subject, Instructor Name, and Time Slot.")
        with act3:
            st.caption(f"Minimum attendance threshold: **{int(min_req)}%** (customizable in Settings).")

    cum_df = compute_student_cumulative_summary(min_threshold=min_req, slabs=slabs)
    if cum_df.empty:
        st.markdown(
            '<div class="empty-box"><h4>No Subject Attendance Records Yet</h4>'
            '<p>Enroll students in <strong>Roster &amp; Reports</strong>, then click <strong>Record Subject Attendance</strong> above to calculate Theory &amp; Practical grades.</p></div>',
            unsafe_allow_html=True,
        )
    else:
        if st.session_state.user_role == "Instructor / Mentor":
            opts = {f"{r['student_name']} ({r['student_id']}) — {r['cumulative_pct']}%": r["student_id"] for _, r in cum_df.iterrows()}
            chosen = st.selectbox("Inspect Student", list(opts.keys()))
            target_sid = opts[chosen]
        else:
            target_sid = st.session_state.active_student_id
            if target_sid not in cum_df["student_id"].values:
                st.info("No subject records recorded for the selected student yet.")
                target_sid = None

        if target_sid:
            row_s = cum_df[cum_df["student_id"] == target_sid].iloc[0]
            below_min = row_s["cumulative_pct"] < min_req
            if below_min:
                st.markdown(
                    f'<div class="flag-banner">{SVG_ICONS["flag"]}<span>'
                    f'Below {int(min_req)}% Attendance Flag — {row_s["student_name"]} is at {row_s["cumulative_pct"]}%. '
                    f'Warnings logged for Student &amp; Guardian portals ({row_s["recovery"]} needed).'
                    f"</span></div>",
                    unsafe_allow_html=True,
                )

            m1, m2, m3, m4 = st.columns(4)
            m1.markdown(render_kpi_html("Cumulative Attendance", row_s["cumulative_pct"], f"Target: {int(min_req)}%", flagged=below_min, tag="Flagged" if below_min else "Eligible"), unsafe_allow_html=True)
            m2.markdown(render_kpi_html("Theory Lectures", row_s["theory_pct"], "All subjects combined", flagged=(row_s["theory_pct"] < min_req), tag="Flagged" if row_s["theory_pct"] < min_req else "On Track"), unsafe_allow_html=True)
            m3.markdown(render_kpi_html("Practical Labs", row_s["practical_pct"], "All labs combined", flagged=(row_s["practical_pct"] < min_req), tag="Flagged" if row_s["practical_pct"] < min_req else "On Track"), unsafe_allow_html=True)
            with m4:
                card_cls = "kpi-card kpi-card-flagged" if below_min else "kpi-card"
                tag_cls = "kpi-tag kpi-tag-flag" if below_min else "kpi-tag kpi-tag-ok"
                st.markdown(
                    f'<div class="{card_cls}"><div class="kpi-top"><span class="kpi-label">Internal Grade</span><span class="{tag_cls}">{row_s["risk_tier"]}</span></div>'
                    f'<div style="font-size:1.35rem;font-weight:800;color:{"var(--flag)" if below_min else "var(--ink)"};">{row_s["internal_grade"]}</div>'
                    f'<div class="kpi-sub">{row_s["recovery"]}</div></div>',
                    unsafe_allow_html=True,
                )
            st.write("")

            sub_df = get_student_subject_records(target_sid)
            calc_rows = []
            for _, sr in sub_df.iterrows():
                th_p = round((sr["theory_attended"] / sr["theory_total"]) * 100, 1) if sr["theory_total"] else 0.0
                pr_p = round((sr["practical_attended"] / sr["practical_total"]) * 100, 1) if sr["practical_total"] else 0.0
                c_att = int(sr["theory_attended"] + sr["practical_attended"])
                c_tot = int(sr["theory_total"] + sr["practical_total"])
                c_p = round((c_att / c_tot) * 100, 1) if c_tot else 0.0
                grd, _ = compute_internal_grade(c_p, min_threshold=min_req, slabs=slabs)
                rmode, rcnt = compute_recovery_classes(c_att, c_tot, target_pct=min_req)
                calc_rows.append({
                    "Code": sr["subject_code"],
                    "Subject": sr["subject_name"],
                    "Theory": f"{sr['theory_attended']}/{sr['theory_total']}",
                    "Theory %": f"{th_p}%",
                    "Practical": f"{sr['practical_attended']}/{sr['practical_total']}",
                    "Practical %": f"{pr_p}%",
                    "Overall %": f"{c_p}%",
                    "Grade": grd,
                    f"{int(min_req)}% Goal": f"Attend +{rcnt}" if rmode == "Need" else f"{rcnt} buffer",
                })

            with st.container(border=True):
                st.markdown(f'<p class="sec-title">Subject-Wise Breakdown — {row_s["student_name"]}</p>', unsafe_allow_html=True)
                st.dataframe(pd.DataFrame(calc_rows), use_container_width=True, hide_index=True)

    d1, d2 = st.columns([1.2, 1], gap="medium")
    with d1:
        with st.container(border=True):
            dh1, dh2 = st.columns([1.8, 1], vertical_alignment="center")
            with dh1:
                st.markdown('<p class="sec-title">Daily Attendance Summary</p>', unsafe_allow_html=True)
                st.markdown(f'<p class="sec-sub">Session log for {datetime.now().strftime("%B %d, %Y")}.</p>', unsafe_allow_html=True)
            df_daily = get_daily_logs(None if st.session_state.user_role == "Instructor / Mentor" else st.session_state.active_student_id)
            with dh2:
                if not df_daily.empty:
                    st.download_button(
                        "Export CSV",
                        data=df_daily.to_csv(index=False).encode("utf-8"),
                        file_name=f"AttendAI_Daily_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        icon=":material/download:",
                        use_container_width=True,
                    )
            if df_daily.empty:
                st.caption("No daily attendance entries logged today.")
            else:
                st.dataframe(
                    df_daily[["time_slot", "student_name", "subject_name", "session_type", "status", "proctor_strikes"]].rename(
                        columns={"time_slot": "Time", "student_name": "Student", "subject_name": "Subject", "session_type": "Type", "status": "Status", "proctor_strikes": "Flags"}
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

    with d2:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Attendance Correction Requests</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-sub">Students can flag missed or incorrect attendance directly to their Mentor or Subject Instructor.</p>', unsafe_allow_html=True)

            with st.expander("Flag a Missed or Incorrect Record", expanded=False):
                if not students:
                    st.caption("Enroll students first to submit a flag.")
                else:
                    s_map = {f"{s['name']} ({s['student_id']})": s for s in students}
                    f_stu = s_map[st.selectbox("Student", list(s_map.keys()), key="flag_stu")]
                    f_subj = st.text_input("Subject Name", placeholder="Example: Embedded Systems")
                    f_type = st.radio("Type", ["Theory", "Practical"], horizontal=True, key="flag_type")
                    f_route = st.radio("Send To", ["Assigned Mentor", "Subject Instructor"], horizontal=True)
                    f_recip = st.text_input("Recipient Name", placeholder="Example: Dr. Vikram Deshmukh")
                    f_reason = st.text_area("Reason for Correction", placeholder="Example: Present in Lab Bay 2 during equipment setup; missed snapshot.")
                    if st.button("Submit Correction Flag", icon=":material/flag:", type="primary", use_container_width=True):
                        if f_subj.strip() and f_recip.strip() and f_reason.strip():
                            create_dispute_ticket(None, f_stu["student_id"], f_stu["name"], f_subj, f_type, f_route, f_recip, f_reason)
                            st.toast(f"Flag sent to {f_recip}.")
                            st.rerun(scope="fragment")
                        else:
                            st.error("Fill in Subject Name, Recipient Name, and Reason.")

            t_df = get_dispute_tickets(None if st.session_state.user_role == "Instructor / Mentor" else st.session_state.active_student_id)
            if t_df.empty:
                st.caption("No open correction requests.")
            else:
                for _, tk in t_df.head(5).iterrows():
                    is_pend = tk["status"] == "Pending Review"
                    st.markdown(
                        f'<div class="ink-card {"ink-card-flag" if is_pend else ""}">'
                        f'<div class="row-between"><span class="card-title">{tk["student_name"]} &middot; {tk["subject_name"]} ({tk["session_type"]})</span>'
                        f'<span class="kpi-tag {"kpi-tag-flag" if is_pend else ""}">{tk["status"]}</span></div>'
                        f'<div class="card-meta">To {tk["routed_to"]} ({tk["recipient_name"]}): {tk["reason"]}</div></div>',
                        unsafe_allow_html=True,
                    )
                    if is_pend and st.session_state.user_role == "Instructor / Mentor":
                        b1, b2 = st.columns(2)
                        with b1:
                            if st.button("Approve & Recalculate", key=f"appr_{tk['id']}", type="primary", use_container_width=True):
                                resolve_dispute_ticket(int(tk["id"]), True, "Verified by faculty; attendance updated.")
                                st.rerun(scope="fragment")
                        with b2:
                            if st.button("Decline", key=f"rej_{tk['id']}", use_container_width=True):
                                resolve_dispute_ticket(int(tk["id"]), False, "Attendance could not be verified.")
                                st.rerun(scope="fragment")


# ==============================================================================
# TAB 4: GUARDIAN & STUDENT SAFETY
# ==============================================================================
@st.fragment
def render_guardian_and_safety() -> None:
    min_req = float(st.session_state.min_attendance_pct)
    students = load_all_students()
    p_l, p_r = st.columns([1.25, 1], gap="medium")

    with p_l:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Guardian Alerts &amp; Attendance Warnings</p>', unsafe_allow_html=True)
            st.markdown(f'<p class="sec-sub">In-portal alerts for students below {int(min_req)}% attendance (real Email/SMS delivery wired in Phase 4).</p>', unsafe_allow_html=True)

            if st.button(f"Run Below-{int(min_req)}% Warning Audit", icon=":material/notifications_active:", use_container_width=True):
                cnt = dispatch_below_threshold_warnings(min_threshold=min_req)
                st.toast(f"Logged {cnt} portal warning(s)." if cnt else "All alerts are up to date.")
                st.rerun(scope="fragment")

            notifs = get_notifications(recipient_role="Parent" if st.session_state.user_role == "Parent / Guardian" else None)
            if notifs.empty:
                st.markdown(
                    '<div class="empty-box"><h4>No Guardian Alerts Yet</h4>'
                    '<p>Warnings for low attendance and safety check-ins will appear here automatically.</p></div>',
                    unsafe_allow_html=True,
                )
            else:
                for _, nf in notifs.head(6).iterrows():
                    is_crit = nf["severity"] == "Critical"
                    st.markdown(
                        f'<div class="ink-card {"ink-card-flag" if is_crit else ""}">'
                        f'<div class="row-between"><span class="card-title">{nf["title"]}</span><span class="card-meta">{nf["created_at"]}</span></div>'
                        f'<div style="font-size:0.82rem;margin-top:4px;">{nf["message"]}</div>'
                        f'<div class="card-meta">To: {nf["recipient_role"]} &middot; Channel: {nf["channels"]} &middot; <strong>{"Read" if nf["acknowledged"] else "Unread"}</strong></div></div>',
                        unsafe_allow_html=True,
                    )
                    if not nf["acknowledged"]:
                        if st.button("Mark as Read", key=f"ack_{nf['id']}", use_container_width=True):
                            acknowledge_notification(int(nf["id"]))
                            st.rerun(scope="fragment")

    with p_r:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Student Safety &amp; Mentor Communication</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-sub">Discreet safety check-ins during class hours and direct Guardian-to-Mentor notes.</p>', unsafe_allow_html=True)

            st.markdown("**Private Safety Check-In**")
            if students:
                s_map = {f"{s['name']} ({s['student_id']})": s for s in students}
                sel_safe = s_map[st.selectbox("Student", list(s_map.keys()), key="safe_stu")]
            else:
                sel_safe = {"student_id": "UNASSIGNED", "name": "Student"}

            sos_msg = st.text_input("Safety Check-In Note", placeholder="Example: Feeling unwell in Lab Block B; requesting mentor check-in.")
            if st.button("Send Private Safety Alert", icon=":material/health_and_safety:", type="primary", use_container_width=True):
                body = sos_msg.strip() or f"{sel_safe['name']} requested a private safety check-in."
                for r_role in ("Instructor", "Parent"):
                    dispatch_notification(r_role, sel_safe["student_id"], sel_safe["name"], "Student Safety", "Critical", f"Safety Check-In — {sel_safe['name']}", body, "Portal")
                st.success("Private safety alert logged for Mentor and Guardian portals.")
                st.rerun(scope="fragment")

            st.divider()
            st.markdown("**Guardian Note to Mentor**")
            with st.form("guardian_msg_form", clear_on_submit=True, border=False):
                g_note = st.text_input("Message", placeholder="Example: My ward has a medical appointment during Period 3 today.")
                if st.form_submit_button("Send to Mentor", icon=":material/mail:", use_container_width=True) and g_note.strip():
                    dispatch_notification("Instructor", sel_safe["student_id"], sel_safe["name"], "Guardian Note", "Info", f"Note from Guardian ({sel_safe['name']})", g_note.strip(), "Portal")
                    st.toast("Message sent to Mentor.")
                    st.rerun(scope="fragment")


# ==============================================================================
# TAB 5: ROSTER & REPORTS
# ==============================================================================
@st.fragment
def render_roster_and_reports() -> None:
    st1, st2 = st.tabs([":material/group: Student Roster", ":material/description: Automated PDF Archive"])

    with st1:
        render_phase1_roster_enrollment()

    with st2:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Automated Session PDF Archive</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-sub">Reports reflect real snapshot observation counts and measured head-pose ratios; Demo Mode reports are tagged SIMULATED.</p>', unsafe_allow_html=True)
            rep_df = get_session_reports()
            if rep_df.empty:
                st.markdown(
                    '<div class="empty-box"><h4>No Archived Reports Yet</h4>'
                    '<p>Click <strong>End &amp; Auto-PDF</strong> in the Live Session tab to generate your first session dossier.</p></div>',
                    unsafe_allow_html=True,
                )
            else:
                for _, rr in rep_df.head(8).iterrows():
                    demo_tag = " **[SIMULATED]**" if int(rr.get("is_demo", 0)) == 1 else ""
                    rc1, rc2 = st.columns([3, 1], vertical_alignment="center")
                    with rc1:
                        st.markdown(
                            f"**{rr['subject_name']}**{demo_tag} ({rr['lobby_code']}) &middot; "
                            f"Present: **{rr['present_count']}/{rr['total_count']}** &middot; "
                            f"Focus Events: **{rr['proctor_violations']}** &middot; _{rr['generated_at']}_"
                        )
                    with rc2:
                        st.download_button(
                            "Download PDF",
                            data=base64.b64decode(rr["pdf_b64"]),
                            file_name=f"AttendAI_Report_{rr['session_id']}.pdf",
                            mime="application/pdf",
                            icon=":material/picture_as_pdf:",
                            key=f"dl_{rr['id']}",
                            use_container_width=True,
                        )


# ==============================================================================
# TAB 6: SETTINGS
# ==============================================================================
@st.fragment
def render_settings_tab() -> None:
    s_l, s_r = st.columns(2, gap="medium")

    with s_l:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Face Matching &amp; Attendance Rules (Phase 1)</p>', unsafe_allow_html=True)
            st.session_state.cosine_threshold = st.slider("Cosine Match Threshold", 0.25, 0.80, float(st.session_state.cosine_threshold), 0.01)
            st.session_state.ambiguity_margin = st.slider("Top-2 Ambiguity Margin", 0.02, 0.25, float(st.session_state.ambiguity_margin), 0.01)
            st.session_state.min_det_score = st.slider("Minimum Face Detection Score", 0.30, 0.95, float(st.session_state.min_det_score), 0.05)
            st.session_state.min_face_size_px = st.slider("Minimum Face Size (px)", 20, 120, int(st.session_state.min_face_size_px), 5)
            st.session_state.min_observations = st.number_input("Min Snapshots Required for PRESENT (N)", 1, 10, int(st.session_state.min_observations))
            st.session_state.min_observation_pct = st.slider("OR Min Snapshot Percentage (%)", 10, 100, int(st.session_state.min_observation_pct), 5)
            st.session_state.scheduled_snapshot_count = st.slider("Scheduled Snapshots per Lecture", 2, 10, int(st.session_state.scheduled_snapshot_count))

        with st.container(border=True):
            st.markdown('<p class="sec-title">Head-Pose &amp; Focus Monitor Rules (Phase 2)</p>', unsafe_allow_html=True)
            st.session_state.max_yaw_deg = st.slider("Max Front-Facing Yaw (°)", 10.0, 45.0, float(st.session_state.max_yaw_deg), 1.0)
            st.session_state.max_pitch_deg = st.slider("Max Front-Facing Pitch (°)", 10.0, 40.0, float(st.session_state.max_pitch_deg), 1.0)
            st.session_state.focus_review_threshold = st.slider(
                "Window Exits Before Queuing NEEDS REVIEW (Never Auto-Absent)",
                1,
                10,
                int(st.session_state.focus_review_threshold),
            )

        with st.container(border=True):
            st.markdown('<p class="sec-title">Institution &amp; Color Customization</p>', unsafe_allow_html=True)
            org_in = st.text_input("Institution / Department Name", value=st.session_state.org_name, placeholder="Example: Department of ECE")
            if st.button("Save Institution Name", use_container_width=True):
                if org_in.strip():
                    st.session_state.org_name = org_in.strip()
                    st.rerun()

            preset_name = st.selectbox("Quick Flag Color Preset", list(ACCENT_PRESETS.keys()))
            c_btn1, c_btn2 = st.columns(2)
            with c_btn1:
                if st.button("Apply Preset Color", use_container_width=True):
                    st.session_state.accent_color = ACCENT_PRESETS[preset_name]
                    st.rerun()
            with c_btn2:
                custom_hex = st.color_picker("Or Choose Custom Color", value=st.session_state.accent_color)
                if custom_hex != st.session_state.accent_color:
                    st.session_state.accent_color = custom_hex
                    st.rerun()

    with s_r:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Lecture Duration &amp; Attendance Grade Slabs</p>', unsafe_allow_html=True)
            dur_choice = st.selectbox(
                "Default Class Duration",
                list(DURATION_OPTIONS.keys()),
                index=list(DURATION_OPTIONS.keys()).index(st.session_state.class_duration_label),
            )
            if dur_choice != st.session_state.class_duration_label:
                st.session_state.class_duration_label = dur_choice
                st.session_state.session_remaining_sec = DURATION_OPTIONS[dur_choice] * 60
                st.session_state.snapshot_schedule = []
                st.rerun()

            st.session_state.min_attendance_pct = st.slider("Minimum Mandatory Attendance Warning Threshold (%)", 50, 95, int(st.session_state.min_attendance_pct), 1)
            g1, g2, g3 = st.columns(3)
            with g1:
                st.session_state.grade_a_plus = st.number_input("A+ Cutoff (%)", 75, 100, int(st.session_state.grade_a_plus))
            with g2:
                st.session_state.grade_a = st.number_input("A Cutoff (%)", 65, 99, int(st.session_state.grade_a))
            with g3:
                st.session_state.grade_max_marks = st.number_input("Max Internal Marks", 1, 20, int(st.session_state.grade_max_marks))

        with st.container(border=True):
            st.markdown('<p class="sec-title">Workspace Data Reset</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-sub">Clear saved database records to begin with an empty workspace.</p>', unsafe_allow_html=True)
            if st.button("Clear All Workspace Data", icon=":material/delete_forever:", use_container_width=True):
                clear_all_data()
                st.session_state.tracker = None
                st.session_state.engagement_history = []
                st.session_state.suggestion_feed = []
                st.session_state.active_lobby = None
                st.session_state.active_student_id = None
                st.session_state.last_generated_pdf = None
                st.session_state.student_joined_room = ""
                st.session_state.student_joined_id = ""
                st.toast("All records cleared.")
                st.rerun()


# --- Main Navigation Tabs ---
tabs = st.tabs([
    ":material/sensors: Live Session",
    ":material/meeting_room: Course Rooms",
    ":material/calculate: Attendance & Grades",
    ":material/family_restroom: Guardian & Safety",
    ":material/folder_shared: Roster & Reports",
    ":material/tune: Settings",
])

with tabs[0]:
    if st.session_state.stream_playing:
        render_live_streaming()
    else:
        render_live_paused()

with tabs[1]:
    render_course_rooms()

with tabs[2]:
    render_attendance_and_grades()

with tabs[3]:
    render_guardian_and_safety()

with tabs[4]:
    render_roster_and_reports()

with tabs[5]:
    render_settings_tab()


    

import base64
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import streamlit as st

try:
    import bcrypt as _bcrypt
except ImportError:  # pragma: no cover
    _bcrypt = None

try:
    from cryptography.fernet import Fernet as _Fernet, InvalidToken as _InvalidToken
except ImportError:  # pragma: no cover
    _Fernet = None
    _InvalidToken = Exception

DEFAULT_ORG_ID = "default_org"
CURRENT_POLICY_VERSION = "1.0-biometric-v1"
SANDBOX_DIR = Path("data/sandboxes")


def get_secret_or_env(key: str, default: str = "") -> str:
    try:
        if key in st.secrets and st.secrets[key]:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.environ.get(key, default)


def resolve_database_url() -> str:
    """Returns DATABASE_URL from st.secrets/env (Postgres/Supabase) or local SQLite fallback."""
    url = get_secret_or_env("DATABASE_URL", "").strip()
    if url:
        return url
    db_path = Path("data/classroom.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path.resolve().as_posix()}"


def _sandbox_db_path(session_token: str) -> Path:
    safe = "".join(ch for ch in session_token if ch.isalnum())[:24] or "guest"
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    return SANDBOX_DIR / f"sandbox_{safe}.db"


def get_scoped_sqlite_connection(
    default_db_path: Path,
    *,
    authenticated: bool = False,
    session_token: str = "guest",
) -> sqlite3.Connection:
    """
    Returns an isolated per-session sandbox SQLite DB for unauthenticated visitors,
    or the shared DB for authenticated users.
    """
    if not authenticated:
        target = _sandbox_db_path(session_token)
        is_new = not target.exists()
        conn = sqlite3.connect(target, check_same_thread=False)
        if is_new:
            _init_sandbox_schema(conn)
        return conn

    default_db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(default_db_path, check_same_thread=False)


def _init_sandbox_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY, name TEXT NOT NULL, embedding TEXT,
            biometric_enrolled INTEGER NOT NULL DEFAULT 0, org_id TEXT NOT NULL DEFAULT 'sandbox',
            consent_given INTEGER NOT NULL DEFAULT 0, consent_version TEXT DEFAULT '',
            consent_at TEXT DEFAULT '', created_at TEXT NOT NULL
        )"""
    )
    cur.execute(
        """INSERT OR IGNORE INTO students
           (student_id, name, embedding, biometric_enrolled, org_id, created_at)
           VALUES ('DEMO-S1', 'Sandbox Student One (Fake)', NULL, 0, 'sandbox', ?)""",
        (datetime.now().strftime("%Y-%m-%d %H:%M"),),
    )
    conn.commit()


# --- Fernet Embedding Encryption at Rest ---
def _get_fernet() -> Any | None:
    if _Fernet is None:
        return None
    raw_key = get_secret_or_env("EMBEDDING_ENCRYPTION_KEY", "").strip()
    if not raw_key:
        return None
    try:
        key_bytes = raw_key.encode("utf-8") if len(raw_key) == 44 else base64.urlsafe_b64encode(hashlib.sha256(raw_key.encode("utf-8")).digest())
        return _Fernet(key_bytes)
    except Exception:
        return None


def encrypt_embedding_payload(emb: np.ndarray) -> str:
    arr = np.asarray(emb, dtype=np.float32).reshape(-1)
    raw_json = json.dumps(arr.tolist())
    fernet = _get_fernet()
    if fernet is None:
        return raw_json
    token = fernet.encrypt(raw_json.encode("utf-8")).decode("utf-8")
    return f"FERNET::{token}"


def decrypt_embedding_payload(payload: str | None) -> np.ndarray | None:
    if not payload or not str(payload).strip():
        return None
    text = str(payload).strip()
    if text.startswith("FERNET::"):
        fernet = _get_fernet()
        if fernet is None:
            raise RuntimeError("Encrypted embedding found, but EMBEDDING_ENCRYPTION_KEY is not configured.")
        try:
            raw_json = fernet.decrypt(text[len("FERNET::") :].encode("utf-8")).decode("utf-8")
        except _InvalidToken as exc:
            raise ValueError("Failed to decrypt student embedding: invalid key or corrupted ciphertext.") from exc
    else:
        raw_json = text
    return np.array(json.loads(raw_json), dtype=np.float32)


# --- Passwords, Users, Roles & Row-Level Query Enforcement ---
def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password cannot be empty.")
    if _bcrypt is not None:
        return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return f"pbkdf2${salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False
    if password_hash.startswith("pbkdf2$"):
        _, salt, expected = password_hash.split("$", 2)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
        return actual == expected
    if _bcrypt is not None:
        try:
            return _bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except ValueError:
            return False
    return False


def init_auth_privacy_tables(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            org_id TEXT NOT NULL DEFAULT 'default_org',
            student_id TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS guardian_student_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guardian_username TEXT NOT NULL,
            student_id TEXT NOT NULL,
            org_id TEXT NOT NULL DEFAULT 'default_org',
            UNIQUE(guardian_username, student_id, org_id)
        )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL DEFAULT 'default_org',
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            target_table TEXT NOT NULL,
            target_id TEXT NOT NULL,
            before_json TEXT,
            after_json TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    for tbl in ("students", "attendance", "lobbies", "notifications", "review_queue"):
        cur.execute(f"PRAGMA table_info({tbl})")
        cols = {r[1] for r in cur.fetchall()}
        if "org_id" not in cols:
            cur.execute(f"ALTER TABLE {tbl} ADD COLUMN org_id TEXT NOT NULL DEFAULT 'default_org'")
    cur.execute("PRAGMA table_info(students)")
    scols = {r[1] for r in cur.fetchall()}
    for col, defn in [
        ("consent_given", "INTEGER NOT NULL DEFAULT 0"),
        ("consent_version", "TEXT DEFAULT ''"),
        ("consent_at", "TEXT DEFAULT ''"),
    ]:
        if col not in scols:
            cur.execute(f"ALTER TABLE students ADD COLUMN {col} {defn}")
    conn.commit()


def create_user(
    conn: sqlite3.Connection,
    username: str,
    password: str,
    role: str,
    *,
    org_id: str = DEFAULT_ORG_ID,
    student_id: str | None = None,
) -> bool:
    role_clean = role.strip().lower()
    if role_clean not in {"admin", "instructor", "student", "guardian"}:
        raise ValueError("Invalid role.")
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO users (username, password_hash, role, org_id, student_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (username.strip(), hash_password(password), role_clean, org_id, student_id, datetime.now().strftime("%Y-%m-%d %H:%M")),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def authenticate_user(conn: sqlite3.Connection, username: str, password: str) -> dict[str, Any] | None:
    cur = conn.cursor()
    cur.execute("SELECT id, username, password_hash, role, org_id, student_id FROM users WHERE username = ?", (username.strip(),))
    row = cur.fetchone()
    if not row or not verify_password(password, row[2]):
        return None
    return {"id": row[0], "username": row[1], "role": row[3], "org_id": row[4], "student_id": row[5]}


def link_guardian_to_student(conn: sqlite3.Connection, guardian_username: str, student_id: str, org_id: str = DEFAULT_ORG_ID) -> None:
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO guardian_student_links (guardian_username, student_id, org_id) VALUES (?, ?, ?)",
        (guardian_username.strip(), student_id.strip(), org_id),
    )
    conn.commit()


def list_accessible_students(conn: sqlite3.Connection, user: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Enforces role and org_id permissions in the database query layer."""
    if not user:
        return []
    role = user.get("role", "")
    org_id = user.get("org_id", DEFAULT_ORG_ID)
    cur = conn.cursor()
    if role in {"admin", "instructor"}:
        cur.execute(
            "SELECT student_id, name, biometric_enrolled, consent_given, consent_version, created_at FROM students WHERE org_id = ? ORDER BY student_id",
            (org_id,),
        )
        rows = cur.fetchall()
    elif role == "student" and user.get("student_id"):
        cur.execute(
            "SELECT student_id, name, biometric_enrolled, consent_given, consent_version, created_at FROM students WHERE org_id = ? AND student_id = ?",
            (org_id, user["student_id"]),
        )
        rows = cur.fetchall()
    elif role == "guardian":
        cur.execute(
            """SELECT s.student_id, s.name, s.biometric_enrolled, s.consent_given, s.consent_version, s.created_at
               FROM students s
               INNER JOIN guardian_student_links g
                 ON s.student_id = g.student_id AND s.org_id = g.org_id
               WHERE g.guardian_username = ? AND s.org_id = ?
               ORDER BY s.student_id""",
            (user["username"], org_id),
        )
        rows = cur.fetchall()
    else:
        rows = []
    return [
        {
            "student_id": r[0],
            "name": r[1],
            "biometric_enrolled": bool(r[2]),
            "consent_given": bool(r[3]),
            "consent_version": r[4] or "",
            "created_at": r[5],
        }
        for r in rows
    ]


# --- Consent, Audit Log, Delete-My-Data & Retention Purge ---
def record_biometric_consent(
    conn: sqlite3.Connection,
    student_id: str,
    *,
    consent_given: bool,
    policy_version: str = CURRENT_POLICY_VERSION,
    org_id: str = DEFAULT_ORG_ID,
    actor: str = "system",
) -> None:
    if not consent_given:
        raise ValueError("Explicit consent is required before biometric enrollment.")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.cursor()
    cur.execute(
        "SELECT consent_given, consent_version FROM students WHERE student_id = ? AND org_id = ?",
        (student_id, org_id),
    )
    before = cur.fetchone()
    cur.execute(
        "UPDATE students SET consent_given = 1, consent_version = ?, consent_at = ? WHERE student_id = ? AND org_id = ?",
        (policy_version, now_str, student_id, org_id),
    )
    log_audit_event(
        conn,
        org_id=org_id,
        actor=actor,
        action="RECORD_CONSENT",
        target_table="students",
        target_id=student_id,
        before_data={"consent_given": bool(before[0]), "consent_version": before[1]} if before else None,
        after_data={"consent_given": True, "consent_version": policy_version, "consent_at": now_str},
    )
    conn.commit()


def log_audit_event(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    actor: str,
    action: str,
    target_table: str,
    target_id: str,
    before_data: dict[str, Any] | None,
    after_data: dict[str, Any] | None,
) -> None:
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO audit_log
           (org_id, actor, action, target_table, target_id, before_json, after_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            org_id,
            actor,
            action,
            target_table,
            target_id,
            json.dumps(before_data) if before_data is not None else None,
            json.dumps(after_data) if after_data is not None else None,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()


def delete_student_my_data(
    conn: sqlite3.Connection,
    student_id: str,
    *,
    org_id: str = DEFAULT_ORG_ID,
    actor: str = "self_service",
) -> None:
    cur = conn.cursor()
    cur.execute("SELECT student_id, name, biometric_enrolled FROM students WHERE student_id = ? AND org_id = ?", (student_id, org_id))
    row = cur.fetchone()
    for tbl in ("student_embeddings", "attendance", "subject_records", "daily_logs", "dispute_tickets", "notifications", "guardian_student_links"):
        cur.execute(f"DELETE FROM {tbl} WHERE student_id = ?", (student_id,))
    cur.execute("DELETE FROM students WHERE student_id = ? AND org_id = ?", (student_id, org_id))
    log_audit_event(
        conn,
        org_id=org_id,
        actor=actor,
        action="DELETE_MY_DATA",
        target_table="students",
        target_id=student_id,
        before_data={"student_id": row[0], "name": row[1]} if row else None,
        after_data=None,
    )
    conn.commit()


def purge_expired_records(conn: sqlite3.Connection, retention_days: int = 90, org_id: str = DEFAULT_ORG_ID) -> int:
    cutoff = (datetime.now() - timedelta(days=max(1, int(retention_days)))).strftime("%Y-%m-%d")
    cur = conn.cursor()
    cur.execute("DELETE FROM daily_logs WHERE log_date < ?", (cutoff,))
    deleted = cur.rowcount
    log_audit_event(
        conn,
        org_id=org_id,
        actor="retention_job",
        action="PURGE_EXPIRED",
        target_table="daily_logs",
        target_id=f"before_{cutoff}",
        before_data={"retention_days": retention_days, "cutoff": cutoff},
        after_data={"deleted_rows": deleted},
    )
    conn.commit()
    return max(0, int(deleted))

    # ==============================================================================
# PHASE 4: REAL NOTIFICATIONS (EMAIL/SMS) & CSV / EXCEL / PDF EXPORTS
# ==============================================================================
from modules.database import get_session_data
from modules.notifications_reports import (
    build_rich_pdf_bytes,
    export_attendance_csv_bytes,
    export_attendance_excel_bytes,
    send_real_alert,
)

with st.expander("Real Alerts & Attendance Exports (Phase 4)", expanded=False):
    ea1, ea2 = st.text_input("Student / Guardian Email", key="p4_email"), st.text_input("Phone (E.164 for Twilio SMS)", key="p4_phone")
    e_msg = st.text_input("Alert Message", value="Attendance threshold notice from AttendAI.", key="p4_msg")
    if st.button("Send Alert & Log Status", key="p4_send_btn", type="primary"):
        res = send_real_alert(
            recipient_email=ea1,
            recipient_phone=ea2,
            subject=f"AttendAI Alert — {st.session_state.session_id}",
            body=e_msg,
            is_demo=bool(st.session_state.get("demo_mode", False)),
        )
        dispatch_notification(
            "Parent",
            st.session_state.active_student_id or "GENERAL",
            "Student",
            "Attendance Alert",
            "Warning",
            f"Alert ({res['delivery_status']})",
            e_msg,
            channels=res["channels_label"],
        )
        st.info(f"Channels: **{res['channels_label']}** · Status: **{res['delivery_status']}**")

    att_df, eng_df, _ = get_session_data("ALL")
    if not att_df.empty:
        xc1, xc2, xc3 = st.columns(3)
        with xc1:
            st.download_button("Download Attendance CSV", data=export_attendance_csv_bytes(att_df), file_name="attendai_attendance.csv", mime="text/csv", key="p4_csv_btn")
        with xc2:
            st.download_button("Download Attendance Excel", data=export_attendance_excel_bytes(att_df, eng_df), file_name="attendai_attendance.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="p4_xlsx_btn")
        with xc3:
            pdf_b = build_rich_pdf_bytes(
                title="AttendAI Attendance Report",
                subtitle=f"Session {st.session_state.session_id}",
                df_att=att_df,
                is_demo=bool(st.session_state.get("demo_mode", False)),
            )
            st.download_button("Download Tabular PDF", data=pdf_b, file_name="attendai_tabular_report.pdf", mime="application/pdf", key="p4_pdf_btn")

            # ==============================================================================
# PHASE 5: ANTI-SPOOFING CHECK & HONEST MODEL EVALUATION VIEWER
# ==============================================================================
from modules.liveness_eval import check_liveness, run_synthetic_smoke_evaluation

with st.expander("Anti-Spoofing & Model Evaluation (Phase 5)", expanded=False):
    st.caption("Evaluation status on real classroom dataset: **Not yet run**. Synthetic smoke test only below.")
    ev1, ev2 = st.columns(2)
    with ev1:
        ch_req = st.selectbox("Enrollment / Check-In Challenge", ["NONE", "LEFT", "RIGHT", "CENTER"], key="p5_ch_req")
        ch_obs = st.selectbox("Observed Head Turn", ["NONE", "LEFT", "RIGHT", "CENTER"], key="p5_ch_obs")
        if st.button("Test Liveness Gate", key="p5_live_btn"):
            lv = check_liveness(None, challenge_head_turn=ch_req, observed_head_turn=ch_obs)
            st.write(f"**Passed:** `{lv.passed}` · **Method:** `{lv.method}` — {lv.reason}")
    with ev2:
        if st.button("Run Synthetic Smoke Check", key="p5_eval_btn"):
            st.session_state.p5_smoke_res = run_synthetic_smoke_evaluation()
        if "p5_smoke_res" in st.session_state:
            st.json(st.session_state.p5_smoke_res)