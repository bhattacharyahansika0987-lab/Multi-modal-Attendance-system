import html

SVG_ICONS = {
    "brand": """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#F8FAFC" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>""",
    "lock": """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>""",
    "alert": """<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#F87171" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>""",
    "bell": """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#FCA5A5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>""",
    "room": """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="14" rx="2"/><path d="M8 21h8"/><path d="M12 18v3"/></svg>""",
}


def get_app_css() -> str:
    return """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap');

    :root {
        --bg-canvas: #0F172A;
        --bg-surface: #131C31;
        --bg-elevated: #1E293B;
        --bg-hover: #26354D;
        --border-subtle: #334155;
        --border-muted: rgba(148, 163, 184, 0.18);
        --text-primary: #F8FAFC;
        --text-secondary: #CBD5E1;
        --text-muted: #94A3B8;
        --accent-indigo: #6366F1;
        --accent-indigo-solid: #4F46E5;
        --accent-indigo-hover: #4338CA;
        --emerald: #10B981;
        --sky: #0EA5E9;
        --amber: #F59E0B;
        --crimson: #EF4444;
        --shadow-card: 0 4px 16px rgba(2, 6, 23, 0.35);
    }

    html, body, .stApp, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif !important;
        color: var(--text-primary);
        -webkit-font-smoothing: antialiased;
    }

    .mono, .kpi-value, .kpi-delta, .timer-val, .seat-pct {
        font-family: 'Inter', sans-serif;
        font-variant-numeric: tabular-nums;
    }

    /* Keep header transparent so sidebar reopen icon stays visible & crisp */
    header[data-testid="stHeader"] {
        background: transparent !important;
    }
    header[data-testid="stHeader"] button,
    header[data-testid="stHeader"] svg {
        color: #CBD5E1 !important;
        fill: #CBD5E1 !important;
    }
    #MainMenu,
    footer,
    div[data-testid="stAppDeployButton"],
    div[data-testid="stDecoration"],
    div[data-testid="stStatusWidget"] {
        display: none !important;
        visibility: hidden !important;
    }

    .stApp {
        background:
            radial-gradient(circle at 10% 0%, rgba(99, 102, 241, 0.12) 0%, transparent 38%),
            radial-gradient(circle at 90% 4%, rgba(14, 165, 233, 0.08) 0%, transparent 36%),
            var(--bg-canvas) !important;
    }

    .block-container {
        padding-top: 2.5rem !important;
        padding-bottom: 3.5rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 1460px;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #0B1222 !important;
        border-right: 1px solid var(--border-muted) !important;
    }
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1.25rem !important;
        padding-left: 1.15rem !important;
        padding-right: 1.15rem !important;
    }
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] span {
        color: var(--text-secondary);
    }

    /* Sidebar Demo Controls & Settings Expanders */
    section[data-testid="stSidebar"] details {
        background-color: var(--bg-surface) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 10px !important;
        padding: 2px 6px;
    }
    section[data-testid="stSidebar"] summary {
        font-weight: 600 !important;
        font-size: 0.85rem !important;
        color: var(--text-primary) !important;
    }

    /* Inputs, Selectboxes, Textareas & Dropdown Menus */
    div[data-baseweb="input"] > div,
    div[data-baseweb="select"] > div,
    textarea,
    .stTextInput input,
    .stNumberInput input {
        background-color: var(--bg-elevated) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 8px !important;
        color: var(--text-primary) !important;
        transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }
    div[data-baseweb="select"] > div *,
    div[data-baseweb="input"] input {
        color: var(--text-primary) !important;
    }
    div[data-baseweb="select"] svg {
        fill: #CBD5E1 !important;
    }
    div[data-baseweb="input"] > div:hover,
    div[data-baseweb="select"] > div:hover {
        border-color: var(--accent-indigo) !important;
    }
    ul[data-baseweb="menu"] {
        background-color: var(--bg-elevated) !important;
        border: 1px solid var(--border-subtle) !important;
    }
    ul[data-baseweb="menu"] li {
        color: var(--text-primary) !important;
    }
    ul[data-baseweb="menu"] li:hover {
        background-color: var(--bg-hover) !important;
    }

    /* Popover Trigger Buttons & Popover Body (Fixes Dark-on-Dark Buttons) */
    [data-testid="stPopover"] button,
    [data-testid="stPopoverButton"] {
        background-color: var(--bg-elevated) !important;
        border: 1px solid #475569 !important;
        border-radius: 8px !important;
        color: var(--text-primary) !important;
        font-weight: 600 !important;
        font-size: 0.84rem !important;
        min-height: 2.45rem !important;
        transition: all 0.16s ease !important;
    }
    [data-testid="stPopover"] button *,
    [data-testid="stPopoverButton"] * {
        color: var(--text-primary) !important;
        fill: var(--text-primary) !important;
    }
    [data-testid="stPopover"] button:hover,
    [data-testid="stPopoverButton"]:hover {
        background-color: var(--accent-indigo-solid) !important;
        border-color: var(--accent-indigo) !important;
        color: #FFFFFF !important;
    }
    [data-testid="stPopoverBody"] {
        background-color: var(--bg-surface) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 12px !important;
        color: var(--text-primary) !important;
    }

    /* High-Contrast Buttons (Primary & Outline Secondary — Fixes Washed-Out 'Host Next') */
    .stButton > button,
    .stDownloadButton > button,
    .stFormSubmitButton > button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.84rem !important;
        min-height: 2.4rem !important;
        white-space: nowrap !important;
        transition: all 0.16s ease !important;
    }
    .stButton > button[kind="secondary"],
    .stDownloadButton > button[kind="secondary"],
    .stFormSubmitButton > button[kind="secondary"] {
        background-color: rgba(99, 102, 241, 0.12) !important;
        border: 1px solid rgba(99, 102, 241, 0.55) !important;
        color: #E0E7FF !important;
    }
    .stButton > button[kind="secondary"] *,
    .stDownloadButton > button[kind="secondary"] *,
    .stFormSubmitButton > button[kind="secondary"] * {
        color: #E0E7FF !important;
    }
    .stButton > button[kind="secondary"]:hover,
    .stDownloadButton > button[kind="secondary"]:hover,
    .stFormSubmitButton > button[kind="secondary"]:hover {
        background-color: var(--accent-indigo-solid) !important;
        border-color: var(--accent-indigo) !important;
        color: #FFFFFF !important;
        transform: translateY(-1px);
    }
    .stButton > button[kind="secondary"]:hover *,
    .stDownloadButton > button[kind="secondary"]:hover * {
        color: #FFFFFF !important;
    }
    .stButton > button[kind="primary"],
    .stDownloadButton > button[kind="primary"],
    .stFormSubmitButton > button[kind="primary"] {
        background-color: var(--accent-indigo-solid) !important;
        border: 1px solid var(--accent-indigo) !important;
        color: #FFFFFF !important;
    }
    .stButton > button[kind="primary"] *,
    .stDownloadButton > button[kind="primary"] *,
    .stFormSubmitButton > button[kind="primary"] * {
        color: #FFFFFF !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stDownloadButton > button[kind="primary"]:hover {
        background-color: var(--accent-indigo-hover) !important;
        border-color: #818CF8 !important;
    }

    /* Elevated Dark Slate Containers */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: var(--bg-surface) !important;
        border: 1px solid var(--border-subtle) !important;
        border-radius: 12px !important;
        box-shadow: var(--shadow-card) !important;
    }

    [data-testid="stFileUploaderDropzone"] {
        background-color: var(--bg-elevated) !important;
        border: 1px dashed #475569 !important;
        border-radius: 10px !important;
    }

    /* High-Contrast Navigation Tabs (Fixes Invisible Inactive Tabs & Red Underline) */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px !important;
        background-color: var(--bg-surface) !important;
        padding: 5px !important;
        border-radius: 11px !important;
        border: 1px solid var(--border-subtle) !important;
        margin-bottom: 1.25rem !important;
    }
    .stTabs button[data-baseweb="tab"] {
        border-radius: 8px !important;
        padding: 8px 16px !important;
        background-color: transparent !important;
        border: 1px solid transparent !important;
        transition: all 0.16s ease !important;
    }
    .stTabs button[data-baseweb="tab"] p,
    .stTabs button[data-baseweb="tab"] span {
        color: #94A3B8 !important;
        font-weight: 500 !important;
        font-size: 0.86rem !important;
    }
    .stTabs button[data-baseweb="tab"]:hover {
        background-color: rgba(148, 163, 184, 0.10) !important;
    }
    .stTabs button[data-baseweb="tab"]:hover p,
    .stTabs button[data-baseweb="tab"]:hover span {
        color: #F8FAFC !important;
    }
    .stTabs button[data-baseweb="tab"][aria-selected="true"] {
        background-color: var(--accent-indigo-solid) !important;
        border: 1px solid var(--accent-indigo) !important;
        box-shadow: 0 2px 10px rgba(79, 70, 229, 0.35) !important;
    }
    .stTabs button[data-baseweb="tab"][aria-selected="true"] p,
    .stTabs button[data-baseweb="tab"][aria-selected="true"] span {
        color: #F8FAFC !important;
        font-weight: 600 !important;
    }
    .stTabs [data-baseweb="tab-highlight"],
    .stTabs [data-baseweb="tab-border"] {
        display: none !important;
        background: transparent !important;
    }

    /* Top Workspace Header */
    .top-bar {
        background-color: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: 12px;
        padding: 15px 22px;
        margin-bottom: 16px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        box-shadow: var(--shadow-card);
    }
    .brand-wrap {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .brand-mark {
        width: 38px;
        height: 38px;
        border-radius: 9px;
        background: linear-gradient(135deg, #4F46E5, #6366F1);
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        box-shadow: 0 2px 10px rgba(99, 102, 241, 0.35);
    }
    .brand-name {
        font-size: 1.18rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em !important;
        color: #F8FAFC !important;
        margin: 0 !important;
        line-height: 1.2 !important;
    }
    .brand-desc {
        font-size: 0.80rem !important;
        color: #94A3B8 !important;
        margin: 2px 0 0 0 !important;
        line-height: 1.3 !important;
    }
    .top-meta {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: nowrap;
    }
    .chip {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        white-space: nowrap;
        width: fit-content;
        padding: 5px 12px;
        border-radius: 999px;
        font-size: 0.74rem;
        font-weight: 600;
        border: 1px solid var(--border-subtle);
        background-color: var(--bg-elevated);
        color: #E2E8F0;
    }
    .chip-live {
        background-color: rgba(16, 185, 129, 0.14);
        border-color: rgba(16, 185, 129, 0.45);
        color: #6EE7B7;
    }
    .chip-alert {
        background-color: rgba(239, 68, 68, 0.16);
        border-color: rgba(239, 68, 68, 0.45);
        color: #FCA5A5;
    }
    .dot-live {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background-color: #10B981;
        box-shadow: 0 0 8px rgba(16, 185, 129, 0.85);
    }

    /* Typography Hierarchy */
    .sec-title {
        font-size: 0.98rem !important;
        font-weight: 600 !important;
        letter-spacing: -0.015em !important;
        color: #F8FAFC !important;
        margin: 0 0 3px 0 !important;
    }
    .sec-sub {
        font-size: 0.81rem !important;
        color: #94A3B8 !important;
        margin: 0 0 12px 0 !important;
    }

    /* KPI Cards */
    .kpi-card {
        background-color: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: 12px;
        padding: 16px 18px;
        box-shadow: var(--shadow-card);
    }
    .kpi-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;
    }
    .kpi-label {
        font-size: 0.76rem;
        font-weight: 500;
        color: #94A3B8;
    }
    .kpi-badge {
        font-size: 0.69rem;
        font-weight: 600;
        padding: 2px 9px;
        border-radius: 999px;
        white-space: nowrap;
    }
    .badge-optimal { background: rgba(16, 185, 129, 0.15); color: #6EE7B7; border: 1px solid rgba(16, 185, 129, 0.4); }
    .badge-watch { background: rgba(245, 158, 11, 0.15); color: #FCD34D; border: 1px solid rgba(245, 158, 11, 0.4); }
    .badge-risk { background: rgba(239, 68, 68, 0.15); color: #FCA5A5; border: 1px solid rgba(239, 68, 68, 0.4); }

    .kpi-mid {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        gap: 10px;
    }
    .kpi-value {
        font-size: 1.75rem;
        font-weight: 700;
        letter-spacing: -0.025em;
        color: #F8FAFC;
        line-height: 1.1;
    }
    .kpi-delta {
        display: inline-block;
        margin-top: 5px;
        font-size: 0.73rem;
        font-weight: 600;
        padding: 2px 7px;
        border-radius: 6px;
    }
    .delta-pos { background: rgba(16, 185, 129, 0.16); color: #6EE7B7; }
    .delta-neg { background: rgba(245, 158, 11, 0.16); color: #FCD34D; }
    .delta-flat { background: var(--bg-elevated); color: #94A3B8; }

    /* Elevated Faculty Cards & Glowing Pill Badges */
    .faculty-card {
        background-color: var(--bg-elevated);
        border: 1px solid var(--border-subtle);
        border-radius: 10px;
        padding: 13px 16px;
        margin-bottom: 10px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
    }
    .faculty-card-hosting {
        border-color: rgba(16, 185, 129, 0.45);
        background: linear-gradient(90deg, rgba(16, 185, 129, 0.08) 0%, #1E293B 45%);
    }
    .faculty-name {
        font-size: 0.90rem;
        font-weight: 600;
        color: #F8FAFC;
        line-height: 1.25;
    }
    .faculty-subject {
        font-size: 0.79rem;
        color: #94A3B8;
        margin-top: 3px;
    }
    .status-pill-hosting {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 11px;
        border-radius: 999px;
        font-size: 0.73rem;
        font-weight: 600;
        color: #6EE7B7;
        background-color: rgba(16, 185, 129, 0.16);
        border: 1px solid rgba(16, 185, 129, 0.55);
        box-shadow: 0 0 14px rgba(16, 185, 129, 0.25);
        white-space: nowrap;
    }
    .status-pill-available {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 11px;
        border-radius: 999px;
        font-size: 0.73rem;
        font-weight: 600;
        color: #7DD3FC;
        background-color: rgba(14, 165, 233, 0.15);
        border: 1px solid rgba(14, 165, 233, 0.45);
        white-space: nowrap;
    }
    .pill-dot-emerald {
        width: 7px; height: 7px; border-radius: 50%;
        background-color: #10B981;
        box-shadow: 0 0 8px #10B981;
    }
    .pill-dot-sky {
        width: 7px; height: 7px; border-radius: 50%;
        background-color: #0EA5E9;
    }

    /* Student Seat Cards */
    .seat-card {
        background-color: var(--bg-elevated);
        border: 1px solid var(--border-subtle);
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 8px;
    }
    .seat-card-risk {
        background-color: rgba(239, 68, 68, 0.10);
        border-color: rgba(239, 68, 68, 0.45);
    }
    .seat-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .seat-name { font-size: 0.85rem; font-weight: 600; color: #F8FAFC; }
    .seat-id { font-size: 0.74rem; color: #94A3B8; }
    .seat-bar-bg { height: 5px; width: 100%; background-color: #334155; border-radius: 99px; overflow: hidden; margin: 6px 0; }
    .seat-bar-fill { height: 100%; border-radius: 99px; }
    .seat-meta { display: flex; justify-content: space-between; align-items: center; font-size: 0.74rem; color: #CBD5E1; }

    /* Assistant & Notification Cards */
    .coach-card {
        background-color: var(--bg-elevated);
        border: 1px solid var(--border-subtle);
        border-left: 3px solid var(--accent-indigo);
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 8px;
    }
    .coach-meta { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .coach-badge {
        font-size: 0.68rem;
        font-weight: 600;
        padding: 2px 9px;
        border-radius: 999px;
        background-color: rgba(99, 102, 241, 0.18);
        color: #C7D2FE;
        border: 1px solid rgba(99, 102, 241, 0.4);
    }
    .coach-body { font-size: 0.83rem; line-height: 1.55; color: #E2E8F0; }

    .alert-banner {
        display: flex;
        align-items: center;
        gap: 10px;
        background-color: rgba(239, 68, 68, 0.14);
        border: 1px solid rgba(239, 68, 68, 0.45);
        border-radius: 10px;
        padding: 11px 15px;
        color: #FCA5A5;
        font-size: 0.83rem;
        font-weight: 500;
        margin-bottom: 14px;
    }

    .notif-card {
        background-color: var(--bg-elevated);
        border: 1px solid var(--border-subtle);
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 8px;
    }
    .notif-critical { border-left: 3px solid #EF4444; }
    .notif-warning { border-left: 3px solid #F59E0B; }
    .notif-info { border-left: 3px solid #10B981; }

    .room-summary {
        background-color: var(--bg-elevated);
        border: 1px solid var(--border-subtle);
        border-radius: 10px;
        padding: 14px 16px;
        margin-bottom: 12px;
    }
    .room-code {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.74rem;
        font-weight: 600;
        color: #A5B4FC;
        background-color: rgba(99, 102, 241, 0.14);
        border: 1px solid rgba(99, 102, 241, 0.35);
        padding: 3px 9px;
        border-radius: 6px;
        white-space: nowrap;
    }

    .privacy-box {
        background-color: var(--bg-surface);
        border: 1px solid var(--border-subtle);
        border-radius: 10px;
        padding: 12px 13px;
        font-size: 0.76rem;
        line-height: 1.65;
        color: #CBD5E1;
    }
    .dot-ok { color: #10B981; font-weight: 700; margin-right: 5px; }
    .dot-muted { color: #94A3B8; font-weight: 700; margin-right: 5px; }
    </style>
    """


