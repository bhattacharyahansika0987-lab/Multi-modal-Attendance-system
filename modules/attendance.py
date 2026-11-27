from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

import numpy as np

# Canonical Phase 1 per-observation and per-student states
STATE_PRESENT = "PRESENT"
STATE_ABSENT = "ABSENT"
STATE_NEEDS_REVIEW = "NEEDS REVIEW"
STATE_UNKNOWN = "UNKNOWN"
STATE_LOW_QUALITY = "LOW QUALITY"
STATE_AMBIGUOUS = "AMBIGUOUS"

VALID_OVERRIDE_STATES = {STATE_PRESENT, STATE_ABSENT}


@dataclass(frozen=True)
class FaceDetection:
    """Normalized detector output for a single face in a snapshot."""

    embedding: np.ndarray | None
    det_score: float
    bbox: tuple[float, float, float, float]  # (x1, y1, x2, y2)
    kps: np.ndarray | None = None  # Optional (5, 2) InsightFace facial keypoints

    @property
    def face_size_px(self) -> float:
        x1, y1, x2, y2 = self.bbox
        return float(max(0.0, min(x2 - x1, y2 - y1)))


@dataclass
class FaceObservation:
    """Result of evaluating a single detected face against the roster gallery."""

    snapshot_index: int
    timestamp: str
    state: str
    student_id: str | None = None
    student_name: str | None = None
    similarity: float = 0.0
    second_student_id: str | None = None
    second_student_name: str | None = None
    second_similarity: float = 0.0
    margin: float = 0.0
    det_score: float = 0.0
    face_size_px: float = 0.0
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    reason: str = ""


@dataclass
class StudentAttendanceSummary:
    """Aggregated attendance status for a single enrolled student."""

    student_id: str
    name: str
    biometric_enrolled: bool
    embedding_count: int
    observed_snapshots: int
    total_snapshots: int
    observation_ratio: float
    state: str
    manual_override: str | None = None
    override_reason: str = ""
    first_seen: str | None = None
    last_seen: str | None = None
    flagged_events: int = 0


def l2_normalize(vec: np.ndarray) -> np.ndarray:
    arr = np.asarray(vec, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(arr))
    if norm <= 1e-12:
        raise ValueError("Embedding vector has zero norm and cannot be normalized.")
    return arr / norm


def build_snapshot_schedule(
    duration_minutes: int,
    num_snapshots: int = 4,
    jitter_fraction: float = 0.20,
    seed: int | None = None,
) -> list[int]:
    """
    Schedules `num_snapshots` verification points across a lecture with
    controlled random jitter so students cannot game fixed timestamps.
    """
    duration = max(5, int(duration_minutes))
    count = max(1, min(int(num_snapshots), duration - 2))
    rng = random.Random(seed)
    interval = duration / (count + 1)
    max_jitter = interval * max(0.0, min(0.45, float(jitter_fraction)))

    points: list[int] = []
    for i in range(1, count + 1):
        base = interval * i
        offset = base + rng.uniform(-max_jitter, max_jitter)
        minute = int(round(offset))
        minute = max(1, min(duration - 1, minute))
        points.append(minute)

    points.sort()
    deduped: list[int] = []
    for p in points:
        if deduped and p <= deduped[-1]:
            p = min(duration - 1, deduped[-1] + 1)
        if not deduped or p > deduped[-1]:
            deduped.append(p)
    return deduped


def load_face_analyzer(
    model_name: str = "buffalo_sc",
    det_size: tuple[int, int] = (320, 320),
) -> tuple[Any | None, str | None]:
    """
    Lazy-loads InsightFace FaceAnalysis on CPU with friendly error reporting.
    Returns (analyzer_instance, None) on success or (None, user_friendly_error).
    """
    try:
        from insightface.app import FaceAnalysis
    except ImportError:
        return (
            None,
            "InsightFace is not installed. Run `pip install -r requirements.txt` (Python 3.11) to enable real face matching.",
        )
    except Exception as exc:
        return None, f"Could not import InsightFace: {exc}"

    try:
        analyzer = FaceAnalysis(name=model_name, providers=["CPUExecutionProvider"])
        analyzer.prepare(ctx_id=-1, det_size=det_size)
        return analyzer, None
    except Exception as exc:
        return (
            None,
            f"InsightFace model '{model_name}' failed to initialize (check network access for first-run download): {exc}",
        )


