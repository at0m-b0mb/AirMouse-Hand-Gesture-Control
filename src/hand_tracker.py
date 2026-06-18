"""MediaPipe hand-tracking wrapper (Tasks API, mediapipe >= 0.10.18)."""
import shutil
import ssl
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


def _ssl_context() -> ssl.SSLContext:
    """Build an SSL context with a real CA bundle.

    Many macOS Python builds ship without access to the system trust store
    (``ssl.get_default_verify_paths().cafile`` is None), which makes urllib fail
    with CERTIFICATE_VERIFY_FAILED. Using certifi's bundle fixes that.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _ensure_model() -> str:
    if _MODEL_PATH.exists():
        return str(_MODEL_PATH)
    print("[HandTracker] Downloading hand landmarker model (~8 MB) ...")
    tmp = _MODEL_PATH.with_name(_MODEL_PATH.name + ".part")
    try:
        req = urllib.request.Request(_MODEL_URL, headers={"User-Agent": "AirMouse"})
        with urllib.request.urlopen(req, context=_ssl_context(), timeout=60) as resp, \
                open(tmp, "wb") as out:
            shutil.copyfileobj(resp, out)
        tmp.replace(_MODEL_PATH)          # atomic — never leave a partial model
        print(f"[HandTracker] Model saved to {_MODEL_PATH}")
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        _MODEL_PATH.unlink(missing_ok=True)
        raise RuntimeError(
            f"Model download failed: {exc}\n\n"
            "This is usually a macOS Python SSL/certificate issue. Try one of:\n"
            "  • pip install --upgrade certifi          (then relaunch)\n"
            "  • run the 'Install Certificates.command' that ships with python.org Python\n"
            "  • download the model manually:\n"
            f"      curl -fL -o '{_MODEL_PATH}' \\\n          '{_MODEL_URL}'"
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
