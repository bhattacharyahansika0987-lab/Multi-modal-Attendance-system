# =====================================================================
# AuraClass AI - app.py  (UI/UX upgraded)
# Stack detected: Python + Streamlit + Plotly + OpenCV + SQLite + Ollama
# No new installs needed (plotly is already in requirements.txt).
# Only this file changed. All modules/ files stay exactly as they are.
# Search for "CUSTOMIZE:" to find every easy-to-tweak value.
# =====================================================================
import cv2
import time
import tempfile
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
from insightface.app import FaceAnalysis
from modules.database import init_db, get_connection, load_all_students, save_student
from modules.attendance import SustainedAttendanceTracker
from modules.engagement import MultimodalEngagementAnalyzer
from modules.agent import TeachingAdvisorAgent

st.set_page_config(
    page_title="AuraClass • Multimodal Attendance & Engagement Agent",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

# ---------------------------------------------------------------------
# CUSTOMIZE: themes. Edit any colour here; every component follows.
# ---------------------------------------------------------------------
THEMES = {
    "Pastel Daylight": {
        "bg": "linear-gradient(135deg, #FFF8F6 0%, #F6F0FF 55%, #FFF0F5 100%)",
        "card": "rgba(255,255,255,0.70)",
        "border": "rgba(124,92,191,0.28)",
        "accent": "#7C5CBF",
        "accent2": "#EC4899",
        "text": "#2A2438",
        "sub": "#5E5473",
        "shadow": "rgba(124,92,191,0.18)",
        "sidebar": "rgba(255,255,255,0.62)",
        "chart": ["#8B5CF6", "#EC4899", "#10B981"],
    },
    "Ultramarine & Gold": {
        "bg": "linear-gradient(135deg, #0B1026 0%, #151E3F 55%, #0D132B 100%)",
        "card": "rgba(24,34,68,0.62)",
        "border": "rgba(212,175,55,0.40)",
        "accent": "#F3C64F",
        "accent2": "#6C8CFF",
        "text": "#F8F6F0",
        "sub": "#C5CAE9",
        "shadow": "rgba(243,198,79,0.20)",
        "sidebar": "rgba(15,22,48,0.70)",
        "chart": ["#F3C64F", "#6C8CFF", "#34D399"],
    },
}
ANIM_SPEED = "0.6s"      # CUSTOMIZE: entrance animation duration
STAGGER_MS = 90          # CUSTOMIZE: delay between staggered cards (ms)
HOVER_LIFT_PX = 4        # CUSTOMIZE: how far cards rise on hover
SCROLL_BAR_HEIGHT = 3    # CUSTOMIZE: scroll-progress bar thickness (px)

# --- Session State Initialization ---
defaults = {
    "running": False,
    "session_id": datetime.now().strftime("SESSION_%Y%m%d_%H%M%S"),
    "engagement_history": [],
    "suggestion_feed": [],
    "attendance_summary": [],
    "latest_metrics": {"total_engagement": 0.0, "gaze_score": 0.0, "movement_score": 0.0, "audio_score": 0.0, "inactivity_sec": 0.0},
    "ui_theme": "Pastel Daylight",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# --- Sidebar Theme & Controls ---
with st.sidebar:
    st.markdown("## ✨ AuraClass AI")
    st.caption("Offline Multimodal Classroom Intelligence")
    st.session_state.ui_theme = st.selectbox(
        "🎨 Interface Theme", list(THEMES.keys()),
        index=list(THEMES.keys()).index(st.session_state.ui_theme),
    )

T = THEMES[st.session_state.ui_theme]

# ---------------------------------------------------------------------
# Global CSS (theme tokens first, static styles second)
# ---------------------------------------------------------------------
THEME_VARS = f"""
:root {{
  --bg:{T['bg']}; --card:{T['card']}; --border:{T['border']};
  --accent:{T['accent']}; --accent2:{T['accent2']};
  --text:{T['text']}; --sub:{T['sub']}; --shadow:{T['shadow']}; --sidebar:{T['sidebar']};
  --speed:{ANIM_SPEED}; --lift:-{HOVER_LIFT_PX}px; --bar-h:{SCROLL_BAR_HEIGHT}px;
}}
"""

STATIC_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

html { scroll-behavior: smooth; }
.stApp, .stApp button, .stApp input, .stApp textarea {
  font-family: 'Manrope', system-ui, -apple-system, 'Segoe UI', sans-serif;
}
.stApp { background: var(--bg); background-attachment: fixed; color: var(--text); }
.stApp h1, .stApp h2, .stApp h3, .stApp label, .stApp p,
.stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stMetricValue"],
.stApp [data-testid="stMetricLabel"] { color: var(--text); }
.stApp h2, .stApp h3 { letter-spacing: -0.02em; font-weight: 800; }
.stApp [data-testid="stCaptionContainer"] { color: var(--sub); }
.block-container { padding-top: 2rem; max-width: 1400px; }

/* Keyframes (one orchestrated page-load moment) */
@keyframes rise  { from { opacity:0; transform: translateY(18px); } to { opacity:1; transform:none; } }
@keyframes pulse { 0%,100% { box-shadow:0 0 0 0 rgba(16,185,129,.55);} 50% { box-shadow:0 0 0 10px rgba(16,185,129,0);} }
@keyframes drift { 0%,100% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } }

/* Glass sidebar */
section[data-testid="stSidebar"] {
  background: var(--sidebar) !important;
  backdrop-filter: blur(18px) saturate(1.4);
  -webkit-backdrop-filter: blur(18px) saturate(1.4);
  border-right: 1px solid var(--border);
}

/* Hero banner with cursor-following glow */
.hero-banner {
  position: relative; overflow: hidden;
  background: var(--card); border: 1px solid var(--border); border-radius: 22px;
  padding: 24px 30px; margin-bottom: 20px;
  display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap;
  backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 12px 36px var(--shadow);
  animation: rise var(--speed) cubic-bezier(.2,.8,.2,1) both;
}
.hero-banner::before {
  content:""; position:absolute; inset:0; pointer-events:none; opacity:.9;
  background: radial-gradient(420px circle at var(--mx,80%) var(--my,0%), var(--shadow), transparent 65%);
  transition: background .2s;
}
.hero-banner h2 { margin:0; font-size: clamp(1.25rem, 2.6vw, 1.9rem); }
.hero-banner p  { margin:6px 0 0; color: var(--sub); }

/* KPI cards: glow follows the cursor, lift on hover, press on click */
.kpi-card {
  position: relative; overflow: hidden; text-align: center; cursor: default;
  background: var(--card); border: 1px solid var(--border); border-radius: 18px;
  padding: 18px 14px 16px;
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  box-shadow: 0 6px 18px var(--shadow);
  transition: transform .25s ease, box-shadow .25s ease, border-color .25s ease;
}
.kpi-card::before {
  content:""; position:absolute; inset:0; pointer-events:none; opacity:0; transition: opacity .25s;
  background: radial-gradient(180px circle at var(--mx,50%) var(--my,50%), var(--shadow), transparent 70%);
}
.kpi-card:hover { transform: translateY(var(--lift)); border-color: var(--accent); box-shadow: 0 16px 34px var(--shadow); }
.kpi-card:hover::before { opacity: 1; }
.kpi-card:active { transform: translateY(-1px) scale(.985); }
.kpi-enter { animation: rise var(--speed) cubic-bezier(.2,.8,.2,1) both; }
.kpi-label { font-size:.8rem; letter-spacing:.04em; color: var(--sub); font-weight:600; }
.kpi-val   { font-size: clamp(1.6rem, 3vw, 2.2rem); font-weight:800; color: var(--accent); margin:4px 0 10px; line-height:1.1; }
.kpi-bar   { height:5px; border-radius:99px; background: var(--border); overflow:hidden; }
.kpi-bar > span { display:block; height:100%; border-radius:99px; background: linear-gradient(90deg, var(--accent), var(--accent2)); }

/* AI coach cards */
.coach-card {
  background: var(--card); border: 1px solid var(--border); border-left: 5px solid var(--accent);
  border-radius: 16px; padding: 16px 20px; margin-bottom: 12px;
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  transition: transform .25s ease, box-shadow .25s ease;
  animation: rise var(--speed) cubic-bezier(.2,.8,.2,1) both;
}
.coach-card:hover { transform: translateX(4px); box-shadow: 0 10px 26px var(--shadow); }

/* Status pills */
.live-pill { background:#10B981; color:#fff; padding:7px 16px; border-radius:999px; font-weight:700; font-size:.82rem; animation: pulse 1.8s infinite; }
.idle-pill { background: var(--border); color: var(--text); padding:7px 16px; border-radius:999px; font-weight:700; font-size:.82rem; }

/* Buttons: elevation, glow, click feedback */
.stApp .stButton > button, .stApp .stDownloadButton > button {
  border-radius: 12px; font-weight: 700; border: 1px solid var(--border);
  transition: transform .2s ease, box-shadow .2s ease, filter .2s ease;
}
.stApp .stButton > button:hover, .stApp .stDownloadButton > button:hover {
  transform: translateY(-2px); box-shadow: 0 10px 24px var(--shadow); filter: brightness(1.05);
}
.stApp .stButton > button:active, .stApp .stDownloadButton > button:active { transform: translateY(0) scale(.97); box-shadow: none; }
.stApp .stButton > button[kind="primary"] {
  background: linear-gradient(120deg, var(--accent), var(--accent2), var(--accent));
  background-size: 200% 200%; color: #fff; border: none; animation: drift 6s ease infinite;
}

/* Inputs: focus glow */
.stApp input, .stApp textarea, .stApp [data-baseweb="select"] > div {
  border-radius: 12px !important; transition: box-shadow .2s ease, border-color .2s ease;
}
.stApp input:focus, .stApp textarea:focus, .stApp [data-baseweb="select"] > div:focus-within {
  box-shadow: 0 0 0 3px var(--shadow) !important; border-color: var(--accent) !important;
}

/* Tabs: pill style, animated panel switch */
.stTabs [data-baseweb="tab-list"] { gap: 6px; background: var(--card); border:1px solid var(--border); border-radius: 16px; padding: 6px; overflow-x: auto; }
.stTabs [data-baseweb="tab"] { border-radius: 12px; padding: 8px 18px; font-weight: 700; transition: background .2s ease, transform .2s ease; }
.stTabs [data-baseweb="tab"]:hover { background: var(--shadow); transform: translateY(-1px); }
.stTabs [aria-selected="true"] { background: var(--shadow); color: var(--accent) !important; }
.stTabs [data-baseweb="tab-highlight"] { background: var(--accent); height: 3px; border-radius: 3px; }
.stTabs [data-baseweb="tab-panel"] { animation: rise .45s ease both; }

/* Charts, tables, images */
[data-testid="stPlotlyChart"], [data-testid="stDataFrame"], [data-testid="stImage"] img {
  border-radius: 16px; transition: box-shadow .25s ease;
}
[data-testid="stPlotlyChart"]:hover, [data-testid="stDataFrame"]:hover { box-shadow: 0 12px 30px var(--shadow); }

/* Scroll-progress bar (created by the script below) */
#aura-progress { position: fixed; top: 0; left: 0; height: var(--bar-h); width: 0; z-index: 999999;
  background: linear-gradient(90deg, var(--accent), var(--accent2)); transition: width .1s linear; }

/* Responsive */
@media (max-width: 768px) {
  .block-container { padding: 1rem .8rem; }
  .hero-banner { padding: 18px; border-radius: 18px; }
  .kpi-card { padding: 14px 10px; }
}
/* Accessibility: respect reduced-motion preference */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
}
"""
st.markdown(f"<style>{THEME_VARS}{STATIC_CSS}</style>", unsafe_allow_html=True)

# ---------------------------------------------------------------------
# JS: scroll-progress bar + cursor glow. Runs once per browser tab.
# Streamlit strips <script> from st.markdown, so we use a 0-height iframe
# that reaches into the parent page.
# ---------------------------------------------------------------------
components.html(
    """
