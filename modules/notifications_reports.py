from __future__ import annotations

import csv
import io
import smtplib
import urllib.request
import urllib.parse
from email.message import EmailMessage
from typing import Any

import pandas as pd

from modules.auth_privacy import get_secret_or_env


def send_real_alert(
    *,
    recipient_email: str = "",
    recipient_phone: str = "",
    subject: str,
    body: str,
    is_demo: bool = False,
) -> dict[str, Any]:
    """
    Attempts real Email (Resend or SMTP) and optional SMS (Twilio) using
    st.secrets / env vars. Returns honest delivery_status and channels_used.
    """
    if is_demo:
        subject = f"[SIMULATED] {subject}"

    channels_used: list[str] = ["Portal"]
    statuses: list[str] = []

    # 1. Email via Resend API or SMTP
    resend_key = get_secret_or_env("RESEND_API_KEY", "").strip()
    from_email = get_secret_or_env("ALERT_FROM_EMAIL", "").strip()
    smtp_host = get_secret_or_env("SMTP_HOST", "").strip()
    smtp_user = get_secret_or_env("SMTP_USER", "").strip()
    smtp_pass = get_secret_or_env("SMTP_PASSWORD", "").strip()
    smtp_port = int(get_secret_or_env("SMTP_PORT", "587") or "587")

    if recipient_email.strip():
        if resend_key and from_email:
            try:
                req = urllib.request.Request(
                    "https://api.resend.com/emails",
                    data=f'{{"from":"{from_email}","to":["{recipient_email.strip()}"],"subject":{subject!r},"text":{body!r}}}'.encode("utf-8"),
                    headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    if 200 <= resp.status < 300:
                        channels_used.append("Email")
                        statuses.append("sent")
                    else:
                        statuses.append("failed")
            except Exception:
                statuses.append("failed")
        elif smtp_host and smtp_user and smtp_pass and from_email:
            try:
                msg = EmailMessage()
                msg["From"] = from_email
                msg["To"] = recipient_email.strip()
                msg["Subject"] = subject
                msg.set_content(body)
                with smtplib.SMTP(smtp_host, smtp_port, timeout=8) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                    server.send_message(msg)
                channels_used.append("Email")
                statuses.append("sent")
            except Exception:
                statuses.append("failed")
        else:
            statuses.append("simulated (no credentials)")

    # 2. Optional SMS via Twilio
    tw_sid = get_secret_or_env("TWILIO_ACCOUNT_SID", "").strip()
    tw_token = get_secret_or_env("TWILIO_AUTH_TOKEN", "").strip()
    tw_from = get_secret_or_env("TWILIO_FROM_NUMBER", "").strip()
    if recipient_phone.strip():
        if tw_sid and tw_token and tw_from:
            try:
                data = urllib.parse.urlencode({
                    "From": tw_from,
                    "To": recipient_phone.strip(),
                    "Body": f"{subject}: {body}",
                }).encode("utf-8")
                auth_b64 = __import__("base64").b64encode(f"{tw_sid}:{tw_token}".encode("utf-8")).decode("ascii")
                req = urllib.request.Request(
                    f"https://api.twilio.com/2010-04-01/Accounts/{tw_sid}/Messages.json",
                    data=data,
                    headers={"Authorization": f"Basic {auth_b64}", "Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    if 200 <= resp.status < 300:
                        channels_used.append("SMS")
                        statuses.append("sent")
                    else:
                        statuses.append("failed")
            except Exception:
                statuses.append("failed")
        else:
            statuses.append("simulated (no credentials)")

    if not statuses:
        delivery_status = "simulated (no credentials)" if not is_demo else "simulated (demo mode)"
    elif any(s == "failed" for s in statuses):
        delivery_status = "failed"
    elif all(s == "sent" for s in statuses):
        delivery_status = "sent"
    else:
        delivery_status = "simulated (no credentials)"

    return {
        "channels_label": " · ".join(channels_used),
        "delivery_status": delivery_status,
    }


def export_attendance_csv_bytes(df_att: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    if df_att is None or df_att.empty:
        return b""
    df_att.to_csv(buf, index=False, quoting=csv.QUOTE_MINIMAL)
    return buf.getvalue().encode("utf-8")


def export_attendance_excel_bytes(df_att: pd.DataFrame, df_eng: pd.DataFrame | None = None) -> bytes:
    """Exports Excel (.xlsx) if openpyxl is installed, falling back to CSV bytes cleanly."""
    if df_att is None or df_att.empty:
        return b""
    try:
        import openpyxl  # noqa: F401
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            df_att.to_excel(writer, sheet_name="Attendance", index=False)
            if df_eng is not None and not df_eng.empty:
                df_eng.to_excel(writer, sheet_name="Engagement", index=False)
        return out.getvalue()
    except Exception:
        return export_attendance_csv_bytes(df_att)


def build_rich_pdf_bytes(
    *,
    title: str,
    subtitle: str,
    df_att: pd.DataFrame,
    is_demo: bool = False,
) -> bytes:
    """
    Uses fpdf2 when installed to produce a clean tabular PDF report;
    falls back to a minimal valid PDF byte stream if fpdf2 is unavailable.
    """
    sim_tag = " [SIMULATED]" if is_demo else ""
    try:
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, f"{title}{sim_tag}", ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, subtitle, ln=True)
        pdf.ln(4)

        if df_att is not None and not df_att.empty:
            cols = [c for c in ["student_id", "name", "status", "observed_snapshots", "total_snapshots", "presence_ratio"] if c in df_att.columns]
            if not cols:
                cols = list(df_att.columns[:5])
            col_w = max(22.0, 185.0 / max(1, len(cols)))
            pdf.set_font("Helvetica", "B", 9)
            for c in cols:
                pdf.cell(col_w, 8, str(c)[:16], border=1)
            pdf.ln()
            pdf.set_font("Helvetica", "", 8)
            for _, r in df_att.head(40).iterrows():
                for c in cols:
                    pdf.cell(col_w, 7, str(r[c])[:22], border=1)
                pdf.ln()
        else:
            pdf.cell(0, 8, "No attendance rows recorded.", ln=True)

        raw = pdf.output(dest="S")
        return raw.encode("latin-1") if isinstance(raw, str) else bytes(raw)
    except Exception:
        safe_txt = f"{title}{sim_tag} - {subtitle}".replace("(", "[").replace(")", "]")
        stream = f"BT /F1 12 Tf 40 750 Td ({safe_txt[:120]}) Tj ET"
        pdf_str = (
            "%PDF-1.4\n"
            "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
            "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
            f"4 0 obj << /Length {len(stream)} >> stream\n{stream}\nendstream endobj\n"
            "5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
            "xref\n0 6\n0000000000 65535 f \n"
            "trailer << /Size 6 /Root 1 0 R >>\nstartxref\n9\n%%EOF"
        )
        return pdf_str.encode("latin-1", errors="replace")