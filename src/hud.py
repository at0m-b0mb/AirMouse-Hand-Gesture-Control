"""Heads-up display: themed status bar, help overlay, click ripples, toasts.

All colours come from src.branding so the HUD always matches the active theme.
"""
import time
import cv2
import numpy as np

from src import branding as b

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
    ("/  /  N", "Show-hide tips  /  never show"),
    ("P / Space", "Pause / freeze cursor"),
    ("C", "Calibrate hand range"),
    ("S", "Screenshot"),
    ("L", "Toggle landmarks"),
    ("F", "Toggle mirror flip"),
    ("G / I", "Toggle FPS / stats"),
    ("T / Y", "Always-on-top / cycle theme"),
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
        pad = 14
        # Background pill
        ov = frame.copy()
        cv2.rectangle(ov, (x - pad, y - th - pad), (x + tw + pad, y + pad),
                      b.bgr("surface2"), -1)
        cv2.addWeighted(ov, 0.88, frame, 0.12, 0, frame)
        # Colored left accent bar
        cv2.rectangle(frame, (x - pad, y - th - pad), (x - pad + 4, y + pad),
                      b.bgr("accent"), -1)
        # Message text
        cv2.putText(frame, self._msg, (x, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, b.bgr("accent"), 2, cv2.LINE_AA)


class Ripples:
    """Expanding-ring feedback at click locations (in frame coordinates)."""
    def __init__(self) -> None:
        self._items: list[dict] = []

    def add(self, x: int, y: int, color=None) -> None:
        self._items.append({"x": x, "y": y, "t": time.time(),
                            "color": color or b.bgr("accent")})

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


def draw_status_bar(frame, fps, engine, sensitivity, calibrated,
                    show_fps=True, frozen=False):
    h, w = frame.shape[:2]

    # Frosted-glass dark strip
    ov = frame.copy()
    cv2.rectangle(ov, (0, 0), (w, 36), b.bgr("surface"), -1)
    cv2.addWeighted(ov, 0.92, frame, 0.08, 0, frame)

    # Mode indicator
    if frozen:
        mode, color = "FROZEN", b.bgr("warning")
    elif engine.paused:
        mode, color = "PAUSED", b.bgr("warning")
    elif engine.in_keyboard_mode:
        mode, color = "KEYBOARD", b.bgr("accent")
    else:
        mode, color = "MOUSE", b.bgr("primary")

    # Glowing dot + mode label
    cv2.circle(frame, (16, 18), 6, color, -1, cv2.LINE_AA)
    cv2.circle(frame, (16, 18), 9, color, 1, cv2.LINE_AA)  # outer ring
    cv2.putText(frame, mode, (30, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)

    tag = f"sens {sensitivity:.1f}   {'◈ CAL' if calibrated else 'margin'}"
    cv2.putText(frame, tag, (170, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                b.bgr("muted"), 1, cv2.LINE_AA)
    if show_fps:
        cv2.putText(frame, f"{fps} fps", (w - 130, 24), cv2.FONT_HERSHEY_SIMPLEX,
                    0.45, b.bgr("muted"), 1, cv2.LINE_AA)
    cv2.putText(frame, "H help", (w - 66, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                b.bgr("muted"), 1, cv2.LINE_AA)

    # Colored bottom border
    cv2.line(frame, (0, 36), (w, 36), b.bgr("primary"), 2, cv2.LINE_AA)

    # Hold-progress bar (under the border)
    for prog, col in ((engine.palm_progress, b.bgr("accent")),
                      (engine.pause_progress, b.bgr("warning"))):
        if 0 < prog < 1.0:
            cv2.rectangle(frame, (0, 38), (int(w * prog), 42), col, -1)
            break


def draw_gesture_label(frame, label, nx, ny):
    if not label:
        return
    h, w = frame.shape[:2]
    x, y = int(nx * w), int(ny * h)

    # Glow rings — concentric soft halos around the cursor
    for radius, alpha in ((22, 0.08), (14, 0.14)):
        ov = frame.copy()
        cv2.circle(ov, (x, y), radius, b.bgr("accent"), -1, cv2.LINE_AA)
        cv2.addWeighted(ov, alpha, frame, 1 - alpha, 0, frame)

    # Solid cursor ring + centre dot
    cv2.circle(frame, (x, y), 9, b.bgr("accent"), 2, cv2.LINE_AA)
    cv2.circle(frame, (x, y), 3, b.bgr("accent"), -1, cv2.LINE_AA)

    # Gesture label with shadow
    cv2.putText(frame, label, (x + 14, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(frame, label, (x + 14, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, b.bgr("text"), 1, cv2.LINE_AA)


def draw_hints(frame, engine):
    h, w = frame.shape[:2]
    if engine.in_keyboard_mode:
        txt = "Pinch = press key   |   open palm (hold) = exit   |   H = help"
    else:
        txt = "Index=move  Pinch=click  R-pinch=right  Peace=scroll  Fist=drag  Palm=keys  Thumb=pause"
    cv2.putText(frame, txt, (6, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.36,
                b.bgr("muted"), 1, cv2.LINE_AA)


def draw_stats(frame, line: str):
    """Compact session-stats strip just under the status bar."""
    if not line:
        return
    h, w = frame.shape[:2]
    (tw, _), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
    x = w - tw - 12
    cv2.putText(frame, line, (x, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                b.bgr("secondary"), 1, cv2.LINE_AA)


def draw_watermark(frame):
    h, w = frame.shape[:2]
    txt = f"{b.APP_NAME} {b.VERSION}"
    (tw, _), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
    cv2.putText(frame, txt, (w - tw - 10, h - 24), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                b.bgr("muted"), 1, cv2.LINE_AA)


def draw_help(frame):
    h, w = frame.shape[:2]
    ov = frame.copy()
    cv2.rectangle(ov, (0, 0), (w, h), b.bgr("bg"), -1)
    cv2.addWeighted(ov, 0.86, frame, 0.14, 0, frame)

    x0 = int(w * 0.10)
    y = int(h * 0.11)
    cv2.putText(frame, f"{b.APP_NAME} — Quick Reference", (x0, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, b.bgr("accent"), 2, cv2.LINE_AA)
    y += 32
    for left, right in _HELP_LINES:
        if left in ("GESTURES", "HOTKEYS"):
            cv2.putText(frame, left, (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        b.bgr("secondary"), 2, cv2.LINE_AA)
        else:
            if left:
                cv2.putText(frame, left, (x0, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            b.bgr("text"), 1, cv2.LINE_AA)
            if right:
                cv2.putText(frame, right, (x0 + int(w * 0.28), y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, b.bgr("muted"), 1, cv2.LINE_AA)
        y += 24
    cv2.putText(frame, "Press H to close", (x0, int(h * 0.96)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, b.bgr("muted"), 1, cv2.LINE_AA)


_COACH_LINES = [
    ("Point", "index finger only  -  move the cursor"),
    ("Pinch", "thumb + index  -  left click"),
    ("Peace", "index + middle  -  scroll"),
    ("Fist",  "close your hand  -  drag"),
]


def draw_coach(frame, seconds_left=None):
    """First-run 'getting started' card. Explains the core gestures and how to
    reach the full guide. Dismissible — the caller decides when to stop drawing."""
    h, w = frame.shape[:2]
    cw, ch = 360, 196
    x0 = 16
    y0 = h - ch - 52          # sit above the hints line
    x1, y1 = x0 + cw, y0 + ch

    # Frosted panel
    ov = frame.copy()
    cv2.rectangle(ov, (x0, y0), (x1, y1), b.bgr("surface"), -1)
    cv2.addWeighted(ov, 0.90, frame, 0.10, 0, frame)
    # Accent left bar + subtle border
    cv2.rectangle(frame, (x0, y0), (x0 + 4, y1), b.bgr("primary"), -1)
    cv2.rectangle(frame, (x0, y0), (x1, y1), b.bgr("surface2"), 1, cv2.LINE_AA)

    # Title
    cv2.putText(frame, "Getting Started", (x0 + 16, y0 + 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.62, b.bgr("accent"), 2, cv2.LINE_AA)

    # Gesture lines
    yy = y0 + 58
    for tag, desc in _COACH_LINES:
        cv2.putText(frame, tag, (x0 + 16, yy), cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                    b.bgr("primary"), 2, cv2.LINE_AA)
        cv2.putText(frame, desc, (x0 + 86, yy), cv2.FONT_HERSHEY_SIMPLEX, 0.44,
                    b.bgr("text"), 1, cv2.LINE_AA)
        yy += 26

    # Footer controls
    cv2.line(frame, (x0 + 12, y1 - 36), (x1 - 12, y1 - 36), b.bgr("surface2"), 1, cv2.LINE_AA)
    cv2.putText(frame, "H = full guide    / = hide    N = never show",
                (x0 + 16, y1 - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.40,
                b.bgr("muted"), 1, cv2.LINE_AA)

    # Auto-dismiss countdown chip
    if seconds_left is not None and seconds_left > 0:
        chip = f"{int(seconds_left) + 1}s"
        (tw, _), _ = cv2.getTextSize(chip, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
        cv2.putText(frame, chip, (x1 - tw - 14, y0 + 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, b.bgr("muted"), 1, cv2.LINE_AA)


def draw_calibration(frame, stage_text, box=None):
    h, w = frame.shape[:2]
    ov = frame.copy()
    cv2.rectangle(ov, (0, 0), (w, h), b.bgr("bg"), -1)
    cv2.addWeighted(ov, 0.5, frame, 0.5, 0, frame)
    cv2.putText(frame, "CALIBRATION", (int(w * 0.5) - 110, int(h * 0.4)),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, b.bgr("primary"), 2, cv2.LINE_AA)
    cv2.putText(frame, stage_text, (int(w * 0.5) - 220, int(h * 0.5)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, b.bgr("text"), 1, cv2.LINE_AA)
    if box:
        x0, y0, x1, y1 = box
        cv2.rectangle(frame, (int(x0 * w), int(y0 * h)),
                      (int(x1 * w), int(y1 * h)), b.bgr("accent"), 2)
