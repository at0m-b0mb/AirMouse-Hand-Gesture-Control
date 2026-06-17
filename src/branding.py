"""Central branding & theming for AirMouse.

One source of truth for the app's identity and colour palette so the GUI
(hex strings) and the OpenCV HUD (BGR tuples) always look cohesive. Switch
the whole look by changing the active theme.
"""
from __future__ import annotations

# ── Identity ────────────────────────────────────────────────────────────────────
APP_NAME = "AirMouse"
APP_TAGLINE = "Gesture Laptop Controller"
APP_BLURB = "Control your laptop with your hand — cursor, clicks, scroll, drag & type, all in the air."
VERSION = "3.0"
AUTHOR = "at0m-b0mb"
REPO_URL = "https://github.com/at0m-b0mb/AirMouse-Hand-Gesture-Control"

# ── Themes ──────────────────────────────────────────────────────────────────────
# Every theme defines the same keys (hex). The default, "Aurora", is an
# indigo → violet → teal identity. "Cyber" leans neon, "Mono" stays minimal.
THEMES: dict[str, dict[str, object]] = {
    "Aurora": {
        "bg": "#0E0B16", "surface": "#1A1626", "surface2": "#241E36",
        "primary": "#6C5CE7", "secondary": "#A855F7", "accent": "#2DD4BF",
        "text": "#ECEAF5", "muted": "#8A85A0",
        "success": "#2DD4BF", "warning": "#FBBF24", "danger": "#FB7185",
        "gradient": ["#6C5CE7", "#A855F7", "#2DD4BF"],
    },
    "Cyber": {
        "bg": "#05060A", "surface": "#0E1320", "surface2": "#16203A",
        "primary": "#22D3EE", "secondary": "#FF2EC4", "accent": "#A3FF12",
        "text": "#D6F7FF", "muted": "#5E7A86",
        "success": "#A3FF12", "warning": "#FFC857", "danger": "#FF3B6B",
        "gradient": ["#22D3EE", "#7C5CFF", "#FF2EC4"],
    },
    "Mono": {
        "bg": "#0F1115", "surface": "#1A1D24", "surface2": "#242833",
        "primary": "#3B82F6", "secondary": "#60A5FA", "accent": "#93C5FD",
        "text": "#E5E7EB", "muted": "#8B92A0",
        "success": "#34D399", "warning": "#FBBF24", "danger": "#F87171",
        "gradient": ["#3B82F6", "#60A5FA", "#93C5FD"],
    },
}

_DEFAULT = "Aurora"
_active = _DEFAULT


# ── Active-theme management ──────────────────────────────────────────────────────
def use(name: str) -> str:
    """Set the active theme. Falls back to the default for unknown names."""
    global _active
    _active = name if name in THEMES else _DEFAULT
    return _active


def active_name() -> str:
    return _active


def theme(name: str | None = None) -> dict:
    return THEMES.get(name or _active, THEMES[_DEFAULT])


# ── Colour helpers ──────────────────────────────────────────────────────────────
def hx(key: str, name: str | None = None) -> str:
    """Hex colour for the GUI (customtkinter)."""
    return str(theme(name)[key])


def hex_to_bgr(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b, g, r)  # OpenCV is BGR


def bgr(key: str, name: str | None = None) -> tuple[int, int, int]:
    """BGR colour for the OpenCV HUD."""
    return hex_to_bgr(str(theme(name)[key]))


def gradient(name: str | None = None) -> list[str]:
    return list(theme(name)["gradient"])  # type: ignore[arg-type]