def render_top_nav_html(room_code: str, role: str, status_label: str, unread_alerts: int) -> str:
    alert_chip = (
        f'<span class="chip chip-alert">{SVG_ICONS["bell"]}<span>{unread_alerts} Alert{"s" if unread_alerts != 1 else ""}</span></span>'
        if unread_alerts > 0
        else '<span class="chip"><span>No Alerts</span></span>'
    )
    return f"""
    <div class="top-bar">
        <div class="brand-wrap">
            <div class="brand-mark">{SVG_ICONS["brand"]}</div>
            <div>
                <div class="brand-name">AttendAI</div>
                <div class="brand-desc">Classroom Attendance, Engagement &amp; Student Safeguarding</div>
            </div>
        </div>
        <div class="top-meta">
            <span class="chip">{SVG_ICONS["room"]}<span>{html.escape(room_code)}</span></span>
            <span class="chip"><span>{html.escape(role)}</span></span>
            {alert_chip}
            <span class="chip chip-live"><span class="dot-live"></span><span>{html.escape(status_label)}</span></span>
        </div>
    </div>
    """


def render_faculty_card_html(teacher_name: str, subject: str, is_live: bool) -> str:
    pill = (
        '<span class="status-pill-hosting"><span class="pill-dot-emerald"></span>Hosting</span>'
        if is_live
        else '<span class="status-pill-available"><span class="pill-dot-sky"></span>Available</span>'
    )
    card_cls = "faculty-card faculty-card-hosting" if is_live else "faculty-card"
    return f"""
    <div class="{card_cls}">
        <div>
            <div class="faculty-name">{html.escape(teacher_name)}</div>
            <div class="faculty-subject">{html.escape(subject)}</div>
        </div>
        <div>{pill}</div>
    </div>
    """


