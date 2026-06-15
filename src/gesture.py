"""Gesture recognition engine based on MediaPipe hand landmarks."""
import time
from enum import Enum, auto
from typing import Optional

# MediaPipe hand landmark indices
_WRIST = 0
_THUMB_TIP, _THUMB_IP = 4, 3
_IDX_TIP, _IDX_PIP = 8, 6
_MID_TIP, _MID_PIP = 12, 10
_RNG_TIP, _RNG_PIP = 16, 14
_PNK_TIP, _PNK_PIP = 20, 18
_MID_MCP = 9  # used as hand-size reference


class Gesture(Enum):
    NONE = auto()
    MOVE = auto()
    LEFT_CLICK = auto()
    RIGHT_CLICK = auto()
    SCROLL = auto()
    DRAG = auto()


def _dist(a, b) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5


def _up(lm, tip, pip) -> bool:
    """True when finger tip is above its PIP joint (finger extended)."""
    return lm[tip].y < lm[pip].y


class GestureEngine:
    def __init__(
        self,
        keyboard_toggle_hold: float = 1.0,
        click_threshold: float = 0.06,
        click_cooldown: float = 0.38,
    ):
        self._toggle_hold = keyboard_toggle_hold
        self._click_thresh = click_threshold
        self._click_cd = click_cooldown

        self._in_kb: bool = False
        self._palm_t: Optional[float] = None
        self._last_click: float = 0.0

    # ── public state ──────────────────────────────────────────────────────────

    @property
    def in_keyboard_mode(self) -> bool:
        return self._in_kb

    @property
    def palm_progress(self) -> float:
        """0-1 progress toward keyboard toggle (for UI progress bar)."""
        if self._palm_t is None:
            return 0.0
        return min(1.0, (time.time() - self._palm_t) / self._toggle_hold)

    # ── recognition ──────────────────────────────────────────────────────────

    def recognize(self, lm) -> Gesture:
        now = time.time()
        hs = _dist(lm[_WRIST], lm[_MID_MCP])
        if hs < 1e-6:
            return Gesture.NONE

        idx_up = _up(lm, _IDX_TIP, _IDX_PIP)
        mid_up = _up(lm, _MID_TIP, _MID_PIP)
        rng_up = _up(lm, _RNG_TIP, _RNG_PIP)
        pnk_up = _up(lm, _PNK_TIP, _PNK_PIP)
        all_up = idx_up and mid_up and rng_up and pnk_up

        pinch_idx = _dist(lm[_THUMB_TIP], lm[_IDX_TIP]) / hs
        pinch_mid = _dist(lm[_THUMB_TIP], lm[_MID_TIP]) / hs
        can_click = now - self._last_click > self._click_cd

        # Open palm held → toggle keyboard mode
        if all_up:
            if self._palm_t is None:
                self._palm_t = now
            elif now - self._palm_t >= self._toggle_hold:
                self._in_kb = not self._in_kb
                self._palm_t = None
                return Gesture.NONE
        else:
            self._palm_t = None

        # Left click: thumb pinches index (not middle)
        if can_click and pinch_idx < self._click_thresh and pinch_mid >= self._click_thresh:
            self._last_click = now
            return Gesture.LEFT_CLICK

        # Right click: thumb pinches middle finger
        if can_click and pinch_mid < self._click_thresh:
            self._last_click = now
            return Gesture.RIGHT_CLICK

        # Fist: all fingers curled → drag
        if not idx_up and not mid_up and not rng_up and not pnk_up:
            return Gesture.DRAG

        # Peace sign: index + middle only → scroll
        if idx_up and mid_up and not rng_up and not pnk_up:
            return Gesture.SCROLL

        # Index finger or open palm → move cursor
        if idx_up or all_up:
            return Gesture.MOVE

        return Gesture.NONE

    # ── coordinate helpers ────────────────────────────────────────────────────

    def cursor_pos(self, lm) -> tuple[float, float]:
        """Normalized (x, y) of index fingertip for cursor positioning."""
        return lm[_IDX_TIP].x, lm[_IDX_TIP].y

    def scroll_y(self, lm) -> float:
        """Normalized Y midpoint of index+middle tips for scroll direction."""
        return (lm[_IDX_TIP].y + lm[_MID_TIP].y) / 2.0
