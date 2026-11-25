import html

# Crisp inline vector icons (zero OS emojis)
SVG_ICONS = {
    "shield": """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#3B82F6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>""",
    "lock": """<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>""",
    "users": """<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#3B82F6" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>""",
    "alert": """<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#F87171" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>""",
    "spark": """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#60A5FA" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>""",
    "chart": """<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#64748B" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>""",
}


def get_app_css() -> str:
    return """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    :root {
        --bg-base: #0B1120;
        --bg-surface: #111827;
        --bg-widget: #1E293B;
        --bg-widget-hover: #263449;
        --border-subtle: rgba(148, 163, 184, 0.20);
        --border-faint: rgba(148, 163, 184, 0.12);
        --accent-blue: #3B82F6;
        --accent-blue-hover: #2563EB;
        --accent-cyan: #38BDF8;
        --text-primary: #F8FAFC;
        --text-secondary: #94A3B8;
        --status-green: #10B981;
        --status-amber: #F59E0B;
        --status-red: #EF4444;
    }

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
        color: var(--text-primary);
    }

    /* Hide Default Streamlit Chrome & Tighten Top Padding */
    header[data-testid="stHeader"],
    #MainMenu,
    footer,
    div[data-testid="stToolbar"],
    div[data-testid="stDecoration"],
    div[data-testid="stStatusWidget"] {
        display: none !important;
        visibility: hidden !important;
        height: 0 !important;
    }

    .block-container {
        padding-top: 1.25rem !important;
        padding-bottom: 2.25rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 1480px;
    }

    .stApp {
        background:
            radial-gradient(circle at 10% 0%, rgba(59, 130, 246, 0.13) 0%, transparent 38%),
            radial-gradient(circle at 90% 8%, rgba(56, 189, 248, 0.08) 0%, transparent 36%),
            var(--bg-base);
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: rgba(17, 24, 39, 0.94);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border-right: 1px solid var(--border-faint);
    }
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1.25rem !important;
        padding-left: 1.15rem !important;
        padding-right: 1.15rem !important;
    }

    /* Override Default Warm-Gray Streamlit Widgets -> Cool Slate */
    div[data-baseweb="input"] > div,
    div[data-baseweb="select"] > div,
    textarea,
    .stTextInput input,
    .stNumberInput input {
        background-color: var(--bg-widget) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 8px !important;
        color: var(--text-primary) !important;
        transition: border-color 0.18s ease, box-shadow 0.18s ease;
    }
    div[data-baseweb="input"] > div:hover,
    div[data-baseweb="select"] > div:hover,
    textarea:hover {
        border-color: var(--accent-blue) !important;
    }
    div[data-baseweb="input"] > div:focus-within,
    div[data-baseweb="select"] > div:focus-within {
        border-color: var(--accent-blue) !important;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.22) !important;
    }

    /* Secondary & Primary Buttons */
    .stButton > button,
    .stDownloadButton > button,
    .stFormSubmitButton > button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
        min-height: 2.5rem !important;
        white-space: nowrap !important;
        transition: all 0.18s ease !important;
    }
    .stButton > button[kind="secondary"],
    .stDownloadButton > button[kind="secondary"],
    .stFormSubmitButton > button[kind="secondary"] {
        background-color: var(--bg-widget) !important;
        border: 1px solid var(--border-subtle) !important;
        color: var(--text-primary) !important;
    }
    .stButton > button[kind="secondary"]:hover,
    .stDownloadButton > button[kind="secondary"]:hover,
    .stFormSubmitButton > button[kind="secondary"]:hover {
        border-color: var(--accent-blue) !important;
        background-color: var(--bg-widget-hover) !important;
        color: #FFFFFF !important;
    }
    .stButton > button[kind="primary"],
    .stDownloadButton > button[kind="primary"],
    .stFormSubmitButton > button[kind="primary"] {
        background-color: var(--accent-blue) !important;
        border: 1px solid var(--accent-blue) !important;
        color: #FFFFFF !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stDownloadButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button[kind="primary"]:hover {
        background-color: var(--accent-blue-hover) !important;
        border-color: #60A5FA !important;
    }

    /* File Uploader & Bordered Containers */
    [data-testid="stFileUploaderDropzone"] {
        background-color: var(--bg-widget) !important;
        border: 1px dashed var(--border-subtle) !important;
        border-radius: 10px !important;
    }
    [data-testid="stFileUploaderDropzone"]:hover {
        border-color: var(--accent-blue) !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(17, 24, 39, 0.72) !important;
        border: 1px solid var(--border-faint) !important;
        border-radius: 14px !important;
        backdrop-filter: blur(12px);
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background: rgba(17, 24, 39, 0.75);
        padding: 5px;
        border-radius: 10px;
        border: 1px solid var(--border-faint);
        margin-bottom: 1rem;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 7px;
        padding: 8px 16px;
        color: var(--text-secondary);
        font-weight: 600;
        font-size: 0.88rem;
        border: none !important;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(59, 130, 246, 0.18) !important;
        color: #FFFFFF !important;
    }
    .stTabs [data-baseweb="tab-highlight"] {
        background-color: var(--accent-blue) !important;
    }

    /* Hero Header & Single-Line Pulsing Status Pill */
    .attend-hero {
        background: rgba(17, 24, 39, 0.78);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border: 1px solid var(--border-subtle);
        border-radius: 14px;
        padding: 18px 24px;
        margin-bottom: 18px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
    }
    .hero-left {
        display: flex;
        align-items: center;
        gap: 14px;
        min-width: 0;
    }
    .hero-icon-box {
        width: 42px;
        height: 42px;
        border-radius: 10px;
        background: rgba(59, 130, 246, 0.14);
        border: 1px solid rgba(59, 130, 246, 0.32);
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
    }
    .hero-title {
        font-size: 1.38rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        color: var(--text-primary);
        margin: 0;
        line-height: 1.2;
    }
    .hero-title span {
        color: var(--accent-blue);
    }
    .hero-sub {
        font-size: 0.84rem;
        color: var(--text-secondary);
        margin: 3px 0 0 0;
    }
    .status-pill {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        white-space: nowrap;
        width: fit-content;
        flex-shrink: 0;
        padding: 7px 14px;
        border-radius: 999px;
        font-size: 0.74rem;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
    }
    .status-pill-ready {
        background: rgba(16, 185, 129, 0.12);
        border: 1px solid rgba(16, 185, 129, 0.38);
        color: #34D399;
    }
    .status-pill-idle {
        background: rgba(148, 163, 184, 0.12);
        border: 1px solid rgba(148, 163, 184, 0.28);
        color: #CBD5E1;
    }
    .pulse-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background-color: #10B981;
        box-shadow: 0 0 0 rgba(16, 185, 129, 0.6);
        animation: pulse-green 2s infinite;
        flex-shrink: 0;
    }
    @keyframes pulse-green {
        0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.65); }
        70% { box-shadow: 0 0 0 7px rgba(16, 185, 129, 0); }
        100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }

    /* Upgraded KPI Cards with tabular-nums, Delta Badge & Status Pill */
    .kpi-card {
        background: rgba(17, 24, 39, 0.78);
        backdrop-filter: blur(12px);
        border: 1px solid var(--border-faint);
        border-radius: 12px;
        padding: 16px 18px;
        transition: border-color 0.2s ease;
    }
    .kpi-card:hover {
        border-color: rgba(59, 130, 246, 0.42);
    }
    .kpi-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 8px;
        margin-bottom: 10px;
    }
    .kpi-label {
        font-size: 0.73rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--text-secondary);
        white-space: nowrap;
    }
    .kpi-pill {
        font-size: 0.68rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 999px;
        white-space: nowrap;
        letter-spacing: 0.03em;
    }
    .kpi-pill-optimal { background: rgba(16, 185, 129, 0.14); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.30); }
    .kpi-pill-watch { background: rgba(245, 158, 11, 0.14); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.30); }
    .kpi-pill-risk { background: rgba(239, 68, 68, 0.14); color: #F87171; border: 1px solid rgba(239, 68, 68, 0.30); }
    .kpi-pill-idle { background: rgba(148, 163, 184, 0.12); color: #94A3B8; border: 1px solid rgba(148, 163, 184, 0.22); }

    .kpi-bottom {
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 10px;
    }
    .kpi-value {
        font-size: 1.85rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        color: var(--text-primary);
        font-variant-numeric: tabular-nums;
        line-height: 1.1;
    }
    .kpi-delta {
        font-size: 0.78rem;
        font-weight: 700;
        font-variant-numeric: tabular-nums;
        padding: 2px 7px;
        border-radius: 6px;
        white-space: nowrap;
    }
    .delta-pos { background: rgba(16, 185, 129, 0.14); color: #34D399; }
    .delta-neg { background: rgba(245, 158, 11, 0.14); color: #FBBF24; }
    .delta-flat { background: rgba(148, 163, 184, 0.12); color: #94A3B8; }

    /* Preset Subtitle Helper */
    .preset-sub {
        font-size: 0.74rem;
        color: var(--text-secondary);
        text-align: center;
        margin-top: -8px;
        margin-bottom: 10px;
        font-variant-numeric: tabular-nums;
    }

    /* Section Headings */
    .sec-title {
        font-size: 0.96rem;
        font-weight: 700;
        color: var(--text-primary);
        margin: 0 0 2px 0;
        letter-spacing: -0.01em;
    }
    .sec-caption {
        font-size: 0.80rem;
        color: var(--text-secondary);
        margin: 0 0 12px 0;
    }

    /* Actionable AI Coach Cards */
    .coach-card {
        background: rgba(30, 41, 59, 0.62);
        border: 1px solid var(--border-faint);
        border-left: 3px solid var(--accent-blue);
        border-radius: 10px;
        padding: 13px 15px;
        margin-bottom: 10px;
    }
    .coach-meta {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
        gap: 8px;
    }
    .coach-cat {
        font-size: 0.70rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        padding: 2px 8px;
        border-radius: 6px;
        white-space: nowrap;
    }
    .cat-engagement { background: rgba(59, 130, 246, 0.18); color: #60A5FA; }
    .cat-pacing { background: rgba(245, 158, 11, 0.16); color: #FBBF24; }
    .cat-comprehension { background: rgba(16, 185, 129, 0.16); color: #34D399; }
    .cat-participation { background: rgba(56, 189, 248, 0.16); color: #7DD3FC; }
    .cat-query { background: rgba(139, 92, 246, 0.18); color: #C4B5FD; }
    .coach-time {
        font-size: 0.73rem;
        color: var(--text-secondary);
        font-variant-numeric: tabular-nums;
    }
    .coach-body {
        font-size: 0.86rem;
        line-height: 1.55;
        color: #E2E8F0;
    }

    /* Alert Banner */
    .alert-strip {
        display: flex;
        align-items: center;
        gap: 10px;
        background: rgba(239, 68, 68, 0.12);
        border: 1px solid rgba(239, 68, 68, 0.36);
        border-radius: 10px;
        padding: 11px 15px;
        color: #FCA5A5;
        font-size: 0.85rem;
        font-weight: 600;
        margin-bottom: 14px;
    }

    /* Empty State Cards */
    .empty-card {
        background: rgba(17, 24, 39, 0.65);
        border: 1px dashed var(--border-subtle);
        border-radius: 12px;
        padding: 32px 24px;
        text-align: center;
        margin-bottom: 12px;
    }
    .empty-card-icon {
        width: 54px;
        height: 54px;
        margin: 0 auto 12px auto;
        border-radius: 12px;
        background: rgba(59, 130, 246, 0.12);
        border: 1px solid rgba(59, 130, 246, 0.25);
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .empty-card h4 {
        margin: 0 0 6px 0;
        font-size: 0.98rem;
        font-weight: 700;
        color: var(--text-primary);
    }
    .empty-card p {
        margin: 0 auto;
        max-width: 440px;
        font-size: 0.83rem;
        line-height: 1.5;
        color: var(--text-secondary);
    }

    /* Sidebar Privacy & Health Audit Card */
    .audit-panel {
        background: rgba(30, 41, 59, 0.55);
        border: 1px solid var(--border-faint);
        border-radius: 11px;
        padding: 12px 13px;
        font-size: 0.78rem;
        line-height: 1.65;
        color: #CBD5E1;
    }
    .audit-hdr {
        display: flex;
        align-items: center;
        gap: 7px;
        font-weight: 700;
        color: #F8FAFC;
        margin-bottom: 6px;
        font-size: 0.80rem;
    }
    .dot-ok { color: #10B981; font-weight: 800; margin-right: 4px; }
    .dot-warn { color: #F59E0B; font-weight: 800; margin-right: 4px; }
    .audit-divider {
        border: 0;
        border-top: 1px solid var(--border-faint);
        margin: 8px 0;
    }
    </style>
    """