def detect_faces_in_bgr_image(analyzer: Any, bgr_image: np.ndarray) -> list[FaceDetection]:
    """Runs InsightFace multi-face detection + 5-point keypoints on a BGR image (RAM only)."""
    if analyzer is None or bgr_image is None or bgr_image.size == 0:
        return []

    raw_faces = analyzer.get(bgr_image)
    detections: list[FaceDetection] = []
    for f in raw_faces:
        bbox_arr = getattr(f, "bbox", None)
        if bbox_arr is None or len(bbox_arr) < 4:
            continue
        bbox = (float(bbox_arr[0]), float(bbox_arr[1]), float(bbox_arr[2]), float(bbox_arr[3]))
        score = float(getattr(f, "det_score", 0.0))
        emb = getattr(f, "normed_embedding", None)
        if emb is None:
            emb = getattr(f, "embedding", None)
        emb_arr = np.asarray(emb, dtype=np.float32) if emb is not None else None
        raw_kps = getattr(f, "kps", None)
        kps_arr = np.asarray(raw_kps, dtype=np.float32) if raw_kps is not None else None
        detections.append(FaceDetection(embedding=emb_arr, det_score=score, bbox=bbox, kps=kps_arr))
    return detections


class SustainedPresenceTracker:
    """
    Multi-snapshot, vectorized cosine face matcher with quality filtering,
    distinct-student ambiguity detection, minimum-observation attendance rules,
    and manual instructor overrides.
    """

    def __init__(
        self,
        roster_meta: Iterable[dict[str, Any]],
        roster_embeddings: dict[str, list[np.ndarray]],
        *,
        cosine_threshold: float = 0.45,
        ambiguity_margin: float = 0.08,
        min_det_score: float = 0.60,
        min_face_size_px: float = 40.0,
        min_observations: int = 2,
        min_observation_ratio: float = 0.50,
    ) -> None:
        self.cosine_threshold = float(cosine_threshold)
        self.ambiguity_margin = float(ambiguity_margin)
        self.min_det_score = float(min_det_score)
        self.min_face_size_px = float(min_face_size_px)
        self.min_observations = max(1, int(min_observations))
        self.min_observation_ratio = max(0.01, min(1.0, float(min_observation_ratio)))

        self.roster_meta: dict[str, dict[str, Any]] = {}
        gallery_rows: list[np.ndarray] = []
        self._gallery_sids: list[str] = []
        self._sid_to_indices: dict[str, list[int]] = {}
        self._embedding_counts: dict[str, int] = {}

        for student in roster_meta:
            sid = str(student["student_id"])
            enrolled = bool(student.get("biometric_enrolled", False))
            self.roster_meta[sid] = {
                "student_id": sid,
                "name": str(student["name"]),
                "biometric_enrolled": enrolled,
            }
            valid_vecs: list[np.ndarray] = []
            if enrolled:
                for raw_vec in roster_embeddings.get(sid, []):
                    if raw_vec is None:
                        continue
                    try:
                        norm_vec = l2_normalize(raw_vec)
                        valid_vecs.append(norm_vec)
                    except ValueError:
                        continue

            self._embedding_counts[sid] = len(valid_vecs)
            if enrolled and valid_vecs:
                idxs: list[int] = []
                for vec in valid_vecs:
                    idxs.append(len(gallery_rows))
                    gallery_rows.append(vec)
                    self._gallery_sids.append(sid)
                self._sid_to_indices[sid] = idxs
            else:
                self.roster_meta[sid]["biometric_enrolled"] = False

        if gallery_rows:
            self._gallery_matrix: np.ndarray | None = np.vstack(gallery_rows).astype(np.float32)
        else:
            self._gallery_matrix = None

        self.total_snapshots: int = 0
        self.observations: list[FaceObservation] = []
        self._clean_hits: dict[str, set[int]] = {sid: set() for sid in self.roster_meta}
        self._flagged_events: dict[str, int] = {sid: 0 for sid in self.roster_meta}
        self._first_seen: dict[str, str] = {}
        self._last_seen: dict[str, str] = {}
        self._manual_overrides: dict[str, tuple[str, str]] = {}

    @property
    def gallery_size(self) -> int:
        return 0 if self._gallery_matrix is None else int(self._gallery_matrix.shape[0])

    def process_snapshot(
        self,
        detections: list[FaceDetection],
        timestamp: str | None = None,
    ) -> list[FaceObservation]:
        """Evaluates all faces detected in one snapshot using a single matrix multiply."""
        self.total_snapshots += 1
        snap_idx = self.total_snapshots
        ts = timestamp or datetime.now().strftime("%H:%M:%S")

        snap_obs: list[FaceObservation] = []
        valid_indices: list[int] = []
        valid_vectors: list[np.ndarray] = []

        for idx, det in enumerate(detections):
            fsize = det.face_size_px
            if det.det_score < self.min_det_score:
                snap_obs.append(
                    FaceObservation(
                        snapshot_index=snap_idx,
                        timestamp=ts,
                        state=STATE_LOW_QUALITY,
                        det_score=round(det.det_score, 3),
                        face_size_px=round(fsize, 1),
                        bbox=det.bbox,
                        reason=f"Detection score {det.det_score:.2f} < {self.min_det_score:.2f}",
                    )
                )
                continue
            if fsize < self.min_face_size_px:
                snap_obs.append(
                    FaceObservation(
                        snapshot_index=snap_idx,
                        timestamp=ts,
                        state=STATE_LOW_QUALITY,
                        det_score=round(det.det_score, 3),
                        face_size_px=round(fsize, 1),
                        bbox=det.bbox,
                        reason=f"Face size {fsize:.0f}px < {self.min_face_size_px:.0f}px",
                    )
                )
                continue
            if det.embedding is None:
                snap_obs.append(
                    FaceObservation(
                        snapshot_index=snap_idx,
                        timestamp=ts,
                        state=STATE_LOW_QUALITY,
                        det_score=round(det.det_score, 3),
                        face_size_px=round(fsize, 1),
                        bbox=det.bbox,
                        reason="Missing face embedding from detector",
                    )
                )
                continue
            try:
                valid_vectors.append(l2_normalize(det.embedding))
                valid_indices.append(idx)
            except ValueError:
                snap_obs.append(
                    FaceObservation(
                        snapshot_index=snap_idx,
                        timestamp=ts,
                        state=STATE_LOW_QUALITY,
                        det_score=round(det.det_score, 3),
                        face_size_px=round(fsize, 1),
                        bbox=det.bbox,
                        reason="Zero-norm embedding rejected",
                    )
                )

        if valid_vectors:
            if self._gallery_matrix is None:
                for det_idx in valid_indices:
                    det = detections[det_idx]
                    snap_obs.append(
                        FaceObservation(
                            snapshot_index=snap_idx,
                            timestamp=ts,
                            state=STATE_UNKNOWN,
                            det_score=round(det.det_score, 3),
                            face_size_px=round(det.face_size_px, 1),
                            bbox=det.bbox,
                            reason="No biometrically enrolled students in gallery",
                        )
                    )
            else:
                query_matrix = np.vstack(valid_vectors).astype(np.float32)
                sim_matrix = query_matrix @ self._gallery_matrix.T

                for row_i, det_idx in enumerate(valid_indices):
                    det = detections[det_idx]
                    row_sims = sim_matrix[row_i]

                    per_student_scores: list[tuple[str, float]] = [
                        (sid, float(np.max(row_sims[col_idxs])))
                        for sid, col_idxs in self._sid_to_indices.items()
                    ]
                    per_student_scores.sort(key=lambda item: item[1], reverse=True)

                    top1_sid, top1_sim = per_student_scores[0]
                    top1_name = self.roster_meta[top1_sid]["name"]
                    if len(per_student_scores) > 1:
                        top2_sid, top2_sim = per_student_scores[1]
                        top2_name = self.roster_meta[top2_sid]["name"]
                        margin = top1_sim - top2_sim
                    else:
                        top2_sid, top2_name, top2_sim = None, None, -1.0
                        margin = 1.0

                    if top1_sim < self.cosine_threshold:
                        snap_obs.append(
                            FaceObservation(
                                snapshot_index=snap_idx,
                                timestamp=ts,
                                state=STATE_UNKNOWN,
                                similarity=round(top1_sim, 4),
                                det_score=round(det.det_score, 3),
                                face_size_px=round(det.face_size_px, 1),
                                bbox=det.bbox,
                                reason=f"Best similarity {top1_sim:.3f} < threshold {self.cosine_threshold:.2f}",
                            )
                        )
                    elif top2_sid is not None and margin < self.ambiguity_margin:
                        self._flagged_events[top1_sid] = self._flagged_events.get(top1_sid, 0) + 1
                        self._flagged_events[top2_sid] = self._flagged_events.get(top2_sid, 0) + 1
                        snap_obs.append(
                            FaceObservation(
                                snapshot_index=snap_idx,
                                timestamp=ts,
                                state=STATE_AMBIGUOUS,
                                student_id=top1_sid,
                                student_name=top1_name,
                                similarity=round(top1_sim, 4),
                                second_student_id=top2_sid,
                                second_student_name=top2_name,
                                second_similarity=round(top2_sim, 4),
                                margin=round(margin, 4),
                                det_score=round(det.det_score, 3),
                                face_size_px=round(det.face_size_px, 1),
                                bbox=det.bbox,
                                reason=(
                                    f"Margin {margin:.3f} < {self.ambiguity_margin:.2f} "
                                    f"between {top1_name} ({top1_sim:.3f}) and {top2_name} ({top2_sim:.3f})"
                                ),
                            )
                        )
                    else:
                        self._clean_hits.setdefault(top1_sid, set()).add(snap_idx)
                        if top1_sid not in self._first_seen:
                            self._first_seen[top1_sid] = ts
                        self._last_seen[top1_sid] = ts
                        snap_obs.append(
                            FaceObservation(
                                snapshot_index=snap_idx,
                                timestamp=ts,
                                state=STATE_PRESENT,
                                student_id=top1_sid,
                                student_name=top1_name,
                                similarity=round(top1_sim, 4),
                                second_student_id=top2_sid,
                                second_student_name=top2_name,
                                second_similarity=round(top2_sim, 4) if top2_sid else 0.0,
                                margin=round(margin, 4),
                                det_score=round(det.det_score, 3),
                                face_size_px=round(det.face_size_px, 1),
                                bbox=det.bbox,
                                reason="Verified biometric match",
                            )
                        )

        self.observations.extend(snap_obs)
        return snap_obs

    def apply_manual_override(self, student_id: str, final_state: str, reason: str) -> None:
        if final_state not in VALID_OVERRIDE_STATES:
            raise ValueError(f"Override state must be one of {VALID_OVERRIDE_STATES}")
        if not reason or not reason.strip():
            raise ValueError("A non-empty override reason is required.")
        if student_id not in self.roster_meta:
            raise KeyError(f"Unknown student_id: {student_id}")
        self._manual_overrides[student_id] = (final_state, reason.strip())

    def get_student_summaries(self) -> list[StudentAttendanceSummary]:
        summaries: list[StudentAttendanceSummary] = []
        for sid, meta in sorted(self.roster_meta.items()):
            obs = len(self._clean_hits.get(sid, set()))
            ratio = (obs / self.total_snapshots) if self.total_snapshots > 0 else 0.0
            flags = self._flagged_events.get(sid, 0)

            override = self._manual_overrides.get(sid)
            if override is not None:
                final_state, override_reason = override
                manual_flag = final_state
            else:
                manual_flag = None
                override_reason = ""
                if self.total_snapshots == 0:
                    final_state = STATE_ABSENT
                elif obs >= self.min_observations or (obs > 0 and ratio >= self.min_observation_ratio):
                    final_state = STATE_PRESENT
                elif obs > 0 or flags > 0:
                    final_state = STATE_NEEDS_REVIEW
                else:
                    final_state = STATE_ABSENT

            summaries.append(
                StudentAttendanceSummary(
                    student_id=sid,
                    name=meta["name"],
                    biometric_enrolled=meta["biometric_enrolled"],
                    embedding_count=self._embedding_counts.get(sid, 0),
                    observed_snapshots=obs,
                    total_snapshots=self.total_snapshots,
                    observation_ratio=round(ratio * 100.0, 1),
                    state=final_state,
                    manual_override=manual_flag,
                    override_reason=override_reason,
                    first_seen=self._first_seen.get(sid),
                    last_seen=self._last_seen.get(sid),
                    flagged_events=flags,
                )
            )
        return summaries


