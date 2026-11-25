import cv2
import time
import tempfile
import importlib.util
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime

from modules.database import (
    init_db,
    load_all_students,
    save_student,
    delete_student,
    log_engagement,
    get_session_list,
    get_session_data,
    seed_demo_sessions,
    seed_sample_roster,
)
from modules.attendance import SustainedAttendanceTracker
from modules.engagement import MultimodalEngagementAnalyzer, AUDIO_AVAILABLE
from modules.agent import TeachingAdvisorAgent, check_ollama_status
from modules.styles import (
    SVG_ICONS,
    get_app_css,
    render_hero_html,
    render_kpi_html,
    render_coach_card_html,
    render_empty_roster_html,
    render_audit_panel_html,
)

# --- Page Configuration ---
st.set_page_config(
    page_title="AttendAI • Classroom Intelligence",
    page_icon=":material/verified_user:",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
st.markdown(get_app_css(), unsafe_allow_html=True)

PLOTLY_CONFIG = {"displayModeBar": False}
PLOTLY_HOVER = dict(
    bgcolor="#1E293B",
    bordercolor="rgba(148, 163, 184, 0.28)",
    font=dict(color="#F8FAFC", family="Inter", size=12),
)


# --- Cached Loaders ---
@st.cache_resource(show_spinner="Loading local InsightFace (buffalo_sc) model...")
def get_face_analyzer():
    from insightface.app import FaceAnalysis

    face_app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
    face_app.prepare(ctx_id=0, det_size=(320, 320))
    return face_app


@st.cache_data(ttl=30)
def get_system_diagnostics():
    ollama_ok, ollama_label = check_ollama_status()
    insightface_pkg = importlib.util.find_spec("insightface") is not None
    return {
        "ollama_ok": ollama_ok,
        "ollama_label": ollama_label,
        "insightface_ok": insightface_pkg,
        "audio_ok": AUDIO_AVAILABLE,
    }


# --- Session State Initialization ---
defaults = {
    "running": False,
    "session_id": datetime.now().strftime("SESSION_%Y%m%d_%H%M%S"),
    "engagement_history": [],
    "suggestion_feed": [],
    "attendance_summary": [],
    "latest_metrics": {
        "total_engagement": 0.0,
        "gaze_score": 0.0,
        "movement_score": 0.0,
        "audio_score": 0.0,
        "inactivity_sec": 0.0,
    },
    "prev_metrics": None,
    "sim_gaze": 88,
    "sim_move": 84,
    "sim_audio": 78,
    "drop_alert": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# --- Telemetry Helpers ---
def check_engagement_drop(history: list, current_score: float) -> str | None:
    if len(history) >= 2:
        recent_peak = max(item["Overall"] for item in history[-5:])
        drop = round(recent_peak - current_score, 1)
        if drop >= 15.0:
            return (
                f"Sharp Engagement Drop: -{drop}% from recent peak "
                f"({recent_peak}% to {current_score}%). Consider an interactive check-in."
            )
    if 0 < current_score < 55.0:
        return f"At-Risk Attention Alert: Engagement is at {current_score}%. Review AI Teaching Coach guidance."
    return None


def compute_deltas(current: dict, previous: dict | None) -> dict:
    if not previous:
        return {k: None for k in ["total_engagement", "gaze_score", "movement_score", "audio_score"]}
    return {
        k: round(current[k] - previous[k], 1)
        for k in ["total_engagement", "gaze_score", "movement_score", "audio_score"]
    }


def push_simulator_step(gaze: float, move: float, audio: float, trigger_ai: bool = False):
    total = round(0.50 * gaze + 0.25 * move + 0.25 * audio, 1)
    inactivity = 19.5 if move < 52 else 1.8

    if st.session_state.engagement_history:
        st.session_state.prev_metrics = dict(st.session_state.latest_metrics)

    metrics = {
        "total_engagement": total,
        "gaze_score": round(float(gaze), 1),
        "movement_score": round(float(move), 1),
        "audio_score": round(float(audio), 1),
        "inactivity_sec": inactivity,
    }
    st.session_state.latest_metrics = metrics
    st.session_state.engagement_history.append({
        "Time": datetime.now().strftime("%H:%M:%S"),
        "Overall": total,
        "Visual Gaze": metrics["gaze_score"],
        "Posture & Motion": metrics["movement_score"],
        "Vocal Audio": metrics["audio_score"],
    })
    log_engagement(
        st.session_state.session_id,
        metrics["gaze_score"],
        metrics["movement_score"],
        metrics["audio_score"],
        total,
    )
    st.session_state.drop_alert = check_engagement_drop(st.session_state.engagement_history, total)

    if trigger_ai:
        agent = TeachingAdvisorAgent()
        roster = load_all_students()
        advice = agent.generate_advice(
            st.session_state.session_id,
            metrics,
            present_count=max(1, len(roster)),
            total_students=max(1, len(roster)),
        )
        st.session_state.suggestion_feed.insert(
            0,
            {
                "category": advice["category"],
                "time": datetime.now().strftime("%H:%M:%S"),
                "text": advice["text"],
            },
        )


def build_live_telemetry_chart(history: list) -> go.Figure:
    df_h = pd.DataFrame(history)
    fig = go.Figure()
    series_cfg = [
        ("Overall", "#3B82F6", 3),
        ("Visual Gaze", "#38BDF8", 2),
        ("Vocal Audio", "#10B981", 2),
    ]
    for col_name, color, width in series_cfg:
        if col_name in df_h.columns:
            fig.add_trace(
                go.Scatter(
                    x=df_h["Time"],
                    y=df_h[col_name],
                    mode="lines+markers",
                    name=col_name,
                    line=dict(color=color, width=width, shape="spline"),
                    marker=dict(size=6, line=dict(width=1, color="#0B1120")),
                    hovertemplate=f"<b>{col_name}</b>: %{{y:.1f}}%<extra></extra>",
                )
            )
    fig.add_hline(
        y=60,
        line_dash="dot",
        line_color="rgba(245, 158, 11, 0.55)",
        annotation_text="Watch Threshold (60%)",
        annotation_position="bottom right",
        annotation_font=dict(color="#FBBF24", size=11),
    )
    fig.update_layout(
        height=275,
        margin=dict(l=8, r=8, t=16, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#94A3B8", family="Inter", size=12),
        hovermode="x unified",
        hoverlabel=PLOTLY_HOVER,
        yaxis=dict(range=[0, 105], title="Score (%)", gridcolor="rgba(148, 163, 184, 0.1)", zeroline=False),
        xaxis=dict(title="", gridcolor="rgba(148, 163, 184, 0.06)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


# --- Sidebar Controls & Edge Privacy Audit ---
diag = get_system_diagnostics()
enrolled_roster = load_all_students()

with st.sidebar:
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">'
        f'{SVG_ICONS["shield"]}<span style="font-size:1.15rem;font-weight:800;letter-spacing:-0.02em;">Attend<span style="color:#3B82F6;">AI</span></span>'
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption("Privacy-First Multimodal Classroom Engine")
    st.divider()

    st.markdown("**Session Source**")
    input_mode = st.radio(
        "Session Source",
        ["Interactive Demo Simulator", "Live Webcam", "Recorded Video (.mp4)"],
        label_visibility="collapsed",
    )

    uploaded_video = None
    if input_mode == "Recorded Video (.mp4)":
        uploaded_video = st.file_uploader("Upload Classroom Clip", type=["mp4", "avi", "mov"])

    presence_req = st.slider("Sustained Presence Threshold (%)", 30, 95, 60, 5)
    ai_interval = st.slider("Auto Coach Interval (sec)", 10, 60, 20, 5)

    if input_mode != "Interactive Demo Simulator":
        b1, b2 = st.columns(2)
        with b1:
            if st.button("Start", icon=":material/play_arrow:", width="stretch", type="primary"):
                st.session_state.running = True
                st.session_state.session_id = datetime.now().strftime("SESSION_%Y%m%d_%H%M%S")
                st.session_state.engagement_history = []
                st.session_state.suggestion_feed = []
                st.session_state.prev_metrics = None
                st.session_state.drop_alert = None
                st.rerun()
        with b2:
            if st.button("Stop", icon=":material/stop:", width="stretch"):
                st.session_state.running = False
                st.rerun()
    else:
        if st.button("Reset Simulator", icon=":material/refresh:", width="stretch"):
            st.session_state.session_id = datetime.now().strftime("SIM_%Y%m%d_%H%M%S")
            st.session_state.engagement_history = []
            st.session_state.suggestion_feed = []
            st.session_state.prev_metrics = None
            st.session_state.latest_metrics = {
                "total_engagement": 0.0,
                "gaze_score": 0.0,
                "movement_score": 0.0,
                "audio_score": 0.0,
                "inactivity_sec": 0.0,
            }
            st.session_state.drop_alert = None
            st.rerun()

    st.divider()
    st.markdown(render_audit_panel_html(diag), unsafe_allow_html=True)
    st.caption(f"Session: `{st.session_state.session_id}` | Roster: {len(enrolled_roster)}")


# --- Top Hero Header ---
if st.session_state.running:
    hero_status, hero_active = "LIVE TELEMETRY ACTIVE", True
elif input_mode == "Interactive Demo Simulator":
    hero_status, hero_active = "INTERACTIVE SIMULATOR READY", True
else:
    hero_status, hero_active = "SYSTEM STANDBY", False

st.markdown(render_hero_html(hero_status, hero_active), unsafe_allow_html=True)


# --- Fragment 1: Live Command Center (Smooth Partial Reruns) ---
@st.fragment
def render_live_command_center():
    roster_now = load_all_students()
    alert_slot = st.empty()
    if st.session_state.drop_alert:
        alert_slot.markdown(
            f'<div class="alert-strip">{SVG_ICONS["alert"]}<span>{st.session_state.drop_alert}</span></div>',
            unsafe_allow_html=True,
        )

    # Upgraded KPI Row (Value + Delta Badge + Status Pill)
    k1, k2, k3, k4 = st.columns(4)
    kpi_slots = [k1.empty(), k2.empty(), k3.empty(), k4.empty()]

    def paint_kpis(m: dict, prev: dict | None):
        deltas = compute_deltas(m, prev)
        specs = [
            ("Overall Engagement", m["total_engagement"], deltas["total_engagement"]),
            ("Visual Gaze Focus", m["gaze_score"], deltas["gaze_score"]),
            ("Posture & Motion", m["movement_score"], deltas["movement_score"]),
            ("Vocal Interaction", m["audio_score"], deltas["audio_score"]),
        ]
        for slot, (lbl, val, dlt) in zip(kpi_slots, specs):
            slot.markdown(render_kpi_html(lbl, val, dlt), unsafe_allow_html=True)

    paint_kpis(st.session_state.latest_metrics, st.session_state.prev_metrics)
    st.write("")

    col_main, col_side = st.columns([1.28, 1], gap="medium")

    with col_main:
        if input_mode == "Interactive Demo Simulator":
            with st.container(border=True):
                st.markdown('<p class="sec-title">Interactive Classroom Scenario Simulator</p>', unsafe_allow_html=True)
                st.markdown(
                    '<p class="sec-caption">Select a preset scenario or fine-tune multimodal signals to evaluate AttendAI without a webcam.</p>',
                    unsafe_allow_html=True,
                )

                p1, p2, p3 = st.columns(3)
                with p1:
                    if st.button("Active Q&A", icon=":material/forum:", width="stretch"):
                        st.session_state.sim_gaze, st.session_state.sim_move, st.session_state.sim_audio = 88, 84, 78
                        push_simulator_step(88, 84, 78, trigger_ai=True)
                        st.rerun(scope="fragment")
                    st.markdown('<div class="preset-sub">88% Gaze &bull; 78% Audio</div>', unsafe_allow_html=True)

                with p2:
                    if st.button("Mid-Lecture Drift", icon=":material/trending_down:", width="stretch"):
                        st.session_state.sim_gaze, st.session_state.sim_move, st.session_state.sim_audio = 44, 48, 12
                        push_simulator_step(44, 48, 12, trigger_ai=True)
                        st.rerun(scope="fragment")
                    st.markdown('<div class="preset-sub">44% Gaze &bull; 12% Audio</div>', unsafe_allow_html=True)

                with p3:
                    if st.button("Silent Note-Taking", icon=":material/edit_note:", width="stretch"):
                        st.session_state.sim_gaze, st.session_state.sim_move, st.session_state.sim_audio = 74, 79, 18
                        push_simulator_step(74, 79, 18, trigger_ai=True)
                        st.rerun(scope="fragment")
                    st.markdown('<div class="preset-sub">74% Gaze &bull; 18% Audio</div>', unsafe_allow_html=True)

                s1, s2, s3 = st.columns(3)
                with s1:
                    g_val = st.slider("Visual Gaze (%)", 0, 100, int(st.session_state.sim_gaze))
                with s2:
                    m_val = st.slider("Posture & Motion (%)", 0, 100, int(st.session_state.sim_move))
                with s3:
                    a_val = st.slider("Vocal Interaction (%)", 0, 100, int(st.session_state.sim_audio))

                st.session_state.sim_gaze = g_val
                st.session_state.sim_move = m_val
                st.session_state.sim_audio = a_val

                act1, act2 = st.columns(2)
                with act1:
                    if st.button("Log Telemetry Window", icon=":material/add_chart:", type="primary", width="stretch"):
                        push_simulator_step(g_val, m_val, a_val, trigger_ai=False)
                        st.rerun(scope="fragment")
                with act2:
                    if st.button("Simulate 5-Window Arc", icon=":material/bolt:", width="stretch"):
                        arc = [(85, 83, 62), (76, 78, 35), (48, 51, 14), (66, 70, 48), (88, 86, 76)]
                        for idx, (ag, am, aa) in enumerate(arc):
                            push_simulator_step(ag, am, aa, trigger_ai=(idx in [2, 4]))
                        st.rerun(scope="fragment")

            video_slot = st.empty()
        else:
            with st.container(border=True):
                st.markdown('<p class="sec-title">Multimodal Vision &amp; Verification Stream</p>', unsafe_allow_html=True)
                video_slot = st.empty()
                if not st.session_state.running:
                    video_slot.info("Click **Start** in the left sidebar to launch real-time verification and tracking.")

        # Live Telemetry Spline Chart
        with st.container(border=True):
            st.markdown('<p class="sec-title">Real-Time Engagement Telemetry</p>', unsafe_allow_html=True)
            st.markdown(
                '<p class="sec-caption">Weighted multimodal fusion: 50% Visual Gaze + 25% Posture &amp; Motion + 25% Vocal Audio</p>',
                unsafe_allow_html=True,
            )
            chart_slot = st.empty()

            def paint_chart():
                if st.session_state.engagement_history:
                    fig = build_live_telemetry_chart(st.session_state.engagement_history)
                    chart_slot.plotly_chart(
                        fig,
                        width="stretch",
                        config=PLOTLY_CONFIG,
                        key=f"live_spline_{len(st.session_state.engagement_history)}",
                    )
                else:
                    chart_slot.markdown(
                        f'<div class="empty-card" style="padding:26px 20px;margin:4px 0;">'
                        f'<div class="empty-card-icon" style="width:44px;height:44px;">{SVG_ICONS["chart"]}</div>'
                        f'<h4>Awaiting Telemetry Windows</h4>'
                        f'<p>Trigger a scenario preset or click <strong>Simulate 5-Window Arc</strong> above to render real-time spline trends.</p>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            paint_chart()

    with col_side:
        # Actionable AI Teaching Coach Panel
        with st.container(border=True):
            ch_l, ch_r = st.columns([1.05, 1], vertical_alignment="center")
            with ch_l:
                st.markdown('<p class="sec-title" style="margin-bottom:0;">AI Teaching Coach</p>', unsafe_allow_html=True)
            with ch_r:
                ask_now = st.button("Ask Coach Now", icon=":material/auto_awesome:", type="primary", width="stretch")

            st.markdown(
                '<p class="sec-caption" style="margin-top:4px;">Categorized pedagogical guidance powered by local LLM + rule fallback.</p>',
                unsafe_allow_html=True,
            )

            coach_slot = st.empty()

            if ask_now:
                agent = TeachingAdvisorAgent()
                present_cnt = sum(1 for r in st.session_state.attendance_summary if r["Status"] == "Present")
                cur_m = st.session_state.latest_metrics
                if cur_m["total_engagement"] == 0.0 and input_mode == "Interactive Demo Simulator":
                    push_simulator_step(st.session_state.sim_gaze, st.session_state.sim_move, st.session_state.sim_audio, trigger_ai=True)
                else:
                    advice = agent.generate_advice(
                        st.session_state.session_id,
                        cur_m,
                        present_cnt or max(1, len(roster_now)),
                        max(1, len(roster_now)),
                    )
                    st.session_state.suggestion_feed.insert(
                        0,
                        {
                            "category": advice["category"],
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "text": advice["text"],
                        },
                    )
                st.rerun(scope="fragment")

            def paint_coach():
                if not st.session_state.suggestion_feed:
                    coach_slot.markdown(
                        render_coach_card_html(
                            "Pacing",
                            "Standby",
                            "Click Ask Coach Now, run a scenario preset, or type a question below to receive tailored pedagogical guidance.",
                        ),
                        unsafe_allow_html=True,
                    )
                else:
                    html_cards = "".join(
                        render_coach_card_html(item["category"], item["time"], item["text"])
                        for item in st.session_state.suggestion_feed[:3]
                    )
                    coach_slot.markdown(html_cards, unsafe_allow_html=True)

            paint_coach()

            # Quick-Ask Input Bar
            with st.form("coach_quick_ask", clear_on_submit=True, border=False):
                qa_c1, qa_c2 = st.columns([3.4, 1])
                with qa_c1:
                    quick_q = st.text_input(
                        "Quick-ask coach",
                        placeholder="Ask Coach (e.g., How to recover focus?)",
                        label_visibility="collapsed",
                    )
                with qa_c2:
                    send_q = st.form_submit_button("Ask", icon=":material/send:", width="stretch")

                if send_q and quick_q.strip():
                    agent = TeachingAdvisorAgent()
                    cur_m = st.session_state.latest_metrics
                    advice = agent.generate_advice(
                        st.session_state.session_id,
                        cur_m,
                        present_count=max(1, len(roster_now)),
                        total_students=max(1, len(roster_now)),
                        custom_question=quick_q.strip(),
                    )
                    st.session_state.suggestion_feed.insert(
                        0,
                        {
                            "category": advice["category"],
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "text": advice["text"],
                        },
                    )
                    st.rerun(scope="fragment")

        # Sustained-Presence Attendance Table
        with st.container(border=True):
            st.markdown('<p class="sec-title">Sustained-Presence Attendance</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-caption">Continuous presence verification against enrolled 512-D embeddings.</p>', unsafe_allow_html=True)
            att_slot = st.empty()
            att_col_cfg = {
                "Presence %": st.column_config.ProgressColumn("Presence %", min_value=0, max_value=100, format="%.1f%%"),
            }
            if st.session_state.attendance_summary:
                att_slot.dataframe(
                    pd.DataFrame(st.session_state.attendance_summary),
                    width="stretch",
                    hide_index=True,
                    column_config=att_col_cfg,
                )
            elif roster_now:
                preview_df = pd.DataFrame([
                    {"Student ID": r["student_id"], "Name": r["name"], "Presence %": 0.0, "Status": "Standby"}
                    for r in roster_now
                ])
                att_slot.dataframe(preview_df, width="stretch", hide_index=True, column_config=att_col_cfg)
            else:
                att_slot.caption("No students enrolled. Load a sample roster in the Roster & Enrollment Manager tab.")

    # Live Webcam / Video Processing Loop
    if st.session_state.running and input_mode != "Interactive Demo Simulator":
        if input_mode == "Recorded Video (.mp4)" and uploaded_video is not None:
            tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            tfile.write(uploaded_video.read())
            cap = cv2.VideoCapture(tfile.name)
        else:
            cap = cv2.VideoCapture(0)

        if not cap.isOpened():
            st.error("Unable to access video source. Switch to Interactive Demo Simulator or upload an .mp4 clip on cloud servers.")
            st.session_state.running = False
        else:
            face_app = get_face_analyzer()
            tracker = SustainedAttendanceTracker(presence_threshold=presence_req / 100.0, face_app=face_app)
            analyzer = MultimodalEngagementAnalyzer()
            agent = TeachingAdvisorAgent()

            if input_mode == "Live Webcam":
                analyzer.start_audio()

            last_log_time = time.time()
            last_ai_time = time.time()

            try:
                while st.session_state.running and cap.isOpened():
                    ret, frame = cap.read()
                    if not ret:
                        st.session_state.running = False
                        break

                    annotated = tracker.process_frame(frame)
                    metrics = analyzer.analyze_frame(frame)
                    prev_m = dict(st.session_state.latest_metrics) if st.session_state.engagement_history else None
                    st.session_state.latest_metrics = metrics

                    rgb_frame = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
                    video_slot.image(rgb_frame, channels="RGB", width="stretch")
                    paint_kpis(metrics, prev_m)

                    now = time.time()
                    if now - last_log_time >= 3.0:
                        st.session_state.prev_metrics = prev_m
                        analyzer.save_window_metrics(st.session_state.session_id, metrics)
                        st.session_state.engagement_history.append({
                            "Time": datetime.now().strftime("%H:%M:%S"),
                            "Overall": metrics["total_engagement"],
                            "Visual Gaze": metrics["gaze_score"],
                            "Posture & Motion": metrics["movement_score"],
                            "Vocal Audio": metrics["audio_score"],
                        })
                        alert_msg = check_engagement_drop(st.session_state.engagement_history, metrics["total_engagement"])
                        st.session_state.drop_alert = alert_msg
                        if alert_msg:
                            alert_slot.markdown(
                                f'<div class="alert-strip">{SVG_ICONS["alert"]}<span>{alert_msg}</span></div>',
                                unsafe_allow_html=True,
                            )
                        else:
                            alert_slot.empty()
                        paint_chart()
                        last_log_time = now

                    summary = tracker.get_summary()
                    st.session_state.attendance_summary = summary
                    if summary:
                        att_slot.dataframe(
                            pd.DataFrame(summary),
                            width="stretch",
                            hide_index=True,
                            column_config=att_col_cfg,
                        )

                    if now - last_ai_time >= ai_interval:
                        present_cnt = sum(1 for r in summary if r["Status"] == "Present")
                        advice = agent.generate_advice(
                            st.session_state.session_id,
                            metrics,
                            present_cnt,
                            max(1, len(summary)),
                        )
                        st.session_state.suggestion_feed.insert(
                            0,
                            {
                                "category": advice["category"],
                                "time": datetime.now().strftime("%H:%M:%S"),
                                "text": advice["text"],
                            },
                        )
                        paint_coach()
                        last_ai_time = now

                    time.sleep(0.05)
            finally:
                analyzer.stop_audio()
                cap.release()
                st.session_state.attendance_summary = tracker.finalize_session(st.session_state.session_id)
                st.toast(f"Session {st.session_state.session_id} finalized and archived locally.")


# --- Fragment 2: Roster & Enrollment Manager ---
@st.fragment
def render_roster_manager():
    r_left, r_right = st.columns([1, 1.35], gap="medium")

    with r_left:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Enroll New Student</p>', unsafe_allow_html=True)
            st.markdown(
                '<p class="sec-caption">Extracts a 512-D mathematical embedding locally in RAM and discards the raw photo immediately.</p>',
                unsafe_allow_html=True,
            )

            new_id = st.text_input("Student ID", placeholder="e.g., S106")
            new_name = st.text_input("Full Name", placeholder="e.g., Priya Deshmukh")
            enroll_method = st.radio(
                "Capture Source",
                ["Upload Portrait Image", "Live Camera Snapshot"],
                horizontal=True,
            )

            img_source = (
                st.file_uploader("Select Front-Facing Portrait", type=["jpg", "jpeg", "png"])
                if enroll_method == "Upload Portrait Image"
                else st.camera_input("Capture Student Snapshot")
            )

            if st.button("Extract & Save 512-D Vector", icon=":material/person_add:", type="primary", width="stretch"):
                if not new_id.strip() or not new_name.strip() or img_source is None:
                    st.error("Provide Student ID, Full Name, and a facial photo.")
                else:
                    file_bytes = np.asarray(bytearray(img_source.read()), dtype=np.uint8)
                    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
                    if img is None:
                        st.error("Could not decode image. Upload a valid JPG or PNG.")
                    else:
                        face_app = get_face_analyzer()
                        faces = face_app.get(img)
                        if len(faces) == 1:
                            emb = faces[0].embedding / np.linalg.norm(faces[0].embedding)
                            save_student(new_id.strip(), new_name.strip(), emb)
                            st.success(f"Enrolled {new_name.strip()} ({new_id.strip()}). Raw photo discarded.")
                            st.rerun(scope="fragment")
                        elif len(faces) == 0:
                            st.error("No face detected. Ensure even lighting and a clear frontal view.")
                        else:
                            st.error("Multiple faces detected. Ensure only one student is in frame.")

    with r_right:
        with st.container(border=True):
            h_col1, h_col2 = st.columns([1.4, 1], vertical_alignment="center")
            with h_col1:
                st.markdown('<p class="sec-title">Enrolled Student Directory</p>', unsafe_allow_html=True)
            with h_col2:
                if st.button("Load Sample Roster (5)", icon=":material/group_add:", width="stretch"):
                    added = seed_sample_roster()
                    if added > 0:
                        st.toast(f"Loaded {added} sample student embeddings.")
                        st.rerun(scope="fragment")
                    else:
                        st.toast("Sample roster is already loaded.")

            roster = load_all_students()
            if not roster:
                st.markdown(render_empty_roster_html(), unsafe_allow_html=True)
                if st.button("Load Sample Roster (5 Students)", icon=":material/group_add:", type="primary", width="stretch"):
                    seed_sample_roster()
                    st.rerun(scope="fragment")
            else:
                roster_df = pd.DataFrame([
                    {
                        "Student ID": r["student_id"],
                        "Full Name": r["name"],
                        "Vector Status": "Verified (512-D L2)",
                        "Norm": round(float(np.linalg.norm(r["embedding"])), 4),
                        "Enrolled At": r["created_at"],
                    }
                    for r in roster
                ])
                st.dataframe(
                    roster_df,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Norm": st.column_config.NumberColumn("L2 Norm", format="%.4f"),
                    },
                )

                st.divider()
                st.markdown('<p class="sec-caption" style="margin-bottom:8px;">Inspect Embedding Fingerprint or Remove Record</p>', unsafe_allow_html=True)
                m1, m2, m3 = st.columns([2.1, 1, 1], vertical_alignment="center")
                options = [f"{r['student_id']} — {r['name']}" for r in roster]
                with m1:
                    selected_label = st.selectbox("Target Student", options=options, label_visibility="collapsed")
                target_id = selected_label.split(" — ")[0]
                target_obj = next(r for r in roster if r["student_id"] == target_id)

                with m2:
                    with st.popover("Inspect", icon=":material/fingerprint:", width="stretch"):
                        st.markdown(f"**{target_obj['name']}** (`{target_obj['student_id']}`)")
                        st.caption("Raw Image Stored: None (0 Bytes)")
                        st.caption(f"Dimensions: {len(target_obj['embedding'])} float32 values")
                        st.caption(f"L2 Norm: {float(np.linalg.norm(target_obj['embedding'])):.6f}")
                        preview_vals = ", ".join(f"{v:+.4f}" for v in target_obj["embedding"][:8])
                        st.code(f"[{preview_vals}, ...]", language="text")

                with m3:
                    if st.button("Remove", icon=":material/delete:", width="stretch"):
                        delete_student(target_id)
                        st.toast(f"Removed {target_id} from local database.")
                        st.rerun(scope="fragment")


# --- Fragment 3: Analytics & Executive Reports ---
@st.fragment
def render_analytics_tab():
    sessions = get_session_list()

    # Top Action Bar: Session Filter + Refresh + Export Report (CSV / PDF)
    bar_filter, bar_refresh, bar_csv, bar_pdf = st.columns([2.1, 0.75, 1.05, 1.05], vertical_alignment="bottom")

    with bar_filter:
        selected_session = st.selectbox(
            "Session Filter",
            options=["ALL"] + sessions,
            format_func=lambda x: "All Archived Sessions" if x == "ALL" else x,
        )

    with bar_refresh:
        if st.button("Refresh", icon=":material/refresh:", width="stretch"):
            st.rerun(scope="fragment")

    df_att, df_eng, df_sug = get_session_data(selected_session)
    agent = TeachingAdvisorAgent()
    safe_tag = str(selected_session).replace(" ", "_")

    # Pre-build clean exports for instant top-bar downloads
    csv_export_bytes = (
        df_eng.rename(
            columns={
                "gaze_score": "Visual Gaze",
                "movement_score": "Posture & Motion",
                "audio_score": "Vocal Audio",
                "total_engagement": "Overall Engagement",
            }
        )
        .to_csv(index=False)
        .encode("utf-8")
        if not df_eng.empty
        else b"session_id,timestamp,Visual Gaze,Posture & Motion,Vocal Audio,Overall Engagement\n"
    )
    md_report, pdf_bytes = agent.generate_executive_report(selected_session, df_att, df_eng, df_sug)

    with bar_csv:
        st.download_button(
            "Export CSV",
            data=csv_export_bytes,
            file_name=f"AttendAI_Telemetry_{safe_tag}.csv",
            mime="text/csv",
            icon=":material/table_view:",
            width="stretch",
            disabled=df_eng.empty,
        )

    with bar_pdf:
        st.download_button(
            "Export PDF",
            data=pdf_bytes,
            file_name=f"AttendAI_Executive_Report_{safe_tag}.pdf",
            mime="application/pdf",
            icon=":material/picture_as_pdf:",
            type="primary",
            width="stretch",
            disabled=df_eng.empty and df_att.empty,
        )

    if df_eng.empty and df_att.empty:
        st.markdown(
            f'<div class="empty-card">'
            f'<div class="empty-card-icon">{SVG_ICONS["chart"]}</div>'
            f'<h4>No Archived Session Telemetry Found</h4>'
            f'<p>Run the Interactive Demo Simulator or seed a realistic lecture dataset below to inspect multimodal breakdowns and export executive reports.</p>'
            f'</div>',
            unsafe_allow_html=True,
        )
        c_seed1, c_seed2, c_seed3 = st.columns([1.2, 1.4, 1.2])
        with c_seed2:
            if st.button("Seed Sample Lecture Dataset", icon=":material/database:", type="primary", width="stretch"):
                seed_demo_sessions()
                seed_sample_roster()
                st.toast("Sample lecture telemetry and student roster seeded.")
                st.rerun(scope="fragment")
        return

    # Charts Row: Clean-labeled Multimodal Bar + Centered-KPI Modality Donut
    ch_left, ch_right = st.columns([1.55, 1], gap="medium")

    with ch_left:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Multimodal Engagement Breakdown</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-caption">Recent 20 telemetry windows across visual, postural, and vocal channels.</p>', unsafe_allow_html=True)
            if not df_eng.empty:
                df_plot = df_eng.tail(20).rename(
                    columns={
                        "gaze_score": "Visual Gaze",
                        "movement_score": "Posture & Motion",
                        "audio_score": "Vocal Audio",
                    }
                )
                fig_bar = go.Figure()
                bar_specs = [
                    ("Visual Gaze", "#3B82F6"),
                    ("Posture & Motion", "#38BDF8"),
                    ("Vocal Audio", "#10B981"),
                ]
                for series_name, color in bar_specs:
                    fig_bar.add_trace(
                        go.Bar(
                            x=df_plot["timestamp"],
                            y=df_plot[series_name],
                            name=series_name,
                            marker_color=color,
                            hovertemplate=f"<b>{series_name}</b>: %{{y:.1f}}%<extra></extra>",
                        )
                    )
                fig_bar.update_layout(
                    barmode="group",
                    height=310,
                    margin=dict(l=8, r=8, t=12, b=8),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#94A3B8", family="Inter", size=12),
                    hovermode="x unified",
                    hoverlabel=PLOTLY_HOVER,
                    yaxis=dict(range=[0, 105], title="Score (%)", gridcolor="rgba(148, 163, 184, 0.1)", zeroline=False),
                    xaxis=dict(title="", gridcolor="rgba(148, 163, 184, 0.05)"),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                )
                st.plotly_chart(fig_bar, width="stretch", config=PLOTLY_CONFIG)

    with ch_right:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Mean Modality Balance</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-caption">Composite score centered against weighted modality averages.</p>', unsafe_allow_html=True)
            if not df_eng.empty:
                avg_gaze = round(float(df_eng["gaze_score"].mean()), 1)
                avg_move = round(float(df_eng["movement_score"].mean()), 1)
                avg_audio = round(float(df_eng["audio_score"].mean()), 1)
                composite_avg = round(float(df_eng["total_engagement"].mean()), 1)

                fig_donut = go.Figure(
                    data=[
                        go.Pie(
                            labels=["Visual Gaze", "Posture & Motion", "Vocal Audio"],
                            values=[avg_gaze, avg_move, avg_audio],
                            hole=0.66,
                            textinfo="percent",
                            textposition="outside",
                            textfont=dict(color="#E2E8F0", size=11, family="Inter"),
                            marker=dict(
                                colors=["#3B82F6", "#38BDF8", "#10B981"],
                                line=dict(color="#0B1120", width=2),
                            ),
                            hovertemplate="<b>%{label}</b><br>Mean Score: %{value:.1f}%<extra></extra>",
                        )
                    ]
                )
                fig_donut.update_layout(
                    height=310,
                    margin=dict(l=16, r=16, t=24, b=36),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#94A3B8", family="Inter", size=12),
                    hoverlabel=PLOTLY_HOVER,
                    showlegend=True,
                    legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.08),
                    annotations=[
                        dict(
                            text=f"<b>{composite_avg:.1f}%</b><br><span style='font-size:11px;color:#94A3B8;'>Composite</span>",
                            x=0.5,
                            y=0.5,
                            font=dict(size=22, color="#F8FAFC", family="Inter"),
                            showarrow=False,
                        )
                    ],
                )
                st.plotly_chart(fig_donut, width="stretch", config=PLOTLY_CONFIG)

    # Executive Summary Preview & Markdown Download
    with st.container(border=True):
        ex_l, ex_r = st.columns([2.2, 1], vertical_alignment="center")
        with ex_l:
            st.markdown('<p class="sec-title">Executive Session Brief</p>', unsafe_allow_html=True)
            st.markdown('<p class="sec-caption" style="margin-bottom:0;">Synthesizes verified attendance, engagement peaks/dips, and pedagogical interventions.</p>', unsafe_allow_html=True)
        with ex_r:
            st.download_button(
                "Download Markdown (.md)",
                data=md_report.encode("utf-8"),
                file_name=f"AttendAI_Executive_Report_{safe_tag}.md",
                mime="text/markdown",
                icon=":material/description:",
                width="stretch",
            )
        with st.expander("Preview Executive Report", expanded=False):
            st.markdown(md_report)

    # Archived Tables Row
    t1, t2 = st.columns(2, gap="medium")
    with t1:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Sustained-Presence Attendance Logs</p>', unsafe_allow_html=True)
            if not df_att.empty:
                att_clean = df_att[["session_id", "student_id", "name", "presence_ratio", "status"]].rename(
                    columns={
                        "session_id": "Session",
                        "student_id": "ID",
                        "name": "Student",
                        "presence_ratio": "Presence %",
                        "status": "Status",
                    }
                )
                st.dataframe(
                    att_clean,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Presence %": st.column_config.ProgressColumn("Presence %", min_value=0, max_value=100, format="%.1f%%"),
                    },
                )
            else:
                st.caption("No attendance records logged for this filter.")

    with t2:
        with st.container(border=True):
            st.markdown('<p class="sec-title">AI Coach Intervention Log</p>', unsafe_allow_html=True)
            if not df_sug.empty:
                sug_clean = df_sug[["timestamp", "engagement_level", "suggestion"]].rename(
                    columns={
                        "timestamp": "Time",
                        "engagement_level": "Engagement %",
                        "suggestion": "Recommendation",
                    }
                )
                st.dataframe(sug_clean, width="stretch", hide_index=True)
            else:
                st.caption("No AI coaching interventions logged for this filter.")


# --- Main Workspace Tabs (Material Vector Icons, Zero Emojis) ---
tab_live, tab_roster, tab_analytics = st.tabs([
    ":material/sensors: Live Command Center",
    ":material/group: Roster & Enrollment Manager",
    ":material/analytics: Analytics & Executive Reports",
])

with tab_live:
    render_live_command_center()

with tab_roster:
    render_roster_manager()

with tab_analytics:
    render_analytics_tab()