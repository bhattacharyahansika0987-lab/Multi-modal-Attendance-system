from __future__ import annotations

import numpy as np
import pytest

from modules import database as db
from modules.attendance import (
    STATE_ABSENT,
    STATE_AMBIGUOUS,
    STATE_LOW_QUALITY,
    STATE_NEEDS_REVIEW,
    STATE_PRESENT,
    STATE_UNKNOWN,
    FaceDetection,
    SustainedPresenceTracker,
    build_snapshot_schedule,
    l2_normalize,
)


def _unit_vec(index: int, dim: int = 512) -> np.ndarray:
    v = np.zeros(dim, dtype=np.float32)
    v[index] = 1.0
    return v


def test_vectorized_matching_and_multi_embedding_best_match():
    roster_meta = [
        {"student_id": "S1", "name": "Aarav", "biometric_enrolled": True},
        {"student_id": "S2", "name": "Rohan", "biometric_enrolled": True},
        {"student_id": "S3", "name": "Unenrolled", "biometric_enrolled": False},
    ]
    roster_embs = {
        "S1": [_unit_vec(0), _unit_vec(1), _unit_vec(2)],
        "S2": [_unit_vec(10)],
        "S3": [_unit_vec(20)],  # Must be ignored because biometric_enrolled=False
    }
    tracker = SustainedPresenceTracker(
        roster_meta,
        roster_embs,
        cosine_threshold=0.45,
        ambiguity_margin=0.08,
        min_observations=2,
        min_observation_ratio=0.50,
    )
    assert tracker.gallery_size == 4  # S3 excluded

    obs1 = tracker.process_snapshot([
        FaceDetection(embedding=_unit_vec(2), det_score=0.95, bbox=(0, 0, 100, 100)),
        FaceDetection(embedding=_unit_vec(20), det_score=0.95, bbox=(120, 0, 220, 100)),
    ])
    assert obs1[0].state == STATE_PRESENT
    assert obs1[0].student_id == "S1"
    assert obs1[1].state == STATE_UNKNOWN
    assert obs1[1].student_id is None


def test_quality_filter_rejects_low_score_and_small_face():
    roster_meta = [{"student_id": "S1", "name": "Aarav", "biometric_enrolled": True}]
    roster_embs = {"S1": [_unit_vec(0)]}
    tracker = SustainedPresenceTracker(
        roster_meta, roster_embs, min_det_score=0.60, min_face_size_px=40.0
    )

    obs = tracker.process_snapshot([
        FaceDetection(embedding=_unit_vec(0), det_score=0.45, bbox=(0, 0, 100, 100)),
        FaceDetection(embedding=_unit_vec(0), det_score=0.95, bbox=(0, 0, 25, 80)),
    ])
    assert [o.state for o in obs] == [STATE_LOW_QUALITY, STATE_LOW_QUALITY]
    assert all(o.student_id is None for o in obs)


def test_ambiguity_margin_across_distinct_students():
    roster_meta = [
        {"student_id": "S1", "name": "Aarav", "biometric_enrolled": True},
        {"student_id": "S2", "name": "Rohan", "biometric_enrolled": True},
    ]
    v1, v2 = _unit_vec(0), _unit_vec(1)
    tracker = SustainedPresenceTracker(
        roster_meta,
        {"S1": [v1], "S2": [v2]},
        cosine_threshold=0.45,
        ambiguity_margin=0.08,
    )

    ambiguous_q = l2_normalize(0.72 * v1 + 0.69 * v2)
    obs = tracker.process_snapshot([
        FaceDetection(embedding=ambiguous_q, det_score=0.90, bbox=(0, 0, 100, 100)),
    ])
    assert obs[0].state == STATE_AMBIGUOUS
    assert obs[0].student_id == "S1"
    assert obs[0].second_student_id == "S2"
    assert obs[0].margin < 0.08

    summaries = {s.student_id: s for s in tracker.get_student_summaries()}
    assert summaries["S1"].state == STATE_NEEDS_REVIEW
    assert summaries["S2"].state == STATE_NEEDS_REVIEW


def test_minimum_observation_rule_and_manual_override():
    roster_meta = [
        {"student_id": "S1", "name": "Aarav", "biometric_enrolled": True},
        {"student_id": "S2", "name": "Rohan", "biometric_enrolled": True},
        {"student_id": "S3", "name": "Meera", "biometric_enrolled": True},
    ]
    tracker = SustainedPresenceTracker(
        roster_meta,
        {"S1": [_unit_vec(0)], "S2": [_unit_vec(1)], "S3": [_unit_vec(2)]},
        min_observations=2,
        min_observation_ratio=0.50,
    )
    tracker.process_snapshot([
        FaceDetection(_unit_vec(0), 0.9, (0, 0, 100, 100)),
        FaceDetection(_unit_vec(1), 0.9, (120, 0, 220, 100)),
    ])
    tracker.process_snapshot([FaceDetection(_unit_vec(0), 0.9, (0, 0, 100, 100))])
    tracker.process_snapshot([])
    tracker.process_snapshot([])

    summaries = {s.student_id: s for s in tracker.get_student_summaries()}
    assert summaries["S1"].state == STATE_PRESENT
    assert summaries["S1"].observed_snapshots == 2
    assert summaries["S2"].state == STATE_NEEDS_REVIEW
    assert summaries["S2"].observed_snapshots == 1
    assert summaries["S3"].state == STATE_ABSENT

    with pytest.raises(ValueError):
        tracker.apply_manual_override("S2", STATE_PRESENT, "   ")

    tracker.apply_manual_override("S2", STATE_PRESENT, "Visually confirmed in Lab Row 1")
    updated = {s.student_id: s for s in tracker.get_student_summaries()}
    assert updated["S2"].state == STATE_PRESENT
    assert updated["S2"].override_reason == "Visually confirmed in Lab Row 1"


def test_database_quick_roster_null_and_multi_embedding_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test_attendai.db")
    db.init_db()

    db.save_student("S101", "Quick Student", embedding=None)
    students = db.load_all_students()
    assert len(students) == 1
    assert students[0]["embedding"] is None
    assert students[0]["biometric_enrolled"] is False
    assert students[0]["embedding_count"] == 0

    for i in range(6):
        cnt = db.add_student_embedding("S101", _unit_vec(i), det_score=0.9, face_size_px=80.0, max_embeddings=5)
    assert cnt == 5

    meta, emb_map = db.load_roster_embeddings()
    assert meta[0]["biometric_enrolled"] is True
    assert len(emb_map["S101"]) == 5

    item_id = db.enqueue_review_item("SESS_1", 1, "S101", "Quick Student", STATE_AMBIGUOUS, "Close match")
    with pytest.raises(ValueError):
        db.resolve_review_item(item_id, STATE_PRESENT, "")
    db.resolve_review_item(item_id, STATE_PRESENT, "Verified at desk")
    rq = db.get_review_queue("SESS_1")
    assert rq.iloc[0]["status"] == "RESOLVED"
    assert rq.iloc[0]["override_reason"] == "Verified at desk"


def test_snapshot_schedule_bounds_and_jitter():
    sched = build_snapshot_schedule(duration_minutes=45, num_snapshots=4, jitter_fraction=0.20, seed=7)
    assert len(sched) == 4
    assert sched == sorted(sched)
    assert all(1 <= m <= 44 for m in sched)