def build_demo_snapshot_batch(
    roster_meta: list[dict[str, Any]],
    roster_embeddings: dict[str, list[np.ndarray]],
) -> list[FaceDetection]:
    """DEMO MODE ONLY: synthetic detection batch with sample keypoints."""
    enrolled_sids = [
        s["student_id"]
        for s in roster_meta
        if s.get("biometric_enrolled") and roster_embeddings.get(s["student_id"])
    ]
    rng = np.random.default_rng(42)
    dets: list[FaceDetection] = []

    front_kps = np.array(
        [[95.0, 100.0], [145.0, 100.0], [120.0, 124.0], [100.0, 150.0], [140.0, 150.0]],
        dtype=np.float32,
    )
    turned_kps = np.array(
        [[230.0, 95.0], [280.0, 95.0], [274.0, 120.0], [236.0, 145.0], [274.0, 145.0]],
        dtype=np.float32,
    )

    if enrolled_sids:
        base_v = l2_normalize(roster_embeddings[enrolled_sids[0]][0])
        noisy = l2_normalize(base_v + 0.08 * rng.standard_normal(base_v.shape).astype(np.float32))
        dets.append(FaceDetection(embedding=noisy, det_score=0.92, bbox=(60.0, 60.0, 180.0, 180.0), kps=front_kps))

    if len(enrolled_sids) >= 2:
        v1 = l2_normalize(roster_embeddings[enrolled_sids[0]][0])
        v2 = l2_normalize(roster_embeddings[enrolled_sids[1]][0])
        midpoint = l2_normalize(0.51 * v1 + 0.49 * v2)
        dets.append(FaceDetection(embedding=midpoint, det_score=0.88, bbox=(200.0, 60.0, 310.0, 170.0), kps=turned_kps))

    dets.append(FaceDetection(embedding=None, det_score=0.45, bbox=(10.0, 10.0, 35.0, 35.0), kps=None))

    unk = l2_normalize(rng.standard_normal(512).astype(np.float32))
    dets.append(FaceDetection(embedding=unk, det_score=0.85, bbox=(340.0, 70.0, 440.0, 170.0), kps=front_kps))
    return dets