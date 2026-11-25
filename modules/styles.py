import html

SVG_ICONS = {
    "shield": """<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#3B82F6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>""",
    "lock": """<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>""",
    "alert": """<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#EF4444" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>""",
    "eye": """<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#38BDF8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>""",
    "bell": """<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#F59E0B" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>""",
    "safety": """<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10B981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/></svg>""",
    "lobby": """<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3B82F6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 12h4"/><path d="M8 10v4"/><line x1="15" y1="13" x2="15.01" y2="13"/><line x1="18" y1="11" x2="18.01" y2="11"/></svg>""",
}


def get_app_css() -> str:
    return """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap');

    :root {
        --bg-canvas: #060913;
        --bg-surface: #0D1322;
        --bg-glass: rgba(255, 255, 255, 0.032);
        --bg-widget: #141D33;
        --border-specular: rgba(148, 163, 184, 0.16);
        --border-faint: rgba(148, 163, 184, 0.10);
        --cobalt: #3B82F6;
        --cobalt-hover: #2563EB;
        --cyan: #38BDF8;
        --emerald: #10B981;
        --amber: #F59E0B;
        --crimson: #EF4444;
        --text-main: #F8FAFC;
        --text-muted: #94A3B8;
    }

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
        color: var(--text-main);
    }

    .mono, .kpi-value, .kpi-delta, .countdown-val, .seat-pct {
        font-family: 'JetBrains Mono', monospace;
        font-variant-numeric: tabular-nums;
    }

    /* Kill Default Streamlit Chrome */
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
        padding-top: 1rem !important;
        padding-bottom: 2.5rem !important;
        padding-left: 1.75rem !important;
        padding-right: 1.75rem !important;
        max-width: 1520px;
    }

    .stApp {
        background:
            radial-gradient(circle at 8% 0%, rgba(59, 130, 246, 0.14) 0%, transparent 35%),
            radial-gradient(circle at 92% 4%, rgba(56, 189, 248, 0.09) 0%, transparent 35%),
            var(--bg-canvas);
    }

    /* Slim Commercial Sidebar */
    section[data-testid="stSidebar"] {
        background: rgba(13, 19, 34, 0.96);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border-right: 1px solid var(--border-faint);
    }

    /* Cool-Slate Widget Overrides */
    div[data-baseweb="input"] > div,
    div[data-baseweb="select"] > div,
    textarea,
    .stTextInput input,
    .stNumberInput input {
        background-color: var(--bg-widget) !important;
        border: 1px solid var(--border-specular) !important;
        border-radius: 8px !important;
        color: var(--text-main) !important;
    }
    div[data-baseweb="input"] > div:hover,
    div[data-baseweb="select"] > div:hover {
        border-color: var(--cobalt) !important;
    }

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
        background-color: var(--bg-widget) !important;
        border: 1px solid var(--border-specular) !important;
        color: var(--text-main) !important;
    }
    .stButton > button[kind="secondary"]:hover,
    .stDownloadButton > button[kind="secondary"]:hover {
        border-color: var(--cobalt) !important;
        background-color: #1B2844 !important;
    }
    .stButton > button[kind="primary"],
    .stDownloadButton > button[kind="primary"],
    .stFormSubmitButton > button[kind="primary"] {
        background-color: var(--cobalt) !important;
        border: 1px solid var(--cobalt) !important;
        color: #FFFFFF !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: var(--cobalt-hover) !important;
    }

    [data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--bg-glass) !important;
        border: 1px solid var(--border-specular) !important;
        border-radius: 14px !important;
        backdrop-filter: blur(16px);
    }

    /* Navigation Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background: rgba(13, 19, 34, 0.85);
        padding: 5px;
        border-radius: 10px;
        border: 1px solid var(--border-faint);
        margin-bottom: 1rem;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 7px;
        padding: 8px 14px;
        color: var(--text-muted);
        font-weight: 600;
        font-size: 0.85rem;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(59, 130, 246, 0.18) !important;
        color: #FFFFFF !important;
    }
    .stTabs [data-baseweb="tab-highlight"] {
        background-color: var(--cobalt) !important;
    }

    /* Top Commercial Navbar Banner */
    .top-nav {
        background: rgba(13, 19, 34, 0.86);
        backdrop-filter: blur(18px);
        -webkit-backdrop-filter: blur(18px);
        border: 1px solid var(--border-specular);
        border-radius: 14px;
        padding: 14px 22px;
        margin-bottom: 14px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
    }
    .nav-brand {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .nav-icon {
        width: 38px;
        height: 38px;
        border-radius: 10px;
        background: rgba(59, 130, 246, 0.15);
        border: 1px solid rgba(59, 130, 246, 0.35);
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .nav-title {
        font-size: 1.25rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        margin: 0;
        line-height: 1.15;
    }
    .nav-title span { color: var(--cobalt); }
    .nav-sub {
        font-size: 0.78rem;
        color: var(--text-muted);
        margin: 2px 0 0 0;
    }
    .nav-right {
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: nowrap;
    }
    .pill {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        white-space: nowrap;
        width: fit-content;
        padding: 6px 12px;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }
    .pill-live { background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.38); color: #34D399; }
    .pill-lobby { background: rgba(59, 130, 246, 0.12); border: 1px solid rgba(59, 130, 246, 0.35); color: #93C5FD; }
    .pill-alert { background: rgba(239, 68, 68, 0.14); border: 1px solid rgba(239, 68, 68, 0.42); color: #FCA5A5; }
    .pulse-dot {
        width: 8px; height: 8px; border-radius: 50%;
        background: #10B981;
        animation: pulse-ring 1.8s infinite;
    }
    @keyframes pulse-ring {
        0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
        70% { box-shadow: 0 0 0 7px rgba(16, 185, 129, 0); }
        100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }

    /* Glass KPI Cards with Sparkline */
    .kpi-card {
        background: rgba(13, 19, 34, 0.80);
        border: 1px solid var(--border-specular);
        border-radius: 12px;
        padding: 14px 16px;
    }
    .kpi-top {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 8px;
    }
    .kpi-label {
        font-size: 0.71rem; font-weight: 600; text-transform: uppercase;
        letter-spacing: 0.06em; color: var(--text-muted);
    }
    .kpi-pill {
        font-size: 0.66rem; font-weight: 700; padding: 2px 8px;
        border-radius: 999px; white-space: nowrap;
    }
    .kpi-optimal { background: rgba(16, 185, 129, 0.14); color: #34D399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .kpi-watch { background: rgba(245, 158, 11, 0.14); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.3); }
    .kpi-risk { background: rgba(239, 68, 68, 0.14); color: #F87171; border: 1px solid rgba(239, 68, 68, 0.3); }
    .kpi-mid {
        display: flex; justify-content: space-between; align-items: flex-end; gap: 8px;
    }
    .kpi-value {
        font-size: 1.75rem; font-weight: 700; color: var(--text-main); line-height: 1.1;
    }
    .kpi-delta {
        font-size: 0.74rem; font-weight: 700; padding: 2px 7px; border-radius: 6px;
    }
    .delta-pos { background: rgba(16, 185, 129, 0.14); color: #34D399; }
    .delta-neg { background: rgba(245, 158, 11, 0.14); color: #FBBF24; }
    .delta-flat { background: rgba(148, 163, 184, 0.12); color: #94A3B8; }

    /* Classroom Attention Grid Seat Cards */
    .seat-card {
        background: rgba(20, 29, 51, 0.65);
        border: 1px solid var(--border-faint);
        border-radius: 10px;
        padding: 11px 13px;
        margin-bottom: 8px;
    }
    .seat-card-risk {
        border-color: rgba(239, 68, 68, 0.55);
        background: rgba(239, 68, 68, 0.08);
    }
    .seat-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px; }
    .seat-name { font-size: 0.84rem; font-weight: 700; color: var(--text-main); }
    .seat-id { font-size: 0.72rem; color: var(--text-muted); }
    .seat-bar-bg { height: 5px; width: 100%; background: rgba(148, 163, 184, 0.15); border-radius: 99px; overflow: hidden; margin: 6px 0; }
    .seat-bar-fill { height: 100%; border-radius: 99px; }
    .seat-meta { display: flex; justify-content: space-between; align-items: center; font-size: 0.72rem; }

    /* Coach, Alert & Notification Cards */
    .sec-title { font-size: 0.95rem; font-weight: 700; color: var(--text-main); margin: 0 0 2px 0; }
    .sec-sub { font-size: 0.78rem; color: var(--text-muted); margin: 0 0 10px 0; }

    .coach-card {
        background: rgba(20, 29, 51, 0.65);
        border: 1px solid var(--border-faint);
        border-left: 3px solid var(--cobalt);
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 8px;
    }
    .coach-meta { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .coach-badge {
        font-size: 0.68rem; font-weight: 700; text-transform: uppercase;
        padding: 2px 8px; border-radius: 6px; letter-spacing: 0.04em;
        background: rgba(59, 130, 246, 0.18); color: #93C5FD;
    }
    .coach-body { font-size: 0.84rem; line-height: 1.5; color: #E2E8F0; }

    .alert-banner {
        display: flex; align-items: center; gap: 10px;
        background: rgba(239, 68, 68, 0.13);
        border: 1px solid rgba(239, 68, 68, 0.42);
        border-radius: 10px; padding: 11px 15px;
        color: #FCA5A5; font-size: 0.84rem; font-weight: 600;
        margin-bottom: 12px;
    }
    .notif-card {
        background: rgba(20, 29, 51, 0.6);
        border: 1px solid var(--border-faint);
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 8px;
    }
    .notif-critical { border-left: 3px solid var(--crimson); }
    .notif-warning { border-left: 3px solid var(--amber); }
    .notif-info { border-left: 3px solid var(--emerald); }

    /* Lobby Card */
    .lobby-card {
        background: rgba(20, 29, 51, 0.65);
        border: 1px solid var(--border-specular);
        border-radius: 12px;
        padding: 15px 16px;
        margin-bottom: 10px;
    }
    .lobby-code {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.74rem;
        font-weight: 700;
        color: #38BDF8;
        background: rgba(56, 189, 248, 0.12);
        border: 1px solid rgba(56, 189, 248, 0.30);
        padding: 2px 8px;
        border-radius: 6px;
    }
    .audit-panel {
        background: rgba(20, 29, 51, 0.65);
        border: 1px solid var(--border-faint);
        border-radius: 10px;
        padding: 11px 12px;
        font-size: 0.76rem;
        line-height: 1.65;
        color: #CBD5E1;
    }
    .dot-ok { color: #10B981; font-weight: 800; margin-right: 4px; }
    .dot-warn { color: #F59E0B; font-weight: 800; margin-right: 4px; }
    </style>
    """


