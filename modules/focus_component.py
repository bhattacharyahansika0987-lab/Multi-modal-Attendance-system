from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit.components.v1 as components

_COMPONENT_DIR = Path(__file__).resolve().parent.parent / "components" / "focus_monitor"
_focus_monitor_func = components.declare_component(
    "attendai_focus_monitor",
    path=str(_COMPONENT_DIR),
)


def compute_away_duration_sec(left_at_iso: str, returned_at_iso: str | None) -> float | None:
    """Computes real away duration in seconds from ISO-8601 leave and return timestamps."""
    if not left_at_iso or not returned_at_iso:
        return None
    try:
        t_left = datetime.fromisoformat(left_at_iso.replace("Z", "+00:00"))
        t_ret = datetime.fromisoformat(returned_at_iso.replace("Z", "+00:00"))
        delta = (t_ret - t_left).total_seconds()
        return round(max(0.0, delta), 1)
    except ValueError:
        return None


def render_student_focus_monitor(
    *,
    session_id: str,
    room_code: str,
    student_id: str,
    student_name: str,
    review_threshold: int = 3,
    accent_color: str = "#C81E1E",
    key: str = "student_focus_monitor",
) -> dict[str, Any] | None:
    """
    Renders the bidirectional HTML/JS focus monitor on the student's browser.
    Returns the latest focus event payload whenever the student leaves or returns.
    """
    value = _focus_monitor_func(
        session_id=session_id,
        room_code=room_code,
        student_id=student_id,
        student_name=student_name,
        review_threshold=int(review_threshold),
        accent_color=accent_color,
        default=None,
        key=key,
    )
    return value if isinstance(value, dict) else None