import json
from dataclasses import dataclass, asdict
from pathlib import Path

_PATH = Path(__file__).parent / "config.json"

# ── Tuning profiles ────────────────────────────────────────────────────────────
# Named presets that set the "feel" of the cursor in one click. Only the keys
# listed here are overwritten when a profile is applied; everything else (camera,
# calibration, toggles) is left untouched.
PROFILES: dict[str, dict] = {
    "Balanced": dict(sensitivity=1.4, oe_beta=0.012, oe_min_cutoff=1.0,
                     cursor_margin=0.12, scroll_speed=4, click_threshold=0.055),
    "Precision": dict(sensitivity=1.0, oe_beta=0.006, oe_min_cutoff=0.7,
                      cursor_margin=0.14, scroll_speed=3, click_threshold=0.050),
    "Fast": dict(sensitivity=2.1, oe_beta=0.022, oe_min_cutoff=1.3,
                 cursor_margin=0.08, scroll_speed=6, click_threshold=0.060),
    "Presentation": dict(sensitivity=1.2, oe_beta=0.010, oe_min_cutoff=0.9,
                         cursor_margin=0.10, scroll_speed=5, click_threshold=0.070),
    "Gaming": dict(sensitivity=2.4, oe_beta=0.030, oe_min_cutoff=1.5,
                   cursor_margin=0.06, scroll_speed=7, click_threshold=0.058),
    "Accessibility": dict(sensitivity=0.8, oe_beta=0.004, oe_min_cutoff=0.5,
                          cursor_margin=0.16, scroll_speed=3, click_threshold=0.075),
}


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

    # Active tuning profile name (see PROFILES). "Custom" = user-tuned values.
    profile: str = "Balanced"

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
    enable_middle_click: bool = False  # Thumb+ring pinch → middle click (opt-in)

    # ── Scrolling ─────────────────────────────────────────────────────────────
    scroll_speed: int = 4
    horizontal_scroll: bool = True
    scroll_inertia: bool = False       # Keep scrolling (decaying) after the gesture ends
    scroll_friction: float = 0.85      # Per-frame inertia decay (0..1, higher = longer glide)

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
    show_stats: bool = False        # Show the live session-stats line in the HUD
    window_scale: float = 1.0
    always_on_top: bool = False     # Keep the AirMouse window above other windows
    theme: str = "Aurora"           # Visual theme (Aurora / Cyber / Mono)

    # ── Comfort ───────────────────────────────────────────────────────────────
    idle_pause_secs: float = 0.0    # Auto-pause after no hand for N seconds (0 = off)

    # ── Misc ──────────────────────────────────────────────────────────────────
    screenshot_dir: str = "screenshots"
    log_level: str = "INFO"
    sound_feedback: bool = False    # Play a brief click sound on gesture events

    # ── Onboarding / tutorial ─────────────────────────────────────────────────
    show_tutorial: bool = True      # Show the Studio welcome walkthrough on launch
    coach_overlay: bool = True      # Show the first-run coach card in the camera window

    # ── Hand detection ────────────────────────────────────────────────────────
    max_hands: int = 1
    detection_confidence: float = 0.7
    tracking_confidence: float = 0.5

    # ── helpers ───────────────────────────────────────────────────────────────
    @property
    def is_calibrated(self) -> bool:
        return self.calib_x1 > self.calib_x0 and self.calib_y1 > self.calib_y0

    def apply_profile(self, name: str) -> bool:
        """Overwrite tuning fields with a named preset. Returns True if applied."""
        preset = PROFILES.get(name)
        if not preset:
            return False
        for key, value in preset.items():
            setattr(self, key, value)
        self.profile = name
        return True

    def matches_profile(self, name: str) -> bool:
        """True if current tuning fields equal the named preset (within epsilon)."""
        preset = PROFILES.get(name)
        if not preset:
            return False
        return all(abs(getattr(self, k) - v) < 1e-9 if isinstance(v, float)
                   else getattr(self, k) == v
                   for k, v in preset.items())

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