<script>
(function () {
  const doc = window.parent.document, win = window.parent;
  if (win.__auraInit) return;
  win.__auraInit = true;

  // Scroll-progress bar
  const bar = doc.createElement('div'); bar.id = 'aura-progress'; doc.body.appendChild(bar);
  const scroller = () => doc.querySelector('[data-testid="stMain"]') || doc.querySelector('section.main') || doc.scrollingElement;
  const update = () => {
    const s = scroller(); if (!s) return;
    const max = s.scrollHeight - s.clientHeight;
    bar.style.width = (max > 0 ? (s.scrollTop / max) * 100 : 0) + '%';
  };
  doc.addEventListener('scroll', update, true);

  // Cursor-following glow (event delegation survives Streamlit re-renders)
  doc.addEventListener('mousemove', (e) => {
    const el = e.target.closest && e.target.closest('.kpi-card, .hero-banner');
    if (!el) return;
    const r = el.getBoundingClientRect();
    el.style.setProperty('--mx', (e.clientX - r.left) + 'px');
    el.style.setProperty('--my', (e.clientY - r.top) + 'px');
  }, { passive: true });
})();
</script>
""",
    height=0,
)

# --- Hero Header ---
status_badge = '<span class="live-pill">● LIVE SESSION ACTIVE</span>' if st.session_state.running else '<span class="idle-pill">○ STANDBY MODE</span>'
st.markdown(
    f"""
    <div class="hero-banner">
        <div>
            <h2>🎓 Multimodal Attendance & Engagement Agent</h2>
            <p>Privacy-Preserving Vision • Audio Voice Activity • Local Agentic Reasoning</p>
        </div>
        <div>{status_badge}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- Sidebar Controls ---
