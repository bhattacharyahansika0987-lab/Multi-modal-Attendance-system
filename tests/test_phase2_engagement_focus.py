from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from modules import database as db
from modules.attendance import FaceDetection
from modules.engagement import (
    analyze_snapshot_attention,
    estimate_head_pose_from_kps,
    renormalize_weights,
)
from modules.focus_component import compute_away_duration_sec


def _front_kps() -> np.ndarray:
    # [left_eye, right_eye, nose, left_mouth, right_mouth]
    return np.array(
        [[100.0, 100.0], [150.0, 100.0], [125.0, 124.0], [105.0, 150.0], [145.0, 150.0]],
        dtype=np.float32,
    )


def _turned_right_kps() -> np.ndarray:
    return np.array(
        [[100.0, 100.0], [150.0, 100.0], [145.0, 124.0], [105.0, 150.0], [145.0, 150.0]],
        dtype=np.float32,
    )


def _tilted_down_kps() -> np.ndarray:
    return np.array(
        [[100.0, 100.0], [150.0, 100.0], [125.0, 140.0], [105.0, 150.0], [145.0, 150.0]],
        dtype=np.float32,
    )


def test_head_pose_front_facing_vs_turned_and_tilted():
    front = estimate_head_pose_from_kps(_front_kps())
    assert front is not None
    assert front.facing_front is True
    assert abs(front.yaw_deg) < 2.0
    assert abs(front.pitch_deg) < 2.0
    assert front.alignment_score >= 95.0

    turned = estimate_head_pose_from_kps(_turned_right_kps())
    assert turned is not None
    assert turned.yaw_deg > 25.0
    assert turned.facing_front is False

    tilted = estimate_head_pose_from_kps(_tilted_down_kps())
    assert tilted is not None
    assert tilted.pitch_deg > 20.0
    assert tilted.facing_front is False

    assert estimate_head_pose_from_kps(None) is None


def test_renormalize_weights_drops_unmeasured_audio():
    req = {"facing_front": 50.0, "head_alignment": 25.0, "audio": 25.0}
    res = renormalize_weights(req, {"facing_front", "head_alignment"})
    assert "audio" not in res
    assert res["facing_front"] == pytest.approx(2 / 3, abs=1e-3)
    assert res["head_alignment"] == pytest.approx(1 / 3, abs=1e-3)
    assert sum(res.values()) == pytest.approx(1.0, abs=1e-3)


def test_snapshot_attention_honest_metrics_and_quality_filter():
    dets = [
        FaceDetection(embedding=None, det_score=0.95, bbox=(50, 50, 180, 180), kps=_front_kps()),
        FaceDetection(embedding=None, det_score=0.92, bbox=(200, 50, 330, 180), kps=_turned_right_kps()),
        # Low-quality face must be ignored
        FaceDetection(embedding=None, det_score=0.40, bbox=(0, 0, 100, 100), kps=_front_kps()),
    ]
    summary = analyze_snapshot_attention(dets, min_det_score=0.60, min_face_size_px=40.0)
    assert summary.measured is True
    assert summary.faces_evaluated == 2
    assert summary.faces_facing_front == 1
    assert summary.facing_front_ratio == 50.0
    assert summary.audio_measured is False
    assert summary.audio_status == "Not measured"
    assert "audio" not in summary.active_weights
    assert summary.combined_attention_score is not None

    empty_summary = analyze_snapshot_attention([])
    assert empty_summary.measured is False
    assert empty_summary.facing_front_ratio is None
    assert empty_summary.combined_attention_score is None


def test_compute_away_duration_from_real_iso_timestamps():
    dur = compute_away_duration_sec("2026-11-27T10:00:00.000Z", "2026-11-27T10:00:12.500Z")
    assert dur == 12.5
    assert compute_away_duration_sec("2026-11-27T10:00:00.000Z", None) is None
    assert Path("components/focus_monitor/index.html").exists()


def test_focus_events_dedup_real_duration_and_needs_review_no_auto_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test_phase2.db")
    db.init_db()
    db.save_student("S101", "Aarav Sharma", embedding=None)

    # First exit: AWAY then RETURNED with same event_uid (deduplicated, real duration computed)
    r1_away = db.record_focus_event(
        event_uid="EV_1",
        session_id="ROOM_ECE301_20261127",
        lobby_code="ECE301",
        student_id="S101",
        student_name="Aarav Sharma",
        event_type="tab_hidden",
        status="AWAY",
        left_at="2026-11-27T10:00:00.000Z",
        returned_at=None,
        review_threshold=2,
    )
    assert r1_away["total_exits"] == 1
    assert r1_away["review_queued"] is False

    r1_ret = db.record_focus_event(
        event_uid="EV_1",
        session_id="ROOM_ECE301_20261127",
        lobby_code="ECE301",
        student_id="S101",
        student_name="Aarav Sharma",
        event_type="tab_hidden",
        status="RETURNED",
        left_at="2026-11-27T10:00:00.000Z",
        returned_at="2026-11-27T10:00:15.400Z",
        review_threshold=2,
    )
    assert r1_ret["total_exits"] == 1
    assert r1_ret["duration_sec"] == 15.4
    assert r1_ret["review_queued"] is False

    # Second exit reaches review_threshold=2 -> queues NEEDS REVIEW, never auto-marks Absent
    r2_ret = db.record_focus_event(
        event_uid="EV_2",
        session_id="ROOM_ECE301_20261127",
        lobby_code="ECE301",
        student_id="S101",
        student_name="Aarav Sharma",
        event_type="window_blur",
        status="RETURNED",
        left_at="2026-11-27T10:05:00.000Z",
        returned_at="2026-11-27T10:05:10.000Z",
        review_threshold=2,
    )
    assert r2_ret["total_exits"] == 2
    assert r2_ret["total_away_sec"] == 25.4
    assert r2_ret["review_queued"] is True

    rq = db.get_review_queue("ROOM_ECE301_20261127", pending_only=True)
    assert len(rq) == 1
    assert rq.iloc[0]["flag_state"] == "NEEDS REVIEW"
    assert rq.iloc[0]["student_id"] == "S101"

    # Confirm no automatic Absent record was written to attendance
    df_att, _, _ = db.get_session_data("ROOM_ECE301_20261127")
    assert df_att.empty


def test_attention_snapshot_db_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test_phase2_att.db")
    db.init_db()
    db.log_attention_snapshot(
        session_id="SESS_P2",
        snapshot_index=1,
        faces_evaluated=4,
        faces_facing_front=3,
        facing_front_ratio=75.0,
        head_alignment_score=82.5,
        mean_abs_yaw_deg=11.2,
        mean_abs_pitch_deg=6.4,
        combined_attention_score=77.5,
        active_weights={"facing_front": 0.6667, "head_alignment": 0.3333},
        audio_measured=False,
        audio_status="Not measured",
    )
    df = db.get_attention_snapshots("SESS_P2")
    assert len(df) == 1
    assert df.iloc[0]["facing_front_ratio"] == 75.0
    assert df.iloc[0]["audio_status"] == "Not measured"