def render_top_nav_html(lobby_code: str, role: str, status_label: str, unread_alerts: int) -> str:
    alert_pill = (
        f'<span class="pill pill-alert">{SVG_ICONS["bell"]}<span>{unread_alerts} Alert{"s" if unread_alerts != 1 else ""}</span></span>'
        if unread_alerts > 0
        else '<span class="pill pill-live"><span>0 Active Alerts</span></span>'
    )
    return f"""
    <div class="top-nav">
        <div class="nav-brand">
            <div class="nav-icon">{SVG_ICONS["shield"]}</div>
            <div>
                <h1 class="nav-title">Attend<span>AI</span> Enterprise</h1>
                <p class="nav-sub">Privacy-First Attendance &bull; Focus Proctoring &bull; Parent &amp; Student Safety Suite</p>
            </div>
        </div>
        <div class="nav-right">
            <span class="pill pill-lobby">{SVG_ICONS["lobby"]}<span>{html.escape(lobby_code)}</span></span>
            <span class="pill pill-lobby"><span>Role: {html.escape(role)}</span></span>
            {alert_pill}
            <span class="pill pill-live"><span class="pulse-dot"></span><span>{html.escape(status_label)}</span></span>
        </div>
    </div>
    """


def _mini_sparkline_svg(values: list[float], stroke: str) -> str:
    pts = values[-8:] if len(values) >= 2 else [65.0, 68.0, 72.0, 75.0]
    w, h = 76, 26
    lo, hi = min(pts), max(pts)
    span = max(10.0, hi - lo)
    coords = []
    for i, v in enumerate(pts):
        x = round(i * (w / max(1, len(pts) - 1)), 1)
        y = round(h - 3 - ((v - lo) / span) * (h - 6), 1)
        coords.append(f"{x},{y}")
    poly = " ".join(coords)
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none"><polyline points="{poly}" stroke="{stroke}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'