def _mini_sparkline_svg(values: list[float], stroke: str) -> str:
    pts = values[-8:] if len(values) >= 2 else [70.0, 74.0, 76.0, 80.0]
    w, h = 74, 26
    lo, hi = min(pts), max(pts)
    span = max(10.0, hi - lo)
    coords = []
    for i, v in enumerate(pts):
        x = round(i * (w / max(1, len(pts) - 1)), 1)
        y = round(h - 3 - ((v - lo) / span) * (h - 6), 1)
        coords.append(f"{x},{y}")
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none"><polyline points="{" ".join(coords)}" stroke="{stroke}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'


def render_kpi_html(label: str, value: float, delta: float | None, series: list[float]) -> str:
    if value >= 75.0:
        b_cls, b_txt, stroke = "badge-optimal", "On Track", "#10B981"
    elif value >= 55.0:
        b_cls, b_txt, stroke = "badge-watch", "Needs Focus", "#F59E0B"
    else:
        b_cls, b_txt, stroke = "badge-risk", "Low", "#EF4444"

    if delta is None:
        d_cls, d_txt = "delta-flat", "Current"
    elif delta > 0.05:
        d_cls, d_txt = "delta-pos", f"+{delta:.1f}%"
    elif delta < -0.05:
        d_cls, d_txt = "delta-neg", f"{delta:.1f}%"
    else:
        d_cls, d_txt = "delta-flat", "0.0%"

    spark = _mini_sparkline_svg(series, stroke)
    return f"""
    <div class="kpi-card">
        <div class="kpi-top">
            <span class="kpi-label">{html.escape(label)}</span>
            <span class="kpi-badge {b_cls}">{b_txt}</span>
        </div>
        <div class="kpi-mid">
            <div>
                <div class="kpi-value">{value:.1f}%</div>
                <span class="kpi-delta {d_cls}">{d_txt}</span>
            </div>
            <div>{spark}</div>
        </div>
    </div>
    """


