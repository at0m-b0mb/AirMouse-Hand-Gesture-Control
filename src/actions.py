"""Cross-platform system actions: volume, media, screenshots, special keys."""
import datetime
import logging
import os
import platform
from pathlib import Path
from typing import Optional

log = logging.getLogger("airmouse.actions")

try:
    from pynput.keyboard import Key, Controller as _KbdCtrl
    _kbd = _KbdCtrl()
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


# Special key tokens → pynput Key
_KEY_TOKENS = {
    "BKSP":  "backspace",
    "ENTER": "enter",
    "SPACE": "space",
    "TAB":   "tab",
    "ESC":   "esc",
    "UP":    "up",
    "DOWN":  "down",
    "LEFT":  "left",
    "RIGHT": "right",
}

_MEDIA_TOKENS = {
    "VOL_UP":   "media_volume_up",
    "VOL_DOWN": "media_volume_down",
    "MUTE":     "media_volume_mute",
    "PLAY":     "media_play_pause",
}


def _tap(key) -> None:
    if _PYNPUT:
        _kbd.press(key)
        _kbd.release(key)


def tap_token(token: str) -> None:
    """Press a named special key (BKSP, ENTER, arrows, ESC, ...)."""
    if not _PYNPUT:
        if _PYAUTOGUI and token in _KEY_TOKENS:
            pyautogui.press(_KEY_TOKENS[token])
        return
    name = _KEY_TOKENS.get(token)
    if name:
        key = getattr(Key, name, None)
        if key:
            _tap(key)


def media(token: str) -> bool:
    """Trigger a media/volume key. Returns True if handled."""
    if not _PYNPUT:
        return False
    name = _MEDIA_TOKENS.get(token)
    if not name:
        return False
    key = getattr(Key, name, None)
    if key is None:
        return False
    _tap(key)
    return True


def screenshot(out_dir: str = "screenshots") -> Optional[str]:
    """Capture the full screen to a timestamped PNG. Returns the path."""
    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)
    fname = path / f"airmouse_{datetime.datetime.now():%Y%m%d_%H%M%S}.png"
    try:
        if platform.system() == "Darwin":
            # screencapture avoids stealing focus / is silent
            os.system(f'screencapture -x "{fname}"')
        elif _PYAUTOGUI:
            pyautogui.screenshot(str(fname))
        else:
            return None
        log.info("Screenshot saved: %s", fname)
        return str(fname)
    except Exception as exc:
        log.warning("Screenshot failed: %s", exc)
        return None


def is_token(s: str) -> bool:
    return s in _KEY_TOKENS or s in _MEDIA_TOKENS or s == "SCRNSHOT"