def render_kpi_html(label: str, value: float, delta: float | None, series: list[float]) -> str:
    if value >= 75.0:
        p_cls, p_txt, stroke = "kpi-optimal", "Optimal", "#10B981"
    elif value >= 55.0:
        p_cls, p_txt, stroke = "kpi-watch", "Watch", "#F59E0B"
    else:
        p_cls, p_txt, stroke = "kpi-risk", "At-Risk", "#EF4444"

    if delta is None:
        d_cls, d_txt = "delta-flat", "Live"
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
            <span class="kpi-pill {p_cls}">{p_txt}</span>
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
    bar_col = "#EF4444" if is_risk else ("#F59E0B" if focus_state in ("Drifting", "Tab-Switch Warning") else "#10B981")
    strike_badge = (
        f'<span style="color:#F87171;font-weight:700;">Strikes {strikes}/{max_strikes}</span>'
        if strikes > 0
        else f'<span style="color:#34D399;">Focus Clean (0/{max_strikes})</span>'
    )
    return f"""
    <div class="seat-card {'seat-card-risk' if is_risk else ''}">
        <div class="seat-top">
            <div><span class="seat-name">{html.escape(name)}</span> <span class="seat-id mono">({html.escape(sid)})</span></div>
            <span class="seat-pct" style="font-size:0.78rem;font-weight:700;color:{bar_col};">{presence:.0f}%</span>
        </div>
        <div class="seat-bar-bg"><div class="seat-bar-fill" style="width:{min(100, max(5, presence))}%;background:{bar_col};"></div></div>
        <div class="seat-meta">
            <span style="color:#CBD5E1;">{html.escape(focus_state)} &bull; <strong>{html.escape(status)}</strong></span>
            {strike_badge}
        </div>
    </div>
    """