def render_seat_card_html(sid: str, name: str, presence: float, focus_state: str, strikes: int, max_strikes: int, status: str) -> str:
    is_risk = strikes >= max_strikes or "Absent" in status
    bar_col = "#EF4444" if is_risk else ("#F59E0B" if focus_state in ("Distracted", "Focus Warning") else "#10B981")
    strike_txt = (
        f'<span style="color:#FCA5A5;font-weight:600;">{strikes}/{max_strikes} Focus Alerts</span>'
        if strikes > 0
        else '<span style="color:#6EE7B7;font-weight:500;">In Window</span>'
    )
    return f"""
    <div class="seat-card {'seat-card-risk' if is_risk else ''}">
        <div class="seat-top">
            <div><span class="seat-name">{html.escape(name)}</span> <span class="seat-id">&middot; {html.escape(sid)}</span></div>
            <span class="seat-pct" style="font-size:0.78rem;font-weight:600;color:{bar_col};">{presence:.0f}%</span>
        </div>
        <div class="seat-bar-bg"><div class="seat-bar-fill" style="width:{min(100, max(5, presence))}%;background:{bar_col};"></div></div>
        <div class="seat-meta">
            <span>{html.escape(focus_state)} &middot; <strong>{html.escape(status)}</strong></span>
            {strike_txt}
        </div>
    </div>
    """