with st.sidebar:
    st.divider()
    st.subheader("🎥 Input & Session Setup")
    input_mode = st.radio(
        "Select Mode",
        ["Live Webcam", "Recorded Video (.mp4)", "Interactive Demo Simulator"],
    )

    uploaded_video = None
    sim_gaze, sim_move, sim_audio = 82.0, 85.0, 45.0

    if input_mode == "Recorded Video (.mp4)":
        uploaded_video = st.file_uploader("Upload Lecture Clip", type=["mp4", "avi", "mov"])
    elif input_mode == "Interactive Demo Simulator":
        st.info("Slide values below to test AI Coach responses live without a camera:")
        sim_gaze = st.slider("Simulated Gaze Focus %", 0, 100, 48)
        sim_move = st.slider("Simulated Posture Activity %", 0, 100, 55)
        sim_audio = st.slider("Simulated Vocal Interaction %", 0, 100, 12)

    presence_req = st.slider("Sustained Presence Threshold (%)", 30, 95, 60, 5)
    ai_interval = st.slider("Auto AI Advice Interval (sec)", 10, 60, 20, 5)

    c_start, c_stop = st.columns(2)
    with c_start:
        if st.button("▶ Start", use_container_width=True, type="primary"):
            st.session_state.running = True
            st.session_state.session_id = datetime.now().strftime("SESSION_%Y%m%d_%H%M%S")
            st.session_state.engagement_history = []
            st.session_state.suggestion_feed = []
            st.rerun()
    with c_stop:
        if st.button("⏹ Stop", use_container_width=True):
            st.session_state.running = False
            st.rerun()

    st.divider()
    enrolled_students = load_all_students()
    st.metric("Enrolled Roster", f"{len(enrolled_students)} Students")

