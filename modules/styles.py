import html

SVG_ICONS = {
    "brand": """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>""",
    "lock": """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#059669" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>""",
    "alert": """<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#DC2626" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>""",
    "bell": """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#B91C1C" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>""",
    "room": """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#475569" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="14" rx="2"/><path d="M8 21h8"/><path d="M12 18v3"/></svg>""",
}


def get_app_css() -> str:
    return """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap');

    :root {
        --bg-canvas: #F8FAFC;
        --bg-card: #FFFFFF;
        --bg-subtle: #F1F5F9;
        --border-hairline: #E2E8F0;
        --border-hover: #CBD5E1;
        --ink-primary: #0F172A;
        --ink-secondary: #334155;
        --ink-muted: #64748B;
        --accent-ink: #0F172A;
        --accent-indigo: #4F46E5;
        --emerald-bg: #ECFDF5;
        --emerald-text: #047857;
        --emerald-border: #A7F3D0;
        --amber-bg: #FFFBEB;
        --amber-text: #B45309;
        --amber-border: #FDE68A;
        --rose-bg: #FEF2F2;
        --rose-text: #B91C1C;
        --rose-border: #FECACA;
        --shadow-xs: 0 1px 2px rgba(15, 23, 42, 0.04);
        --shadow-sm: 0 1px 3px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.03);
    }

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
        color: var(--ink-primary);
        -webkit-font-smoothing: antialiased;
    }

    .mono, .kpi-value, .kpi-delta, .timer-val, .seat-pct {
        font-family: 'Inter', sans-serif;
        font-variant-numeric: tabular-nums;
    }

    /* Hide Default Streamlit Chrome */
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

    .stApp {
        background-color: var(--bg-canvas);
    }

    .block-container {
        padding-top: 1.25rem !important;
        padding-bottom: 2.5rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 1440px;
    }

    /* Clean White Sidebar */
    section[data-testid="stSidebar"] {
        background-color: var(--bg-card);
        border-right: 1px solid var(--border-hairline);
    }
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1.25rem !important;
        padding-left: 1.15rem !important;
        padding-right: 1.15rem !important;
    }

    /* Clean Inputs, Selects & Expanders */
    div[data-baseweb="input"] > div,
    div[data-baseweb="select"] > div,
    textarea,
    .stTextInput input,
    .stNumberInput input {
        background-color: var(--bg-card) !important;
        border: 1px solid var(--border-hairline) !important;
        border-radius: 8px !important;
        color: var(--ink-primary) !important;
        box-shadow: var(--shadow-xs);
        transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }
    div[data-baseweb="input"] > div:hover,
    div[data-baseweb="select"] > div:hover,
    textarea:hover {
        border-color: var(--border-hover) !important;
    }
    div[data-baseweb="input"] > div:focus-within,
    div[data-baseweb="select"] > div:focus-within {
        border-color: var(--ink-primary) !important;
        box-shadow: 0 0 0 3px rgba(15, 23, 42, 0.06) !important;
    }

    /* Sidebar Demo Controls Drawer */
    section[data-testid="stSidebar"] details {
        background-color: var(--bg-canvas) !important;
        border: 1px solid var(--border-hairline) !important;
        border-radius: 10px !important;
        padding: 2px 4px;
    }
    section[data-testid="stSidebar"] summary {
        font-weight: 600 !important;
        font-size: 0.85rem !important;
        color: var(--ink-primary) !important;
    }

    /* Linear / Vercel Style Buttons */
    .stButton > button,
    .stDownloadButton > button,
    .stFormSubmitButton > button {
        border-radius: 8px !important;
        font-weight: 500 !important;
        font-size: 0.84rem !important;
        min-height: 2.35rem !important;
        white-space: nowrap !important;
        transition: all 0.15s ease !important;
    }
    .stButton > button[kind="secondary"],
    .stDownloadButton > button[kind="secondary"],
    .stFormSubmitButton > button[kind="secondary"] {
        background-color: var(--bg-card) !important;
        border: 1px solid var(--border-hairline) !important;
        color: var(--ink-primary) !important;
        box-shadow: var(--shadow-xs);
    }
    .stButton > button[kind="secondary"]:hover,
    .stDownloadButton > button[kind="secondary"]:hover,
    .stFormSubmitButton > button[kind="secondary"]:hover {
        background-color: var(--bg-canvas) !important;
        border-color: var(--border-hover) !important;
        color: var(--ink-primary) !important;
    }
    .stButton > button[kind="primary"],
    .stDownloadButton > button[kind="primary"],
    .stFormSubmitButton > button[kind="primary"] {
        background-color: var(--ink-primary) !important;
        border: 1px solid var(--ink-primary) !important;
        color: #FFFFFF !important;
        box-shadow: var(--shadow-xs);
    }
    .stButton > button[kind="primary"]:hover,
    .stDownloadButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button[kind="primary"]:hover {
        background-color: #1E293B !important;
        border-color: #1E293B !important;
    }

    /* Pure White Bordered Cards */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: var(--bg-card) !important;
        border: 1px solid var(--border-hairline) !important;
        border-radius: 12px !important;
        box-shadow: var(--shadow-xs) !important;
    }

    [data-testid="stFileUploaderDropzone"] {
        background-color: var(--bg-canvas) !important;
        border: 1px dashed var(--border-hover) !important;
        border-radius: 10px !important;
    }

    /* Segmented SaaS Navigation Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background-color: var(--bg-subtle);
        padding: 4px;
        border-radius: 10px;
        border: 1px solid var(--border-hairline);
        margin-bottom: 1.25rem;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 7px;
        padding: 7px 14px;
        color: var(--ink-muted);
        font-weight: 500;
        font-size: 0.85rem;
        border: none !important;
    }
    .stTabs [aria-selected="true"] {
        background-color: var(--bg-card) !important;
        color: var(--ink-primary) !important;
        font-weight: 600 !important;
        box-shadow: var(--shadow-xs);
    }
    .stTabs [data-baseweb="tab-highlight"] {
        display: none !important;
    }

    /* Top Workspace Header */
    .top-bar {
        background-color: var(--bg-card);
        border: 1px solid var(--border-hairline);
        border-radius: 12px;
        padding: 14px 20px;
        margin-bottom: 16px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        box-shadow: var(--shadow-xs);
    }
    .brand-wrap {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .brand-mark {
        width: 34px;
        height: 34px;
        border-radius: 8px;
        background-color: var(--ink-primary);
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
    }
    .brand-name {
        font-size: 1.12rem;
        font-weight: 700;
        letter-spacing: -0.025em;
        color: var(--ink-primary);
        margin: 0;
        line-height: 1.2;
    }
    .brand-desc {
        font-size: 0.80rem;
        color: var(--ink-muted);
        margin: 2px 0 0 0;
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
        padding: 5px 11px;
        border-radius: 999px;
        font-size: 0.74rem;
        font-weight: 600;
        border: 1px solid var(--border-hairline);
        background-color: var(--bg-canvas);
        color: var(--ink-secondary);
    }
    .chip-live {
        background-color: var(--emerald-bg);
        border-color: var(--emerald-border);
        color: var(--emerald-text);
    }
    .chip-alert {
        background-color: var(--rose-bg);
        border-color: var(--rose-border);
        color: var(--rose-text);
    }
    .dot-live {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background-color: #10B981;
        box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.20);
    }

    /* Clean Engagement KPI Cards */
    .kpi-card {
        background-color: var(--bg-card);
        border: 1px solid var(--border-hairline);
        border-radius: 12px;
        padding: 16px 18px;
        box-shadow: var(--shadow-xs);
        transition: border-color 0.15s ease;
    }
    .kpi-card:hover {
        border-color: var(--border-hover);
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
        color: var(--ink-muted);
    }
    .kpi-badge {
        font-size: 0.69rem;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 999px;
        white-space: nowrap;
    }
    .badge-optimal { background: var(--emerald-bg); color: var(--emerald-text); border: 1px solid var(--emerald-border); }
    .badge-watch { background: var(--amber-bg); color: var(--amber-text); border: 1px solid var(--amber-border); }
    .badge-risk { background: var(--rose-bg); color: var(--rose-text); border: 1px solid var(--rose-border); }

    .kpi-mid {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        gap: 10px;
    }
    .kpi-value {
        font-size: 1.75rem;
        font-weight: 700;
        letter-spacing: -0.03em;
        color: var(--ink-primary);
        line-height: 1.1;
    }
    .kpi-delta {
        display: inline-block;
        margin-top: 4px;
        font-size: 0.73rem;
        font-weight: 600;
        padding: 1px 6px;
        border-radius: 5px;
    }
    .delta-pos { background: var(--emerald-bg); color: var(--emerald-text); }
    .delta-neg { background: var(--amber-bg); color: var(--amber-text); }
    .delta-flat { background: var(--bg-subtle); color: var(--ink-muted); }

    /* Typography Helpers */
    .sec-title {
        font-size: 0.94rem;
        font-weight: 600;
        letter-spacing: -0.015em;
        color: var(--ink-primary);
        margin: 0 0 2px 0;
    }
    .sec-sub {
        font-size: 0.80rem;
        color: var(--ink-muted);
        margin: 0 0 12px 0;
    }

    /* Student Attention Seat Cards */
    .seat-card {
        background-color: var(--bg-canvas);
        border: 1px solid var(--border-hairline);
        border-radius: 10px;
        padding: 11px 13px;
        margin-bottom: 8px;
    }
    .seat-card-risk {
        background-color: var(--rose-bg);
        border-color: var(--rose-border);
    }
    .seat-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 6px;
    }
    .seat-name {
        font-size: 0.84rem;
        font-weight: 600;
        color: var(--ink-primary);
    }
    .seat-id {
        font-size: 0.73rem;
        color: var(--ink-muted);
    }
    .seat-bar-bg {
        height: 5px;
        width: 100%;
        background-color: #E2E8F0;
        border-radius: 99px;
        overflow: hidden;
        margin: 6px 0;
    }
    .seat-bar-fill {
        height: 100%;
        border-radius: 99px;
    }
    .seat-meta {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.73rem;
        color: var(--ink-secondary);
    }

    /* Assistant & Notification Cards */
    .coach-card {
        background-color: var(--bg-canvas);
        border: 1px solid var(--border-hairline);
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 8px;
    }
    .coach-meta {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 6px;
    }
    .coach-badge {
        font-size: 0.68rem;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 999px;
        background-color: #EEF2FF;
        color: #4338CA;
        border: 1px solid #E0E7FF;
    }
    .coach-body {
        font-size: 0.83rem;
        line-height: 1.55;
        color: var(--ink-secondary);
    }

    .alert-banner {
        display: flex;
        align-items: center;
        gap: 10px;
        background-color: var(--rose-bg);
        border: 1px solid var(--rose-border);
        border-radius: 10px;
        padding: 11px 15px;
        color: var(--rose-text);
        font-size: 0.83rem;
        font-weight: 500;
        margin-bottom: 14px;
    }

    .notif-card {
        background-color: var(--bg-canvas);
        border: 1px solid var(--border-hairline);
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 8px;
    }
    .notif-critical { border-left: 3px solid #DC2626; }
    .notif-warning { border-left: 3px solid #D97706; }
    .notif-info { border-left: 3px solid #059669; }

    .room-summary {
        background-color: var(--bg-canvas);
        border: 1px solid var(--border-hairline);
        border-radius: 10px;
        padding: 14px 16px;
        margin-bottom: 12px;
    }
    .room-code {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 600;
        color: var(--ink-secondary);
        background-color: var(--bg-card);
        border: 1px solid var(--border-hairline);
        padding: 2px 8px;
        border-radius: 6px;
    }

    /* Privacy Card */
    .privacy-box {
        background-color: var(--bg-canvas);
        border: 1px solid var(--border-hairline);
        border-radius: 10px;
        padding: 12px 13px;
        font-size: 0.76rem;
        line-height: 1.65;
        color: var(--ink-secondary);
    }
    .dot-ok { color: #059669; font-weight: 700; margin-right: 5px; }
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
                <h1 class="brand-name">AttendAI</h1>
                <p class="brand-desc">Classroom Attendance, Engagement &amp; Student Safeguarding</p>
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
        b_cls, b_txt, stroke = "badge-optimal", "On Track", "#059669"
    elif value >= 55.0:
        b_cls, b_txt, stroke = "badge-watch", "Needs Focus", "#D97706"
    else:
        b_cls, b_txt, stroke = "badge-risk", "Low", "#DC2626"

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
    bar_col = "#DC2626" if is_risk else ("#D97706" if focus_state in ("Distracted", "Focus Warning") else "#059669")
    strike_txt = (
        f'<span style="color:#B91C1C;font-weight:600;">{strikes}/{max_strikes} Focus Alerts</span>'
        if strikes > 0
        else '<span style="color:#047857;font-weight:500;">In Window</span>'
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
            <span style="font-size:0.72rem;color:#64748B;font-variant-numeric:tabular-nums;">{html.escape(timestamp)}</span>
        </div>
        <div class="coach-body">{safe_body}</div>
    </div>
    """


