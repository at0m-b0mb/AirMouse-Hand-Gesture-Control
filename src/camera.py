"""Camera auto-detection and setup."""
import cv2


def list_cameras(max_index: int = 6) -> list[tuple[int, int, int]]:
    """Probe indices 0..max_index-1. Returns [(index, width, height), ...]."""
    found = []
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                h, w = frame.shape[:2]
                found.append((idx, w, h))
        cap.release()
    return found


def detect_camera(preferred: int = -1) -> int:
    """Return a working camera index, scanning 0-5 if preferred=-1."""
    if preferred >= 0:
        cap = cv2.VideoCapture(preferred)
        if cap.isOpened():
            cap.release()
            print(f"[Camera] Using configured index {preferred}")
            return preferred
        cap.release()
        print(f"[Camera] Index {preferred} not available, scanning...")

    for idx in range(6):
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            ret, _ = cap.read()
            cap.release()
            if ret:
                print(f"[Camera] Auto-detected camera at index {idx}")
                return idx
        cap.release()

    raise RuntimeError(
        "No camera found.\n"
        "  • Make sure a webcam is connected.\n"
        "  • On macOS, grant Camera access to Terminal in\n"
        "    System Settings → Privacy & Security → Camera."
    )


def open_camera(index: int, width: int = 1280, height: int = 720):
    """Open camera at requested resolution. Returns (VideoCapture, actual_w, actual_h)."""
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera index {index}.")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[Camera] Opened at {actual_w}x{actual_h}")
    # Warm up — discard first few frames while exposure settles
    for _ in range(5):
        cap.read()
    return cap, actual_w, actual_h