def render_hero_html(status_text: str, is_active: bool) -> str:
    pill_cls = "status-pill-ready" if is_active else "status-pill-idle"
    dot_html = '<span class="pulse-dot"></span>' if is_active else '<span style="width:7px;height:7px;border-radius:50%;background:#94A3B8;display:inline-block;"></span>'
    return f"""
    <div class="attend-hero">
        <div class="hero-left">
            <div class="hero-icon-box">{SVG_ICONS["shield"]}</div>
            <div>
                <h1 class="hero-title">Attend<span>AI</span> Command Suite</h1>
                <p class="hero-sub">Sustained-Presence Attendance &bull; Multimodal Engagement Fusion &bull; Offline Pedagogical AI</p>
            </div>
        </div>
        <div class="status-pill {pill_cls}">{dot_html}<span>{html.escape(status_text)}</span></div>
    </div>
    """


def render_kpi_html(label: str, value: float, delta: float | None) -> str:
    if value <= 0.0 and delta is None:
        pill_cls, pill_txt = "kpi-pill-idle", "Standby"
    elif value >= 75.0:
        pill_cls, pill_txt = "kpi-pill-optimal", "Optimal"
    elif value >= 55.0:
        pill_cls, pill_txt = "kpi-pill-watch", "Watch"
    else:
        pill_cls, pill_txt = "kpi-pill-risk", "At-Risk"

    if delta is None:
        delta_cls, delta_txt = "delta-flat", "Baseline"
    elif delta > 0.05:
        delta_cls, delta_txt = "delta-pos", f"+{delta:.1f}%"
    elif delta < -0.05:
        delta_cls, delta_txt = "delta-neg", f"{delta:.1f}%"
    else:
        delta_cls, delta_txt = "delta-flat", "0.0%"

    return f"""
    <div class="kpi-card">
        <div class="kpi-top">
            <span class="kpi-label">{html.escape(label)}</span>
            <span class="kpi-pill {pill_cls}">{pill_txt}</span>
        </div>
        <div class="kpi-bottom">
            <span class="kpi-value">{value:.1f}%</span>
            <span class="kpi-delta {delta_cls}">{delta_txt}</span>
        </div>
    </div>
    """


