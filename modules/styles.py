import html

SVG_ICONS = {
    "brand": """<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>""",
    "lock": """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#059669" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>""",
    "flag": """<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/></svg>""",
}


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return f"rgba(200, 30, 30, {alpha})"
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def get_app_css(accent_color: str = "#C81E1E") -> str:
    """
    Market-Ready B2B EdTech SaaS Theme (Stripe / Linear / Vercel Aesthetic):
      - Canvas: Cool Off-White (#F8FAFC)
      - Cards: Pure White (#FFFFFF) with hairline #E2E8F0 borders & soft depth shadows
      - Ink & Brand: Deep Slate (#0F172A) + Indigo (#4F46E5) focus accents
      - Alerts & Flags: User-customizable Flag Color (accent_color)
    """
    flag_soft = _hex_to_rgba(accent_color, 0.08)
    flag_border = _hex_to_rgba(accent_color, 0.35)

    return f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    :root {{
        --canvas: #F8FAFC;
        --surface: #FFFFFF;
        --surface-muted: #F1F5F9;
        --ink: #0F172A;
        --ink-secondary: #475569;
        --ink-muted: #64748B;
        --border: #E2E8F0;
        --border-strong: #CBD5E1;
        --brand: #4F46E5;
        --brand-soft: #EEF2FF;
        --emerald-text: #047857;
        --emerald-bg: #ECFDF5;
        --emerald-border: #A7F3D0;
        --flag: {accent_color};
        --flag-soft: {flag_soft};
        --flag-border: {flag_border};
        --shadow-xs: 0 1px 2px rgba(15, 23, 42, 0.04);
        --shadow-sm: 0 1px 3px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.04);
        --shadow-md: 0 4px 12px rgba(15, 23, 42, 0.06), 0 1px 3px rgba(15, 23, 42, 0.04);
    }}

    html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif !important;
        background-color: var(--canvas) !important;
        color: var(--ink) !important;
        color-scheme: light !important;
        -webkit-font-smoothing: antialiased;
    }}

    .num, .kpi-value, .timer-val {{
        font-variant-numeric: tabular-nums;
    }}

    /* Clean Top Bar & Visible Sidebar Toggle Arrow */
    header[data-testid="stHeader"] {{
        background: rgba(248, 250, 252, 0.90) !important;
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border-bottom: 1px solid var(--border) !important;
    }}
    header[data-testid="stHeader"] button,
    [data-testid="stExpandSidebarButton"],
    [data-testid="collapsedControl"] button,
    [data-testid="stSidebarCollapseButton"] button {{
        background-color: var(--surface) !important;
        color: var(--ink) !important;
        border: 1px solid var(--border-strong) !important;
        border-radius: 8px !important;
        box-shadow: var(--shadow-xs) !important;
    }}
    header[data-testid="stHeader"] button svg,
    [data-testid="stExpandSidebarButton"] svg,
    [data-testid="collapsedControl"] svg,
    [data-testid="stSidebarCollapseButton"] svg {{
        color: var(--ink) !important;
        fill: var(--ink) !important;
        stroke: var(--ink) !important;
    }}
    #MainMenu,
    footer,
    div[data-testid="stAppDeployButton"],
    div[data-testid="stDecoration"],
    div[data-testid="stStatusWidget"] {{
        display: none !important;
        visibility: hidden !important;
    }}

    .block-container {{
        padding-top: 4.4rem !important;
        padding-bottom: 3.5rem !important;
        padding-left: 2.25rem !important;
        padding-right: 2.25rem !important;
        max-width: 1440px;
    }}

    /* Crisp White Sidebar */
    section[data-testid="stSidebar"] {{
        background-color: var(--surface) !important;
        border-right: 1px solid var(--border) !important;
    }}
    section[data-testid="stSidebar"] .block-container {{
        padding-top: 1.5rem !important;
        padding-left: 1.25rem !important;
        padding-right: 1.25rem !important;
    }}
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] span,
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stRadio"] label,
    [data-testid="stRadio"] p,
    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] summary span {{
        color: var(--ink) !important;
    }}
    section[data-testid="stSidebar"] details,
    [data-testid="stExpander"] details {{
        background-color: var(--canvas) !important;
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
        padding: 3px 6px;
    }}
    section[data-testid="stSidebar"] summary,
    [data-testid="stExpander"] summary {{
        font-weight: 600 !important;
        font-size: 0.84rem !important;
    }}

    /* Polished Light Inputs, Selectboxes ('1x', 'View As', etc.) & Menus */
    [data-testid="stSelectbox"] div[data-baseweb="select"],
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div > div,
    div[data-baseweb="select"] > div,
    div[data-baseweb="input"],
    div[data-baseweb="input"] > div,
    div[data-baseweb="base-input"],
    textarea,
    .stTextInput input,
    .stNumberInput input,
    .stDateInput input {{
        background-color: var(--surface) !important;
        color: var(--ink) !important;
        -webkit-text-fill-color: var(--ink) !important;
    }}
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div,
    textarea {{
        border: 1px solid var(--border-strong) !important;
        border-radius: 8px !important;
        box-shadow: var(--shadow-xs) !important;
        transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
    }}
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div:hover,
    div[data-baseweb="input"] > div:hover,
    textarea:hover {{
        border-color: #94A3B8 !important;
    }}
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div:focus-within,
    div[data-baseweb="input"] > div:focus-within,
    textarea:focus {{
        border-color: var(--brand) !important;
        box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.14) !important;
    }}
    [data-testid="stSelectbox"] div[data-baseweb="select"] *,
    div[data-baseweb="select"] * {{
        color: var(--ink) !important;
        -webkit-text-fill-color: var(--ink) !important;
    }}
    div[data-baseweb="select"] svg {{
        fill: var(--ink-secondary) !important;
        color: var(--ink-secondary) !important;
    }}
    input::placeholder,
    textarea::placeholder {{
        color: var(--ink-muted) !important;
        -webkit-text-fill-color: var(--ink-muted) !important;
        opacity: 1 !important;
    }}
    div[data-baseweb="popover"],
    div[data-baseweb="popover"] > div,
    ul[data-baseweb="menu"] {{
        background-color: var(--surface) !important;
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
        box-shadow: var(--shadow-md) !important;
    }}
    ul[data-baseweb="menu"] li,
    ul[data-baseweb="menu"] li * {{
        background-color: var(--surface) !important;
        color: var(--ink) !important;
    }}
    ul[data-baseweb="menu"] li:hover,
    ul[data-baseweb="menu"] li:hover * {{
        background-color: var(--surface-muted) !important;
        color: var(--ink) !important;
    }}

    /* Enterprise SaaS Buttons (Fixes 'Ask', Popovers & Primary CTAs) */
    button[data-testid^="stBaseButton-"],
    [data-testid="stFormSubmitButton"] button,
    [data-testid="stPopover"] button,
    [data-testid="stPopoverButton"] {{
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.84rem !important;
        min-height: 2.45rem !important;
        white-space: nowrap !important;
        transition: all 0.15s ease !important;
    }}

    /* Secondary, Form Submit ('Ask') & Popover Buttons -> Crisp White Elevated */
    button[data-testid="stBaseButton-secondary"],
    button[data-testid="stBaseButton-secondaryFormSubmit"],
    [data-testid="stFormSubmitButton"] button,
    button[kind="secondary"],
    button[kind="secondaryFormSubmit"],
    [data-testid="stPopover"] button,
    [data-testid="stPopoverButton"] {{
        background-color: var(--surface) !important;
        border: 1px solid var(--border-strong) !important;
        color: var(--ink) !important;
        box-shadow: var(--shadow-xs) !important;
    }}
    button[data-testid="stBaseButton-secondary"] *,
    button[data-testid="stBaseButton-secondaryFormSubmit"] *,
    [data-testid="stFormSubmitButton"] button *,
    button[kind="secondary"] *,
    button[kind="secondaryFormSubmit"] *,
    [data-testid="stPopover"] button *,
    [data-testid="stPopoverButton"] * {{
        color: var(--ink) !important;
        fill: var(--ink) !important;
    }}
    button[data-testid="stBaseButton-secondary"]:hover,
    button[data-testid="stBaseButton-secondaryFormSubmit"]:hover,
    [data-testid="stFormSubmitButton"] button:hover,
    [data-testid="stPopover"] button:hover,
    [data-testid="stPopoverButton"]:hover {{
        background-color: var(--canvas) !important;
        border-color: #94A3B8 !important;
        box-shadow: var(--shadow-sm) !important;
    }}

    /* Primary Buttons ('Start Class', 'Generate Tip', 'Enroll Student') -> Rich Deep Slate */
    button[data-testid="stBaseButton-primary"],
    button[data-testid="stBaseButton-primaryFormSubmit"],
    button[kind="primary"],
    button[kind="primaryFormSubmit"] {{
        background: linear-gradient(180deg, #1E293B 0%, #0F172A 100%) !important;
        border: 1px solid #0F172A !important;
        color: #FFFFFF !important;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.08) !important;
    }}
    button[data-testid="stBaseButton-primary"] *,
    button[data-testid="stBaseButton-primaryFormSubmit"] *,
    button[kind="primary"] *,
    button[kind="primaryFormSubmit"] * {{
        color: #FFFFFF !important;
        fill: #FFFFFF !important;
    }}
    button[data-testid="stBaseButton-primary"]:hover,
    button[data-testid="stBaseButton-primaryFormSubmit"]:hover {{
        background: linear-gradient(180deg, #334155 0%, #1E293B 100%) !important;
        border-color: #1E293B !important;
        box-shadow: var(--shadow-sm) !important;
    }}

    [data-testid="stPopoverBody"] {{
        background-color: var(--surface) !important;
        border: 1px solid var(--border) !important;
        border-radius: 12px !important;
        box-shadow: var(--shadow-md) !important;
        color: var(--ink) !important;
    }}

    /* Segmented SaaS Navigation Tabs (Linear / Vercel Style) */
    div[data-baseweb="tab-list"] {{
        gap: 4px !important;
        background-color: var(--surface-muted) !important;
        padding: 4px !important;
        border-radius: 10px !important;
        border: 1px solid var(--border) !important;
        margin-bottom: 1.35rem !important;
    }}
    button[data-baseweb="tab"],
    button[role="tab"] {{
        border-radius: 7px !important;
        padding: 8px 15px !important;
        background-color: transparent !important;
        border: 1px solid transparent !important;
        opacity: 1 !important;
        transition: all 0.15s ease !important;
    }}
    button[data-baseweb="tab"] *,
    button[role="tab"] * {{
        color: var(--ink-secondary) !important;
        fill: var(--ink-secondary) !important;
        font-weight: 500 !important;
        font-size: 0.85rem !important;
        opacity: 1 !important;
    }}
    button[data-baseweb="tab"]:hover,
    button[role="tab"]:hover {{
        background-color: rgba(255, 255, 255, 0.65) !important;
    }}
    button[data-baseweb="tab"]:hover *,
    button[role="tab"]:hover * {{
        color: var(--ink) !important;
        fill: var(--ink) !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"],
    button[role="tab"][aria-selected="true"] {{
        background-color: var(--surface) !important;
        border: 1px solid var(--border) !important;
        box-shadow: var(--shadow-sm) !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"] *,
    button[role="tab"][aria-selected="true"] * {{
        color: var(--ink) !important;
        fill: var(--ink) !important;
        font-weight: 600 !important;
    }}
    div[data-baseweb="tab-highlight"],
    div[data-baseweb="tab-border"] {{
        display: none !important;
        background: transparent !important;
    }}

    /* Elevated Pure White SaaS Containers */
    [data-testid="stVerticalBlockBorderWrapper"] {{
        background-color: var(--surface) !important;
        border: 1px solid var(--border) !important;
        border-radius: 14px !important;
        box-shadow: var(--shadow-sm) !important;
    }}
    [data-testid="stFileUploaderDropzone"] {{
        background-color: var(--canvas) !important;
        border: 1.5px dashed var(--border-strong) !important;
        border-radius: 10px !important;
    }}
    [data-testid="stDataFrame"] {{
        border: 1px solid var(--border) !important;
        border-radius: 10px !important;
        overflow: hidden !important;
    }}

    /* Top Workspace Header Banner */
    .top-bar {{
        background-color: var(--surface);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 16px 22px;
        margin-bottom: 18px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        box-shadow: var(--shadow-sm);
    }}
    .brand-wrap {{ display: flex; align-items: center; gap: 13px; }}
    .brand-mark {{
        width: 38px; height: 38px; border-radius: 10px;
        background: linear-gradient(135deg, #0F172A 0%, #4F46E5 100%);
        display: flex; align-items: center; justify-content: center;
        flex-shrink: 0;
        box-shadow: 0 2px 8px rgba(79, 70, 229, 0.28);
    }}
    .brand-name {{
        font-size: 1.15rem; font-weight: 700; letter-spacing: -0.025em;
        color: var(--ink); margin: 0; line-height: 1.2;
    }}
    .brand-desc {{
        font-size: 0.80rem; color: var(--ink-muted); margin: 2px 0 0 0;
    }}
    .top-meta {{ display: flex; align-items: center; gap: 8px; flex-wrap: nowrap; }}
    .chip {{
        display: inline-flex; align-items: center; gap: 6px;
        white-space: nowrap; width: fit-content;
        padding: 5px 12px; border-radius: 999px;
        font-size: 0.74rem; font-weight: 600;
        border: 1px solid var(--border);
        background-color: var(--canvas);
        color: var(--ink-secondary);
    }}
    .chip-live {{
        border-color: var(--emerald-border);
        background-color: var(--emerald-bg);
        color: var(--emerald-text);
    }}
    .chip-flag {{
        border-color: var(--flag-border);
        background-color: var(--flag-soft);
        color: var(--flag);
    }}
    .dot-flag {{
        width: 7px; height: 7px; border-radius: 50%;
        background-color: #10B981;
        box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.22);
    }}

    /* Clean Typographic Hierarchy */
    .sec-title {{
        font-size: 0.98rem !important; font-weight: 600 !important;
        letter-spacing: -0.015em !important; color: var(--ink) !important;
        margin: 0 0 3px 0 !important;
    }}
    .sec-sub {{
        font-size: 0.81rem !important; color: var(--ink-muted) !important;
        margin: 0 0 12px 0 !important;
    }}

    /* Polished KPI Metric Cards */
    .kpi-card {{
        background-color: var(--surface);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 18px 20px;
        box-shadow: var(--shadow-sm);
        transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }}
    .kpi-card:hover {{
        border-color: var(--border-strong);
        box-shadow: var(--shadow-md);
    }}
    .kpi-card-flagged {{
        border-color: var(--flag-border);
        background: linear-gradient(180deg, var(--flag-soft) 0%, #FFFFFF 100%);
    }}
    .kpi-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
    .kpi-label {{
        font-size: 0.74rem; font-weight: 600; color: var(--ink-muted);
        text-transform: uppercase; letter-spacing: 0.05em;
    }}
    .kpi-tag {{
        font-size: 0.70rem; font-weight: 600; padding: 2px 9px;
        border-radius: 999px; border: 1px solid var(--border);
        color: var(--ink-secondary); background: var(--canvas);
    }}
    .kpi-tag-ok {{
        border-color: var(--emerald-border); color: var(--emerald-text); background: var(--emerald-bg);
    }}
    .kpi-tag-flag {{
        border-color: var(--flag-border); color: var(--flag); background: var(--flag-soft);
    }}
    .kpi-value {{
        font-size: 1.9rem; font-weight: 700; letter-spacing: -0.03em;
        color: var(--ink); line-height: 1.1;
    }}
    .kpi-sub {{ font-size: 0.76rem; color: var(--ink-muted); margin-top: 6px; font-weight: 400; }}

    /* Flag / Important Alert Banner */
    .flag-banner {{
        display: flex; align-items: center; gap: 10px;
        background-color: var(--flag-soft);
        border: 1px solid var(--flag-border);
        border-left: 4px solid var(--flag);
        border-radius: 10px; padding: 12px 16px;
        color: var(--flag); font-size: 0.84rem; font-weight: 600;
        margin-bottom: 16px;
    }}

    /* Faculty, Seat, Coach & Notification Cards */
    .ink-card {{
        background-color: var(--canvas);
        border: 1px solid var(--border);
        border-left: 3px solid var(--brand);
        border-radius: 10px;
        padding: 13px 15px;
        margin-bottom: 9px;
    }}
    .ink-card-flag {{
        border-color: var(--flag-border);
        border-left: 3px solid var(--flag);
        background-color: var(--flag-soft);
    }}
    .row-between {{ display: flex; justify-content: space-between; align-items: center; gap: 10px; }}
    .card-title {{ font-size: 0.87rem; font-weight: 600; color: var(--ink); }}
    .card-meta {{ font-size: 0.77rem; color: var(--ink-muted); margin-top: 2px; }}
    .bar-track {{ height: 6px; width: 100%; background: var(--border); border-radius: 99px; overflow: hidden; margin: 8px 0; }}
    .bar-fill {{ height: 100%; border-radius: 99px; }}

    /* Refined Empty State Panels */
    .empty-box {{
        background-color: var(--canvas);
        border: 1.5px dashed var(--border-strong);
        border-radius: 12px;
        padding: 30px 22px;
        text-align: center;
        margin: 8px 0;
    }}
    .empty-box h4 {{ margin: 0 0 6px 0; font-size: 0.94rem; font-weight: 600; color: var(--ink); }}
    .empty-box p {{ margin: 0 auto; max-width: 460px; font-size: 0.82rem; color: var(--ink-muted); line-height: 1.55; }}
    </style>
    """


def render_top_nav_html(org_name: str, room_label: str, role: str, status_label: str, unread_alerts: int) -> str:
    alert_chip = (
        f'<span class="chip chip-flag">{SVG_ICONS["flag"]}<span>{unread_alerts} Flag{"s" if unread_alerts != 1 else ""}</span></span>'
        if unread_alerts > 0
        else '<span class="chip"><span>0 Flags</span></span>'
    )
    live_cls = "chip chip-live" if status_label == "Live" else "chip"
    live_dot = '<span class="dot-flag"></span>' if status_label == "Live" else ""
    return f"""
    <div class="top-bar">
        <div class="brand-wrap">
            <div class="brand-mark">{SVG_ICONS["brand"]}</div>
            <div>
                <div class="brand-name">AttendAI &middot; {html.escape(org_name)}</div>
                <div class="brand-desc">Classroom Attendance, Engagement &amp; Student Safeguarding</div>
            </div>
        </div>
        <div class="top-meta">
            <span class="chip"><span>{html.escape(room_label)}</span></span>
            <span class="chip"><span>{html.escape(role)}</span></span>
            {alert_chip}
            <span class="{live_cls}">{live_dot}<span>{html.escape(status_label)}</span></span>
        </div>
    </div>
    """


def render_kpi_html(label: str, value: float, sub_text: str, flagged: bool = False, tag: str = "Normal") -> str:
    card_cls = "kpi-card kpi-card-flagged" if flagged else "kpi-card"
    if flagged:
        tag_cls = "kpi-tag kpi-tag-flag"
    elif tag in ("On Track", "Eligible", "Normal"):
        tag_cls = "kpi-tag kpi-tag-ok"
    else:
        tag_cls = "kpi-tag"
    val_style = "color:var(--flag);" if flagged else "color:var(--ink);"
    return f"""
    <div class="{card_cls}">
        <div class="kpi-top">
            <span class="kpi-label">{html.escape(label)}</span>
            <span class="{tag_cls}">{html.escape(tag)}</span>
        </div>
        <div class="kpi-value" style="{val_style}">{value:.1f}%</div>
        <div class="kpi-sub">{html.escape(sub_text)}</div>
    </div>
    """


def render_faculty_card_html(teacher_name: str, subject: str, is_live: bool) -> str:
    cls = "ink-card"
    tag = '<span class="kpi-tag kpi-tag-ok">Hosting Now</span>' if is_live else '<span class="kpi-tag">Available</span>'
    return f"""
    <div class="{cls}">
        <div class="row-between">
            <div>
                <div class="card-title">{html.escape(teacher_name)}</div>
                <div class="card-meta">{html.escape(subject)}</div>
            </div>
            <div>{tag}</div>
        </div>
    </div>
    """


def render_seat_card_html(sid: str, name: str, presence: float, focus_state: str, strikes: int, max_strikes: int, status: str, accent_color: str) -> str:
    is_flag = strikes >= max_strikes or "Absent" in status or focus_state in ("Distracted", "Focus Alert")
    cls = "ink-card ink-card-flag" if is_flag else "ink-card"
    bar_col = accent_color if is_flag else "#4F46E5"
    strike_label = f"{strikes}/{max_strikes} Focus Flags" if strikes > 0 else "In Window"
    strike_col = accent_color if strikes > 0 else "#047857"
    return f"""
    <div class="{cls}">
        <div class="row-between">
            <div><span class="card-title">{html.escape(name)}</span> <span class="card-meta">({html.escape(sid)})</span></div>
            <span class="num" style="font-size:0.80rem;font-weight:700;color:{bar_col};">{presence:.0f}%</span>
        </div>
        <div class="bar-track"><div class="bar-fill" style="width:{min(100, max(5, presence))}%;background:{bar_col};"></div></div>
        <div class="row-between" style="font-size:0.74rem;color:#475569;">
            <span>{html.escape(focus_state)} &middot; <strong style="color:#0F172A;">{html.escape(status)}</strong></span>
            <span style="font-weight:600;color:{strike_col};">{strike_label}</span>
        </div>
    </div>
    """


def render_focus_guard_widget(max_strikes: int, accent_color: str) -> str:
    return f"""
    <div id="fg-box" style="font-family:Inter,system-ui,sans-serif;background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:13px 15px;color:#0F172A;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <div style="font-size:12px;font-weight:600;color:#0F172A;">Window Focus Monitor</div>
        <span id="fg-status" style="font-size:11px;font-weight:600;padding:2px 9px;border-radius:99px;background:#ECFDF5;color:#047857;border:1px solid #A7F3D0;">Active &middot; 0/{max_strikes}</span>
      </div>
      <div id="fg-msg" style="font-size:12px;color:#64748B;line-height:1.45;">
        Detects tab switches or window exits automatically. Switch browser tabs briefly to test live tracking.
      </div>
      <div id="fg-log" style="margin-top:8px;font-size:11px;color:#334155;max-height:54px;overflow-y:auto;"></div>
    </div>
    <script>
      (function() {{
        const maxStrikes = {max_strikes};
        const flagColor = "{accent_color}";
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
          box.style.borderColor = flagColor;
          box.style.background = "#FEF2F2";
          statusEl.style.background = "#FFFFFF";
          statusEl.style.borderColor = flagColor;
          statusEl.style.color = flagColor;
          if (strikes >= maxStrikes) {{
            statusEl.textContent = "Limit Reached (" + strikes + "/" + maxStrikes + ")";
            msgEl.innerHTML = "<strong style='color:" + flagColor + ";'>Focus limit exceeded — attendance marked Absent.</strong>";
          }} else {{
            statusEl.textContent = "Flag " + strikes + "/" + maxStrikes;
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
        window.addEventListener("blur", function() {{ recordExit("Exited classroom window"); }});
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