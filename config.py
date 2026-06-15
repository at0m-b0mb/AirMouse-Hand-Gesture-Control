import json
from dataclasses import dataclass, asdict
from pathlib import Path

_PATH = Path(__file__).parent / "config.json"


@dataclass
class Config:
    # Camera
    camera_index: int = -1          # -1 = auto-detect on first run

    # Cursor movement
    smoothing: float = 0.18        # EMA alpha: lower = smoother but laggier
    sensitivity: float = 1.3       # Speed multiplier
    dead_zone: float = 0.008       # Ignore movement below this (fraction of screen)
    cursor_margin: float = 0.12    # Edge fraction ignored for mapping; central 76% → full screen

    # Click detection
    click_threshold: float = 0.06  # Pinch distance to fire click (relative to hand size)
    click_cooldown: float = 0.38   # Seconds between consecutive clicks

    # Scrolling
    scroll_speed: int = 3

    # Keyboard toggle
    keyboard_toggle_hold: float = 1.0  # Seconds to hold open palm to toggle keyboard

    # Display
    flip: bool = True
    show_fps: bool = True
    show_landmarks: bool = True

    # Hand detection
    max_hands: int = 1
    detection_confidence: float = 0.75
    tracking_confidence: float = 0.5

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
