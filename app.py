import base64
import cv2
import random
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timedelta

from modules.database import (
    init_db,
    clear_all_data,
    load_all_students,
    save_student,
    delete_student,
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
    add_or_update_subject_record,
    get_student_subject_records,
    compute_student_cumulative_summary,
    compute_internal_grade,
    compute_recovery_classes,
    add_daily_log,
    get_daily_logs,
    create_dispute_ticket,
    get_dispute_tickets,
    resolve_dispute_ticket,
    dispatch_notification,
    dispatch_below_threshold_warnings,
    get_notifications,
    acknowledge_notification,
)
from modules.agent import TeachingAdvisorAgent
from modules.styles import (
    SVG_ICONS,
    get_app_css,
    render_top_nav_html,
    render_kpi_html,
    render_faculty_card_html,
    render_seat_card_html,
    render_focus_guard_widget,
    render_auto_pdf_download_script,
)

# --- Page Config (Strict Light Mode) ---
st.set_page_config(
    page_title="AttendAI — Classroom Workspace",
    page_icon=":material/verified_user:",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

# Exact 6 Lecture Duration Options requested (45 min to 2 hrs)
DURATION_OPTIONS = {
    "45 minutes": 45,
    "1 hour": 60,
    "1 hour 15 minutes": 75,
    "1 hour 30 minutes": 90,
    "1 hour 45 minutes": 105,
    "2 hours": 120,
}

ACCENT_PRESETS = {
    "Crimson Red": "#DC2626",
    "Cobalt Blue": "#2563EB",
    "Forest Green": "#059669",
    "Burnt Amber": "#D97706",
    "Deep Plum": "#7C3AED",
}

# --- Session State (Clean Blank Defaults — Zero Predefined Data) ---
defaults = {
    "org_name": "Campus Workspace",
    "default_mentor": "",
    "accent_color": "#DC2626",
    "user_role": "Instructor / Mentor",
    "active_lobby": None,
    "active_student_id": None,
    "session_subject": "",
    "session_host": "",
    "session_id": datetime.now().strftime("SESS_%Y%m%d_%H%M%S"),
    "class_duration_label": "45 minutes",
    "session_remaining_sec": 45 * 60,
    "stream_playing": False,
    "stream_speed": "1x",
    "max_strikes": 3,
    "min_attendance_pct": 75,
    "presence_req_pct": 60,
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
    "live_seats": {},
    "drop_alert": None,
    "auto_pdf_payload": None,
    "last_generated_pdf": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Inject 3-Color Light Theme CSS (White + Black Ink + User's Flag Color)
ACCENT = st.session_state.accent_color
st.markdown(get_app_css(ACCENT), unsafe_allow_html=True)

PLOTLY_CFG = {"displayModeBar": False}
PLOTLY_HOVER = dict(bgcolor="#FFFFFF", bordercolor="#000000", font=dict(color="#000000", family="Inter", size=12))


@st.cache_resource(show_spinner="Preparing face verification engine...")
def get_face_analyzer():
    from insightface.app import FaceAnalysis

    face_app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
    face_app.prepare(ctx_id=0, det_size=(320, 320))
    return face_app


def get_grade_slabs() -> dict:
    return {
        "a_plus": st.session_state.grade_a_plus,
        "a": st.session_state.grade_a,
        "max_marks": st.session_state.grade_max_marks,
    }


def sync_live_seats():
    """Keeps live classroom tracking cards synced strictly to the user's enrolled roster."""
    roster = load_all_students()
    valid_ids = {s["student_id"] for s in roster}
    # Remove deleted students
    for sid in list(st.session_state.live_seats.keys()):
        if sid not in valid_ids:
            del st.session_state.live_seats[sid]
    # Add newly enrolled students
    for s in roster:
        sid = s["student_id"]
        if sid not in st.session_state.live_seats:
            st.session_state.live_seats[sid] = {
                "student_id": sid,
                "name": s["name"],
                "presence": 100.0,
                "focus_state": "Ready",
                "strikes": 0,
                "status": "Present",
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


def compute_weighted_engagement(gaze: float, move: float, audio: float) -> float:
    w_sum = max(1, st.session_state.w_gaze + st.session_state.w_move + st.session_state.w_audio)
    score = (
        gaze * (st.session_state.w_gaze / w_sum)
        + move * (st.session_state.w_move / w_sum)
        + audio * (st.session_state.w_audio / w_sum)
    )
    return round(score, 1)


def push_telemetry_step(gaze: float, move: float, audio: float, trigger_ai: bool = False):
    total = compute_weighted_engagement(gaze, move, audio)
    metrics = {
        "total_engagement": total,
        "gaze_score": round(gaze, 1),
        "movement_score": round(move, 1),
        "audio_score": round(audio, 1),
        "inactivity_sec": 18.0 if move < 50 else 1.5,
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

    for seat in st.session_state.live_seats.values():
        if seat["strikes"] < int(st.session_state.max_strikes):
            delta = 0.5 if total >= 65 else -1.5
            seat["presence"] = round(min(100.0, max(20.0, seat["presence"] + delta)), 1)
            seat["focus_state"] = "Engaged" if gaze >= 70 else ("Distracted" if gaze >= 50 else "Low Focus")
            seat["status"] = "Present" if seat["presence"] >= st.session_state.presence_req_pct else "Verifying"

    hist = st.session_state.engagement_history
    peak = max(item["Overall"] for item in hist[-5:]) if len(hist) >= 2 else total
    if peak - total >= 15.0:
        st.session_state.drop_alert = f"Attention dropped {round(peak - total, 1)}% ({peak}% to {total}%). Consider a brief interactive check."
    elif 0 < total < 55.0:
        st.session_state.drop_alert = f"Class engagement is below target ({total}%). Review Teaching Assistant suggestions."
    else:
        st.session_state.drop_alert = None

    if trigger_ai:
        agent = TeachingAdvisorAgent()
        seats = list(st.session_state.live_seats.values())
        present_cnt = sum(1 for s in seats if "Present" in s["status"])
        adv = agent.generate_advice(st.session_state.session_id, metrics, present_cnt, max(1, len(seats)))
        st.session_state.suggestion_feed.insert(
            0,
            {"category": adv["category"], "time": datetime.now().strftime("%H:%M"), "text": adv["text"]},
        )


def record_focus_flag(student_id: str, reason: str = "Switched tab / left window"):
    max_s = int(st.session_state.max_strikes)
    seat = st.session_state.live_seats.get(student_id)
    if not seat:
        return None, ""
    seat["strikes"] += 1
    room = get_active_room()
    subj = room["active_subject"] if room else (st.session_state.session_subject or "Scheduled Lecture")
    if seat["strikes"] >= max_s:
        seat["status"] = "Absent (Focus Limit)"
        seat["focus_state"] = "Limit Exceeded"
        seat["presence"] = max(0.0, seat["presence"] - 30.0)
        action = f"Marked Absent ({max_s}/{max_s} flags) · Guardian & Instructor Notified"
        for role in ("Parent", "Student", "Instructor"):
            dispatch_notification(
                recipient_role=role,
                student_id=seat["student_id"],
                student_name=seat["name"],
                category="Focus Alert",
                severity="Critical",
                title=f"Marked Absent (Focus Limit) — {seat['name']}",
                message=f"{seat['name']} reached {seat['strikes']}/{max_s} window-exit alerts during {subj} and was marked Absent.",
                channels="Portal · Email · SMS",
            )
    else:
        seat["focus_state"] = "Focus Alert"
        action = f"Focus Flag Recorded ({seat['strikes']}/{max_s})"

    log_proctor_incident(
        session_id=st.session_state.session_id,
        student_id=seat["student_id"],
        student_name=seat["name"],
        event_type=reason,
        duration_sec=round(random.uniform(6.0, 20.0), 1),
        strike_count=seat["strikes"],
        max_strikes=max_s,
        action_taken=action,
    )
    return seat["name"], action


def finalize_and_auto_generate_pdf():
    room = get_active_room()
    room_code = room["lobby_code"] if room else "GENERAL"
    subj_name = room["active_subject"] if room else (st.session_state.session_subject or "Classroom Session")
    sess_id = st.session_state.session_id
    now_t = datetime.now().strftime("%H:%M:%S")

    seats = list(st.session_state.live_seats.values())
    for seat in seats:
        log_attendance(
            session_id=sess_id,
            student_id=seat["student_id"],
            name=seat["name"],
            first_seen=now_t,
            last_seen=now_t,
            ratio=seat["presence"],
            status="Present" if "Present" in seat["status"] else seat["status"],
        )

    df_att, df_eng, df_sug = get_session_data(sess_id)
    df_proctor = get_proctor_incidents(sess_id)
    agent = TeachingAdvisorAgent()
    md_text, pdf_bytes = agent.generate_executive_report(
        session_id=sess_id,
        df_att=df_att,
        df_eng=df_eng,
        df_sug=df_sug,
        df_proctor=df_proctor,
        lobby_code=room_code,
        subject_name=subj_name,
    )

    b64_pdf = base64.b64encode(pdf_bytes).decode("ascii")
    avg_eng = float(df_eng["total_engagement"].mean()) if not df_eng.empty else st.session_state.latest_metrics["total_engagement"]
    present_cnt = sum(1 for s in seats if "Present" in s["status"])

    save_session_report(
        session_id=sess_id,
        lobby_code=room_code,
        subject_name=subj_name,
        avg_engagement=avg_eng,
        present_count=present_cnt,
        total_count=len(seats),
        proctor_violations=len(df_proctor),
        pdf_b64=b64_pdf,
    )

    filename = f"AttendAI_Report_{sess_id}.pdf"
    st.session_state.auto_pdf_payload = (filename, b64_pdf)
    st.session_state.last_generated_pdf = (filename, pdf_bytes, md_text)
    st.session_state.stream_playing = False
    st.session_state.session_remaining_sec = DURATION_OPTIONS[st.session_state.class_duration_label] * 60
    st.session_state.session_id = datetime.now().strftime("SESS_%Y%m%d_%H%M%S")


def auto_tick_session():
    step_sec = 4 if st.session_state.stream_speed == "2x" else 2
    st.session_state.session_remaining_sec = max(0, st.session_state.session_remaining_sec - step_sec)
    if st.session_state.sim_gaze > 0 or st.session_state.sim_move > 0 or st.session_state.sim_audio > 0:
        g = float(np.clip(st.session_state.sim_gaze + random.uniform(-2.5, 2.5), 15, 100))
        m = float(np.clip(st.session_state.sim_move + random.uniform(-2.0, 2.0), 15, 100))
        a = float(np.clip(st.session_state.sim_audio + random.uniform(-3.0, 3.0), 5, 100))
        st.session_state.sim_gaze, st.session_state.sim_move, st.session_state.sim_audio = int(g), int(m), int(a)
        push_telemetry_step(g, m, a, trigger_ai=False)
    if st.session_state.session_remaining_sec <= 0:
        finalize_and_auto_generate_pdf()


def build_trend_chart(history: list) -> go.Figure:
    df_h = pd.DataFrame(history)
    fig = go.Figure()
    styles = [
        ("Overall", "#000000", 3.0, "solid"),
        ("Visual Attention", "#52525B", 1.8, "dash"),
        ("Class Discussion", ACCENT, 1.8, "dot"),
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
                    hovertemplate=f"<b>{name}</b>: %{{y:.1f}}%<extra></extra>",
                )
            )
    fig.add_hline(
        y=60,
        line_dash="dot",
        line_color=ACCENT,
        annotation_text="Minimum Attention Line (60%)",
        annotation_position="bottom right",
        annotation_font=dict(color=ACCENT, size=11),
    )
    fig.update_layout(
        height=265,
        margin=dict(l=8, r=8, t=12, b=8),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font=dict(color="#000000", family="Inter", size=11),
        hovermode="x unified",
        hoverlabel=PLOTLY_HOVER,
        yaxis=dict(range=[0, 105], title="Score (%)", gridcolor="#E4E4E7", zeroline=False),
        xaxis=dict(title="", gridcolor="#F4F4F5"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


sync_live_seats()
lobbies = get_lobbies()
all_students = load_all_students()
active_room = get_active_room()

# --- Sidebar: Workspace Role, Room Selector, Class Duration & Collapsible Controls ---
with st.sidebar:
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:2px;">'
        f'<div class="brand-mark" style="width:28px;height:28px;">{SVG_ICONS["brand"]}</div>'
        f'<span style="font-size:1.05rem;font-weight:800;color:#000000;">AttendAI</span>'
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(st.session_state.org_name)
    st.divider()

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
        st.rerun()

    st.divider()

    # Collapsible Manual Signal & Testing Drawer
    with st.expander("Live Signal Controls", expanded=False):
        st.caption("Manually adjust classroom signals to record an engagement snapshot.")
        g_val = st.slider("Visual Attention (%)", 0, 100, int(st.session_state.sim_gaze))
        m_val = st.slider("Posture & Activity (%)", 0, 100, int(st.session_state.sim_move))
        a_val = st.slider("Class Discussion (%)", 0, 100, int(st.session_state.sim_audio))
        st.session_state.sim_gaze, st.session_state.sim_move, st.session_state.sim_audio = g_val, m_val, a_val

        if st.button("Record Snapshot", icon=":material/add_chart:", type="primary", width="stretch"):
            push_telemetry_step(g_val, m_val, a_val, trigger_ai=False)
            st.rerun()

        if all_students:
            target_opts = {f"{s['name']} ({s['student_id']})": s["student_id"] for s in all_students}
            flag_pick = st.selectbox("Flag Student Focus Alert", list(target_opts.keys()))
            if st.button("Log Focus Alert", icon=":material/flag:", width="stretch"):
                sname, act = record_focus_flag(target_opts[flag_pick])
                if sname:
                    st.toast(f"{sname}: {act}")
                st.rerun()

    st.markdown("**Flag / Highlight Color**")
    chosen_color = st.color_picker(
        "Pick Flag Color",
        value=st.session_state.accent_color,
        help="Controls the 3rd color used for warnings, alerts, and important highlights.",
    )
    if chosen_color != st.session_state.accent_color:
        st.session_state.accent_color = chosen_color
        st.rerun()

# Trigger Auto-PDF download if session ended
if st.session_state.auto_pdf_payload:
    fname, b64_data = st.session_state.auto_pdf_payload
    components.html(render_auto_pdf_download_script(fname, b64_data), height=0)
    st.session_state.auto_pdf_payload = None

# Top Header
role_key = {"Instructor / Mentor": "Instructor", "Student": "Student", "Parent / Guardian": "Parent"}[st.session_state.user_role]
unread_df = get_notifications(recipient_role=role_key)
unread_cnt = int((unread_df["acknowledged"] == 0).sum()) if not unread_df.empty else 0
room_tag = active_room["lobby_code"] if active_room else "No Room Selected"
status_tag = "Live" if st.session_state.stream_playing else "Standby"
st.markdown(render_top_nav_html(st.session_state.org_name, room_tag, st.session_state.user_role, status_tag, unread_cnt), unsafe_allow_html=True)

if st.session_state.last_generated_pdf:
    pdf_name, pdf_raw, _ = st.session_state.last_generated_pdf
    bl, br = st.columns([3.2, 1], vertical_alignment="center")
    with bl:
        st.info(f"Session report **{pdf_name}** was automatically generated and saved under Roster & Reports.")
    with br:
        st.download_button("Download PDF", data=pdf_raw, file_name=pdf_name, mime="application/pdf", icon=":material/picture_as_pdf:", type="primary", width="stretch")


# ==============================================================================
# TAB 1: LIVE SESSION
# ==============================================================================
def _render_live_session():
    if st.session_state.drop_alert:
        st.markdown(f'<div class="flag-banner">{SVG_ICONS["flag"]}<span>{st.session_state.drop_alert}</span></div>', unsafe_allow_html=True)

    # Focused Session Timer Card
    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns([1.85, 0.95, 0.85, 0.7, 1.25], vertical_alignment="center")
        mins, secs = divmod(int(st.session_state.session_remaining_sec), 60)
        subj_title = active_room["active_subject"] if active_room else (st.session_state.session_subject or "New Lecture Session")
        host_sub = (
            f"{active_room['active_host']} · {active_room['name']}"
            if active_room
            else "Create a Course Room or enter a lecture title below to begin."
        )
        with c1:
            st.markdown(f'<div class="sec-title" style="font-size:1.05rem;">{subj_title}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="sec-sub" style="margin:0;">{host_sub}</div>', unsafe_allow_html=True)
        with c2:
            st.markdown(
                f'<div style="text-align:center;">'
                f'<div style="font-size:0.70rem;font-weight:600;color:#3F3F46;text-transform:uppercase;">{st.session_state.class_duration_label}</div>'
                f'<div class="timer-val" style="font-size:1.55rem;font-weight:800;color:#000000;">{mins:02d}:{secs:02d}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
        with c3:
            if st.session_state.stream_playing:
                if st.button("Pause", icon=":material/pause:", width="stretch"):
                    st.session_state.stream_playing = False
                    st.rerun()
            else:
                if st.button("Start Class", icon=":material/play_arrow:", type="primary", width="stretch"):
                    st.session_state.stream_playing = True
                    st.rerun()
        with c4:
            st.session_state.stream_speed = st.selectbox("Speed", ["1x", "2x"], index=0 if st.session_state.stream_speed == "1x" else 1, label_visibility="collapsed")
        with c5:
            if st.button("End & Auto-PDF", icon=":material/picture_as_pdf:", width="stretch"):
                finalize_and_auto_generate_pdf()
                st.rerun()

    # Four Engagement Metric Cards (Pure White + Black Ink + Flag Color when Low)
    m = st.session_state.latest_metrics
    has_data = len(st.session_state.engagement_history) > 0
    k1, k2, k3, k4 = st.columns(4)
    specs = [
        ("Overall Engagement", m["total_engagement"], f"Weighted ({st.session_state.w_gaze}/{st.session_state.w_move}/{st.session_state.w_audio})"),
        ("Visual Attention", m["gaze_score"], "Screen & board focus"),
        ("Posture & Activity", m["movement_score"], "Active classroom alertness"),
        ("Class Discussion", m["audio_score"], "Q&A & vocal interaction"),
    ]
    for col, (lbl, val, sub) in zip([k1, k2, k3, k4], specs):
        if not has_data:
            col.markdown(render_kpi_html(lbl, 0.0, "Awaiting live session data", flagged=False, tag="Standby"), unsafe_allow_html=True)
        else:
            is_low = val < 60.0
            tag = "Low — Flagged" if is_low else "On Track"
            col.markdown(render_kpi_html(lbl, val, sub, flagged=is_low, tag=tag), unsafe_allow_html=True)
    st.write("")

    col_l, col_r = st.columns([1.32, 1], gap="medium")

    with col_l:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Engagement Timeline</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-sub">Open <strong>Live Signal Controls</strong> in the left sidebar to record metrics or click <strong>Start Class</strong> above.</p>', unsafe_allow_html=True)
            if st.session_state.engagement_history:
                st.plotly_chart(build_trend_chart(st.session_state.engagement_history), width="stretch", config=PLOTLY_CFG, theme=None)
            else:
                st.markdown(
                    '<div class="empty-box"><h4>No Session Telemetry Yet</h4>'
                    '<p>Record a snapshot from <strong>Live Signal Controls</strong> in the sidebar to plot real-time classroom engagement.</p></div>',
                    unsafe_allow_html=True,
                )

        with st.container(border=True):
            st.markdown('<p class="sec-title">Live Classroom Roster</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-sub">Real-time presence status and window-focus alerts for enrolled students.</p>', unsafe_allow_html=True)
            seats = list(st.session_state.live_seats.values())
            if not seats:
                st.markdown(
                    '<div class="empty-box"><h4>No Students Enrolled</h4>'
                    '<p>Add students in the <strong>Roster &amp; Reports</strong> tab so they appear here during live classes.</p></div>',
                    unsafe_allow_html=True,
                )
            else:
                g1, g2 = st.columns(2)
                for idx, seat in enumerate(seats):
                    tgt = g1 if idx % 2 == 0 else g2
                    tgt.markdown(
                        render_seat_card_html(
                            seat["student_id"],
                            seat["name"],
                            seat["presence"],
                            seat["focus_state"],
                            seat["strikes"],
                            int(st.session_state.max_strikes),
                            seat["status"],
                            ACCENT,
                        ),
                        unsafe_allow_html=True,
                    )

    with col_r:
        with st.container(border=True):
            h1, h2 = st.columns([1.2, 1], vertical_alignment="center")
            with h1:
                st.markdown('<p class="sec-title" style="margin:0;">Teaching Assistant</p>', unsafe_allow_html=True)
            with h2:
                if st.button("Generate Tip", icon=":material/auto_awesome:", type="primary", width="stretch"):
                    agent = TeachingAdvisorAgent()
                    seats = list(st.session_state.live_seats.values())
                    adv = agent.generate_advice(
                        st.session_state.session_id,
                        st.session_state.latest_metrics,
                        sum(1 for s in seats if "Present" in s["status"]),
                        max(1, len(seats)),
                    )
                    st.session_state.suggestion_feed.insert(0, {"category": adv["category"], "time": datetime.now().strftime("%H:%M"), "text": adv["text"]})
                    st.rerun(scope="fragment")
            st.markdown('<p class="sec-sub" style="margin-top:4px;">Ask for pacing suggestions or engagement activities based on live metrics.</p>', unsafe_allow_html=True)

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
                        placeholder="Example: Suggest a 2-minute concept check for today's topic",
                        label_visibility="collapsed",
                    )
                with q2:
                    q_send = st.form_submit_button("Ask", icon=":material/send:", width="stretch")
                if q_send and q_text.strip():
                    agent = TeachingAdvisorAgent()
                    seats = list(st.session_state.live_seats.values())
                    adv = agent.generate_advice(
                        st.session_state.session_id,
                        st.session_state.latest_metrics,
                        sum(1 for s in seats if "Present" in s["status"]),
                        max(1, len(seats)),
                        custom_question=q_text.strip(),
                    )
                    st.session_state.suggestion_feed.insert(0, {"category": adv["category"], "time": datetime.now().strftime("%H:%M"), "text": adv["text"]})
                    st.rerun(scope="fragment")

        with st.container(border=True):
            st.markdown('<p class="sec-title">Window Focus Integrity</p>', unsafe_allow_html=True)
            st.markdown(f'<p class="sec-sub">Automatically marks a student Absent after <strong>{st.session_state.max_strikes}</strong> tab switches or window exits.</p>', unsafe_allow_html=True)
            components.html(render_focus_guard_widget(int(st.session_state.max_strikes), ACCENT), height=145)
            df_inc = get_proctor_incidents()
            if not df_inc.empty:
                st.dataframe(
                    df_inc[["timestamp", "student_name", "strike_count", "action_taken"]].head(4).rename(
                        columns={"timestamp": "Time", "student_name": "Student", "strike_count": "Flags", "action_taken": "Action"}
                    ),
                    width="stretch",
                    hide_index=True,
                )


@st.fragment(run_every=2)
def render_live_streaming():
    if st.session_state.stream_playing:
        auto_tick_session()
    _render_live_session()


@st.fragment
def render_live_paused():
    _render_live_session()


# ==============================================================================
# TAB 2: COURSE ROOMS (MULTI-TEACHER COLLABORATION)
# ==============================================================================
@st.fragment
def render_course_rooms():
    t1, t2, t3 = st.columns([2.1, 0.95, 0.95], vertical_alignment="center")
    with t1:
        st.markdown('<p class="sec-title" style="font-size:1.05rem;">Course Rooms</p>', unsafe_allow_html=True)
        st.markdown('<p class="sec-sub">Create a shared cohort room where multiple subject teachers track attendance and share assignments together.</p>', unsafe_allow_html=True)

    with t2:
        with st.popover("New Room", icon=":material/add:", width="stretch"):
            c_code = st.text_input("Room Code", placeholder="Example: ECE-301")
            c_name = st.text_input("Room Name", placeholder="Example: B.Tech ECE Semester V")
            c_cohort = st.text_input("Section / Batch", placeholder="Example: Section A (2026-27)")
            c_host = st.text_input("Lead Instructor", placeholder="Example: Dr. Vikram Deshmukh")
            c_sub = st.text_input("Primary Subject", placeholder="Example: Digital Signal Processing")
            if st.button("Create Room", type="primary", width="stretch"):
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
        with st.popover("Join Room", icon=":material/login:", width="stretch"):
            j_code = st.text_input("Room Code to Join", placeholder="Example: ECE-301")
            j_teacher = st.text_input("Your Name", placeholder="Example: Prof. Neha Kulkarni")
            j_sub = st.text_input("Your Subject", placeholder="Example: Embedded Systems")
            if st.button("Join as Instructor", type="primary", width="stretch"):
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
                        if st.button("Host Next", key=f"host_{t['id']}", width="stretch"):
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
                    with st.popover("New Assignment", icon=":material/assignment_add:", width="stretch"):
                        a_sub = st.text_input("Subject", placeholder=f"Example: {room['active_subject']}")
                        a_teacher = st.text_input("Instructor", placeholder=f"Example: {room['active_host']}")
                        a_title = st.text_input("Assignment Title", placeholder="Example: Lab 4 — FIR Filter Design")
                        a_due = st.date_input("Due Date", value=datetime.now() + timedelta(days=7))
                        if st.button("Publish Assignment", type="primary", width="stretch"):
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
                st.dataframe(df_disp, width="stretch", hide_index=True)


# ==============================================================================
# TAB 3: ATTENDANCE & GRADES (THEORY vs PRACTICAL, CUSTOM THRESHOLD & DISPUTES)
# ==============================================================================
@st.fragment
def render_attendance_and_grades():
    min_req = float(st.session_state.min_attendance_pct)
    slabs = get_grade_slabs()
    students = load_all_students()

    # Teacher Data Entry Controls (Zero Predefined Data — Easy Guided Input)
    if st.session_state.user_role == "Instructor / Mentor":
        act1, act2, act3 = st.columns([1.2, 1.2, 1.6], vertical_alignment="center")
        with act1:
            with st.popover("Record Subject Attendance", icon=":material/add_box:", width="stretch"):
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
                    if st.button("Save Subject Record", type="primary", width="stretch"):
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
            with st.popover("Log Daily Class Entry", icon=":material/today:", width="stretch"):
                if not students:
                    st.warning("Enroll at least one student in Roster & Reports first.")
                else:
                    s_opts = {f"{s['name']} ({s['student_id']})": s for s in students}
                    sel_d = s_opts[st.selectbox("Student", list(s_opts.keys()), key="daily_stu")]
                    d_subj = st.text_input("Subject", placeholder="Example: Embedded Systems")
                    d_type = st.radio("Session Type", ["Theory", "Practical"], horizontal=True)
                    d_teacher = st.text_input("Instructor Name", placeholder="Example: Prof. Neha Kulkarni")
                    d_slot = st.text_input("Time Slot", placeholder="Example: 10:30 - 11:15")
                    d_status = st.selectbox("Status", ["Present", "Absent", "Absent (Focus Limit)"])
                    if st.button("Add to Daily Summary", type="primary", width="stretch"):
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
            '<p>Enroll students in <strong>Roster &amp; Reports</strong>, then click <strong>Record Subject Attendance</strong> above to calculate separate Theory &amp; Practical grades and cumulative percentages.</p></div>',
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
                    f'Warnings dispatched to Student &amp; Guardian portals ({row_s["recovery"]} needed).'
                    f"</span></div>",
                    unsafe_allow_html=True,
                )

            m1, m2, m3, m4 = st.columns(4)
            m1.markdown(render_kpi_html("Cumulative Attendance", row_s["cumulative_pct"], f"Target: {int(min_req)}%", flagged=below_min, tag="Flagged" if below_min else "Eligible"), unsafe_allow_html=True)
            m2.markdown(render_kpi_html("Theory Lectures", row_s["theory_pct"], "All subjects combined", flagged=(row_s["theory_pct"] < min_req), tag="Flagged" if row_s["theory_pct"] < min_req else "On Track"), unsafe_allow_html=True)
            m3.markdown(render_kpi_html("Practical Labs", row_s["practical_pct"], "All labs combined", flagged=(row_s["practical_pct"] < min_req), tag="Flagged" if row_s["practical_pct"] < min_req else "On Track"), unsafe_allow_html=True)
            with m4:
                card_cls = "kpi-card kpi-card-flagged" if below_min else "kpi-card"
                tag_cls = "kpi-tag kpi-tag-flag" if below_min else "kpi-tag"
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
                st.dataframe(pd.DataFrame(calc_rows), width="stretch", hide_index=True)

    # Daily Summary & Student Flag/Dispute Desk
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
                        width="stretch",
                    )
            if df_daily.empty:
                st.caption("No daily attendance entries logged today.")
            else:
                st.dataframe(
                    df_daily[["time_slot", "student_name", "subject_name", "session_type", "status", "proctor_strikes"]].rename(
                        columns={"time_slot": "Time", "student_name": "Student", "subject_name": "Subject", "session_type": "Type", "status": "Status", "proctor_strikes": "Flags"}
                    ),
                    width="stretch",
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
                    f_reason = st.text_area("Reason for Correction", placeholder="Example: Present in Lab Bay 2 during equipment setup; missed camera scan.")
                    if st.button("Submit Correction Flag", icon=":material/flag:", type="primary", width="stretch"):
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
                            if st.button("Approve & Recalculate", key=f"appr_{tk['id']}", type="primary", width="stretch"):
                                resolve_dispute_ticket(int(tk["id"]), True, "Verified by faculty; attendance updated.")
                                st.rerun(scope="fragment")
                        with b2:
                            if st.button("Decline", key=f"rej_{tk['id']}", width="stretch"):
                                resolve_dispute_ticket(int(tk["id"]), False, "Attendance could not be verified.")
                                st.rerun(scope="fragment")


# ==============================================================================
# TAB 4: GUARDIAN & STUDENT SAFETY
# ==============================================================================
@st.fragment
def render_guardian_and_safety():
    min_req = float(st.session_state.min_attendance_pct)
    students = load_all_students()
    p_l, p_r = st.columns([1.25, 1], gap="medium")

    with p_l:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Guardian Alerts &amp; Attendance Warnings</p>', unsafe_allow_html=True)
            st.markdown(f'<p class="sec-sub">Automatic alerts for students below {int(min_req)}% attendance, unexpected exits, and daily digests.</p>', unsafe_allow_html=True)

            if st.button(f"Run Below-{int(min_req)}% Warning Audit", icon=":material/notifications_active:", width="stretch"):
                cnt = dispatch_below_threshold_warnings(min_threshold=min_req)
                st.toast(f"Dispatched {cnt} warning(s) to Student & Guardian portals." if cnt else "All alerts are up to date.")
                st.rerun(scope="fragment")

            notifs = get_notifications(recipient_role="Parent" if st.session_state.user_role == "Parent / Guardian" else None)
            if notifs.empty:
                st.markdown(
                    '<div class="empty-box"><h4>No Guardian Alerts Yet</h4>'
                    '<p>Warnings for low attendance, focus-limit absences, and safety check-ins will appear here automatically.</p></div>',
                    unsafe_allow_html=True,
                )
            else:
                for _, nf in notifs.head(6).iterrows():
                    is_crit = nf["severity"] == "Critical"
                    st.markdown(
                        f'<div class="ink-card {"ink-card-flag" if is_crit else ""}">'
                        f'<div class="row-between"><span class="card-title">{nf["title"]}</span><span class="card-meta">{nf["created_at"]}</span></div>'
                        f'<div style="font-size:0.82rem;margin-top:4px;">{nf["message"]}</div>'
                        f'<div class="card-meta">To: {nf["recipient_role"]} &middot; {nf["channels"]} &middot; <strong>{"Read" if nf["acknowledged"] else "Unread"}</strong></div></div>',
                        unsafe_allow_html=True,
                    )
                    if not nf["acknowledged"]:
                        if st.button("Mark as Read", key=f"ack_{nf['id']}", width="stretch"):
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
            if st.button("Send Private Safety Alert", icon=":material/health_and_safety:", type="primary", width="stretch"):
                body = sos_msg.strip() or f"{sel_safe['name']} requested a private safety check-in."
                for r_role in ("Instructor", "Parent"):
                    dispatch_notification(r_role, sel_safe["student_id"], sel_safe["name"], "Student Safety", "Critical", f"Safety Check-In — {sel_safe['name']}", body, "Mentor Desk · SMS")
                st.success("Private safety alert sent to Mentor and Guardian.")
                st.rerun(scope="fragment")

            st.divider()
            st.markdown("**Guardian Note to Mentor**")
            with st.form("guardian_msg_form", clear_on_submit=True, border=False):
                g_note = st.text_input("Message", placeholder="Example: My ward has a medical appointment during Period 3 today.")
                if st.form_submit_button("Send to Mentor", icon=":material/mail:", width="stretch") and g_note.strip():
                    dispatch_notification("Instructor", sel_safe["student_id"], sel_safe["name"], "Guardian Note", "Info", f"Note from Guardian ({sel_safe['name']})", g_note.strip(), "Guardian Portal")
                    st.toast("Message sent to Mentor.")
                    st.rerun(scope="fragment")


# ==============================================================================
# TAB 5: ROSTER & REPORTS
# ==============================================================================
@st.fragment
def render_roster_and_reports():
    st1, st2 = st.tabs([":material/group: Student Roster", ":material/description: Automated PDF Archive"])

    with st1:
        r_l, r_r = st.columns([1, 1.35], gap="medium")
        with r_l:
            with st.container(border=True):
                st.markdown('<p class="sec-title">Enroll Student</p>', unsafe_allow_html=True)
                st.markdown('<p class="sec-sub">Add a student quickly or upload a portrait for local 512-D biometric verification (zero photos stored).</p>', unsafe_allow_html=True)
                nid = st.text_input("Student ID", placeholder="Example: 0103EC231042 or S101")
                nname = st.text_input("Full Name", placeholder="Example: Aarav Sharma")
                mode = st.radio("Enrollment Method", ["Quick Roster Entry", "Portrait Photo (Biometric)", "Camera Snapshot"], horizontal=True)

                img_file = None
                if mode == "Portrait Photo (Biometric)":
                    img_file = st.file_uploader("Upload Front-Facing Portrait", type=["jpg", "jpeg", "png"])
                elif mode == "Camera Snapshot":
                    img_file = st.camera_input("Capture Snapshot")

                if st.button("Enroll Student", icon=":material/person_add:", type="primary", width="stretch"):
                    if not nid.strip() or not nname.strip():
                        st.error("Enter both Student ID and Full Name.")
                    elif mode == "Quick Roster Entry":
                        save_student(nid, nname, None)
                        sync_live_seats()
                        st.success(f"Enrolled {nname.strip()} ({nid.strip()}).")
                        st.rerun()
                    else:
                        if img_file is None:
                            st.error("Upload a photo or switch to Quick Roster Entry.")
                        else:
                            arr = np.asarray(bytearray(img_file.read()), dtype=np.uint8)
                            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                            if img is not None:
                                fapp = get_face_analyzer()
                                faces = fapp.get(img)
                                if len(faces) == 1:
                                    emb = faces[0].embedding / np.linalg.norm(faces[0].embedding)
                                    save_student(nid, nname, emb)
                                    sync_live_seats()
                                    st.success(f"Enrolled {nname.strip()} with 512-D vector. Original photo discarded.")
                                    st.rerun()
                                else:
                                    st.error("Ensure exactly one clear face is visible in the frame.")

        with r_r:
            with st.container(border=True):
                st.markdown('<p class="sec-title">Enrolled Student Directory</p>', unsafe_allow_html=True)
                roster = load_all_students()
                if not roster:
                    st.markdown(
                        '<div class="empty-box"><h4>Roster Is Empty</h4>'
                        '<p>Use the form on the left to enroll your students. No sample or placeholder students are pre-loaded.</p></div>',
                        unsafe_allow_html=True,
                    )
                else:
                    rdf = pd.DataFrame([
                        {"Student ID": r["student_id"], "Full Name": r["name"], "Privacy Status": "512-D Vector · 0 Photos", "Enrolled On": r["created_at"]}
                        for r in roster
                    ])
                    st.dataframe(rdf, width="stretch", hide_index=True)

                    m1, m2 = st.columns([2.2, 1], vertical_alignment="center")
                    opts = {f"{r['name']} ({r['student_id']})": r["student_id"] for r in roster}
                    with m1:
                        del_pick = st.selectbox("Select Student to Remove", list(opts.keys()), label_visibility="collapsed")
                    with m2:
                        if st.button("Remove Student", icon=":material/delete:", width="stretch"):
                            delete_student(opts[del_pick])
                            sync_live_seats()
                            st.toast("Student removed.")
                            st.rerun()

    with st2:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Automated Session PDF Archive</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-sub">Every completed session automatically generates and archives a downloadable PDF report.</p>', unsafe_allow_html=True)
            rep_df = get_session_reports()
            if rep_df.empty:
                st.markdown(
                    '<div class="empty-box"><h4>No Archived Reports Yet</h4>'
                    '<p>Click <strong>End &amp; Auto-PDF</strong> in the Live Session tab to generate your first session dossier.</p></div>',
                    unsafe_allow_html=True,
                )
            else:
                for _, rr in rep_df.head(8).iterrows():
                    rc1, rc2 = st.columns([3, 1], vertical_alignment="center")
                    with rc1:
                        st.markdown(
                            f"**{rr['subject_name']}** ({rr['lobby_code']}) &middot; Engagement: **{rr['avg_engagement']}%** "
                            f"&middot; Present: **{rr['present_count']}/{rr['total_count']}** &middot; Focus Flags: **{rr['proctor_violations']}** "
                            f"&middot; _{rr['generated_at']}_"
                        )
                    with rc2:
                        st.download_button(
                            "Download PDF",
                            data=base64.b64decode(rr["pdf_b64"]),
                            file_name=f"AttendAI_Report_{rr['session_id']}.pdf",
                            mime="application/pdf",
                            icon=":material/picture_as_pdf:",
                            key=f"dl_{rr['id']}",
                            width="stretch",
                        )


# ==============================================================================
# TAB 6: CUSTOMIZE & WORKSPACE SETTINGS (BUILT FOR TEACHERS)
# ==============================================================================
@st.fragment
def render_settings_tab():
    s_l, s_r = st.columns(2, gap="medium")

    with s_l:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Institution &amp; Color Customization</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-sub">Three-color editorial layout: Pure White background, Black Ink highlights, and your chosen Flag Color.</p>', unsafe_allow_html=True)

            org_in = st.text_input("Institution / Department Name", value=st.session_state.org_name, placeholder="Example: Department of ECE, LNCT Bhopal")
            if org_in.strip() and org_in != st.session_state.org_name:
                st.session_state.org_name = org_in.strip()

            preset_name = st.selectbox("Quick Flag Color Preset", list(ACCENT_PRESETS.keys()))
            c_btn1, c_btn2 = st.columns(2)
            with c_btn1:
                if st.button("Apply Preset Color", width="stretch"):
                    st.session_state.accent_color = ACCENT_PRESETS[preset_name]
                    st.rerun()
            with c_btn2:
                custom_hex = st.color_picker("Or Choose Custom Color", value=st.session_state.accent_color)
                if custom_hex != st.session_state.accent_color:
                    st.session_state.accent_color = custom_hex
                    st.rerun()

        with st.container(border=True):
            st.markdown('<p class="sec-title">Lecture Duration &amp; Proctoring Rules</p>', unsafe_allow_html=True)
            dur_choice = st.selectbox(
                "Default Class Duration",
                list(DURATION_OPTIONS.keys()),
                index=list(DURATION_OPTIONS.keys()).index(st.session_state.class_duration_label),
            )
            if dur_choice != st.session_state.class_duration_label:
                st.session_state.class_duration_label = dur_choice
                st.session_state.session_remaining_sec = DURATION_OPTIONS[dur_choice] * 60
                st.rerun()

            st.session_state.max_strikes = st.slider("Tab-Switch / Window-Exit Limit (Marks Absent)", 1, 10, int(st.session_state.max_strikes))
            st.session_state.presence_req_pct = st.slider("Sustained Presence Threshold (%)", 30, 95, int(st.session_state.presence_req_pct), 5)

    with s_r:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Attendance Warning &amp; Grade Slabs</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-sub">Configure university attendance rules and internal marks calculation.</p>', unsafe_allow_html=True)

            st.session_state.min_attendance_pct = st.slider("Minimum Mandatory Attendance Warning Threshold (%)", 50, 95, int(st.session_state.min_attendance_pct), 1)
            g1, g2, g3 = st.columns(3)
            with g1:
                st.session_state.grade_a_plus = st.number_input("A+ Cutoff (%)", 75, 100, int(st.session_state.grade_a_plus))
            with g2:
                st.session_state.grade_a = st.number_input("A Cutoff (%)", 65, 99, int(st.session_state.grade_a))
            with g3:
                st.session_state.grade_max_marks = st.number_input("Max Internal Marks", 1, 20, int(st.session_state.grade_max_marks))

            st.divider()
            st.markdown("**Engagement Score Weights (%)**")
            w1, w2, w3 = st.columns(3)
            with w1:
                st.session_state.w_gaze = st.number_input("Visual Weight", 0, 100, int(st.session_state.w_gaze), 5)
            with w2:
                st.session_state.w_move = st.number_input("Posture Weight", 0, 100, int(st.session_state.w_move), 5)
            with w3:
                st.session_state.w_audio = st.number_input("Discussion Weight", 0, 100, int(st.session_state.w_audio), 5)

        with st.container(border=True):
            st.markdown('<p class="sec-title">Workspace Data Reset</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-sub">Clear any previously saved database records to begin with a completely empty workspace.</p>', unsafe_allow_html=True)
            if st.button("Clear All Workspace Data", icon=":material/delete_forever:", width="stretch"):
                clear_all_data()
                st.session_state.live_seats = {}
                st.session_state.engagement_history = []
                st.session_state.suggestion_feed = []
                st.session_state.active_lobby = None
                st.session_state.active_student_id = None
                st.session_state.drop_alert = None
                st.session_state.last_generated_pdf = None
                st.toast("All records cleared. Workspace is completely empty.")
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