def render_coach_card_html(category: str, timestamp: str, body: str) -> str:
    cat_map = {
        "Engagement": "cat-engagement",
        "Pacing": "cat-pacing",
        "Comprehension": "cat-comprehension",
        "Participation": "cat-participation",
        "Instructor Query": "cat-query",
    }
    cat_cls = cat_map.get(category, "cat-engagement")
    safe_body = html.escape(body).replace("\n", "<br>")
    return f"""
    <div class="coach-card">
        <div class="coach-meta">
            <span class="coach-cat {cat_cls}">{html.escape(category)}</span>
            <span class="coach-time">{html.escape(timestamp)}</span>
        </div>
        <div class="coach-body">{safe_body}</div>
    </div>
    """


def render_empty_roster_html() -> str:
    return f"""
    <div class="empty-card">
        <div class="empty-card-icon">{SVG_ICONS["users"]}</div>
        <h4>No Enrolled Student Embeddings Yet</h4>
        <p>AttendAI enforces zero-image storage. Student portraits are converted transiently into 512-D L2-normalized vectors in RAM and discarded immediately. Enroll a student on the left or load a 5-student sample roster below.</p>
    </div>
    """


def render_audit_panel_html(diag: dict) -> str:
    ollama_cls = "dot-ok" if diag["ollama_ok"] else "dot-warn"
    audio_cls = "dot-ok" if diag["audio_ok"] else "dot-warn"
    vision_cls = "dot-ok" if diag["insightface_ok"] else "dot-warn"
    audio_txt = "WebRTC VAD Active" if diag["audio_ok"] else "Visual-Only (Cloud Safe)"
    return f"""
    <div class="audit-panel">
        <div class="audit-hdr">{SVG_ICONS["lock"]}<span>Edge Privacy &amp; Health Audit</span></div>
        <div><span class="dot-ok">&bull;</span>100% Edge Processing</div>
        <div><span class="dot-ok">&bull;</span>0 Raw Images Stored (512-D)</div>
        <div><span class="dot-ok">&bull;</span>0 External Cloud Leaks</div>
        <hr class="audit-divider">
        <div><span class="{vision_cls}">&bull;</span>Face ID: InsightFace <code>buffalo_sc</code></div>
        <div><span class="dot-ok">&bull;</span>Gaze/Pose: OpenCV Cascades</div>
        <div><span class="{audio_cls}">&bull;</span>Audio: {html.escape(audio_txt)}</div>
        <div><span class="{ollama_cls}">&bull;</span>Advisor: {html.escape(diag["ollama_label"])}</div>
    </div>
    """