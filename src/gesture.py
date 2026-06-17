"""Gesture recognition engine based on MediaPipe hand landmarks."""
import time
from enum import Enum, auto
from typing import Optional

# MediaPipe hand landmark indices
_WRIST = 0
_THUMB_TIP, _THUMB_IP, _THUMB_MCP = 4, 3, 2
_IDX_TIP, _IDX_PIP, _IDX_MCP = 8, 6, 5
_MID_TIP, _MID_PIP, _MID_MCP = 12, 10, 9
_RNG_TIP, _RNG_PIP = 16, 14
_PNK_TIP, _PNK_PIP, _PNK_MCP = 20, 18, 17


class Gesture(Enum):
    NONE = auto()
    MOVE = auto()
    LEFT_CLICK = auto()
    DOUBLE_CLICK = auto()
    RIGHT_CLICK = auto()
    MIDDLE_CLICK = auto()
    SCROLL = auto()
    DRAG = auto()


def _dist(a, b) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5


def _finger_up(lm, tip, pip) -> bool:
    return lm[tip].y < lm[pip].y


class GestureEngine:
    def __init__(
        self,
        keyboard_toggle_hold: float = 0.9,
        pause_toggle_hold: float = 0.7,
        click_threshold: float = 0.055,
        click_release: float = 0.085,
        double_click_window: float = 0.40,
        click_cooldown: float = 0.30,
        enable_middle_click: bool = False,
    ):
        self._kb_hold = keyboard_toggle_hold
        self._pause_hold = pause_toggle_hold
        self._click_engage = click_threshold
        self._click_release = click_release
        self._dbl_window = double_click_window
        self._click_cd = click_cooldown
        self._enable_middle = enable_middle_click

        self._in_kb = False
        self._paused = False

        self._palm_t: Optional[float] = None
        self._thumb_t: Optional[float] = None

        # edge-triggered pinch state
        self._l_engaged = False
        self._r_engaged = False
        self._m_engaged = False
        self._last_click_t = 0.0
        self._last_click_was_single = False

        self._label = ""

    # ── public state ──────────────────────────────────────────────────────────

    @property
    def in_keyboard_mode(self) -> bool:
        return self._in_kb

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def label(self) -> str:
        return self._label

    @property
    def palm_progress(self) -> float:
        if self._palm_t is None:
            return 0.0
        return min(1.0, (time.time() - self._palm_t) / self._kb_hold)

    @property
    def pause_progress(self) -> float:
        if self._thumb_t is None:
            return 0.0
        return min(1.0, (time.time() - self._thumb_t) / self._pause_hold)

    def force_keyboard(self, on: bool) -> None:
        self._in_kb = on

    def toggle_pause(self) -> None:
        self._paused = not self._paused

    # ── finger-pose helpers ───────────────────────────────────────────────────

    def _poses(self, lm):
        idx = _finger_up(lm, _IDX_TIP, _IDX_PIP)
        mid = _finger_up(lm, _MID_TIP, _MID_PIP)
        rng = _finger_up(lm, _RNG_TIP, _RNG_PIP)
        pnk = _finger_up(lm, _PNK_TIP, _PNK_PIP)
        return idx, mid, rng, pnk

    def _is_thumbs_up(self, lm) -> bool:
        idx, mid, rng, pnk = self._poses(lm)
        if idx or mid or rng or pnk:
            return False
        # thumb extended clearly above its IP joint and the index MCP
        return lm[_THUMB_TIP].y < lm[_THUMB_IP].y - 0.02 and \
               lm[_THUMB_TIP].y < lm[_IDX_MCP].y

    # ── recognition ──────────────────────────────────────────────────────────

    def recognize(self, lm) -> Gesture:
        now = time.time()
        hs = _dist(lm[_WRIST], lm[_MID_MCP])
        if hs < 1e-6:
            return Gesture.NONE

        idx_up, mid_up, rng_up, pnk_up = self._poses(lm)
        all_up = idx_up and mid_up and rng_up and pnk_up

        # ── Thumbs-up held → toggle pause ─────────────────────────────────────
        if self._is_thumbs_up(lm):
            if self._thumb_t is None:
                self._thumb_t = now
            elif now - self._thumb_t >= self._pause_hold:
                self._paused = not self._paused
                self._thumb_t = None
            self._label = "PAUSED" if self._paused else "Thumbs-up..."
            return Gesture.NONE
        else:
            self._thumb_t = None

        if self._paused:
            self._label = "PAUSED (thumbs-up to resume)"
            return Gesture.NONE

        # ── Open palm held → toggle keyboard ──────────────────────────────────
        if all_up:
            if self._palm_t is None:
                self._palm_t = now
            elif now - self._palm_t >= self._kb_hold:
                self._in_kb = not self._in_kb
                self._palm_t = None
                self._label = "Keyboard ON" if self._in_kb else "Keyboard OFF"
                return Gesture.NONE
        else:
            self._palm_t = None

        pinch_idx = _dist(lm[_THUMB_TIP], lm[_IDX_TIP]) / hs
        pinch_mid = _dist(lm[_THUMB_TIP], lm[_MID_TIP]) / hs
        pinch_rng = _dist(lm[_THUMB_TIP], lm[_RNG_TIP]) / hs

        # ── Middle click (opt-in): thumb-ring pinch, ring the closest finger ──
        if self._enable_middle:
            if (pinch_rng < self._click_engage
                    and pinch_rng <= pinch_mid and pinch_rng <= pinch_idx):
                if not self._m_engaged and now - self._last_click_t > self._click_cd:
                    self._m_engaged = True
                    self._last_click_t = now
                    self._label = "Middle click"
                    return Gesture.MIDDLE_CLICK
            elif pinch_rng > self._click_release:
                self._m_engaged = False

        # ── Right click: edge-triggered thumb-middle pinch ───────────────────
        if pinch_mid < self._click_engage:
            if not self._r_engaged and now - self._last_click_t > self._click_cd:
                self._r_engaged = True
                self._last_click_t = now
                self._label = "Right click"
                return Gesture.RIGHT_CLICK
        elif pinch_mid > self._click_release:
            self._r_engaged = False

        # ── Left click / double-click: edge-triggered thumb-index pinch ──────
        if pinch_idx < self._click_engage and pinch_mid >= self._click_engage:
            if not self._l_engaged and now - self._last_click_t > self._click_cd:
                self._l_engaged = True
                is_double = (now - self._last_click_t < self._dbl_window) and \
                            self._last_click_was_single
                self._last_click_t = now
                if is_double:
                    self._last_click_was_single = False
                    self._label = "Double click"
                    return Gesture.DOUBLE_CLICK
                self._last_click_was_single = True
                self._label = "Left click"
                return Gesture.LEFT_CLICK
        elif pinch_idx > self._click_release:
            self._l_engaged = False

        # ── Fist → drag ───────────────────────────────────────────────────────
        if not idx_up and not mid_up and not rng_up and not pnk_up:
            self._label = "Drag"
            return Gesture.DRAG

        # ── Peace sign → scroll ──────────────────────────────────────────────
        if idx_up and mid_up and not rng_up and not pnk_up:
            self._label = "Scroll"
            return Gesture.SCROLL

        # ── Index (or palm) → move ───────────────────────────────────────────
        if idx_up or all_up:
            self._label = "Move"
            return Gesture.MOVE

        self._label = ""
        return Gesture.NONE

    # ── coordinate helpers ────────────────────────────────────────────────────

    def cursor_pos(self, lm) -> tuple[float, float]:
        return lm[_IDX_TIP].x, lm[_IDX_TIP].y

    def scroll_anchor(self, lm) -> tuple[float, float]:
        """Midpoint of index+middle tips for scroll tracking."""
        return ((lm[_IDX_TIP].x + lm[_MID_TIP].x) / 2.0,
                (lm[_IDX_TIP].y + lm[_MID_TIP].y) / 2.0)
