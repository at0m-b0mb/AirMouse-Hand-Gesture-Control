"""On-screen virtual keyboard rendered as an OpenCV overlay."""
import time
import cv2
import numpy as np
from typing import Optional

# (display_label, action_key, width_weight)
_ROWS = [
    [("1","1",1),("2","2",1),("3","3",1),("4","4",1),("5","5",1),
     ("6","6",1),("7","7",1),("8","8",1),("9","9",1),("0","0",1),
     ("-","-",1),("=","=",1),("⌫","BKSP",1.5)],
    [("Q","q",1),("W","w",1),("E","e",1),("R","r",1),("T","t",1),
     ("Y","y",1),("U","u",1),("I","i",1),("O","o",1),("P","p",1),
     ("[","[",1),("]","]",1),("\\","\\",1)],
    [("A","a",1),("S","s",1),("D","d",1),("F","f",1),("G","g",1),
     ("H","h",1),("J","j",1),("K","k",1),("L","l",1),
     (";",";",1),("'","'",1),("↵","ENTER",2)],
    [("⇧","SHIFT",1.5),("Z","z",1),("X","x",1),("C","c",1),("V","v",1),
     ("B","b",1),("N","n",1),("M","m",1),(",",",",1),(".",".",1),("/","/",1)],
    [("SPACE","SPACE",6),("TAB","TAB",2)],
]

_SHIFT_MAP = {
    "1":"!","2":"@","3":"#","4":"$","5":"%",
    "6":"^","7":"&","8":"*","9":"(","0":")",
    "-":"_","=":"+","[":"{","]":"}","\\":"|",
    ";":":","'":'"',",":"<",".":">","/":"?",
}

_SPECIALS = {"BKSP","ENTER","SHIFT","SPACE","TAB"}


class VirtualKeyboard:
    """Renders a QWERTY keyboard in the lower portion of the camera frame."""

    def __init__(self, frame_w: int, frame_h: int, press_cooldown: float = 0.45):
        self._fw = frame_w
        self._fh = frame_h
        self._cooldown = press_cooldown

        self.shift: bool = False
        self._hover: Optional[str] = None
        self._last_action: Optional[str] = None
        self._last_t: float = 0.0
        self._keys: list = []
        self._build()

    def _build(self) -> None:
        kb_y0 = int(self._fh * 0.58)
        kb_h  = int(self._fh * 0.40)
        kb_x0 = int(self._fw * 0.01)
        kb_w  = int(self._fw * 0.98)
        row_h = kb_h // len(_ROWS)

        self._keys = []
        for ri, row in enumerate(_ROWS):
            total_w = sum(wt for _, _, wt in row)
            x = kb_x0
            for label, action, wt in row:
                kw = int(wt / total_w * kb_w)
                y1 = kb_y0 + ri * row_h
                self._keys.append({
                    "label":   label,
                    "action":  action,
                    "special": action in _SPECIALS,
                    "x1": x,        "y1": y1,
                    "x2": x + kw - 2, "y2": y1 + row_h - 2,
                })
                x += kw

    # ── hit testing ──────────────────────────────────────────────────────────

    def _hit(self, px: int, py: int) -> Optional[dict]:
        for k in self._keys:
            if k["x1"] <= px <= k["x2"] and k["y1"] <= py <= k["y2"]:
                return k
        return None

    def update_hover(self, nx: float, ny: float) -> None:
        px, py = int(nx * self._fw), int(ny * self._fh)
        hit = self._hit(px, py)
        self._hover = hit["action"] if hit else None

    def try_press(self, nx: float, ny: float) -> Optional[str]:
        """Called on pinch. Returns action key to type, or None."""
        now = time.time()
        px, py = int(nx * self._fw), int(ny * self._fh)
        hit = self._hit(px, py)
        if not hit:
            return None
        action = hit["action"]
        # Debounce: same key within cooldown → ignore
        if action == self._last_action and now - self._last_t < self._cooldown:
            return None
        self._last_action = action
        self._last_t = now
        if action == "SHIFT":
            self.shift = not self.shift
            return None
        return action

    def resolve_char(self, action: str) -> str:
        """Convert action key → actual character respecting shift state."""
        if len(action) == 1:
            if action.isalpha():
                return action.upper() if self.shift else action.lower()
            if self.shift and action in _SHIFT_MAP:
                return _SHIFT_MAP[action]
        return action

    # ── rendering ────────────────────────────────────────────────────────────

    def draw(self, frame: np.ndarray) -> np.ndarray:
        overlay = frame.copy()

        for k in self._keys:
            action = k["action"]
            if action == self._hover:
                bg = (30, 140, 220)
            elif action == "SHIFT" and self.shift:
                bg = (40, 180, 60)
            elif k["special"]:
                bg = (55, 35, 90)
            else:
                bg = (30, 30, 30)

            cv2.rectangle(overlay, (k["x1"], k["y1"]), (k["x2"], k["y2"]), bg, -1)
            cv2.rectangle(overlay, (k["x1"], k["y1"]), (k["x2"], k["y2"]), (85, 85, 85), 1)

            # Display char (shift-aware for letters/numbers)
            disp = k["label"]
            if len(action) == 1 and action.isalpha():
                disp = action.upper() if self.shift else action.lower()
            elif len(action) == 1 and action in _SHIFT_MAP and self.shift:
                disp = _SHIFT_MAP[action]

            scale = 0.40 if k["special"] else 0.50
            (tw, th), _ = cv2.getTextSize(disp, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
            tx = k["x1"] + (k["x2"] - k["x1"] - tw) // 2
            ty = k["y1"] + (k["y2"] - k["y1"] + th) // 2
            cv2.putText(overlay, disp, (tx, ty),
                        cv2.FONT_HERSHEY_SIMPLEX, scale, (235, 235, 235), 1, cv2.LINE_AA)

        cv2.addWeighted(overlay, 0.82, frame, 0.18, 0, frame)
        return frame
