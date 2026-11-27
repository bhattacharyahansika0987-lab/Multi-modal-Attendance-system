from __future__ import annotations

import base64
import html
from datetime import datetime
from typing import Any

import cv2
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.agent import TeachingAdvisorAgent
from modules.attendance import (
    STATE_AMBIGUOUS,
    STATE_LOW_QUALITY,
    STATE_NEEDS_REVIEW,
    STATE_PRESENT,
    SustainedPresenceTracker,
    build_demo_snapshot_batch,
    build_snapshot_schedule,
    detect_faces_in_bgr_image,
    l2_normalize,
    load_face_analyzer,
)
from modules.database import (
    add_student_embedding,
    delete_student,
    enqueue_review_item,
    get_attention_snapshots,
    get_focus_events,
    get_lobbies,
    get_proctor_incidents,
    get_review_queue,
    get_session_data,
    get_snapshot_observations,
    load_all_students,
    load_roster_embeddings,
    log_attendance,
    log_attention_snapshot,
    log_snapshot,
    log_snapshot_observation,
    record_focus_event,
    resolve_review_item,
    save_session_report,
    save_student,
)
from modules.engagement import (
    DEFAULT_MAX_PITCH_DEG,
    DEFAULT_MAX_YAW_DEG,
    analyze_snapshot_attention,
)
from modules.focus_component import render_student_focus_monitor

PLOTLY_CFG = {"displayModeBar": False}
PLOTLY_HOVER = dict(
    bgcolor="#FFFFFF",
    bordercolor="#E2E8F0",
    font=dict(color="#0F172A", family="Inter", size=12),
)


@st.cache_resource(show_spinner="Downloading & caching InsightFace CPU model (first run only)...")
def cached_face_analyzer(model_name: str = "buffalo_sc") -> tuple[Any | None, str | None]:
    return load_face_analyzer(model_name=model_name, det_size=(320, 320))


