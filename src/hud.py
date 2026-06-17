"""Heads-up display: status bar, help overlay, click ripples, toasts."""
import time
import cv2
import numpy as np

_HELP_LINES = [
    ("GESTURES", ""),
    ("Index finger", "Move cursor"),
    ("Pinch thumb+index", "Left click  (pinch twice = double-click)"),
    ("Pinch thumb+middle", "Right click"),
    ("Pinch thumb+ring", "Middle click  (opt-in)"),
    ("Peace sign", "Scroll  (move up/down, left/right)"),
    ("Fist", "Drag  (hold and move)"),
    ("Open palm (hold)", "Toggle virtual keyboard"),
    ("Thumbs-up (hold)", "Pause / resume control"),
    ("", ""),
    ("HOTKEYS", ""),
    ("H", "Toggle this help"),
    ("P", "Pause / resume"),
    ("C", "Calibrate hand range"),
    ("S", "Screenshot"),
    ("L", "Toggle landmarks"),
    ("F", "Toggle mirror flip"),
    ("G", "Toggle FPS counter"),
    ("T", "Toggle always-on-top"),
    ("+ / -", "Sensitivity up / down"),
    ("[ / ]", "Smoothing softer / snappier"),
    ("Q / ESC", "Quit"),
]


class Toast:
    """Transient on-screen message."""
    def __init__(self) -> None:
        self._msg = ""
        self._until = 0.0

    def show(self, msg: str, secs: float = 1.6) -> None:
        self._msg = msg
        self._until = time.time() + secs

    def draw(self, frame: np.ndarray) -> None:
        if time.time() > self._until or not self._msg:
            return
        h, w = frame.shape[:2]
        (tw, th), _ = cv2.getTextSize(self._msg, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        x = (w - tw) // 2
        y = int(h * 0.16)
        pad = 12
        ov = frame.copy()
        cv2.rectangle(ov, (x - pad, y - th - pad), (x + tw + pad, y + pad), (20, 20, 20), -1)
        cv2.addWeighted(ov, 0.7, frame, 0.3, 0, frame)
        cv2.putText(frame, self._msg, (x, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (80, 220, 255), 2, cv2.LINE_AA)


class Ripples:
    """Expanding-ring feedback at click locations (in frame coordinates)."""
    def __init__(self) -> None:
        self._items: list[dict] = []

    def add(self, x: int, y: int, color=(80, 220, 120)) -> None:
        self._items.append({"x": x, "y": y, "t": time.time(), "color": color})

    def draw(self, frame: np.ndarray) -> None:
        now = time.time()
        alive = []
        for r in self._items:
            age = now - r["t"]
            if age > 0.5:
                continue
            alive.append(r)
            radius = int(8 + age * 70)
            thick = max(1, int(3 * (1 - age / 0.5)))
            cv2.circle(frame, (r["x"], r["y"]), radius, r["color"], thick, cv2.LINE_AA)
        self._items = alive


def draw_status_bar(frame, fps, engine, sensitivity, calibrated, show_fps=True):
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (w, 34), (12, 12, 12), -1)

    if engine.paused:
        mode, color = "PAUSED", (60, 200, 255)
    elif engine.in_keyboard_mode:
        mode, color = "KEYBOARD", (70, 220, 70)
    else:
        mode, color = "MOUSE", (70, 150, 255)
    cv2.putText(frame, mode, (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.62, color, 2, cv2.LINE_AA)

    tag = f"sens {sensitivity:.1f}   {'CAL' if calibrated else 'margin'}"
    cv2.putText(frame, tag, (150, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 150, 150), 1, cv2.LINE_AA)
    if show_fps:
        cv2.putText(frame, f"FPS {fps}", (w - 150, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1, cv2.LINE_AA)
    cv2.putText(frame, "H help", (w - 70, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (110, 110, 110), 1, cv2.LINE_AA)

    # hold-progress bars
    for prog, col in ((engine.palm_progress, (60, 220, 170)),
                      (engine.pause_progress, (60, 200, 255))):
        if 0 < prog < 1.0:
            cv2.rectangle(frame, (0, 34), (int(w * prog), 39), col, -1)
            break


def draw_gesture_label(frame, label, nx, ny):
    if not label:
        return
    h, w = frame.shape[:2]
    x, y = int(nx * w), int(ny * h)
    cv2.putText(frame, label, (x + 14, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(frame, label, (x + 14, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.circle(frame, (x, y), 7, (0, 230, 255), 2, cv2.LINE_AA)


def draw_hints(frame, engine):
    h, w = frame.shape[:2]
    if engine.in_keyboard_mode:
        txt = "Pinch = press key   |   open palm (hold) = exit   |   H = help"
    else:
        txt = "Index=move  Pinch=click  R-pinch=right  Peace=scroll  Fist=drag  Palm=keys  Thumb=pause"
    cv2.putText(frame, txt, (6, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (120, 120, 120), 1, cv2.LINE_AA)


def draw_help(frame):
    h, w = frame.shape[:2]
    ov = frame.copy()
    cv2.rectangle(ov, (0, 0), (w, h), (8, 8, 12), -1)
    cv2.addWeighted(ov, 0.82, frame, 0.18, 0, frame)

    x0 = int(w * 0.10)
    y = int(h * 0.12)
    cv2.putText(frame, "AirMouse — Quick Reference", (x0, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (80, 220, 255), 2, cv2.LINE_AA)
    y += 34
    for left, right in _HELP_LINES:
        if left in ("GESTURES", "HOTKEYS"):
            cv2.putText(frame, left, (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (90, 200, 120), 2, cv2.LINE_AA)
        else:
            if left:
                cv2.putText(frame, left, (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            (230, 230, 230), 1, cv2.LINE_AA)
            if right:
                cv2.putText(frame, right, (x0 + int(w * 0.28), y), cv2.FONT_HERSHEY_SIMPLEX,
                            0.5, (170, 170, 170), 1, cv2.LINE_AA)
        y += 26
    cv2.putText(frame, "Press H to close", (x0, int(h * 0.95)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 120, 120), 1, cv2.LINE_AA)


def draw_calibration(frame, stage_text, box=None):
    h, w = frame.shape[:2]
    ov = frame.copy()
    cv2.rectangle(ov, (0, 0), (w, h), (8, 8, 20), -1)
    cv2.addWeighted(ov, 0.5, frame, 0.5, 0, frame)
    cv2.putText(frame, "CALIBRATION", (int(w * 0.5) - 110, int(h * 0.4)),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (60, 200, 255), 2, cv2.LINE_AA)
    cv2.putText(frame, stage_text, (int(w * 0.5) - 220, int(h * 0.5)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (230, 230, 230), 1, cv2.LINE_AA)
    if box:
        x0, y0, x1, y1 = box
        cv2.rectangle(frame, (int(x0 * w), int(y0 * h)),
                      (int(x1 * w), int(y1 * h)), (60, 200, 255), 2)
