"""On-screen virtual keyboard rendered as an OpenCV overlay."""
import time
import cv2
import numpy as np
from typing import Optional

# (display_label, action_token, width_weight)
_FUNC_ROW = [
    ("esc","ESC",1.3),("◀","LEFT",1),("▲","UP",1),("▼","DOWN",1),("▶","RIGHT",1),
    ("vol-","VOL_DOWN",1.3),("vol+","VOL_UP",1.3),("mute","MUTE",1.3),
    ("play","PLAY",1.2),("shot","SCRNSHOT",1.6),
]

_ROWS = [
    [("1","1",1),("2","2",1),("3","3",1),("4","4",1),("5","5",1),
     ("6","6",1),("7","7",1),("8","8",1),("9","9",1),("0","0",1),
     ("-","-",1),("=","=",1),("⌫","BKSP",1.6)],
    [("Q","q",1),("W","w",1),("E","e",1),("R","r",1),("T","t",1),
     ("Y","y",1),("U","u",1),("I","i",1),("O","o",1),("P","p",1),
     ("[","[",1),("]","]",1),("\\","\\",1)],
    [("A","a",1),("S","s",1),("D","d",1),("F","f",1),("G","g",1),
     ("H","h",1),("J","j",1),("K","k",1),("L","l",1),
     (";",";",1),("'","'",1),("↵","ENTER",2)],
    [("caps","CAPS",1.5),("Z","z",1),("X","x",1),("C","c",1),("V","v",1),
     ("B","b",1),("N","n",1),("M","m",1),(",",",",1),(".",".",1),("/","/",1)],
    [("⇧","SHIFT",1.6),("SPACE","SPACE",7),("TAB","TAB",1.8)],
]

_SHIFT_MAP = {
    "1":"!","2":"@","3":"#","4":"$","5":"%",
    "6":"^","7":"&","8":"*","9":"(","0":")",
    "-":"_","=":"+","[":"{","]":"}","\\":"|",
    ";":":","'":'"',",":"<",".":">","/":"?",
}

_SPECIALS = {"BKSP","ENTER","SHIFT","SPACE","TAB","CAPS","ESC",
             "UP","DOWN","LEFT","RIGHT","VOL_UP","VOL_DOWN","MUTE","PLAY","SCRNSHOT"}
_LATCH = {"SHIFT","CAPS"}


class VirtualKeyboard:
    """QWERTY keyboard + function row rendered in the lower portion of the frame."""

    def __init__(self, frame_w: int, frame_h: int, press_cooldown: float = 0.40):
        self._fw = frame_w
        self._fh = frame_h
        self._cooldown = press_cooldown

        self.shift = False
        self.caps = False
        self._hover: Optional[str] = None
        self._last_action: Optional[str] = None
        self._last_t = 0.0
        self._preview = ""          # live typed-text preview
        self._keys: list = []
        self._build()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        kb_y0 = int(self._fh * 0.50)
        kb_h  = int(self._fh * 0.48)
        kb_x0 = int(self._fw * 0.01)
        kb_w  = int(self._fw * 0.98)

        all_rows = [_FUNC_ROW] + _ROWS
        row_h = kb_h // len(all_rows)

        self._keys = []
        for ri, row in enumerate(all_rows):
            total = sum(w for _, _, w in row)
            x = kb_x0
            for label, action, wt in row:
                kw = int(wt / total * kb_w)
                y1 = kb_y0 + ri * row_h
                self._keys.append({
                    "label": label, "action": action,
                    "special": action in _SPECIALS,
                    "func": ri == 0,
                    "x1": x, "y1": y1, "x2": x + kw - 2, "y2": y1 + row_h - 2,
                })
                x += kw

    def _hit(self, px: int, py: int) -> Optional[dict]:
        for k in self._keys:
            if k["x1"] <= px <= k["x2"] and k["y1"] <= py <= k["y2"]:
                return k
        return None

    # ── interaction ─────────────────────────────────────────────────────────────

    def update_hover(self, nx: float, ny: float) -> None:
        hit = self._hit(int(nx * self._fw), int(ny * self._fh))
        self._hover = hit["action"] if hit else None

    def try_press(self, nx: float, ny: float) -> Optional[str]:
        """On pinch. Returns the action token to handle, or None (state-only keys)."""
        now = time.time()
        hit = self._hit(int(nx * self._fw), int(ny * self._fh))
        if not hit:
            return None
        action = hit["action"]
        if action == self._last_action and now - self._last_t < self._cooldown:
            return None
        self._last_action = action
        self._last_t = now

        if action == "SHIFT":
            self.shift = not self.shift
            return None
        if action == "CAPS":
            self.caps = not self.caps
            return None
        return action

    def resolve_char(self, action: str) -> str:
        """Plain-char actions → actual char (respecting shift/caps). Else passthrough."""
        if len(action) == 1 and action.isalpha():
            upper = self.shift ^ self.caps
            return action.upper() if upper else action.lower()
        if len(action) == 1 and self.shift and action in _SHIFT_MAP:
            return _SHIFT_MAP[action]
        return action

    def note_preview(self, action: str) -> None:
        """Update the on-screen preview buffer after a key is handled."""
        if action == "BKSP":
            self._preview = self._preview[:-1]
        elif action == "SPACE":
            self._preview += " "
        elif action == "ENTER":
            self._preview = ""
        elif action == "TAB":
            self._preview += "    "
        elif len(action) == 1:
            self._preview += self.resolve_char(action)
        if len(self._preview) > 60:
            self._preview = self._preview[-60:]

    # ── rendering ────────────────────────────────────────────────────────────────

    def draw(self, frame: np.ndarray) -> np.ndarray:
        overlay = frame.copy()
        h, w = frame.shape[:2]

        # Preview bar
        bar_y = int(self._fh * 0.50) - 30
        cv2.rectangle(overlay, (0, bar_y), (w, bar_y + 28), (20, 20, 28), -1)
        shown = self._preview if self._preview else "type with pinch…"
        col = (210, 210, 210) if self._preview else (110, 110, 110)
        cv2.putText(overlay, "› " + shown + "_", (12, bar_y + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 1, cv2.LINE_AA)

        for k in self._keys:
            action = k["action"]
            if action == self._hover:
                bg = (30, 140, 220)
            elif action == "SHIFT" and self.shift:
                bg = (40, 180, 60)
            elif action == "CAPS" and self.caps:
                bg = (40, 180, 60)
            elif k["func"]:
                bg = (70, 45, 40)
            elif k["special"]:
                bg = (55, 35, 90)
            else:
                bg = (30, 30, 30)

            cv2.rectangle(overlay, (k["x1"], k["y1"]), (k["x2"], k["y2"]), bg, -1)
            cv2.rectangle(overlay, (k["x1"], k["y1"]), (k["x2"], k["y2"]), (85, 85, 85), 1)

            disp = k["label"]
            if len(action) == 1 and action.isalpha():
                disp = action.upper() if (self.shift ^ self.caps) else action.lower()
            elif len(action) == 1 and action in _SHIFT_MAP and self.shift:
                disp = _SHIFT_MAP[action]

            scale = 0.38 if (k["special"] or k["func"]) else 0.50
            (tw, th), _ = cv2.getTextSize(disp, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
            tx = k["x1"] + (k["x2"] - k["x1"] - tw) // 2
            ty = k["y1"] + (k["y2"] - k["y1"] + th) // 2
            cv2.putText(overlay, disp, (tx, ty),
                        cv2.FONT_HERSHEY_SIMPLEX, scale, (235, 235, 235), 1, cv2.LINE_AA)

        cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
        return frame