def render_coach_card_html(category: str, timestamp: str, body: str) -> str:
    safe_body = html.escape(body).replace("\n", "<br>")
    return f"""
    <div class="coach-card">
        <div class="coach-meta">
            <span class="coach-badge">{html.escape(category)}</span>
            <span style="font-size:0.72rem;color:#94A3B8;font-variant-numeric:tabular-nums;">{html.escape(timestamp)}</span>
        </div>
        <div class="coach-body">{safe_body}</div>
    </div>
    """


def render_focus_guard_widget(max_strikes: int) -> str:
    return f"""
    <div id="fg-box" style="font-family:Inter,system-ui,sans-serif;background:#1E293B;border:1px solid #334155;border-radius:10px;padding:12px 14px;color:#F8FAFC;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <div style="font-size:12px;font-weight:600;color:#F8FAFC;">Active Window Focus Monitor</div>
        <span id="fg-status" style="font-size:11px;font-weight:600;padding:2px 9px;border-radius:99px;background:rgba(16,185,129,0.16);color:#6EE7B7;border:1px solid rgba(16,185,129,0.45);">Monitoring &middot; 0/{max_strikes}</span>
      </div>
      <div id="fg-msg" style="font-size:12px;color:#94A3B8;line-height:1.45;">
        Automatically detects tab switches or window exits. Switch tabs briefly to preview live focus tracking.
      </div>
      <div id="fg-log" style="margin-top:8px;font-size:11px;color:#CBD5E1;max-height:54px;overflow-y:auto;"></div>
    </div>
    <script>
      (function() {{
        const maxStrikes = {max_strikes};
        let strikes = 0;
        let leftAt = null;
        const box = document.getElementById("fg-box");
        const statusEl = document.getElementById("fg-status");
        const msgEl = document.getElementById("fg-msg");
        const logEl = document.getElementById("fg-log");

        function recordExit(reason) {{
          if (leftAt !== null) return;
          leftAt = Date.now();
          strikes += 1;
          const nowStr = new Date().toLocaleTimeString();
          if (strikes >= maxStrikes) {{
            box.style.borderColor = "rgba(239,68,68,0.65)";
            box.style.background = "rgba(239,68,68,0.12)";
            statusEl.style.background = "rgba(239,68,68,0.20)";
            statusEl.style.color = "#FCA5A5";
            statusEl.style.borderColor = "rgba(239,68,68,0.5)";
            statusEl.textContent = "Limit Reached (" + strikes + "/" + maxStrikes + ")";
            msgEl.innerHTML = "<strong style='color:#FCA5A5;'>Focus limit exceeded — attendance updated to Absent.</strong>";
          }} else {{
            box.style.borderColor = "rgba(245,158,11,0.55)";
            box.style.background = "rgba(245,158,11,0.10)";
            statusEl.style.background = "rgba(245,158,11,0.18)";
            statusEl.style.color = "#FCD34D";
            statusEl.style.borderColor = "rgba(245,158,11,0.45)";
            statusEl.textContent = "Alert " + strikes + "/" + maxStrikes;
          }}
          const entry = document.createElement("div");
          entry.textContent = nowStr + " — " + reason + " (" + strikes + "/" + maxStrikes + ")";
          logEl.prepend(entry);
        }}

        function recordReturn() {{
          if (leftAt === null) return;
          const sec = ((Date.now() - leftAt) / 1000).toFixed(1);
          leftAt = null;
          if (logEl.firstChild) {{
            logEl.firstChild.textContent += " · away " + sec + "s";
          }}
        }}

        document.addEventListener("visibilitychange", function() {{
          if (document.hidden) recordExit("Switched browser tab");
          else recordReturn();
        }});
        window.addEventListener("blur", function() {{ recordExit("Left classroom window"); }});
        window.addEventListener("focus", function() {{ recordReturn(); }});
      }})();
    </script>
    """


def render_auto_pdf_download_script(filename: str, pdf_b64: str) -> str:
    safe_name = html.escape(filename)
    return f"""
    <script>
      (function() {{
        try {{
          const link = document.createElement('a');
          link.href = 'data:application/pdf;base64,{pdf_b64}';
          link.download = '{safe_name}';
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
        }} catch (e) {{}}
      }})();
    </script>
    """