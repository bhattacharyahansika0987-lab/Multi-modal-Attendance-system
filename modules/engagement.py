import cv2
import time
import numpy as np
from collections import deque
from modules.database import log_engagement

try:
    import sounddevice as sd
    import webrtcvad
    AUDIO_AVAILABLE = True
except Exception:
    sd = None
    webrtcvad = None
    AUDIO_AVAILABLE = False


class MultimodalEngagementAnalyzer:
    def __init__(self, sample_rate: int = 16000):
        # 1. Visual setup: OpenCV Haar Cascades (100% offline, cross-platform)
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        self.eye_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_eye.xml"
        )
        self.prev_center = None
        self.last_active_time = time.time()

        # 2. Audio setup: Cloud-safe WebRTC VAD (100% offline, zero audio recorded)
        self.sample_rate = sample_rate
        self.vad = webrtcvad.Vad(2) if AUDIO_AVAILABLE else None
        self.speech_flags = deque(maxlen=150)
        self.audio_running = False
        self.stream = None

        # 3. Rolling score buffers for smooth multimodal fusion
        self.gaze_history = deque(maxlen=30)
        self.movement_history = deque(maxlen=30)

    def start_audio(self):
        """Starts background microphone monitoring if local audio hardware is available."""
        if self.audio_running or not AUDIO_AVAILABLE or self.vad is None:
            return

        self.audio_running = True
        frame_duration_ms = 30
        frame_size = int(self.sample_rate * frame_duration_ms / 1000)

        def audio_callback(indata, frames, time_info, status):
            if not self.audio_running:
                return
            pcm = (indata[:, 0] * 32767).astype(np.int16).tobytes()
            try:
                is_speech = self.vad.is_speech(pcm, self.sample_rate)
                self.speech_flags.append(1.0 if is_speech else 0.0)
            except Exception:
                pass

        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=frame_size,
                callback=audio_callback,
            )
            self.stream.start()
        except Exception as e:
            print(f"Warning: Microphone unavailable ({e}). Running visual-only mode.")
            self.audio_running = False

    def stop_audio(self):
        """Safely stops microphone stream."""
        self.audio_running = False
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def analyze_frame(self, frame: np.ndarray):
        """Computes visual head-pose/inactivity and fuses with live audio activity."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.15, minNeighbors=5, minSize=(60, 60)
        )

        gaze_score = 0.0
        movement_score = 0.0
        inactivity_sec = round(time.time() - self.last_active_time, 1)

        if len(faces) > 0:
            face_gazes = []
            for (x, y, w, h) in faces:
                roi_gray = gray[y : y + int(h * 0.6), x : x + w]
                eyes = self.eye_cascade.detectMultiScale(
                    roi_gray, scaleFactor=1.1, minNeighbors=4
                )
                if len(eyes) >= 2:
                    face_gazes.append(95.0)
                elif len(eyes) == 1:
                    face_gazes.append(75.0)
                else:
                    face_gazes.append(55.0)

            gaze_score = float(np.mean(face_gazes))

            # Movement & inactivity check using primary face centroid
            x, y, w, h = faces[0]
            curr_center = np.array([x + w / 2.0, y + h / 2.0])
            if self.prev_center is not None:
                delta = float(np.linalg.norm(curr_center - self.prev_center))
                if delta > 2.5:
                    self.last_active_time = time.time()
                    inactivity_sec = 0.0

                if inactivity_sec > 15.0:
                    movement_score = 35.0
                elif delta > 45.0:
                    movement_score = 55.0
                else:
                    movement_score = 88.0
            else:
                movement_score = 80.0
            self.prev_center = curr_center

        self.gaze_history.append(gaze_score)
        self.movement_history.append(movement_score)

        # Audio speech ratio (0-100%) with neutral 50% baseline when visual-only
        audio_score = (float(np.mean(self.speech_flags)) * 100.0) if self.speech_flags else 50.0

        # Multimodal Fusion Formula: 0.50 * Gaze + 0.25 * Movement + 0.25 * Audio
        smooth_gaze = float(np.mean(self.gaze_history))
        smooth_move = float(np.mean(self.movement_history))
        total_engagement = (0.50 * smooth_gaze) + (0.25 * smooth_move) + (0.25 * audio_score)

        return {
            "gaze_score": round(smooth_gaze, 1),
            "movement_score": round(smooth_move, 1),
            "audio_score": round(audio_score, 1),
            "total_engagement": round(total_engagement, 1),
            "inactivity_sec": inactivity_sec,
        }

    def save_window_metrics(self, session_id: str, metrics: dict):
        """Persists time-window engagement scores into SQLite."""
        log_engagement(
            session_id=session_id,
            gaze=metrics["gaze_score"],
            movement=metrics["movement_score"],
            audio=metrics["audio_score"],
            total=metrics["total_engagement"],
        )