def ensure_phase1_state() -> None:
    """Initializes Phase 1 & Phase 2 session state keys with honest defaults."""
    defaults: dict[str, Any] = {
        "demo_mode": False,
        "cosine_threshold": 0.45,
        "ambiguity_margin": 0.08,
        "min_det_score": 0.60,
        "min_face_size_px": 40,
        "min_observations": 2,
        "min_observation_pct": 50,
        "scheduled_snapshot_count": 4,
        "snapshot_schedule": [],
        "tracker": None,
        "tracker_signature": None,
        # Phase 2 head-pose & bidirectional focus defaults
        "max_yaw_deg": DEFAULT_MAX_YAW_DEG,
        "max_pitch_deg": DEFAULT_MAX_PITCH_DEG,
        "focus_review_threshold": 2,
        "student_joined_room": "",
        "student_joined_id": "",
        "student_joined_name": "",
        "student_focus_session_id": "",
        "last_focus_event_sig": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def render_demo_mode_banner() -> None:
    """Persistent banner shown on every screen whenever Demo Mode is enabled."""
    if st.session_state.get("demo_mode", False):
        st.markdown(
            """
            <div style="background:#FEF2F2;border:1.5px solid #DC2626;border-left:5px solid #DC2626;
                        border-radius:10px;padding:10px 16px;margin-bottom:14px;color:#991B1B;
                        font-weight:700;font-size:0.86rem;">
                DEMO MODE ACTIVE — SIMULATED DATA ENABLED. Snapshots, telemetry, and exported PDF reports are labeled SIMULATED.
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_honest_kpi_card(
    label: str,
    value_text: str,
    sub_text: str,
    *,
    flagged: bool = False,
    tag: str = "Standby",
) -> str:
    """Renders a KPI card supporting honest text states such as 'Not measured'."""
    card_cls = "kpi-card kpi-card-flagged" if flagged else "kpi-card"
    if flagged:
        tag_cls = "kpi-tag kpi-tag-flag"
    elif tag in ("Measured", "Real Tracker", "Clear", "On Track"):
        tag_cls = "kpi-tag kpi-tag-ok"
    else:
        tag_cls = "kpi-tag"
    val_style = "color:var(--flag);" if flagged else "color:var(--ink);"
    font_size = "1.35rem" if len(value_text) > 7 else "1.85rem"
    return f"""
    <div class="{card_cls}">
        <div class="kpi-top">
            <span class="kpi-label">{html.escape(label)}</span>
            <span class="{tag_cls}">{html.escape(tag)}</span>
        </div>
        <div class="kpi-value" style="{val_style}font-size:{font_size};">{html.escape(value_text)}</div>
        <div class="kpi-sub">{html.escape(sub_text)}</div>
    </div>
    """


def get_or_build_tracker(force_rebuild: bool = False) -> SustainedPresenceTracker:
    roster_meta, roster_embeddings = load_roster_embeddings()
    sig = (
        st.session_state.session_id,
        len(roster_meta),
        sum(len(v) for v in roster_embeddings.values()),
        st.session_state.cosine_threshold,
        st.session_state.ambiguity_margin,
        st.session_state.min_det_score,
        st.session_state.min_face_size_px,
        st.session_state.min_observations,
        st.session_state.min_observation_pct,
    )
    if force_rebuild or st.session_state.tracker is None or st.session_state.tracker_signature != sig:
        tracker = SustainedPresenceTracker(
            roster_meta=roster_meta,
            roster_embeddings=roster_embeddings,
            cosine_threshold=float(st.session_state.cosine_threshold),
            ambiguity_margin=float(st.session_state.ambiguity_margin),
            min_det_score=float(st.session_state.min_det_score),
            min_face_size_px=float(st.session_state.min_face_size_px),
            min_observations=int(st.session_state.min_observations),
            min_observation_ratio=float(st.session_state.min_observation_pct) / 100.0,
        )
        rq = get_review_queue(session_id=st.session_state.session_id)
        if not rq.empty:
            for _, row in rq[rq["status"] == "RESOLVED"].iterrows():
                if row["student_id"] and row["resolved_state"] in ("PRESENT", "ABSENT") and row["override_reason"]:
                    try:
                        tracker.apply_manual_override(
                            str(row["student_id"]),
                            str(row["resolved_state"]),
                            str(row["override_reason"]),
                        )
                    except (KeyError, ValueError):
                        pass
        st.session_state.tracker = tracker
        st.session_state.tracker_signature = sig
    return st.session_state.tracker


def _record_snapshot_results(tracker: SustainedPresenceTracker, detections: list[Any], is_demo: bool) -> list[Any]:
    obs_list = tracker.process_snapshot(detections)
    snap_idx = tracker.total_snapshots
    sess_id = st.session_state.session_id

    log_snapshot(sess_id, snap_idx, len(detections), is_demo=is_demo)
    for obs in obs_list:
        log_snapshot_observation(
            session_id=sess_id,
            snapshot_index=snap_idx,
            student_id=obs.student_id,
            student_name=obs.student_name,
            state=obs.state,
            similarity=obs.similarity,
            second_student_id=obs.second_student_id,
            second_similarity=obs.second_similarity,
            margin=obs.margin,
            det_score=obs.det_score,
            face_size_px=obs.face_size_px,
            reason=obs.reason,
            is_demo=is_demo,
        )
        if obs.state in (STATE_AMBIGUOUS, STATE_LOW_QUALITY):
            enqueue_review_item(
                session_id=sess_id,
                snapshot_index=snap_idx,
                student_id=obs.student_id,
                student_name=obs.student_name,
                candidate_student_id=obs.second_student_id,
                candidate_student_name=obs.second_student_name,
                flag_state=obs.state,
                detail=obs.reason,
                is_demo=is_demo,
            )

    # Phase 2: Compute real head-pose attention proxy from the exact same detections
    att = analyze_snapshot_attention(
        detections,
        min_det_score=float(st.session_state.min_det_score),
        min_face_size_px=float(st.session_state.min_face_size_px),
        max_yaw_deg=float(st.session_state.max_yaw_deg),
        max_pitch_deg=float(st.session_state.max_pitch_deg),
        requested_weights={
            "facing_front": float(st.session_state.get("w_gaze", 50)),
            "head_alignment": float(st.session_state.get("w_move", 25)),
            "audio": float(st.session_state.get("w_audio", 25)),
        },
    )
    log_attention_snapshot(
        session_id=sess_id,
        snapshot_index=snap_idx,
        faces_evaluated=att.faces_evaluated,
        faces_facing_front=att.faces_facing_front,
        facing_front_ratio=att.facing_front_ratio,
        head_alignment_score=att.mean_alignment_score,
        mean_abs_yaw_deg=att.mean_abs_yaw_deg,
        mean_abs_pitch_deg=att.mean_abs_pitch_deg,
        combined_attention_score=att.combined_attention_score,
        active_weights=att.active_weights,
        audio_measured=att.audio_measured,
        audio_status=att.audio_status,
        is_demo=is_demo,
    )
    if att.measured and att.combined_attention_score is not None:
        st.session_state.latest_metrics = {
            "total_engagement": att.combined_attention_score,
            "gaze_score": att.facing_front_ratio or 0.0,
            "movement_score": att.mean_alignment_score or 0.0,
            "audio_score": 0.0,
            "inactivity_sec": 0.0,
        }
    return obs_list


def seed_demo_biometric_students() -> None:
    """DEMO MODE ONLY: inserts 2 synthetic biometric students so Demo Mode works without a camera."""
    v1 = np.zeros(512, dtype=np.float32)
    v1[0] = 1.0
    v2 = np.zeros(512, dtype=np.float32)
    v2[1] = 1.0
    save_student("DEMO-01", "Demo Student A (Simulated)", l2_normalize(v1), det_score=0.95, face_size_px=120.0)
    save_student("DEMO-02", "Demo Student B (Simulated)", l2_normalize(v2), det_score=0.94, face_size_px=118.0)
    st.session_state.tracker = None


def _build_focus_report_df(sess_id: str, room_code: str) -> pd.DataFrame:
    """Formats real Phase 2 focus_events into the schema expected by the PDF generator."""
    df_focus = get_focus_events(lobby_code=room_code if room_code != "GENERAL" else None)
    if df_focus.empty:
        df_focus = get_focus_events(session_id=sess_id)
    if df_focus.empty:
        return get_proctor_incidents(sess_id)

    rows = []
    counts: dict[str, int] = {}
    for _, r in df_focus.sort_values("id", ascending=True).iterrows():
        sid = str(r["student_id"])
        counts[sid] = counts.get(sid, 0) + 1
        dur = float(r["duration_sec"]) if pd.notna(r["duration_sec"]) else 0.0
        rows.append(
            {
                "session_id": r["session_id"],
                "student_id": sid,
                "student_name": r["student_name"],
                "event_type": r["event_type"],
                "duration_sec": dur,
                "strike_count": counts[sid],
                "max_strikes": int(st.session_state.focus_review_threshold),
                "action_taken": "Queued as NEEDS REVIEW (Instructor decides)",
                "timestamp": str(r["left_at"])[11:19] if len(str(r["left_at"])) >= 19 else str(r["left_at"]),
            }
        )
    return pd.DataFrame(rows)


def finalize_real_session_and_export_pdf(active_room: dict[str, Any] | None, duration_minutes: int) -> None:
    """Persists real SustainedPresenceTracker counts, head-pose attention, and real focus events."""
    tracker = get_or_build_tracker()
    is_demo = bool(st.session_state.get("demo_mode", False))
    sess_id = st.session_state.session_id
    room_code = active_room["lobby_code"] if active_room else "GENERAL"
    base_subj = active_room["active_subject"] if active_room else (st.session_state.get("session_subject") or "Classroom Session")
    subj_label = f"[SIMULATED] {base_subj}" if is_demo else base_subj

    summaries = tracker.get_student_summaries()
    for s in summaries:
        if s.state == STATE_NEEDS_REVIEW:
            enqueue_review_item(
                session_id=sess_id,
                snapshot_index=tracker.total_snapshots,
                student_id=s.student_id,
                student_name=s.name,
                flag_state=STATE_NEEDS_REVIEW,
                detail=f"Observed in {s.observed_snapshots}/{s.total_snapshots} snapshots ({s.observation_ratio}%), below present threshold.",
                is_demo=is_demo,
            )
        status_str = f"{s.state} ({s.observed_snapshots}/{s.total_snapshots})"
        if is_demo:
            status_str = f"SIMULATED · {status_str}"
        log_attendance(
            session_id=sess_id,
            student_id=s.student_id,
            name=s.name,
            first_seen=s.first_seen or "-",
            last_seen=s.last_seen or "-",
            ratio=s.observation_ratio,
            status=status_str,
            observed_snapshots=s.observed_snapshots,
            total_snapshots=s.total_snapshots,
            override_reason=s.override_reason,
            is_demo=is_demo,
        )

    df_att, df_eng, df_sug = get_session_data(sess_id)
    df_att_pose = get_attention_snapshots(sess_id)
    if not df_att_pose.empty and df_att_pose["combined_attention_score"].notna().any():
        measured_rows = df_att_pose[df_att_pose["combined_attention_score"].notna()]
        avg_eng = float(measured_rows["combined_attention_score"].mean())
        df_eng_for_pdf = pd.DataFrame({
            "timestamp": measured_rows["timestamp"],
            "gaze_score": measured_rows["facing_front_ratio"].fillna(0.0),
            "movement_score": measured_rows["head_alignment_score"].fillna(0.0),
            "audio_score": 0.0,
            "total_engagement": measured_rows["combined_attention_score"].fillna(0.0),
        })
    else:
        avg_eng = float(df_eng["total_engagement"].mean()) if not df_eng.empty else 0.0
        df_eng_for_pdf = df_eng

    df_proctor = _build_focus_report_df(sess_id, room_code)
    agent = TeachingAdvisorAgent()
    md_text, pdf_bytes = agent.generate_executive_report(
        session_id=sess_id,
        df_att=df_att,
        df_eng=df_eng_for_pdf,
        df_sug=df_sug,
        df_proctor=df_proctor,
        lobby_code=room_code,
        subject_name=subj_label,
    )

    b64_pdf = base64.b64encode(pdf_bytes).decode("ascii")
    present_cnt = sum(1 for s in summaries if s.state == STATE_PRESENT)

    save_session_report(
        session_id=sess_id,
        lobby_code=room_code,
        subject_name=subj_label,
        avg_engagement=avg_eng,
        present_count=present_cnt,
        total_count=len(summaries),
        proctor_violations=len(df_proctor),
        pdf_b64=b64_pdf,
        is_demo=is_demo,
    )

    prefix = "SIMULATED_" if is_demo else ""
    filename = f"AttendAI_{prefix}Report_{sess_id}.pdf"
    st.session_state.auto_pdf_payload = (filename, b64_pdf)
    st.session_state.last_generated_pdf = (filename, pdf_bytes, md_text)
    st.session_state.stream_playing = False
    st.session_state.session_remaining_sec = duration_minutes * 60
    st.session_state.session_id = datetime.now().strftime("SESS_%Y%m%d_%H%M%S")
    st.session_state.tracker = None
    st.session_state.snapshot_schedule = []


def render_live_face_capture_section(duration_minutes: int, active_room: dict[str, Any] | None = None) -> None:
    """Real multi-face snapshot capture, jitter schedule, observation status & Teacher Review Queue."""
    tracker = get_or_build_tracker()
    is_demo = bool(st.session_state.get("demo_mode", False))

    if not st.session_state.snapshot_schedule:
        st.session_state.snapshot_schedule = build_snapshot_schedule(
            duration_minutes=duration_minutes,
            num_snapshots=int(st.session_state.scheduled_snapshot_count),
            jitter_fraction=0.20,
        )

    with st.container(border=True):
        st.markdown('<p class="sec-title">Real Biometric Snapshot Capture (InsightFace)</p>', unsafe_allow_html=True)
        sched_str = ", ".join(f"Min {m}" for m in st.session_state.snapshot_schedule)
        st.markdown(
            f'<p class="sec-sub">Scheduled check times (controlled jitter): <strong>{sched_str}</strong> &middot; '
            f'Captured: <strong>{tracker.total_snapshots}</strong> &middot; '
            f'Gallery: <strong>{tracker.gallery_size}</strong> embeddings (0 raw photos stored)</p>',
            unsafe_allow_html=True,
        )

        if is_demo:
            st.caption("Demo Mode: run a synthetic multi-face snapshot (with keypoints) through the real matcher & head-pose estimator.")
            dc1, dc2 = st.columns(2)
            with dc1:
                if st.button("1. Add 2 Demo Students (Simulated)", icon=":material/group_add:", use_container_width=True):
                    seed_demo_biometric_students()
                    st.toast("Added 2 simulated biometric students.")
                    st.rerun()
            with dc2:
                if st.button("2. Run Demo Snapshot", icon=":material/science:", type="primary", use_container_width=True):
                    roster_meta, roster_embs = load_roster_embeddings()
                    dets = build_demo_snapshot_batch(roster_meta, roster_embs)
                    obs = _record_snapshot_results(tracker, dets, is_demo=True)
                    st.toast(f"Processed simulated snapshot #{tracker.total_snapshots} ({len(obs)} detections).")
                    st.rerun()
        else:
            cap_mode = st.radio("Capture Source", ["Upload Group / Multi-Photo", "Live Camera Snapshot"], horizontal=True)
            if cap_mode == "Live Camera Snapshot":
                cam_img = st.camera_input("Capture Classroom Snapshot (processed in RAM, never saved)")
                if cam_img is not None and st.button("Match & Analyze Head Pose", icon=":material/face:", type="primary", use_container_width=True):
                    analyzer, err = cached_face_analyzer()
                    if err:
                        st.error(err)
                    else:
                        arr = np.asarray(bytearray(cam_img.getvalue()), dtype=np.uint8)
                        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                        dets = detect_faces_in_bgr_image(analyzer, bgr)
                        obs = _record_snapshot_results(tracker, dets, is_demo=False)
                        st.success(f"Snapshot #{tracker.total_snapshots}: detected {len(dets)} face(s), recorded {len(obs)} observation(s) + head-pose attention.")
                        st.rerun()
            else:
                uploads = st.file_uploader(
                    "Upload one or more classroom group photos (processed in RAM, never written to disk)",
                    type=["jpg", "jpeg", "png"],
                    accept_multiple_files=True,
                )
                if uploads and st.button(f"Process {len(uploads)} Snapshot(s)", icon=":material/groups:", type="primary", use_container_width=True):
                    analyzer, err = cached_face_analyzer()
                    if err:
                        st.error(err)
                    else:
                        total_faces = 0
                        for up in uploads:
                            arr = np.asarray(bytearray(up.getvalue()), dtype=np.uint8)
                            bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                            dets = detect_faces_in_bgr_image(analyzer, bgr)
                            _record_snapshot_results(tracker, dets, is_demo=False)
                            total_faces += len(dets)
                        st.success(f"Processed {len(uploads)} snapshot(s) with {total_faces} total face(s) + real head-pose attention.")
                        st.rerun()

    # Real Per-Student Observation Summary
    with st.container(border=True):
        st.markdown('<p class="sec-title">Per-Student Attendance Status (Real Tracker Output)</p>', unsafe_allow_html=True)
        summaries = tracker.get_student_summaries()
        if not summaries:
            st.info("No students enrolled yet. Add students in Roster & Reports.")
        else:
            df_sum = pd.DataFrame([
                {
                    "Student ID": s.student_id,
                    "Name": s.name,
                    "Biometric": f"Enrolled ({s.embedding_count}/5)" if s.biometric_enrolled else "Not Enrolled",
                    "Observations": f"{s.observed_snapshots}/{s.total_snapshots}",
                    "Ratio %": f"{s.observation_ratio:.1f}%",
                    "State": s.state,
                    "Override Reason": s.override_reason or "-",
                }
                for s in summaries
            ])
            st.dataframe(df_sum, use_container_width=True, hide_index=True)

        obs_df = get_snapshot_observations(st.session_state.session_id)
        if not obs_df.empty:
            with st.expander(f"Raw Face Observations ({len(obs_df)})", expanded=False):
                st.dataframe(
                    obs_df[["snapshot_index", "created_at", "state", "student_name", "similarity", "margin", "det_score", "face_size_px", "reason"]],
                    use_container_width=True,
                    hide_index=True,
                )

    # Teacher Review Queue (includes Phase 1 face flags AND Phase 2 student focus-monitor flags)
    with st.container(border=True):
        st.markdown('<p class="sec-title">Teacher Review Queue (Ambiguous, Low Quality &amp; Focus Flags)</p>', unsafe_allow_html=True)
        rq_all = get_review_queue(pending_only=True)
        room_code = active_room["lobby_code"] if active_room else "GENERAL"
        room_sess_prefix = f"ROOM_{room_code}_"
        if not rq_all.empty:
            rq_df = rq_all[
                (rq_all["session_id"] == st.session_state.session_id)
                | (rq_all["session_id"].astype(str).str.startswith(room_sess_prefix))
            ]
        else:
            rq_df = rq_all

        if rq_df.empty:
            st.caption("No pending review items for this session or room.")
        else:
            for _, row in rq_df.iterrows():
                snap_lbl = f"Snapshot #{row['snapshot_index']}" if int(row["snapshot_index"]) > 0 else "Focus Monitor"
                st.markdown(
                    f'<div class="ink-card ink-card-flag">'
                    f'<div class="row-between"><span class="card-title">{row["flag_state"]} &middot; {snap_lbl}</span>'
                    f'<span class="card-meta">{row["student_name"] or "Unmatched Face"}</span></div>'
                    f'<div class="card-meta">{row["detail"]}</div></div>',
                    unsafe_allow_html=True,
                )
                rc1, rc2, rc3 = st.columns([1.2, 2.2, 1.0], vertical_alignment="center")
                with rc1:
                    decision = st.selectbox("Decision", ["PRESENT", "ABSENT", "DISMISS"], key=f"rq_dec_{row['id']}", label_visibility="collapsed")
                with rc2:
                    reason = st.text_input("Override Reason", placeholder="Required: e.g., Verified in room / approved tab switch", key=f"rq_rsn_{row['id']}", label_visibility="collapsed")
                with rc3:
                    if st.button("Apply", key=f"rq_btn_{row['id']}", type="primary", use_container_width=True):
                        if not reason.strip():
                            st.error("Enter a reason before applying an override.")
                        else:
                            resolve_review_item(int(row["id"]), decision, reason.strip())
                            if row["student_id"] and decision in ("PRESENT", "ABSENT"):
                                try:
                                    tracker.apply_manual_override(str(row["student_id"]), decision, reason.strip())
                                except (KeyError, ValueError):
                                    pass
                            st.toast(f"Review item #{row['id']} resolved as {decision}.")
                            st.rerun()


def render_real_attention_section(accent_color: str) -> None:
    """Displays real head-pose attention telemetry and honest 'Not measured' audio notice."""
    with st.container(border=True):
        st.markdown('<p class="sec-title">Real Head-Pose Attention (Keypoint Yaw &amp; Pitch)</p>', unsafe_allow_html=True)
        st.markdown(
            f'<p class="sec-sub">Measured directly from InsightFace 5-point landmarks '
            f'(|yaw| &le; {st.session_state.max_yaw_deg:.0f}&deg;, |pitch| &le; {st.session_state.max_pitch_deg:.0f}&deg;). '
            f'<strong>Audio: Not measured</strong> (weights renormalized across visual signals only).</p>',
            unsafe_allow_html=True,
        )

        df_pose = get_attention_snapshots(st.session_state.session_id)
        measured = df_pose[df_pose["facing_front_ratio"].notna()] if not df_pose.empty else pd.DataFrame()

        if measured.empty:
            st.markdown(
                '<div class="empty-box"><h4>Awaiting Classroom Snapshot</h4>'
                '<p>Capture or upload a classroom snapshot on the left to measure real <strong>Facing-Front Ratio</strong> and <strong>Head Alignment</strong>. No metrics are fabricated.</p></div>',
                unsafe_allow_html=True,
            )
            return

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=measured["timestamp"],
                y=measured["facing_front_ratio"],
                mode="lines+markers",
                name="Facing-Front Ratio (%)",
                line=dict(color="#0F172A", width=2.8, shape="spline"),
                marker=dict(size=6, color="#0F172A"),
                hovertemplate="<b>Facing-Front Ratio</b>: %{y:.1f}%<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=measured["timestamp"],
                y=measured["head_alignment_score"],
                mode="lines+markers",
                name="Head Alignment (%)",
                line=dict(color="#4F46E5", width=2.0, dash="dash", shape="spline"),
                marker=dict(size=5, color="#4F46E5"),
                hovertemplate="<b>Head Alignment</b>: %{y:.1f}%<extra></extra>",
            )
        )
        fig.add_hline(
            y=60,
            line_dash="dot",
            line_color=accent_color,
            annotation_text="60% Reference Line",
            annotation_position="bottom right",
            annotation_font=dict(color=accent_color, size=11),
        )
        fig.update_layout(
            height=245,
            margin=dict(l=8, r=8, t=12, b=8),
            paper_bgcolor="#FFFFFF",
            plot_bgcolor="#FFFFFF",
            font=dict(color="#0F172A", family="Inter", size=11),
            hovermode="x unified",
            hoverlabel=PLOTLY_HOVER,
            yaxis=dict(range=[0, 105], title="Score (%)", gridcolor="#E2E8F0", zeroline=False),
            xaxis=dict(title="", gridcolor="#F1F5F9"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CFG, theme=None)

        disp = measured[[
            "snapshot_index",
            "timestamp",
            "faces_evaluated",
            "faces_facing_front",
            "facing_front_ratio",
            "mean_abs_yaw_deg",
            "mean_abs_pitch_deg",
            "audio_status",
        ]].rename(
            columns={
                "snapshot_index": "Snap #",
                "timestamp": "Time",
                "faces_evaluated": "Faces",
                "faces_facing_front": "Front",
                "facing_front_ratio": "Facing-Front %",
                "mean_abs_yaw_deg": "|Yaw|°",
                "mean_abs_pitch_deg": "|Pitch|°",
                "audio_status": "Audio",
            }
        )
        st.dataframe(disp.tail(6), use_container_width=True, hide_index=True)


def render_instructor_focus_feed(active_room: dict[str, Any] | None) -> None:
    """Instructor-side live feed reading real student browser focus events from SQLite."""
    with st.container(border=True):
        h1, h2 = st.columns([2.2, 1], vertical_alignment="center")
        room_code = active_room["lobby_code"] if active_room else None
        with h1:
            st.markdown('<p class="sec-title" style="margin:0;">Live Student Focus Feed (Bidirectional DB)</p>', unsafe_allow_html=True)
        with h2:
            if st.button("Refresh Feed", icon=":material/refresh:", use_container_width=True, key="p2_refresh_focus"):
                st.rerun()

        scope_txt = f"room <strong>{room_code}</strong>" if room_code else "all active sessions"
        st.markdown(
            f'<p class="sec-sub" style="margin-top:4px;">Real tab-switch/window-blur events sent by student devices in {scope_txt}. '
            f'Exits reaching <strong>{st.session_state.focus_review_threshold}</strong> queue as <strong>NEEDS REVIEW</strong> (never auto-Absent).</p>',
            unsafe_allow_html=True,
        )

        df_focus = get_focus_events(lobby_code=room_code) if room_code else get_focus_events()
        if df_focus.empty:
            st.caption("No student focus events recorded yet. Students can connect by opening Student mode and joining with Room Code + Student ID.")
        else:
            disp = pd.DataFrame({
                "Room": df_focus["lobby_code"],
                "Student": df_focus.apply(lambda r: f"{r['student_name']} ({r['student_id']})", axis=1),
                "Event": df_focus["event_type"],
                "Status": df_focus["status"],
                "Left At": df_focus["left_at"].astype(str).str.slice(11, 19),
                "Returned At": df_focus["returned_at"].fillna("Still away").astype(str).apply(lambda s: s[11:19] if len(s) >= 19 else s),
                "Away (s)": df_focus["duration_sec"].apply(lambda v: f"{float(v):.1f}s" if pd.notna(v) else "In progress"),
            })
            st.dataframe(disp.head(10), use_container_width=True, hide_index=True)


def render_student_live_focus_view(active_room: dict[str, Any] | None, accent_color: str) -> None:
    """Student-side session join + real bidirectional HTML/JS focus monitor writing to SQLite."""
    with st.container(border=True):
        st.markdown('<p class="sec-title">Student Live Session &amp; Window Focus Monitor</p>', unsafe_allow_html=True)
        st.markdown(
            '<p class="sec-sub">Join your classroom session with your <strong>Room Code</strong> and <strong>Student ID</strong>. '
            'Window exits are measured accurately and sent to your instructor for review (never auto-marked Absent).</p>',
            unsafe_allow_html=True,
        )

        roster = load_all_students()
        lobbies = get_lobbies()
        default_room = active_room["lobby_code"] if active_room else (lobbies[0]["lobby_code"] if lobbies else "GENERAL")

        if not st.session_state.student_joined_id:
            jc1, jc2, jc3 = st.columns([1.2, 1.4, 1.0], vertical_alignment="bottom")
            with jc1:
                join_room = st.text_input("Room Code", value=default_room, placeholder="Example: ECE-301", key="stu_join_room_in")
            with jc2:
                if roster:
                    s_opts = {f"{s['student_id']} — {s['name']}": s for s in roster}
                    picked = st.selectbox("Your Student ID", list(s_opts.keys()), key="stu_join_id_sel")
                    chosen_stu = s_opts[picked]
                    join_sid, join_name = chosen_stu["student_id"], chosen_stu["name"]
                else:
                    join_sid = st.text_input("Your Student ID", placeholder="Example: S101", key="stu_join_id_txt")
                    join_name = join_sid
            with jc3:
                if st.button("Join Live Class", icon=":material/login:", type="primary", use_container_width=True):
                    if not join_room.strip() or not join_sid.strip():
                        st.error("Enter both Room Code and Student ID.")
                    else:
                        code_up = join_room.strip().upper()
                        st.session_state.student_joined_room = code_up
                        st.session_state.student_joined_id = join_sid.strip()
                        st.session_state.student_joined_name = join_name.strip() or join_sid.strip()
                        st.session_state.student_focus_session_id = f"ROOM_{code_up}_{datetime.now().strftime('%Y%m%d')}"
                        st.toast(f"Connected to room {code_up} as {st.session_state.student_joined_name}.")
                        st.rerun()
            return

        # Connected Student View
        hc1, hc2 = st.columns([2.6, 1.0], vertical_alignment="center")
        with hc1:
            st.success(
                f"Connected as **{st.session_state.student_joined_name} ({st.session_state.student_joined_id})** "
                f"in Room **{st.session_state.student_joined_room}**"
            )
        with hc2:
            if st.button("Leave Session", icon=":material/logout:", use_container_width=True):
                st.session_state.student_joined_room = ""
                st.session_state.student_joined_id = ""
                st.session_state.student_joined_name = ""
                st.session_state.last_focus_event_sig = None
                st.rerun()

        event = render_student_focus_monitor(
            session_id=st.session_state.student_focus_session_id,
            room_code=st.session_state.student_joined_room,
            student_id=st.session_state.student_joined_id,
            student_name=st.session_state.student_joined_name,
            review_threshold=int(st.session_state.focus_review_threshold),
            accent_color=accent_color,
            key=f"focus_comp_{st.session_state.student_joined_room}_{st.session_state.student_joined_id}",
        )

        if event and event.get("event_uid"):
            sig = (event["event_uid"], event.get("status"), event.get("returned_at"))
            if sig != st.session_state.last_focus_event_sig:
                res = record_focus_event(
                    event_uid=str(event["event_uid"]),
                    session_id=str(event.get("session_id") or st.session_state.student_focus_session_id),
                    lobby_code=str(event.get("room_code") or st.session_state.student_joined_room),
                    student_id=str(event.get("student_id") or st.session_state.student_joined_id),
                    student_name=str(event.get("student_name") or st.session_state.student_joined_name),
                    event_type=str(event.get("event_type") or "tab_hidden"),
                    status=str(event.get("status") or "AWAY"),
                    left_at=str(event.get("left_at") or datetime.now().isoformat()),
                    returned_at=event.get("returned_at"),
                    duration_sec=event.get("duration_sec"),
                    review_threshold=int(st.session_state.focus_review_threshold),
                    is_demo=bool(st.session_state.get("demo_mode", False)),
                )
                st.session_state.last_focus_event_sig = sig
                if res["review_queued"]:
                    st.warning(
                        f"Logged {res['total_exits']} window exit(s) ({res['total_away_sec']}s total). "
                        f"Sent to Instructor Review Queue as NEEDS REVIEW."
                    )

        my_events = get_focus_events(
            lobby_code=st.session_state.student_joined_room,
            student_id=st.session_state.student_joined_id,
        )
        if not my_events.empty:
            st.markdown("**Your Recorded Focus Events (Synced to Instructor)**")
            st.dataframe(
                pd.DataFrame({
                    "Event": my_events["event_type"],
                    "Status": my_events["status"],
                    "Left At": my_events["left_at"].astype(str).str.slice(11, 19),
                    "Returned At": my_events["returned_at"].fillna("Away").astype(str).apply(lambda s: s[11:19] if len(s) >= 19 else s),
                    "Measured Away": my_events["duration_sec"].apply(lambda v: f"{float(v):.1f}s" if pd.notna(v) else "Active"),
                }),
                use_container_width=True,
                hide_index=True,
            )


def render_phase1_roster_enrollment() -> None:
    """Honest Quick Roster Entry (NULL embeddings) + Multi-Photo (1-5) Biometric Enrollment."""
    r_l, r_r = st.columns([1.05, 1.35], gap="medium")

    with r_l:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Enroll Student or Add Biometric Photos</p>', unsafe_allow_html=True)
            st.markdown(
                '<p class="sec-sub">Quick Roster stores <strong>no biometric</strong> (NULL). Add 3–5 clear photos per student for multi-embedding matching; raw images are discarded immediately in RAM.</p>',
                unsafe_allow_html=True,
            )
            mode = st.radio("Mode", ["Quick Roster (No Biometric)", "Enroll / Add Photos (1–5)", "Camera Capture"], horizontal=True)
            nid = st.text_input("Student ID", placeholder="Example: 0103EC231042 or S101", key="p1_nid")
            nname = st.text_input("Full Name (required for new students)", placeholder="Example: Aarav Sharma", key="p1_nname")

            if mode == "Quick Roster (No Biometric)":
                if st.button("Save Without Biometric", icon=":material/person_add:", type="primary", use_container_width=True):
                    if not nid.strip() or not nname.strip():
                        st.error("Enter both Student ID and Full Name.")
                    else:
                        save_student(nid.strip(), nname.strip(), embedding=None)
                        st.session_state.tracker = None
                        st.success(f"Enrolled {nname.strip()} with NO biometric (NULL embedding). You can add photos later.")
                        st.rerun()
            elif mode == "Enroll / Add Photos (1–5)":
                files = st.file_uploader("Upload 1 to 5 front-facing photos", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key="p1_multi_up")
                if st.button("Extract Embeddings & Save", icon=":material/face_retouching_natural:", type="primary", use_container_width=True):
                    if not nid.strip() or not files:
                        st.error("Enter Student ID and upload 1–5 clear photos.")
                    else:
                        analyzer, err = cached_face_analyzer()
                        if err:
                            st.error(err)
                        else:
                            existing = {s["student_id"]: s for s in load_all_students()}
                            if nid.strip() not in existing:
                                if not nname.strip():
                                    st.error("Enter Full Name for a new student.")
                                    st.stop()
                                save_student(nid.strip(), nname.strip(), embedding=None)
                            added, skipped = 0, 0
                            for f in files[:5]:
                                arr = np.asarray(bytearray(f.getvalue()), dtype=np.uint8)
                                bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                                dets = detect_faces_in_bgr_image(analyzer, bgr)
                                if (
                                    len(dets) == 1
                                    and dets[0].embedding is not None
                                    and dets[0].det_score >= st.session_state.min_det_score
                                    and dets[0].face_size_px >= st.session_state.min_face_size_px
                                ):
                                    add_student_embedding(nid.strip(), dets[0].embedding, dets[0].det_score, dets[0].face_size_px, max_embeddings=5)
                                    added += 1
                                else:
                                    skipped += 1
                            st.session_state.tracker = None
                            if added > 0:
                                st.success(f"Stored {added} normalized 512-D embedding(s) for {nid.strip()} ({skipped} skipped for quality/multi-face). Raw photos discarded.")
                                st.rerun()
                            else:
                                st.error("No usable single-face photos passed quality checks.")
            else:
                snap = st.camera_input("Capture Enrollment Portrait", key="p1_cam_enroll")
                if snap is not None and st.button("Save Camera Embedding", icon=":material/photo_camera:", type="primary", use_container_width=True):
                    if not nid.strip():
                        st.error("Enter Student ID first.")
                    else:
                        analyzer, err = cached_face_analyzer()
                        if err:
                            st.error(err)
                        else:
                            existing = {s["student_id"]: s for s in load_all_students()}
                            if nid.strip() not in existing:
                                if not nname.strip():
                                    st.error("Enter Full Name for a new student.")
                                    st.stop()
                                save_student(nid.strip(), nname.strip(), embedding=None)
                            arr = np.asarray(bytearray(snap.getvalue()), dtype=np.uint8)
                            bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                            dets = detect_faces_in_bgr_image(analyzer, bgr)
                            if len(dets) == 1 and dets[0].embedding is not None:
                                total_cnt = add_student_embedding(nid.strip(), dets[0].embedding, dets[0].det_score, dets[0].face_size_px, max_embeddings=5)
                                st.session_state.tracker = None
                                st.success(f"Added embedding ({total_cnt}/5 stored) for {nid.strip()}. Raw photo discarded.")
                                st.rerun()
                            else:
                                st.error("Ensure exactly one clear face is visible.")

    with r_r:
        with st.container(border=True):
            st.markdown('<p class="sec-title">Enrolled Student Directory</p>', unsafe_allow_html=True)
            roster = load_all_students()
            if not roster:
                st.info("Roster is empty. Enroll students on the left.")
            else:
                rdf = pd.DataFrame([
                    {
                        "Student ID": r["student_id"],
                        "Full Name": r["name"],
                        "Biometric Status": (
                            f"Enrolled ({r['embedding_count']}/5 vectors · 0 raw photos)"
                            if r["biometric_enrolled"]
                            else "Not Enrolled (NULL · Excluded from matching)"
                        ),
                        "Added": r["created_at"],
                    }
                    for r in roster
                ])
                st.dataframe(rdf, use_container_width=True, hide_index=True)

                m1, m2 = st.columns([2.2, 1], vertical_alignment="center")
                opts = {f"{r['name']} ({r['student_id']})": r["student_id"] for r in roster}
                with m1:
                    del_pick = st.selectbox("Select Student to Remove", list(opts.keys()), label_visibility="collapsed", key="p1_del_pick")
                with m2:
                    if st.button("Remove Student", icon=":material/delete:", use_container_width=True, key="p1_del_btn"):
                        delete_student(opts[del_pick])
                        st.session_state.tracker = None
                        st.toast("Student removed.")
                        st.rerun()