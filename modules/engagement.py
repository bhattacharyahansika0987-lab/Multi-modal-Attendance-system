from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from modules.attendance import FaceDetection

# Honest defaults for 5-point InsightFace keypoint head-pose proxy
DEFAULT_MAX_YAW_DEG = 25.0
DEFAULT_MAX_PITCH_DEG = 20.0
NEUTRAL_NOSE_VERTICAL_RATIO = 0.48


@dataclass(frozen=True)
class HeadPoseEstimate:
    """Estimated head orientation for a single detected face (roll-invariant)."""

    yaw_deg: float          # Positive = turned right, negative = turned left
    pitch_deg: float        # Positive = tilted down, negative = tilted up
    facing_front: bool
    alignment_score: float  # 0..100 continuous closeness to front-facing (0, 0)


@dataclass(frozen=True)
class SnapshotAttentionSummary:
    """
    Honest snapshot-level attention metrics derived solely from detected
    facial keypoints. Audio is explicitly reported as unmeasured unless
    live audio capture is provided.
    """

    measured: bool
    faces_evaluated: int
    faces_facing_front: int
    facing_front_ratio: float | None        # Percentage 0..100 (None if no usable faces)
    mean_alignment_score: float | None      # Percentage 0..100 (None if no usable faces)
    mean_abs_yaw_deg: float | None
    mean_abs_pitch_deg: float | None
    audio_measured: bool
    audio_status: str                       # "Not measured" when mic capture is absent
    active_weights: dict[str, float]        # Renormalized weights summing to 1.0
    combined_attention_score: float | None  # Weighted score over measured modalities only


def renormalize_weights(
    requested_weights: dict[str, float],
    available_modalities: set[str],
) -> dict[str, float]:
    """
    Drops unmeasured modalities (e.g., audio when no microphone stream exists)
    and renormalizes remaining non-negative weights so they sum to 1.0.
    """
    active = {
        k: max(0.0, float(v))
        for k, v in requested_weights.items()
        if k in available_modalities
    }
    total = sum(active.values())
    if total <= 1e-9:
        if not available_modalities:
            return {}
        equal = round(1.0 / len(available_modalities), 4)
        return {k: equal for k in sorted(available_modalities)}
    return {k: round(v / total, 4) for k, v in active.items()}


def estimate_head_pose_from_kps(
    kps: np.ndarray | None,
    *,
    max_yaw_deg: float = DEFAULT_MAX_YAW_DEG,
    max_pitch_deg: float = DEFAULT_MAX_PITCH_DEG,
) -> HeadPoseEstimate | None:
    """
    Estimates approximate head yaw and pitch (in degrees) from InsightFace's
    5 facial keypoints: [left_eye, right_eye, nose, left_mouth, right_mouth].
    Returns None if keypoints are missing or degenerate.
    """
    if kps is None:
        return None
    pts = np.asarray(kps, dtype=np.float32)
    if pts.shape != (5, 2) or not np.all(np.isfinite(pts)):
        return None

    left_eye, right_eye, nose, left_mouth, right_mouth = pts
    eye_vec = right_eye - left_eye
    iod = float(np.linalg.norm(eye_vec))
    if iod < 5.0:
        return None

    # Local roll-invariant coordinate frame anchored at eye midpoint
    u_x = eye_vec / iod
    u_y = np.array([-u_x[1], u_x[0]], dtype=np.float32)

    eye_center = 0.5 * (left_eye + right_eye)
    mouth_center = 0.5 * (left_mouth + right_mouth)
    face_height_vec = mouth_center - eye_center

    # Ensure u_y points downward from eyes toward mouth
    if float(np.dot(face_height_vec, u_y)) < 0.0:
        u_y = -u_y

    v_dist = float(np.dot(face_height_vec, u_y))
    if v_dist < 5.0:
        return None

    nose_rel = nose - eye_center
    dx = float(np.dot(nose_rel, u_x))
    dy = float(np.dot(nose_rel, u_y))

    # Yaw: horizontal displacement of nose relative to half inter-ocular distance
    yaw_deg = float(np.clip((dx / (0.5 * iod)) * 45.0, -90.0, 90.0))

    # Pitch: vertical shift of nose relative to neutral eye-to-mouth proportion
    nose_ratio = dy / v_dist
    pitch_deg = float(np.clip(((nose_ratio - NEUTRAL_NOSE_VERTICAL_RATIO) / 0.35) * 45.0, -60.0, 60.0))

    facing_front = (abs(yaw_deg) <= max_yaw_deg) and (abs(pitch_deg) <= max_pitch_deg)
    yaw_pen = min(1.0, abs(yaw_deg) / 45.0)
    pitch_pen = min(1.0, abs(pitch_deg) / 35.0)
    alignment = max(0.0, 100.0 * (1.0 - 0.5 * (yaw_pen + pitch_pen)))

    return HeadPoseEstimate(
        yaw_deg=round(yaw_deg, 1),
        pitch_deg=round(pitch_deg, 1),
        facing_front=facing_front,
        alignment_score=round(alignment, 1),
    )


