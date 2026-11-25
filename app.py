import cv2
import time
import tempfile
import importlib.util
import numpy as np
import pandas as pd
import plotly.express as px
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
)
from modules.attendance import SustainedAttendanceTracker
from modules.engagement import MultimodalEngagementAnalyzer, AUDIO_AVAILABLE
from modules.agent import TeachingAdvisorAgent, check_ollama_status

# --- Page Configuration ---
st.set_page_config(
    page_title="AttendAI • Multimodal Classroom Intelligence",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()


# --- Cached Resource Loaders (Fast Cloud Boot) ---
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


# --- Session State Defaults ---
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
    "sim_gaze": 86,
    "sim_move": 84,
    "sim_audio": 72,
    "active_preset": "Active Q&A Discussion",
    "drop_alert": None,
    "exec_report_md": None,
    "exec_report_html": None,
    "exec_report_session": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# --- Cohesive Enterprise Glassmorphic CSS ---
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .stApp {
        background: radial-gradient(circle at 12% 10%, rgba(99, 102, 241, 0.16) 0%, transparent 38%),
                    radial-gradient(circle at 88% 15%, rgba(56, 189, 248, 0.12) 0%, transparent 40%),
                    linear-gradient(160deg, #090E1A 0%, #0F172A 55%, #0B1120 100%);
        color: #F8FAFC;
    }

    section[data-testid="stSidebar"] {
        background: rgba(15, 23, 42, 0.86);
        backdrop-filter: blur(18px);
        -webkit-backdrop-filter: blur(18px);
        border-right: 1px solid rgba(148, 163, 184, 0.16);
    }

    /* Glass Header Banner */
    .attend-header {
        background: rgba(255, 255, 255, 0.045);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border: 1px solid rgba(255, 255, 255, 0.11);
        border-radius: 16px;
        padding: 20px 26px;
        margin-bottom: 18px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
    }
    .brand-title {
        font-size: 1.55rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        color: #F8FAFC;
        margin: 0;
    }
    .brand-accent {
        background: linear-gradient(90deg, #818CF8, #38BDF8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .brand-sub {
        font-size: 0.88rem;
        color: #94A3B8;
        margin: 4px 0 0 0;
    }

    /* Status Badges */
    .pill-live {
        background: rgba(16, 185, 129, 0.16);
        border: 1px solid rgba(16, 185, 129, 0.45);
        color: #34D399;
        padding: 6px 14px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.06em;
    }
    .pill-sim {
        background: rgba(56, 189, 248, 0.15);
        border: 1px solid rgba(56, 189, 248, 0.45);
        color: #7DD3FC;
        padding: 6px 14px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.06em;
    }
    .pill-idle {
        background: rgba(148, 163, 184, 0.12);
        border: 1px solid rgba(148, 163, 184, 0.28);
        color: #CBD5E1;
        padding: 6px 14px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.05em;
    }

    /* Glass KPI Cards */
    .glass-kpi {
        background: rgba(255, 255, 255, 0.04);
        backdrop-filter: blur(14px);
        -webkit-backdrop-filter: blur(14px);
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 14px;
        padding: 16px 18px;
        transition: border-color 0.2s ease;
    }
    .glass-kpi:hover {
        border-color: rgba(129, 140, 248, 0.45);
    }
    .kpi-label {
        font-size: 0.76rem;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        color: #94A3B8;
        font-weight: 600;
    }
    .kpi-value {
        font-size: 1.95rem;
        font-weight: 800;
        color: #F8FAFC;
        margin: 6px 0 2px 0;
        line-height: 1.1;
    }
    .kpi-tag {
        font-size: 0.75rem;
        font-weight: 600;
    }

    /* Glass Panels & Coach Feed */
    .glass-panel {
        background: rgba(255, 255, 255, 0.035);
        backdrop-filter: blur(14px);
        border: 1px solid rgba(255, 255, 255, 0.10);
        border-radius: 14px;
        padding: 18px;
        margin-bottom: 14px;
    }
    .coach-entry {
        background: rgba(99, 102, 241, 0.08);
        border-left: 3px solid #818CF8;
        border-top: 1px solid rgba(255, 255, 255, 0.08);
        border-right: 1px solid rgba(255, 255, 255, 0.08);
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 14px 16px;
        margin-bottom: 10px;
        font-size: 0.9rem;
        line-height: 1.55;
        color: #E2E8F0;
    }
    .alert-banner {
        background: rgba(239, 68, 68, 0.14);
        border: 1px solid rgba(239, 68, 68, 0.45);
        border-radius: 12px;
        padding: 12px 16px;
        color: #FCA5A5;
        font-size: 0.88rem;
        font-weight: 600;
        margin-bottom: 14px;
    }
    .audit-card {
        background: rgba(16, 185, 129, 0.07);
        border: 1px solid rgba(16, 185, 129, 0.25);
        border-radius: 12px;
        padding: 13px 14px;
        font-size: 0.80rem;
        line-height: 1.6;
        color: #CBD5E1;
    }
    .audit-dot-ok { color: #34D399; font-weight: 700; }
    .audit-dot-warn { color: #FBBF24; font-weight: 700; }

    /* Clean Tab Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: rgba(255, 255, 255, 0.03);
        padding: 6px;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.08);
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 8px 18px;
        color: #94A3B8;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(99, 102, 241, 0.22) !important;
        color: #F8FAFC !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# --- Helper Functions ---
def get_score_color(val: float) -> tuple[str, str]:
    if val >= 75.0:
        return "#34D399", "Optimal"
    if val >= 55.0:
        return "#FBBF24", "Moderate"
    return "#F87171", "Attention Low"


def check_engagement_drop(history: list, current_score: float):
    """Detects sharp >15% drops from recent peak or critical <55% engagement."""
    if len(history) >= 2:
        recent_peak = max(item["Overall"] for item in history[-5:])
        drop = round(recent_peak - current_score, 1)
        if drop >= 15.0:
            return f"Sharp Engagement Drop Detected: -{drop}% from recent peak ({recent_peak}% → {current_score}%). Consider an interactive check-in."
    if current_score > 0 and current_score < 55.0:
        return f"Low Classroom Attention Alert: Engagement is at {current_score}%. Review AI Teaching Coach guidance."
    return None


def apply_simulator_preset(name: str, gaze: int, move: int, audio: int):
    st.session_state.active_preset = name
    st.session_state.sim_gaze = gaze
    st.session_state.sim_move = move
    st.session_state.sim_audio = audio


def push_simulator_step(gaze: float, move: float, audio: float, trigger_ai: bool = False):
    total = round(0.50 * gaze + 0.25 * move + 0.25 * audio, 1)
    inactivity = 19.5 if move < 52 else 1.8
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
        "Gaze": metrics["gaze_score"],
        "Posture": metrics["movement_score"],
        "Audio": metrics["audio_score"],
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
        tip = agent.generate_suggestion(
            st.session_state.session_id,
            metrics,
            present_count=max(1, len(roster)),
            total_students=max(1, len(roster)),
        )
        st.session_state.suggestion_feed.insert(0, (datetime.now().strftime("%H:%M:%S"), tip))


# --- Sidebar: Session Controls & Edge Privacy Audit ---
diag = get_system_diagnostics()
enrolled_roster = load_all_students()

with st.sidebar:
    st.markdown("### 🛡️ AttendAI")
    st.caption("Privacy-First Multimodal Classroom Engine")
    st.divider()

    st.markdown("**Session Mode**")
    input_mode = st.radio(
        "Input Source",
        ["Interactive Demo Simulator", "Live Webcam", "Recorded Video (.mp4)"],
        label_visibility="collapsed",
    )

    uploaded_video = None
    if input_mode == "Recorded Video (.mp4)":
        uploaded_video = st.file_uploader("Upload Classroom Video", type=["mp4", "avi", "mov"])

    presence_req = st.slider("Sustained Presence Threshold (%)", 30, 95, 60, 5)
    ai_interval = st.slider("Auto Coach Interval (sec)", 10, 60, 20, 5)

    if input_mode != "Interactive Demo Simulator":
        b1, b2 = st.columns(2)
        with b1:
            if st.button("▶ Start", width="stretch", type="primary"):
                st.session_state.running = True
                st.session_state.session_id = datetime.now().strftime("SESSION_%Y%m%d_%H%M%S")
                st.session_state.engagement_history = []
                st.session_state.suggestion_feed = []
                st.session_state.drop_alert = None
                st.rerun()
        with b2:
            if st.button("⏹ Stop", width="stretch"):
                st.session_state.running = False
                st.rerun()
    else:
        if st.button("🔄 New Simulator Session", width="stretch"):
            st.session_state.session_id = datetime.now().strftime("SIM_%Y%m%d_%H%M%S")
            st.session_state.engagement_history = []
            st.session_state.suggestion_feed = []
            st.session_state.drop_alert = None
            st.rerun()

    st.divider()

    # Facility 5: Edge Privacy & System Health Audit Panel
    st.markdown("**🔒 Edge Privacy & System Health**")
    ollama_dot = "audit-dot-ok" if diag["ollama_ok"] else "audit-dot-warn"
    audio_dot = "audit-dot-ok" if diag["audio_ok"] else "audit-dot-warn"
    audio_txt = "WebRTC VAD Active" if diag["audio_ok"] else "Visual-Only (Cloud Safe)"
    vision_dot = "audit-dot-ok" if diag["insightface_ok"] else "audit-dot-warn"

    st.markdown(
        f"""
        <div class="audit-card">
            <div><span class="audit-dot-ok">●</span> <strong>100% Edge Processing</strong></div>
            <div><span class="audit-dot-ok">●</span> <strong>0 Raw Images Stored</strong> (512-D Vectors)</div>
            <div><span class="audit-dot-ok">●</span> <strong>0 Cloud Data Leaks</strong></div>
            <hr style="border-color: rgba(255,255,255,0.1); margin: 8px 0;">
            <div><span class="{vision_dot}">●</span> Face ID: InsightFace <code>buffalo_sc</code></div>
            <div><span class="audit-dot-ok">●</span> Gaze/Pose: OpenCV Haar Cascades</div>
            <div><span class="{audio_dot}">●</span> Audio: {audio_txt}</div>
            <div><span class="{ollama_dot}">●</span> Coach: {diag["ollama_label"]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"Active Session: `{st.session_state.session_id}` • Roster: {len(enrolled_roster)}")


# --- Top Brand Header ---
if st.session_state.running:
    pill_html = '<span class="pill-live">● LIVE TELEMETRY ACTIVE</span>'
elif input_mode == "Interactive Demo Simulator":
    pill_html = '<span class="pill-sim">● INTERACTIVE SIMULATOR READY</span>'
else:
    pill_html = '<span class="pill-idle">○ SYSTEM STANDBY</span>'

st.markdown(
    f"""
    <div class="attend-header">
        <div>
            <h1 class="brand-title">Attend<span class="brand-accent">AI</span> &nbsp;Command Suite</h1>
            <p class="brand-sub">Sustained-Presence Attendance • Multimodal Engagement Fusion • Assistive Pedagogical AI</p>
        </div>
        <div>{pill_html}</div>
    </div>
    """,
    unsafe_allow_html=True,
)


# --- Main Facility Tabs ---
tab_live, tab_roster, tab_analytics = st.tabs([
    "📡 Live Command Center",
    "👤 Roster & Enrollment Manager",
    "📊 Analytics & Executive Reports",
])


# ==============================================================================
# TAB 1: LIVE COMMAND CENTER + INTERACTIVE DEMO SIMULATOR
# ==============================================================================
with tab_live:
    # Sharp Engagement Drop Alert Slot
    alert_slot = st.empty()
    if st.session_state.drop_alert:
        alert_slot.markdown(f'<div class="alert-banner">⚠️ {st.session_state.drop_alert}</div>', unsafe_allow_html=True)

    # Glassmorphic KPI Row
    k1, k2, k3, k4 = st.columns(4)
    kpi_overall = k1.empty()
    kpi_gaze = k2.empty()
    kpi_move = k3.empty()
    kpi_audio = k4.empty()

    def render_kpis(m: dict):
        items = [
            (kpi_overall, "Overall Engagement", m["total_engagement"]),
            (kpi_gaze, "Visual Gaze Focus", m["gaze_score"]),
            (kpi_move, "Posture & Motion", m["movement_score"]),
            (kpi_audio, "Vocal Interaction", m["audio_score"]),
        ]
        for slot, label, val in items:
            col, tag = get_score_color(val)
            if val == 0.0:
                col, tag = "#94A3B8", "Awaiting Stream"
            slot.markdown(
                f"""
                <div class="glass-kpi">
                    <div class="kpi-label">{label}</div>
                    <div class="kpi-value">{val:.1f}%</div>
                    <div class="kpi-tag" style="color:{col};">● {tag}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    render_kpis(st.session_state.latest_metrics)
    st.write("")

    col_main, col_side = st.columns([1.3, 1])

    with col_main:
        if input_mode == "Interactive Demo Simulator":
            st.markdown("#### 🎛️ Interactive Classroom Scenario Simulator")
            st.caption("Evaluate AttendAI directly on cloud without a webcam—pick a classroom preset or fine-tune signals below.")

            p1, p2, p3 = st.columns(3)
            with p1:
                if st.button("💬 Active Q&A Discussion", width="stretch"):
                    apply_simulator_preset("Active Q&A Discussion", 88, 84, 78)
                    push_simulator_step(88, 84, 78, trigger_ai=True)
                    st.rerun()
            with p2:
                if st.button("📉 Mid-Lecture Attention Dip", width="stretch"):
                    apply_simulator_preset("Mid-Lecture Attention Dip", 44, 48, 12)
                    push_simulator_step(44, 48, 12, trigger_ai=True)
                    st.rerun()
            with p3:
                if st.button("📝 Silent Note-Taking", width="stretch"):
                    apply_simulator_preset("Silent Note-Taking", 74, 79, 18)
                    push_simulator_step(74, 79, 18, trigger_ai=True)
                    st.rerun()

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
                if st.button("➕ Log Telemetry Window", type="primary", width="stretch"):
                    push_simulator_step(g_val, m_val, a_val, trigger_ai=False)
                    st.rerun()
            with act2:
                if st.button("⚡ Simulate 5-Window Class Arc", width="stretch"):
                    arc = [(85, 83, 62), (76, 78, 35), (48, 51, 14), (66, 70, 48), (88, 86, 76)]
                    for idx, (ag, am, aa) in enumerate(arc):
                        push_simulator_step(ag, am, aa, trigger_ai=(idx in [2, 4]))
                    st.rerun()

            video_slot = st.empty()
        else:
            st.markdown("#### 👁️ Multimodal Vision & Verification Feed")
            video_slot = st.empty()
            if not st.session_state.running:
                video_slot.info("Select **▶ Start** in the sidebar to begin real-time face verification and multimodal tracking.")

        st.markdown("#### 📈 Real-Time Engagement Telemetry")
        chart_slot = st.empty()

        def render_telemetry_chart():
            if st.session_state.engagement_history:
                df_h = pd.DataFrame(st.session_state.engagement_history)
                fig = go.Figure()
                traces = [
                    ("Overall", "#818CF8", 3),
                    ("Gaze", "#38BDF8", 2),
                    ("Audio", "#34D399", 2),
                ]
                for col_name, color, width in traces:
                    if col_name in df_h.columns:
                        fig.add_trace(
                            go.Scatter(
                                x=df_h["Time"],
                                y=df_h[col_name],
                                mode="lines+markers",
                                name=col_name,
                                line=dict(color=color, width=width, shape="spline"),
                                marker=dict(size=6),
                            )
                        )
                fig.add_hline(
                    y=60,
                    line_dash="dash",
                    line_color="rgba(251, 191, 36, 0.55)",
                    annotation_text="Attention Threshold (60%)",
                    annotation_position="bottom right",
                )
                fig.update_layout(
                    height=275,
                    margin=dict(l=8, r=8, t=12, b=8),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(255,255,255,0.02)",
                    font=dict(color="#CBD5E1", family="Inter"),
                    yaxis=dict(range=[0, 105], title="Score (%)", gridcolor="rgba(148,163,184,0.12)"),
                    xaxis=dict(title="", gridcolor="rgba(148,163,184,0.08)"),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                )
                chart_slot.plotly_chart(fig, width="stretch", key=f"live_chart_{len(df_h)}")
            else:
                chart_slot.markdown(
                    '<div class="glass-panel" style="text-align:center; color:#94A3B8; padding:36px;">'
                    'Click a classroom preset or <strong>⚡ Simulate 5-Window Class Arc</strong> above to render real-time spline telemetry.'
                    '</div>',
                    unsafe_allow_html=True,
                )

        render_telemetry_chart()

    with col_side:
        c_head, c_btn = st.columns([1.45, 1])
        with c_head:
            st.markdown("#### 🤖 AI Teaching Coach")
        with c_btn:
            ask_coach = st.button("✨ Ask Coach Now", width="stretch", type="primary")

        coach_slot = st.empty()

        if ask_coach:
            with st.spinner("Synthesizing pedagogical guidance..."):
                agent = TeachingAdvisorAgent()
                present_cnt = sum(1 for r in st.session_state.attendance_summary if r["Status"] == "Present")
                cur_m = st.session_state.latest_metrics
                if cur_m["total_engagement"] == 0.0 and input_mode == "Interactive Demo Simulator":
                    push_simulator_step(st.session_state.sim_gaze, st.session_state.sim_move, st.session_state.sim_audio, trigger_ai=True)
                else:
                    tip = agent.generate_suggestion(
                        st.session_state.session_id,
                        cur_m,
                        present_cnt or max(1, len(enrolled_roster)),
                        max(1, len(enrolled_roster)),
                    )
                    st.session_state.suggestion_feed.insert(0, (datetime.now().strftime("%H:%M:%S"), tip))
            st.rerun()

        def render_coach_feed():
            if not st.session_state.suggestion_feed:
                coach_slot.markdown(
                    '<div class="coach-entry"><strong>Standby:</strong> Trigger a classroom preset or click <em>✨ Ask Coach Now</em> to generate real-time pedagogical interventions.</div>',
                    unsafe_allow_html=True,
                )
            else:
                cards = ""
                for ts, msg in st.session_state.suggestion_feed[:4]:
                    formatted = msg.replace("\n", "<br>")
                    cards += f'<div class="coach-entry"><div style="font-size:0.75rem; color:#94A3B8; margin-bottom:5px;">⏱ {ts} • AttendAI Advisor</div>{formatted}</div>'
                coach_slot.markdown(cards, unsafe_allow_html=True)

        render_coach_feed()

        st.markdown("#### 📋 Sustained-Presence Attendance")
        att_slot = st.empty()
        if st.session_state.attendance_summary:
            att_slot.dataframe(pd.DataFrame(st.session_state.attendance_summary), width="stretch", hide_index=True)
        elif enrolled_roster:
            preview_df = pd.DataFrame([
                {"Student ID": r["student_id"], "Name": r["name"], "Presence %": 0.0, "Status": "Waiting"}
                for r in enrolled_roster
            ])
            att_slot.dataframe(preview_df, width="stretch", hide_index=True)
        else:
            att_slot.info("Enroll students in the **Roster & Enrollment Manager** tab to track live sustained attendance.")

    # --- Live Video / Webcam Loop ---
    if st.session_state.running and input_mode != "Interactive Demo Simulator":
        if input_mode == "Recorded Video (.mp4)" and uploaded_video is not None:
            tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            tfile.write(uploaded_video.read())
            cap = cv2.VideoCapture(tfile.name)
        else:
            cap = cv2.VideoCapture(0)

        if not cap.isOpened():
            st.error("Unable to open video source. On cloud servers without a webcam, switch to **Interactive Demo Simulator** or upload an `.mp4` clip.")
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
                    st.session_state.latest_metrics = metrics

                    rgb_frame = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
                    video_slot.image(rgb_frame, channels="RGB", width="stretch")
                    render_kpis(metrics)

                    now = time.time()
                    if now - last_log_time >= 3.0:
                        analyzer.save_window_metrics(st.session_state.session_id, metrics)
                        st.session_state.engagement_history.append({
                            "Time": datetime.now().strftime("%H:%M:%S"),
                            "Overall": metrics["total_engagement"],
                            "Gaze": metrics["gaze_score"],
                            "Posture": metrics["movement_score"],
                            "Audio": metrics["audio_score"],
                        })
                        alert_msg = check_engagement_drop(st.session_state.engagement_history, metrics["total_engagement"])
                        st.session_state.drop_alert = alert_msg
                        if alert_msg:
                            alert_slot.markdown(f'<div class="alert-banner">⚠️ {alert_msg}</div>', unsafe_allow_html=True)
                        else:
                            alert_slot.empty()
                        render_telemetry_chart()
                        last_log_time = now

                    summary = tracker.get_summary()
                    st.session_state.attendance_summary = summary
                    if summary:
                        att_slot.dataframe(pd.DataFrame(summary), width="stretch", hide_index=True)

                    if now - last_ai_time >= ai_interval:
                        present_cnt = sum(1 for r in summary if r["Status"] == "Present")
                        tip = agent.generate_suggestion(
                            st.session_state.session_id,
                            metrics,
                            present_cnt,
                            max(1, len(summary)),
                        )
                        st.session_state.suggestion_feed.insert(0, (datetime.now().strftime("%H:%M:%S"), tip))
                        render_coach_feed()
                        last_ai_time = now

                    time.sleep(0.05)
            finally:
                analyzer.stop_audio()
                cap.release()
                st.session_state.attendance_summary = tracker.finalize_session(st.session_state.session_id)
                st.toast(f"Session {st.session_state.session_id} finalized and archived locally.", icon="✅")


# ==============================================================================
# TAB 2: PRIVACY-PRESERVING ROSTER & ENROLLMENT MANAGER
# ==============================================================================
with tab_roster:
    st.markdown("#### 👤 Student Enrollment & Vector Roster")
    st.caption("Privacy Guarantee: Raw photos are processed transiently in RAM to compute a normalized 512-D mathematical vector, then permanently discarded.")

    r_col1, r_col2 = st.columns([1, 1.25])

    with r_col1:
        st.markdown('<div class="glass-panel">', unsafe_allow_html=True)
        st.markdown("**Enroll New Student**")
        new_id = st.text_input("Student ID", placeholder="e.g., S106")
        new_name = st.text_input("Full Name", placeholder="e.g., Priya Deshmukh")
        enroll_method = st.radio("Capture Method", ["Upload Portrait Image", "Live Camera Snapshot"], horizontal=True)

        img_source = None
        if enroll_method == "Upload Portrait Image":
            img_source = st.file_uploader("Select Clear Front-Facing Photo", type=["jpg", "jpeg", "png"])
        else:
            img_source = st.camera_input("Capture Student Snapshot")

        if st.button("💾 Extract & Save 512-D Embedding", type="primary", width="stretch"):
            if not new_id.strip() or not new_name.strip() or img_source is None:
                st.error("Provide Student ID, Full Name, and a facial photo.")
            else:
                file_bytes = np.asarray(bytearray(img_source.read()), dtype=np.uint8)
                img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
                if img is None:
                    st.error("Could not decode image. Please upload a valid JPG or PNG.")
                else:
                    face_app = get_face_analyzer()
                    faces = face_app.get(img)
                    if len(faces) == 1:
                        emb = faces[0].embedding / np.linalg.norm(faces[0].embedding)
                        save_student(new_id.strip(), new_name.strip(), emb)
                        st.success(f"Enrolled **{new_name.strip()}** (`{new_id.strip()}`). 512-D vector saved; raw image discarded.")
                        st.rerun()
                    elif len(faces) == 0:
                        st.error("No face detected. Ensure balanced lighting and a clear frontal view.")
                    else:
                        st.error("Multiple faces detected. Ensure only the enrolling student is visible.")
        st.markdown("</div>", unsafe_allow_html=True)

    with r_col2:
        st.markdown("**Enrolled Student Directory**")
        current_roster = load_all_students()
        if current_roster:
            roster_df = pd.DataFrame([
                {
                    "Student ID": r["student_id"],
                    "Full Name": r["name"],
                    "Biometric Storage": "512-D L2-Normalized Vector",
                    "Enrolled At": r["created_at"],
                }
                for r in current_roster
            ])
            st.dataframe(roster_df, width="stretch", hide_index=True)

            st.markdown("---")
            st.markdown("**Manage Roster Records**")
            del_col1, del_col2 = st.columns([2, 1])
            with del_col1:
                remove_target = st.selectbox(
                    "Select student to remove",
                    options=[f"{r['student_id']} — {r['name']}" for r in current_roster],
                    label_visibility="collapsed",
                )
            with del_col2:
                if st.button("🗑️ Remove Record", width="stretch"):
                    target_id = remove_target.split(" — ")[0]
                    delete_student(target_id)
                    st.toast(f"Removed {target_id} from local database.", icon="🗑️")
                    st.rerun()
        else:
            st.info("No students enrolled yet. Use the form on the left to add your first student embedding.")


# ==============================================================================
# TAB 3: ANALYTICS & AUTOMATED EXECUTIVE REPORT BUILDER
# ==============================================================================
with tab_analytics:
    top_a1, top_a2 = st.columns([1.8, 1])
    with top_a1:
        st.markdown("#### 📊 Multi-Session Analytics & Executive Reports")
    with top_a2:
        if st.button("🌱 Seed Sample Classroom Data", width="stretch"):
            seeded = seed_demo_sessions()
            if seeded:
                st.toast("Sample classroom session seeded!", icon="✅")
                st.rerun()
            else:
                st.info("Historical records already exist in classroom.db.")

    sessions = get_session_list()
    selected_session = st.selectbox(
        "Filter by Session",
        options=["ALL"] + sessions,
        format_func=lambda x: "All Archived Sessions" if x == "ALL" else x,
    )

    df_att, df_eng, df_sug = get_session_data(selected_session)

    if df_eng.empty and df_att.empty:
        st.info("No archived session telemetry found yet. Click **🌱 Seed Sample Classroom Data** above or run the **Interactive Demo Simulator** to populate analytics.")
    else:
        # Multimodal Breakdown + Modality Contribution Charts
        ch1, ch2 = st.columns([1.55, 1])
        with ch1:
            if not df_eng.empty:
                fig_bar = px.bar(
                    df_eng.tail(20),
                    x="timestamp",
                    y=["gaze_score", "movement_score", "audio_score"],
                    barmode="group",
                    title="Multimodal Engagement Breakdown (Gaze • Posture • Audio)",
                    color_discrete_sequence=["#818CF8", "#38BDF8", "#34D399"],
                )
                fig_bar.update_layout(
                    height=320,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(255,255,255,0.02)",
                    font=dict(color="#CBD5E1", family="Inter"),
                    yaxis=dict(range=[0, 105], title="Score (%)", gridcolor="rgba(148,163,184,0.12)"),
                    xaxis=dict(title=""),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title=""),
                )
                st.plotly_chart(fig_bar, width="stretch")

        with ch2:
            if not df_eng.empty:
                avg_vals = [
                    round(float(df_eng["gaze_score"].mean()), 1),
                    round(float(df_eng["movement_score"].mean()), 1),
                    round(float(df_eng["audio_score"].mean()), 1),
                ]
                fig_donut = go.Figure(
                    data=[
                        go.Pie(
                            labels=["Visual Gaze (50% wt)", "Posture/Motion (25% wt)", "Vocal Audio (25% wt)"],
                            values=avg_vals,
                            hole=0.58,
                            marker=dict(colors=["#818CF8", "#38BDF8", "#34D399"]),
                        )
                    ]
                )
                fig_donut.update_layout(
                    title="Mean Modality Balance",
                    height=320,
                    paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#CBD5E1", family="Inter"),
                    legend=dict(orientation="h", y=-0.12),
                )
                st.plotly_chart(fig_donut, width="stretch")

        # Executive Report Builder
        st.markdown("---")
        rep_h1, rep_h2 = st.columns([1.6, 1])
        with rep_h1:
            st.markdown("#### 📝 Automated Executive Session Report")
            st.caption("Synthesizes verified attendance, engagement peaks/dips, and pedagogical interventions into downloadable formats.")
        with rep_h2:
            if st.button("✨ Generate Executive Session Report", type="primary", width="stretch"):
                with st.spinner("Compiling executive report..."):
                    agent = TeachingAdvisorAgent()
                    md_out, html_out = agent.generate_executive_report(selected_session, df_att, df_eng, df_sug)
                    st.session_state.exec_report_md = md_out
                    st.session_state.exec_report_html = html_out
                    st.session_state.exec_report_session = selected_session

        if st.session_state.exec_report_md:
            dl1, dl2, _ = st.columns([1, 1, 1.5])
            safe_name = str(st.session_state.exec_report_session).replace(" ", "_")
            with dl1:
                st.download_button(
                    "⬇ Download Markdown (.md)",
                    st.session_state.exec_report_md.encode("utf-8"),
                    file_name=f"AttendAI_Report_{safe_name}.md",
                    mime="text/markdown",
                    width="stretch",
                )
            with dl2:
                st.download_button(
                    "⬇ Download Formatted HTML (.html)",
                    st.session_state.exec_report_html.encode("utf-8"),
                    file_name=f"AttendAI_Report_{safe_name}.html",
                    mime="text/html",
                    width="stretch",
                )
            with st.expander("Preview Executive Report", expanded=True):
                st.markdown(st.session_state.exec_report_md)

        # Raw Tables & CSV Exports
        st.markdown("---")
        t1, t2 = st.columns(2)
        with t1:
            st.markdown("**Sustained-Presence Attendance Logs**")
            st.dataframe(df_att, width="stretch", hide_index=True)
            if not df_att.empty:
                st.download_button(
                    "⬇ Export Attendance CSV",
                    df_att.to_csv(index=False).encode("utf-8"),
                    "attendai_attendance.csv",
                    "text/csv",
                )

        with t2:
            st.markdown("**AI Teaching Coach History**")
            st.dataframe(df_sug, width="stretch", hide_index=True)
            if not df_eng.empty:
                st.download_button(
                    "⬇ Export Engagement Telemetry CSV",
                    df_eng.to_csv(index=False).encode("utf-8"),
                    "attendai_engagement.csv",
                    "text/csv",
                )