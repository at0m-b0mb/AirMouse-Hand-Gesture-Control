"""MediaPipe hand-tracking wrapper (Tasks API, mediapipe >= 0.10.18)."""
import time
import urllib.request
from pathlib import Path
import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision as mp_vision

_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
)
_MODEL_PATH = Path(__file__).parent.parent / "hand_landmarker.task"
_CONNECTIONS = mp_vision.HandLandmarksConnections.HAND_CONNECTIONS


def _ensure_model() -> str:
    if not _MODEL_PATH.exists():
        print("[HandTracker] Downloading hand landmarker model (~8 MB) ...")
        try:
            urllib.request.urlretrieve(_MODEL_URL, _MODEL_PATH)
            print(f"[HandTracker] Model saved to {_MODEL_PATH}")
        except Exception as exc:
            _MODEL_PATH.unlink(missing_ok=True)
            raise RuntimeError(
                f"Model download failed: {exc}\n"
                "Check your internet connection, then retry.\n"
                f"Or download manually from {_MODEL_URL}\n"
                f"and save to {_MODEL_PATH}"
            ) from exc
    return str(_MODEL_PATH)


class HandTracker:
    """Wraps MediaPipe HandLandmarker for VIDEO mode (real-time camera)."""

    def __init__(self, max_hands: int = 1, det_conf: float = 0.75, track_conf: float = 0.5):
        model_path = _ensure_model()
        opts = mp_vision.HandLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=model_path),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_hands=max_hands,
            min_hand_detection_confidence=det_conf,
            min_hand_presence_confidence=det_conf,
            min_tracking_confidence=track_conf,
        )
        self._lm = mp_vision.HandLandmarker.create_from_options(opts)
        self._ts: int = 0  # strictly-increasing timestamp (ms)

    def process(self, frame):
        """Return (results, list_of_landmark_lists) for a BGR frame.

        Each landmark list is a list of 21 NormalizedLandmark objects with .x/.y/.z.
        """
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        self._ts = max(self._ts + 1, int(time.time() * 1000))
        results = self._lm.detect_for_video(mp_img, self._ts)
        lm_lists = list(results.hand_landmarks) if results.hand_landmarks else []
        return results, lm_lists

    def draw(self, frame, results) -> None:
        if not results.hand_landmarks:
            return
        h, w = frame.shape[:2]
        for hand_lm in results.hand_landmarks:
            for conn in _CONNECTIONS:
                a, b = hand_lm[conn.start], hand_lm[conn.end]
                cv2.line(frame,
                         (int(a.x * w), int(a.y * h)),
                         (int(b.x * w), int(b.y * h)),
                         (0, 200, 200), 2)
            for lm in hand_lm:
                cv2.circle(frame, (int(lm.x * w), int(lm.y * h)), 4, (0, 255, 0), -1)

    def close(self) -> None:
        self._lm.close()