def analyze_snapshot_attention(
    detections: Iterable[FaceDetection],
    *,
    min_det_score: float = 0.60,
    min_face_size_px: float = 40.0,
    max_yaw_deg: float = DEFAULT_MAX_YAW_DEG,
    max_pitch_deg: float = DEFAULT_MAX_PITCH_DEG,
    requested_weights: dict[str, float] | None = None,
) -> SnapshotAttentionSummary:
    """
    Computes honest visual attention proxies from a snapshot's detected faces.
    Audio is not captured on Streamlit Cloud CPU without WebRTC and is reported
    explicitly as 'Not measured', with weights renormalized over measured signals.
    """
    req_w = requested_weights or {
        "facing_front": 0.50,
        "head_alignment": 0.25,
        "audio": 0.25,
    }

    poses: list[HeadPoseEstimate] = []
    for det in detections:
        if det.det_score < min_det_score or det.face_size_px < min_face_size_px:
            continue
        est = estimate_head_pose_from_kps(
            det.kps,
            max_yaw_deg=max_yaw_deg,
            max_pitch_deg=max_pitch_deg,
        )
        if est is not None:
            poses.append(est)

    if not poses:
        return SnapshotAttentionSummary(
            measured=False,
            faces_evaluated=0,
            faces_facing_front=0,
            facing_front_ratio=None,
            mean_alignment_score=None,
            mean_abs_yaw_deg=None,
            mean_abs_pitch_deg=None,
            audio_measured=False,
            audio_status="Not measured",
            active_weights={},
            combined_attention_score=None,
        )

    front_cnt = sum(1 for p in poses if p.facing_front)
    front_ratio = round((front_cnt / len(poses)) * 100.0, 1)
    mean_align = round(float(np.mean([p.alignment_score for p in poses])), 1)
    mean_yaw = round(float(np.mean([abs(p.yaw_deg) for p in poses])), 1)
    mean_pitch = round(float(np.mean([abs(p.pitch_deg) for p in poses])), 1)

    # Renormalize strictly across measured modalities (audio excluded)
    active_w = renormalize_weights(req_w, {"facing_front", "head_alignment"})
    combined = round(
        front_ratio * active_w.get("facing_front", 0.0)
        + mean_align * active_w.get("head_alignment", 0.0),
        1,
    )

    return SnapshotAttentionSummary(
        measured=True,
        faces_evaluated=len(poses),
        faces_facing_front=front_cnt,
        facing_front_ratio=front_ratio,
        mean_alignment_score=mean_align,
        mean_abs_yaw_deg=mean_yaw,
        mean_abs_pitch_deg=mean_pitch,
        audio_measured=False,
        audio_status="Not measured",
        active_weights=active_w,
        combined_attention_score=combined,
    )