def render_focus_guard_widget(max_strikes: int) -> str:
    """Light-mode browser window-focus monitoring widget."""
    return f"""
    <div id="fg-box" style="font-family:Inter,system-ui,sans-serif;background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:12px 14px;color:#0F172A;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <div style="font-size:12px;font-weight:600;color:#0F172A;">Active Window Focus Monitor</div>
        <span id="fg-status" style="font-size:11px;font-weight:600;padding:2px 9px;border-radius:99px;background:#ECFDF5;color:#047857;border:1px solid #A7F3D0;">Monitoring &middot; 0/{max_strikes}</span>
      </div>
      <div id="fg-msg" style="font-size:12px;color:#64748B;line-height:1.45;">
        Automatically detects tab switches or window exits. Switch tabs briefly to preview live focus tracking.
      </div>
      <div id="fg-log" style="margin-top:8px;font-size:11px;color:#334155;max-height:54px;overflow-y:auto;"></div>
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
            box.style.borderColor = "#FECACA";
            box.style.background = "#FEF2F2";
            statusEl.style.background = "#FEE2E2";
            statusEl.style.color = "#B91C1C";
            statusEl.style.borderColor = "#FECACA";
            statusEl.textContent = "Limit Reached (" + strikes + "/" + maxStrikes + ")";
            msgEl.innerHTML = "<strong style='color:#B91C1C;'>Focus limit exceeded — attendance updated to Absent.</strong>";
          }} else {{
            box.style.borderColor = "#FDE68A";
            box.style.background = "#FFFBEB";
            statusEl.style.background = "#FEF3C7";
            statusEl.style.color = "#B45309";
            statusEl.style.borderColor = "#FDE68A";
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