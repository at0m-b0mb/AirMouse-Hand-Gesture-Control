"""Mouse and keyboard control via pynput (pyautogui as fallback)."""
import time
from typing import Optional

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

_PYNPUT_KEYS = {
    "BKSP":  "backspace",
    "ENTER": "enter",
    "SPACE": "space",
    "TAB":   "tab",
}

_PYAUTOGUI_KEYS = {
    "BKSP":  "backspace",
    "ENTER": "enter",
    "SPACE": "space",
    "TAB":   "tab",
}


def _move(x: int, y: int) -> None:
    if _PYNPUT:
        _mouse.position = (x, y)
    elif _PYAUTOGUI:
        pyautogui.moveTo(x, y)


def _click_left() -> None:
    if _PYNPUT:
        _mouse.click(Button.left)
    elif _PYAUTOGUI:
        pyautogui.click()


def _click_right() -> None:
    if _PYNPUT:
        _mouse.click(Button.right)
    elif _PYAUTOGUI:
        pyautogui.rightClick()


def _press_btn() -> None:
    if _PYNPUT:
        _mouse.press(Button.left)
    elif _PYAUTOGUI:
        pyautogui.mouseDown()


def _release_btn() -> None:
    if _PYNPUT:
        _mouse.release(Button.left)
    elif _PYAUTOGUI:
        pyautogui.mouseUp()


def _scroll(dy: int) -> None:
    if _PYNPUT:
        _mouse.scroll(0, dy)
    elif _PYAUTOGUI:
        pyautogui.scroll(dy)


def _type(char: str) -> None:
    if char in _PYNPUT_KEYS and _PYNPUT:
        k = getattr(Key, _PYNPUT_KEYS[char], None)
        if k:
            _kbd.press(k); _kbd.release(k)
        return
    if char in _PYAUTOGUI_KEYS and _PYAUTOGUI:
        pyautogui.press(_PYAUTOGUI_KEYS[char])
        return
    if _PYNPUT:
        _kbd.type(char)
    elif _PYAUTOGUI:
        pyautogui.typewrite(char, interval=0)


class MouseController:
    """Smooth cursor movement + click/scroll/drag + keyboard typing."""

    def __init__(
        self,
        screen_w: int,
        screen_h: int,
        smoothing: float = 0.18,
        sensitivity: float = 1.3,
        dead_zone: float = 0.008,
        cursor_margin: float = 0.12,
    ):
        self.sw = screen_w
        self.sh = screen_h
        self.alpha = smoothing
        self.sens = sensitivity
        self.dz = dead_zone
        self.margin = cursor_margin

        self._sx: float = screen_w / 2.0
        self._sy: float = screen_h / 2.0
        self._dragging: bool = False
        self._scroll_y: Optional[float] = None
        self._scroll_t: float = 0.0

    def _map(self, norm: float, size: int) -> int:
        """Map normalized [margin, 1-margin] → [0, size]."""
        m = self.margin
        clamped = max(m, min(1.0 - m, norm))
        return max(0, min(size - 1, int((clamped - m) / (1.0 - 2 * m) * size)))

    def move(self, nx: float, ny: float) -> None:
        tx = self._map(nx, self.sw)
        ty = self._map(ny, self.sh)
        dx = tx - self._sx
        dy = ty - self._sy
        if abs(dx) / self.sw < self.dz and abs(dy) / self.sh < self.dz:
            return
        self._sx += self.alpha * dx * self.sens
        self._sy += self.alpha * dy * self.sens
        x = max(0, min(self.sw - 1, int(self._sx)))
        y = max(0, min(self.sh - 1, int(self._sy)))
        _move(x, y)

    def left_click(self) -> None:
        _click_left()

    def right_click(self) -> None:
        _click_right()

    def start_drag(self) -> None:
        if not self._dragging:
            _press_btn()
            self._dragging = True

    def stop_drag(self) -> None:
        if self._dragging:
            _release_btn()
            self._dragging = False

    def scroll(self, ny: float, speed: int = 3) -> None:
        now = time.time()
        if self._scroll_y is None:
            self._scroll_y = ny
            return
        if now - self._scroll_t < 0.08:
            return
        delta = self._scroll_y - ny  # positive = scroll up
        if abs(delta) > 0.012:
            ticks = int(delta * 45 * speed)
            if ticks:
                _scroll(ticks)
                self._scroll_t = now
        self._scroll_y = ny

    def reset_scroll(self) -> None:
        self._scroll_y = None

    def type_char(self, char: str) -> None:
        _type(char)