# --- Main Navigation Tabs ---
tab_monitor, tab_enroll, tab_reports = st.tabs([
    "📡 Live Command Center",
    "➕ Quick Student Enrollment",
    "📊 Analytics & Export",
])

# ==========================================
# TAB 1: LIVE COMMAND CENTER
# ==========================================
with tab_monitor:
    k1, k2, k3, k4 = st.columns(4)
    kpi_overall = k1.empty()
    kpi_gaze = k2.empty()
    kpi_move = k3.empty()
    kpi_audio = k4.empty()

    def kpi_html(label, value, index, animate):
        # Entrance animation only when idle: during the live loop cards are
        # re-drawn every frame and would flicker if they re-animated.
        cls = "kpi-card kpi-enter" if animate else "kpi-card"
        delay = f"animation-delay:{index * STAGGER_MS}ms;" if animate else ""
        pct = max(0, min(100, float(value)))
        return (
            f'<div class="{cls}" style="{delay}"><div class="kpi-label">{label}</div>'
            f'<div class="kpi-val">{value}%</div>'
            f'<div class="kpi-bar"><span style="width:{pct}%"></span></div></div>'
        )

    def render_kpis(m, animate=False):
        kpi_overall.markdown(kpi_html("Overall Engagement", m["total_engagement"], 0, animate), unsafe_allow_html=True)
        kpi_gaze.markdown(kpi_html("Visual Gaze", m["gaze_score"], 1, animate), unsafe_allow_html=True)
        kpi_move.markdown(kpi_html("Posture & Motion", m["movement_score"], 2, animate), unsafe_allow_html=True)
        kpi_audio.markdown(kpi_html("Vocal Interaction", m["audio_score"], 3, animate), unsafe_allow_html=True)

    render_kpis(st.session_state.latest_metrics, animate=not st.session_state.running)
    st.write("")

    col_left, col_right = st.columns([1.25, 1])

    with col_left:
        st.subheader("👁️ Multimodal Vision & Tracking Stream")
        video_box = st.empty()
        if not st.session_state.running:
            video_box.info("Click **▶ Start** in the left sidebar to launch live face recognition, gaze tracking, and voice activity analysis.")

        st.subheader("📋 Sustained-Presence Attendance")
        att_box = st.empty()

    with col_right:
        head_c1, head_c2 = st.columns([1.6, 1])
        with head_c1:
            st.subheader("🤖 AI Teaching Coach")
        with head_c2:
            ask_now = st.button("✨ Ask Coach Now", use_container_width=True)

        coach_box = st.empty()

        if ask_now:
            with st.spinner("Local Ollama agent analyzing classroom state..."):
                agent = TeachingAdvisorAgent()
                present_cnt = sum(1 for r in st.session_state.attendance_summary if r["Status"] == "Present")
                tip = agent.generate_suggestion(
                    st.session_state.session_id,
                    st.session_state.latest_metrics,
                    present_cnt,
                    max(1, len(enrolled_students)),
                )
                st.session_state.suggestion_feed.insert(0, (datetime.now().strftime("%H:%M:%S"), tip))

        def render_coach():
            if not st.session_state.suggestion_feed:
                coach_box.markdown(
                    '<div class="coach-card"><b>Ready to Assist:</b> Start a session or click <i>✨ Ask Coach Now</i> to generate offline pedagogical insights.</div>',
                    unsafe_allow_html=True,
                )
            else:
                html_blocks = ""
                for ts, msg in st.session_state.suggestion_feed[:3]:
                    formatted_msg = msg.replace("\n", "<br>")
                    html_blocks += f'<div class="coach-card"><small style="opacity:0.75;">⏱ {ts}</small><div style="margin-top:6px;">{formatted_msg}</div></div>'
                coach_box.markdown(html_blocks, unsafe_allow_html=True)

        render_coach()

        st.subheader("📈 Real-Time Engagement Telemetry")
        chart_box = st.empty()

    def render_chart():
        if st.session_state.engagement_history:
            df_h = pd.DataFrame(st.session_state.engagement_history)
            fig = px.line(
                df_h,
                x="Time",
                y=["Overall", "Gaze", "Audio"],
                markers=True,
                line_shape="spline",
                color_discrete_sequence=T["chart"],
            )
            fig.update_layout(
                height=270,
                margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=T["text"], family="Manrope, sans-serif"),
                yaxis=dict(range=[0, 105], title="Score %", gridcolor=T["border"]),
                xaxis=dict(title="", gridcolor="rgba(0,0,0,0)"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title=""),
                hoverlabel=dict(font_family="Manrope, sans-serif"),
            )
            fig.update_traces(line=dict(width=3), marker=dict(size=6))
            chart_box.plotly_chart(fig, use_container_width=True, key=f"chart_{len(df_h)}")

    render_chart()

    # --- Active Session Processing Loop ---
    if st.session_state.running:
        agent = TeachingAdvisorAgent()

        if input_mode == "Interactive Demo Simulator":
            total_sim = round(0.50 * sim_gaze + 0.25 * sim_move + 0.25 * sim_audio, 1)
            sim_metrics = {
                "total_engagement": total_sim,
                "gaze_score": float(sim_gaze),
                "movement_score": float(sim_move),
                "audio_score": float(sim_audio),
                "inactivity_sec": 18.0 if sim_move < 40 else 1.5,
            }
            st.session_state.latest_metrics = sim_metrics
            render_kpis(sim_metrics)
            st.session_state.engagement_history.append({
                "Time": datetime.now().strftime("%H:%M:%S"),
                "Overall": total_sim,
                "Gaze": float(sim_gaze),
                "Audio": float(sim_audio),
            })
            render_chart()
            video_box.success("🎛️ Simulator Active — Adjust sliders on the left and click **✨ Ask Coach Now** to test AI responses!")

        else:
            if input_mode == "Recorded Video (.mp4)" and uploaded_video is not None:
                tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
                tfile.write(uploaded_video.read())
                cap = cv2.VideoCapture(tfile.name)
            else:
                cap = cv2.VideoCapture(0)

            tracker = SustainedAttendanceTracker(presence_threshold=presence_req / 100.0)
            analyzer = MultimodalEngagementAnalyzer()
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
                    video_box.image(rgb_frame, channels="RGB", use_container_width=True)
                    render_kpis(metrics)

                    now = time.time()
                    if now - last_log_time >= 3.0:
                        analyzer.save_window_metrics(st.session_state.session_id, metrics)
                        st.session_state.engagement_history.append({
                            "Time": datetime.now().strftime("%H:%M:%S"),
                            "Overall": metrics["total_engagement"],
                            "Gaze": metrics["gaze_score"],
                            "Audio": metrics["audio_score"],
                        })
                        render_chart()
                        last_log_time = now

                    summary = tracker.get_summary()
                    st.session_state.attendance_summary = summary
                    if summary:
                        att_box.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)

                    if now - last_ai_time >= ai_interval:
                        present_cnt = sum(1 for r in summary if r["Status"] == "Present")
                        tip = agent.generate_suggestion(
                            st.session_state.session_id, metrics, present_cnt, len(summary)
                        )
                        st.session_state.suggestion_feed.insert(0, (datetime.now().strftime("%H:%M:%S"), tip))
                        render_coach()
                        last_ai_time = now

                    time.sleep(0.05)
            finally:
                analyzer.stop_audio()
                cap.release()
                st.session_state.attendance_summary = tracker.finalize_session(st.session_state.session_id)
                st.toast(f"Session {st.session_state.session_id} saved!", icon="✅")

