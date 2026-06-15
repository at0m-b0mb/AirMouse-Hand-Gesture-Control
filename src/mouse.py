"""Mouse and keyboard control via pynput (pyautogui as fallback)."""
import time
from typing import Optional

from src.filters import OneEuroFilter

try:
    from pynput.mouse import Button, Controller as _MC
    from pynput.keyboard import Key, Controller as _KC
    _mouse = _MC()
    _kbd = _KC()
    _PYNPUT = True
except Exception:
    _PYNPUT = False

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
    _PYAUTOGUI = True
except Exception:
    _PYAUTOGUI = False


def _do_move(x: int, y: int) -> None:
    if _PYNPUT:
        _mouse.position = (x, y)
    elif _PYAUTOGUI:
        pyautogui.moveTo(x, y)


def _do_click(button: str, n: int = 1) -> None:
    if _PYNPUT:
        btn = Button.left if button == "left" else Button.right
        _mouse.click(btn, n)
    elif _PYAUTOGUI:
        if button == "left":
            pyautogui.click(clicks=n)
        else:
            pyautogui.rightClick()


def _do_press() -> None:
    if _PYNPUT:
        _mouse.press(Button.left)
    elif _PYAUTOGUI:
        pyautogui.mouseDown()


def _do_release() -> None:
    if _PYNPUT:
        _mouse.release(Button.left)
    elif _PYAUTOGUI:
        pyautogui.mouseUp()


def _do_scroll(dx: int, dy: int) -> None:
    if _PYNPUT:
        _mouse.scroll(dx, dy)
    elif _PYAUTOGUI:
        if dy:
            pyautogui.scroll(dy)
        if dx:
            pyautogui.hscroll(dx)


def _do_type(char: str) -> None:
    if _PYNPUT:
        _kbd.type(char)
    elif _PYAUTOGUI:
        pyautogui.typewrite(char, interval=0)


class MouseController:
    """Smooth cursor + click/scroll/drag + typing. One Euro Filter by default."""

    def __init__(
        self,
        screen_w: int,
        screen_h: int,
        use_one_euro: bool = True,
        oe_min_cutoff: float = 1.0,
        oe_beta: float = 0.012,
        smoothing: float = 0.25,
        sensitivity: float = 1.4,
        dead_zone: float = 0.006,
        cursor_margin: float = 0.12,
        calib: Optional[tuple[float, float, float, float]] = None,
    ):
        self.sw = screen_w
        self.sh = screen_h
        self.use_oe = use_one_euro
        self.alpha = smoothing
        self.sens = sensitivity
        self.dz = dead_zone
        self.margin = cursor_margin
        self.calib = calib  # (x0, y0, x1, y1) normalized active box, or None

        self._fx = OneEuroFilter(oe_min_cutoff, oe_beta)
        self._fy = OneEuroFilter(oe_min_cutoff, oe_beta)

        self._sx = screen_w / 2.0
        self._sy = screen_h / 2.0
        self.last_xy = (int(self._sx), int(self._sy))

        self._dragging = False
        self._scroll_anchor: Optional[tuple[float, float]] = None
        self._scroll_t = 0.0

    # ── mapping ────────────────────────────────────────────────────────────────

    def _map_axis(self, norm: float, lo: float, hi: float, size: int) -> int:
        clamped = max(lo, min(hi, norm))
        return max(0, min(size - 1, int((clamped - lo) / (hi - lo) * size)))

    def _map(self, nx: float, ny: float) -> tuple[int, int]:
        if self.calib:
            x0, y0, x1, y1 = self.calib
        else:
            x0 = y0 = self.margin
            x1 = y1 = 1.0 - self.margin
        return (self._map_axis(nx, x0, x1, self.sw),
                self._map_axis(ny, y0, y1, self.sh))

    # ── movement ────────────────────────────────────────────────────────────────

    def move(self, nx: float, ny: float) -> None:
        tx, ty = self._map(nx, ny)
        if self.use_oe:
            now = time.time()
            fx = self._fx(tx, now)
            fy = self._fy(ty, now)
            # apply sensitivity around current position
            self._sx += (fx - self._sx) * self.sens
            self._sy += (fy - self._sy) * self.sens
        else:
            dx, dy = tx - self._sx, ty - self._sy
            if abs(dx) / self.sw < self.dz and abs(dy) / self.sh < self.dz:
                return
            self._sx += self.alpha * dx * self.sens
            self._sy += self.alpha * dy * self.sens

        x = max(0, min(self.sw - 1, int(self._sx)))
        y = max(0, min(self.sh - 1, int(self._sy)))
        self.last_xy = (x, y)
        _do_move(x, y)

    def warp_filter(self) -> None:
        """Reset filters (call when the hand re-enters frame to avoid a jump)."""
        self._fx.reset()
        self._fy.reset()

    # ── clicks ────────────────────────────────────────────────────────────────

    def left_click(self) -> None:
        _do_click("left", 1)

    def double_click(self) -> None:
        _do_click("left", 2)

    def right_click(self) -> None:
        _do_click("right", 1)

    def start_drag(self) -> None:
        if not self._dragging:
            _do_press()
            self._dragging = True

    def stop_drag(self) -> None:
        if self._dragging:
            _do_release()
            self._dragging = False

    @property
    def dragging(self) -> bool:
        return self._dragging

    # ── scroll (2-axis) ─────────────────────────────────────────────────────────

    def scroll(self, nx: float, ny: float, speed: int = 4, horizontal: bool = True) -> None:
        now = time.time()
        if self._scroll_anchor is None:
            self._scroll_anchor = (nx, ny)
            return
        if now - self._scroll_t < 0.06:
            return
        ax, ay = self._scroll_anchor
        ddy = ay - ny       # up = positive
        ddx = nx - ax       # right = positive
        moved = False
        if abs(ddy) > 0.012:
            ty = int(ddy * 45 * speed)
            if ty:
                _do_scroll(0, ty)
                moved = True
        if horizontal and abs(ddx) > 0.018:
            tx = int(ddx * 35 * speed)
            if tx:
                _do_scroll(tx, 0)
                moved = True
        if moved:
            self._scroll_t = now
        self._scroll_anchor = (nx, ny)

    def reset_scroll(self) -> None:
        self._scroll_anchor = None

    # ── typing ──────────────────────────────────────────────────────────────────

    def type_char(self, char: str) -> None:
        _do_type(char)

    def tap_key(self, name: str) -> None:
        """Tap a named special key via pynput (enter, backspace, arrows, ...)."""
        if not _PYNPUT:
            if _PYAUTOGUI:
                pyautogui.press(name)
            return
        key = getattr(Key, name, None)
        if key:
            _kbd.press(key)
            _kbd.release(key)
