import json
from dataclasses import dataclass, asdict
from pathlib import Path

_PATH = Path(__file__).parent / "config.json"


@dataclass
class Config:
    # ── Camera ────────────────────────────────────────────────────────────────
    camera_index: int = -1          # -1 = auto-detect on first run
    cam_width: int = 1280
    cam_height: int = 720

    # ── Cursor smoothing (One Euro Filter) ────────────────────────────────────
    use_one_euro: bool = True
    oe_min_cutoff: float = 1.0      # lower → smoother when still
    oe_beta: float = 0.012          # higher → snappier when moving fast
    smoothing: float = 0.25         # EMA alpha (fallback if use_one_euro=False)

    sensitivity: float = 1.4        # Speed multiplier
    dead_zone: float = 0.006        # Ignore movement below this (fraction of screen)
    cursor_margin: float = 0.12     # Edge fraction ignored when not calibrated

    # ── Calibration (set via in-app 'c'; zeros = use cursor_margin) ───────────
    calib_x0: float = 0.0
    calib_y0: float = 0.0
    calib_x1: float = 0.0
    calib_y1: float = 0.0

    # ── Clicks ────────────────────────────────────────────────────────────────
    click_threshold: float = 0.055     # Pinch distance to engage click
    click_release: float = 0.085       # Pinch distance to release (hysteresis)
    double_click_window: float = 0.40  # Two clicks within this → double-click
    click_cooldown: float = 0.30       # Min seconds between discrete clicks

    # ── Scrolling ─────────────────────────────────────────────────────────────
    scroll_speed: int = 4
    horizontal_scroll: bool = True

    # ── Hold-to-toggle gestures ───────────────────────────────────────────────
    keyboard_toggle_hold: float = 0.9  # Open palm hold → toggle keyboard
    pause_toggle_hold: float = 0.7     # Thumbs-up hold → pause/resume

    # ── Virtual keyboard ──────────────────────────────────────────────────────
    key_press_cooldown: float = 0.40

    # ── Display ───────────────────────────────────────────────────────────────
    flip: bool = True
    show_fps: bool = True
    show_landmarks: bool = True
    show_help: bool = False
    window_scale: float = 1.0

    # ── Misc ──────────────────────────────────────────────────────────────────
    screenshot_dir: str = "screenshots"
    log_level: str = "INFO"

    # ── Hand detection ────────────────────────────────────────────────────────
    max_hands: int = 1
    detection_confidence: float = 0.7
    tracking_confidence: float = 0.5

    # ── helpers ───────────────────────────────────────────────────────────────
    @property
    def is_calibrated(self) -> bool:
        return self.calib_x1 > self.calib_x0 and self.calib_y1 > self.calib_y0

    def save(self) -> None:
        _PATH.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls) -> "Config":
        if _PATH.exists():
            try:
                raw = json.loads(_PATH.read_text())
                valid = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
                return cls(**valid)
            except Exception:
                pass
        return cls()