def render_coach_card_html(category: str, timestamp: str, body: str) -> str:
    safe_body = html.escape(body).replace("\n", "<br>")
    return f"""
    <div class="coach-card">
        <div class="coach-meta">
            <span class="coach-badge">{html.escape(category)}</span>
            <span class="mono" style="font-size:0.72rem;color:#94A3B8;">{html.escape(timestamp)}</span>
        </div>
        <div class="coach-body">{safe_body}</div>
    </div>
    """


def render_focus_guard_widget(max_strikes: int) -> str:
    """Real browser visibilitychange / window.blur anti-cheat proctoring widget."""
    return f"""
    <div id="fg-box" style="font-family:Inter,system-ui,sans-serif;background:#0D1322;border:1px solid rgba(56,189,248,0.30);border-radius:10px;padding:12px 14px;color:#F8FAFC;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <div style="font-size:12px;font-weight:700;letter-spacing:0.04em;color:#38BDF8;text-transform:uppercase;">Live Browser Window-Focus Guard</div>
        <span id="fg-status" style="font-family:monospace;font-size:11px;font-weight:700;padding:2px 8px;border-radius:99px;background:rgba(16,185,129,0.16);color:#34D399;">ACTIVE • 0/{max_strikes} STRIKES</span>
      </div>
      <div id="fg-msg" style="font-size:12px;color:#94A3B8;line-height:1.45;">
        Monitoring real <code>document.visibilityState</code> &amp; desktop window exits. Switch browser tabs or click outside this window to test live strike detection.
      </div>
      <div id="fg-log" style="margin-top:8px;font-family:monospace;font-size:11px;color:#CBD5E1;max-height:54px;overflow-y:auto;"></div>
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
            box.style.borderColor = "rgba(239,68,68,0.75)";
            box.style.background = "rgba(239,68,68,0.12)";
            statusEl.style.background = "rgba(239,68,68,0.22)";
            statusEl.style.color = "#FCA5A5";
            statusEl.textContent = "BREACHED • " + strikes + "/" + maxStrikes + " -> ABSENT";
            msgEl.innerHTML = "<strong style='color:#FCA5A5;'>Limit exceeded: Student marked ABSENT (Focus Violation).</strong>";
          }} else {{
            box.style.borderColor = "rgba(245,158,11,0.65)";
            statusEl.style.background = "rgba(245,158,11,0.18)";
            statusEl.style.color = "#FBBF24";
            statusEl.textContent = "WARNING • " + strikes + "/" + maxStrikes + " STRIKES";
          }}
          const entry = document.createElement("div");
          entry.textContent = "[" + nowStr + "] Strike " + strikes + "/" + maxStrikes + ": " + reason;
          logEl.prepend(entry);
        }}

        function recordReturn() {{
          if (leftAt === null) return;
          const sec = ((Date.now() - leftAt) / 1000).toFixed(1);
          leftAt = null;
          if (logEl.firstChild) {{
            logEl.firstChild.textContent += " (away " + sec + "s)";
          }}
        }}

        document.addEventListener("visibilitychange", function() {{
          if (document.hidden) recordExit("Tab switched / minimized");
          else recordReturn();
        }});
        window.addEventListener("blur", function() {{ recordExit("Window focus lost"); }});
        window.addEventListener("focus", function() {{ recordReturn(); }});
      }})();
    </script>
    """


def render_auto_pdf_download_script(filename: str, pdf_b64: str) -> str:
    """Automatically triggers a browser PDF download when a scheduled session completes."""
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
        }} catch (e) {{ console.warn('Auto PDF download blocked by browser popup policy:', e); }}
      }})();
    </script>
    """