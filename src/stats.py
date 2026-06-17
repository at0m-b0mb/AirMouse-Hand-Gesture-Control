"""Lightweight session statistics for AirMouse.

Tracks what happened during a session (clicks, scrolls, drags, cursor distance,
uptime) so the HUD and GUI can show a live activity summary. Pure data — no
side effects, trivially testable.
"""
from __future__ import annotations

import time


class SessionStats:
    def __init__(self) -> None:
        self.started = time.time()
        self.left_clicks = 0
        self.right_clicks = 0
        self.middle_clicks = 0
        self.double_clicks = 0
        self.scrolls = 0
        self.drags = 0
        self.keys_typed = 0
        self.screenshots = 0
        self.distance_px = 0.0
        self._last_xy: tuple[int, int] | None = None

    # ── event hooks ─────────────────────────────────────────────────────────────
    def left_click(self) -> None:
        self.left_clicks += 1

    def right_click(self) -> None:
        self.right_clicks += 1

    def middle_click(self) -> None:
        self.middle_clicks += 1

    def double_click(self) -> None:
        self.double_clicks += 1

    def scroll(self) -> None:
        self.scrolls += 1

    def drag(self) -> None:
        self.drags += 1

    def key(self) -> None:
        self.keys_typed += 1

    def screenshot(self) -> None:
        self.screenshots += 1

    def moved_to(self, x: int, y: int) -> None:
        if self._last_xy is not None:
            dx, dy = x - self._last_xy[0], y - self._last_xy[1]
            self.distance_px += (dx * dx + dy * dy) ** 0.5
        self._last_xy = (x, y)

    # ── derived ─────────────────────────────────────────────────────────────────
    @property
    def uptime(self) -> float:
        return time.time() - self.started

    @property
    def total_clicks(self) -> int:
        return self.left_clicks + self.right_clicks + self.middle_clicks

    def uptime_str(self) -> str:
        s = int(self.uptime)
        return f"{s // 60:d}:{s % 60:02d}"

    def hud_line(self) -> str:
        """Compact one-liner for the HUD overlay."""
        return (f"clicks {self.total_clicks}  scroll {self.scrolls}  "
                f"keys {self.keys_typed}  {int(self.distance_px)}px  "
                f"up {self.uptime_str()}")

    def summary(self) -> dict:
        return {
            "Uptime": self.uptime_str(),
            "Left clicks": self.left_clicks,
            "Right clicks": self.right_clicks,
            "Middle clicks": self.middle_clicks,
            "Double clicks": self.double_clicks,
            "Scrolls": self.scrolls,
            "Drags": self.drags,
            "Keys typed": self.keys_typed,
            "Screenshots": self.screenshots,
            "Cursor travel": f"{int(self.distance_px)} px",
        }