# ==========================================
# TAB 2: QUICK STUDENT ENROLLMENT
# ==========================================
with tab_enroll:
    st.subheader("➕ Register New Student (Privacy-Preserving)")
    st.caption("Captures a facial snapshot, extracts a 512-D mathematical embedding locally, and immediately discards the image.")

    en_c1, en_c2 = st.columns([1, 1.2])
    with en_c1:
        new_id = st.text_input("Student ID", placeholder="e.g., S102")
        new_name = st.text_input("Full Name", placeholder="e.g., Aarav Sharma")
        cam_photo = st.camera_input("Take Student Snapshot")

        if st.button("💾 Save Student Embedding", type="primary"):
            if not new_id or not new_name or cam_photo is None:
                st.error("Please enter both ID and Name, and take a camera photo.")
            else:
                file_bytes = np.asarray(bytearray(cam_photo.read()), dtype=np.uint8)
                img = cv2.imdecode(file_bytes, 1)
                face_app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
                face_app.prepare(ctx_id=0, det_size=(320, 320))
                faces = face_app.get(img)
                if len(faces) == 1:
                    emb = faces[0].embedding / np.linalg.norm(faces[0].embedding)
                    save_student(new_id.strip(), new_name.strip(), emb)
                    st.success(f"Enrolled **{new_name}** ({new_id})! Raw image discarded.")
                    st.balloons()
                elif len(faces) == 0:
                    st.error("No face detected. Ensure good lighting and try again.")
                else:
                    st.error("Multiple faces detected. Only one person should be in frame.")

    with en_c2:
        st.markdown("**Currently Enrolled Students**")
        roster = load_all_students()
        if roster:
            st.dataframe(
                pd.DataFrame([{"Student ID": r["student_id"], "Name": r["name"], "Embedding Dim": "512-D Vector"} for r in roster]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No students enrolled yet.")

# ==========================================
# TAB 3: ANALYTICS & EXPORT
# ==========================================
with tab_reports:
    st.subheader("📊 Historical Session Analytics")
    conn = get_connection()
    df_att = pd.read_sql_query("SELECT * FROM attendance ORDER BY id DESC", conn)
    df_eng = pd.read_sql_query("SELECT * FROM engagement_logs ORDER BY id DESC", conn)
    df_sug = pd.read_sql_query("SELECT * FROM agent_suggestions ORDER BY id DESC", conn)
    conn.close()

    if not df_eng.empty:
        fig_bar = px.bar(
            df_eng.head(20),
            x="timestamp",
            y=["gaze_score", "movement_score", "audio_score"],
            barmode="group",
            title="Recent Multimodal Breakdown (Gaze vs. Movement vs. Audio)",
            color_discrete_sequence=T["chart"],  # CUSTOMIZE: bar colours follow the theme
        )
        fig_bar.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=T["text"], family="Manrope, sans-serif"),
            yaxis=dict(gridcolor=T["border"]), legend_title_text="",
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    r1, r2 = st.columns(2)
    with r1:
        st.markdown("**Timestamped Attendance Logs**")
        st.dataframe(df_att, use_container_width=True, hide_index=True)
        if not df_att.empty:
            st.download_button("⬇ Export Attendance CSV", df_att.to_csv(index=False).encode("utf-8"), "attendance.csv", "text/csv")

    with r2:
        st.markdown("**AI Coach Suggestion History**")
        st.dataframe(df_sug, use_container_width=True, hide_index=True)