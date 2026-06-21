#!/usr/bin/env python3
"""
AirMouse Studio — a beautiful control center for AirMouse 3.1.

Two-pane GUI: tune everything on the left (Dashboard / Tuning / Camera /
Options / Gestures / About), watch a LIVE webcam preview on the right.

New in 3.1:
  • Gradient header strip (primary → accent)
  • Animated launch button (smooth colour pulse)
  • Dashboard: system check, last-session mini bar chart, active config
  • Quick sensitivity bar (🐢 → 🚀)
  • Theme swatches for one-click switching
  • Profile cards replacing the old dropdown
  • Visual gesture + hotkey cards
  • Rotating tips in the preview pane
  • Sound feedback toggle
  • Detection & tracking confidence sliders

Run:  python launcher.py     (needs customtkinter + Pillow)
"""
import math
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path

try:
    import customtkinter as ctk
except ImportError:
    print("customtkinter not installed. Run: pip install customtkinter")
    sys.exit(1)

from config import Config, PROFILES
from src import branding
from src.camera import list_cameras
from src.stats import SessionStats

ROOT = Path(__file__).parent
SCREENSHOTS_DIR = ROOT / "screenshots"
LAST_SESSION_FILE = ROOT / "last_session.json"

# ── Content data ─────────────────────────────────────────────────────────────────
GESTURE_CARDS = [
    ("👆", "Index finger",       "Move cursor"),
    ("🤌", "Pinch thumb+index",  "Left click  ·  pinch twice = double-click"),
    ("🤏", "Pinch thumb+middle", "Right click"),
    ("🖐️", "Pinch thumb+ring",   "Middle click  (enable in Options)"),
    ("✌️", "Peace sign",         "Scroll  —  up / down / left / right"),
    ("✊", "Fist",               "Drag  —  hold and move, open hand to drop"),
    ("🖐️", "Open palm (hold)",   "Toggle virtual keyboard"),
    ("👍", "Thumbs-up (hold)",   "Pause / resume control"),
]

HOTKEY_CARDS = [
    ("H",        "Help overlay"),
    ("P / Space", "Pause / freeze cursor"),
    ("C",        "Calibrate hand range"),
    ("S",        "Screenshot"),
    ("L",        "Toggle landmarks"),
    ("F",        "Mirror image"),
    ("G / I",    "FPS / stats"),
    ("Y",        "Cycle theme"),
    ("T",        "Always-on-top"),
    ("+  /  −",  "Sensitivity up / down"),
    ("[ / ]",    "Smoothing softer / snappier"),
    ("Q / ESC",  "Quit"),
]

PROFILE_DESCS = {
    "Balanced":      "Best all-round starting point",
    "Precision":     "Slow & steady, minimal jitter",
    "Fast":          "High-speed cursor workflow",
    "Presentation":  "Smooth & unhurried slide control",
    "Gaming":        "Maximum speed response",
    "Accessibility": "Extra-steady, low-speed comfort",
    "Custom":        "Your custom-tuned settings",
}

SENS_PRESETS = [
    ("🐢", 0.6, "Turtle"),
    ("🦊", 1.0, "Slow"),
    ("⚡", 1.4, "Balanced"),
    ("🦅", 2.0, "Fast"),
    ("🚀", 2.8, "Rocket"),
]

TIPS = [
    "Tip: Press C in AirMouse to calibrate your comfortable hand range",
    "Tip: Peace sign scrolls in four directions",
    "Tip: Hold thumbs-up to pause — great for breaks",
    "Tip: Press Y while running to cycle themes live",
    "Tip: Use Accessibility profile for the steadiest cursor",
    "Tip: Fist = drag · open hand = release",
    "Tip: Press I for live session statistics",
    "Tip: Hold open palm to toggle the virtual keyboard",
    "Tip: [ and ] adjust cursor smoothing without stopping",
    "Tip: Space freezes the cursor in its current position",
]


# ── Gradient canvas helper ────────────────────────────────────────────────────────
class _GradientStrip(tk.Canvas):
    """Thin horizontal gradient bar drawn with the tkinter Canvas API."""

    def __init__(self, master, c1: str, c2: str, h: int = 5, **kw):
        kw.setdefault("bd", 0)
        kw.setdefault("highlightthickness", 0)
        super().__init__(master, height=h, **kw)
        self._c1, self._c2 = c1, c2
        self.bind("<Configure>", self._draw)

    def set_colors(self, c1: str, c2: str) -> None:
        self._c1, self._c2 = c1, c2
        self._draw()

    def _draw(self, *_) -> None:
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1:
            return
        r1, g1, b1 = _parse_hex(self._c1)
        r2, g2, b2 = _parse_hex(self._c2)
        steps = min(w, 160)
        for i in range(steps):
            t = i / max(steps - 1, 1)
            color = "#{:02x}{:02x}{:02x}".format(
                int(r1 + (r2 - r1) * t),
                int(g1 + (g2 - g1) * t),
                int(b1 + (b2 - b1) * t),
            )
            x0 = int(i * w / steps)
            x1 = int((i + 1) * w / steps) + 1
            self.create_rectangle(x0, 0, x1, h, fill=color, outline="")


def _parse_hex(h: str) -> tuple:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _lerp_color(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = _parse_hex(c1)
    r2, g2, b2 = _parse_hex(c2)
    return "#{:02x}{:02x}{:02x}".format(
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    )


# ── Studio ───────────────────────────────────────────────────────────────────────
class Studio(ctk.CTk):
    SLIDERS = {
        "sensitivity":          ("Sensitivity",           0.3,  3.0,  False),
        "oe_beta":              ("Responsiveness",         0.001, 0.06, False),
        "oe_min_cutoff":        ("Smoothness",             0.3,  2.0,  False),
        "cursor_margin":        ("Edge margin",            0.02, 0.25, False),
        "scroll_speed":         ("Scroll speed",           1,    10,   True),
        "click_threshold":      ("Click sensitivity",      0.03, 0.09, False),
        "detection_confidence": ("Detection confidence",   0.3,  1.0,  False),
        "tracking_confidence":  ("Tracking confidence",    0.3,  1.0,  False),
    }

    def __init__(self):
        super().__init__()
        self.cfg = Config.load()
        branding.use(self.cfg.theme)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(f"{branding.APP_NAME} Studio")
        self.geometry("1110x770")
        self.minsize(940, 680)
        self.configure(fg_color=branding.hx("bg"))

        self._suppress = False
        self._cam_map = {"Auto-detect": -1}
        self._sliders: dict = {}
        self._accents: list = []
        self._profile_card_btns: dict = {}
        self._swatch_btns: dict = {}
        self._anim_t = 0.0
        self._tip_idx = 0
        # preview state
        self._preview_on = False
        self._cap = None
        self._tracker = None
        self._engine = None
        self._fx = self._fy = None
        self._pfps = self._pfps_n = 0
        self._pfps_t = 0.0

        self._tutorial_win = None
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._start_anim()
        self.after(3000, self._rotate_tip)
        # First-run walkthrough (unless the user opted out).
        if self.cfg.show_tutorial:
            self.after(450, lambda: self._open_tutorial(force=False))

    # ── layout ──────────────────────────────────────────────────────────────────
    def _build(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_controls()
        self._build_preview()
        self._build_actions()

        self.status = ctk.CTkLabel(
            self, text="Ready  —  configure and press Launch",
            text_color=branding.hx("muted"), font=ctk.CTkFont(size=11))
        self.status.grid(row=3, column=0, columnspan=2, pady=(0, 6))

    # ── header ───────────────────────────────────────────────────────────────────
    def _build_header(self):
        bar = ctk.CTkFrame(self, fg_color=branding.hx("surface"), corner_radius=0)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=10)

        # App icon circle
        self._header_icon = ctk.CTkLabel(
            inner, text="◈",
            font=ctk.CTkFont(size=30, weight="bold"),
            text_color=branding.hx("primary"),
            fg_color=branding.hx("surface2"),
            corner_radius=20, width=48, height=48)
        self._header_icon.pack(side="left", padx=(0, 12))

        title_box = ctk.CTkFrame(inner, fg_color="transparent")
        title_box.pack(side="left")
        self.logo = ctk.CTkLabel(
            title_box, text=branding.APP_NAME,
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color=branding.hx("primary"), anchor="w")
        self.logo.pack(anchor="w")
        ctk.CTkLabel(
            title_box, text=branding.APP_TAGLINE,
            font=ctk.CTkFont(size=11),
            text_color=branding.hx("muted"), anchor="w").pack(anchor="w")

        self.badge = ctk.CTkLabel(
            inner,
            text=f"  v{branding.VERSION}  ·  {branding.active_name()}  ",
            fg_color=branding.hx("surface2"), corner_radius=20,
            text_color=branding.hx("accent"), font=ctk.CTkFont(size=11))
        self.badge.pack(side="right")

        # Tutorial / how-to button (re-opens the walkthrough anytime)
        self.tutorial_btn = ctk.CTkButton(
            inner, text="?  Tutorial", width=96, height=30, corner_radius=15,
            fg_color=branding.hx("surface2"), hover_color=branding.hx("primary"),
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._open_tutorial(force=True))
        self.tutorial_btn.pack(side="right", padx=(0, 10))
        self._accents.append(("tut", self.tutorial_btn))

        # Gradient accent strip
        self._grad_strip = _GradientStrip(
            bar, branding.hx("primary"), branding.hx("accent"),
            h=5, bg=branding.hx("surface"))
        self._grad_strip.pack(fill="x")

    # ── left-pane tabs ───────────────────────────────────────────────────────────
    def _build_controls(self):
        tabs = ctk.CTkTabview(
            self, anchor="w", width=450,
            fg_color=branding.hx("surface"),
            segmented_button_selected_color=branding.hx("primary"),
            segmented_button_selected_hover_color=branding.hx("secondary"))
        tabs.grid(row=1, column=0, sticky="nsew", padx=(14, 7), pady=12)
        self._tabs = tabs
        self._accents.append(("tabs", tabs))
        for name in ("Dashboard", "Tuning", "Camera", "Options", "Gestures", "About"):
            tabs.add(name)
        self._build_dashboard(tabs.tab("Dashboard"))
        self._build_tuning(tabs.tab("Tuning"))
        self._build_camera(tabs.tab("Camera"))
        self._build_options(tabs.tab("Options"))
        self._build_gestures(tabs.tab("Gestures"))
        self._build_about(tabs.tab("About"))

    # ── Dashboard tab ────────────────────────────────────────────────────────────
    def _build_dashboard(self, tab):
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # System check cards
        ctk.CTkLabel(scroll, text="System Check",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=branding.hx("muted")).pack(anchor="w", padx=10, pady=(10, 4))
        row3 = ctk.CTkFrame(scroll, fg_color="transparent")
        row3.pack(fill="x", padx=6)
        row3.columnconfigure((0, 1, 2), weight=1)
        for col, (title, status, ok) in enumerate(self._system_checks()):
            card = ctk.CTkFrame(row3, fg_color=branding.hx("surface2"), corner_radius=12)
            card.grid(row=0, column=col, padx=4, pady=2, sticky="nsew")
            ctk.CTkLabel(card, text="✓" if ok else "✗",
                         text_color=branding.hx("success") if ok else branding.hx("danger"),
                         font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(12, 0))
            ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=branding.hx("text")).pack()
            ctk.CTkLabel(card, text=status, text_color=branding.hx("muted"),
                         font=ctk.CTkFont(size=10), wraplength=110,
                         justify="center").pack(pady=(0, 12))

        # Last session
        last = SessionStats.load_from_file(LAST_SESSION_FILE)
        ctk.CTkLabel(scroll, text="Last Session",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=branding.hx("muted")).pack(anchor="w", padx=10, pady=(12, 4))
        if last:
            self._build_mini_chart(scroll, last)
            qrow = ctk.CTkFrame(scroll, fg_color="transparent")
            qrow.pack(fill="x", padx=6, pady=(4, 0))
            qrow.columnconfigure((0, 1, 2, 3), weight=1)
            total_clicks = last.get("Left clicks", 0) + last.get("Right clicks", 0)
            for i, (key, val) in enumerate([
                ("Uptime",  last.get("Uptime", "—")),
                ("Clicks",  str(total_clicks)),
                ("Scrolls", str(last.get("Scrolls", 0))),
                ("Keys",    str(last.get("Keys typed", 0))),
            ]):
                c = ctk.CTkFrame(qrow, fg_color=branding.hx("surface2"), corner_radius=10)
                c.grid(row=0, column=i, padx=3, pady=2, sticky="nsew")
                ctk.CTkLabel(c, text=val, font=ctk.CTkFont(size=14, weight="bold"),
                             text_color=branding.hx("accent")).pack(pady=(8, 0))
                ctk.CTkLabel(c, text=key, font=ctk.CTkFont(size=9),
                             text_color=branding.hx("muted")).pack(pady=(0, 8))
            saved = last.get("saved_at", "")
            if saved:
                ctk.CTkLabel(scroll, text=f"Saved {saved}",
                             font=ctk.CTkFont(size=9),
                             text_color=branding.hx("muted")).pack(anchor="e", padx=12)
        else:
            no_data = ctk.CTkFrame(scroll, fg_color=branding.hx("surface2"),
                                   corner_radius=10, height=52)
            no_data.pack(fill="x", padx=10, pady=(0, 2))
            no_data.pack_propagate(False)
            ctk.CTkLabel(no_data,
                         text="No session data yet — launch AirMouse to record one.",
                         text_color=branding.hx("muted"),
                         font=ctk.CTkFont(size=10)).pack(expand=True)

        # Active config
        ctk.CTkLabel(scroll, text="Active Configuration",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=branding.hx("muted")).pack(anchor="w", padx=10, pady=(12, 4))
        cfg_frame = ctk.CTkFrame(scroll, fg_color=branding.hx("surface2"), corner_radius=12)
        cfg_frame.pack(fill="x", padx=10, pady=(0, 4))
        self._dash_cfg_lbls: list = []
        for key, val in self._active_cfg_rows():
            r = ctk.CTkFrame(cfg_frame, fg_color="transparent")
            r.pack(fill="x", padx=12, pady=4)
            ctk.CTkLabel(r, text=key, text_color=branding.hx("muted"),
                         font=ctk.CTkFont(size=11)).pack(side="left")
            lbl = ctk.CTkLabel(r, text=val, text_color=branding.hx("accent"),
                               font=ctk.CTkFont(size=11, weight="bold"))
            lbl.pack(side="right")
            self._dash_cfg_lbls.append((key, lbl))

        # Screenshots gallery
        if SCREENSHOTS_DIR.exists():
            shots = sorted(SCREENSHOTS_DIR.glob("*.png"),
                           key=lambda p: p.stat().st_mtime, reverse=True)[:6]
            if shots:
                ctk.CTkLabel(scroll, text=f"Recent Screenshots  ({len(shots)})",
                             font=ctk.CTkFont(size=12, weight="bold"),
                             text_color=branding.hx("muted")).pack(
                                 anchor="w", padx=10, pady=(12, 4))
                sg = ctk.CTkFrame(scroll, fg_color="transparent")
                sg.pack(fill="x", padx=6)
                sg.columnconfigure((0, 1, 2), weight=1)
                for i, shot in enumerate(shots):
                    c = ctk.CTkFrame(sg, fg_color=branding.hx("surface2"), corner_radius=10)
                    c.grid(row=i // 3, column=i % 3, padx=4, pady=4, sticky="nsew")
                    ctk.CTkLabel(c, text="📷", font=ctk.CTkFont(size=26)).pack(pady=(10, 2))
                    ctk.CTkLabel(c, text=shot.stem[-14:], text_color=branding.hx("muted"),
                                 font=ctk.CTkFont(size=9)).pack(pady=(0, 8))
                    c.bind("<Button-1>", lambda e, p=shot: subprocess.Popen(["open", str(p)]))

    def _build_mini_chart(self, parent, stats: dict) -> None:
        data = [
            ("Clicks",  stats.get("Left clicks", 0) + stats.get("Right clicks", 0),
             branding.hx("primary")),
            ("Scrolls", stats.get("Scrolls", 0),     branding.hx("accent")),
            ("Keys",    stats.get("Keys typed", 0),   branding.hx("secondary")),
            ("Drags",   stats.get("Drags", 0),        branding.hx("warning")),
        ]
        max_val = max((d[1] for d in data), default=1) or 1

        wrapper = ctk.CTkFrame(parent, fg_color=branding.hx("surface2"), corner_radius=12)
        wrapper.pack(fill="x", padx=10, pady=(0, 4))
        ctk.CTkLabel(wrapper, text="Activity",
                     font=ctk.CTkFont(size=10), text_color=branding.hx("muted")).pack(
                         anchor="w", padx=12, pady=(8, 2))

        canvas = tk.Canvas(wrapper, height=80, bg=branding.hx("surface2"),
                           highlightthickness=0, bd=0)
        canvas.pack(fill="x", padx=8, pady=(0, 10))

        def _redraw(*_):
            canvas.delete("all")
            cw = canvas.winfo_width()
            ch = canvas.winfo_height()
            if cw <= 10:
                return
            n = len(data)
            bar_w = max(10, int(cw / n * 0.48))
            for i, (label, val, color) in enumerate(data):
                cx = int(cw * (i + 0.5) / n)
                bh = int((val / max_val) * (ch - 26)) if max_val > 0 else 0
                x0, y0 = cx - bar_w // 2, ch - 20
                x1, y1 = cx + bar_w // 2, ch - 20 - bh
                canvas.create_rectangle(x0, y0, x1, min(y0, y1),
                                        fill=color, outline="", width=0)
                canvas.create_text(cx, ch - 10, text=label,
                                   fill=branding.hx("muted"), font=("Helvetica", 8))
                if val > 0:
                    canvas.create_text(cx, max(y1 - 8, 6), text=str(val),
                                       fill=color, font=("Helvetica", 8, "bold"))

        canvas.bind("<Configure>", _redraw)
        wrapper.after(120, _redraw)

    def _active_cfg_rows(self) -> list:
        cam = (f"Index {self.cfg.camera_index}"
               if self.cfg.camera_index >= 0 else "Auto-detect")
        calib = "Yes ✓" if self.cfg.is_calibrated else "No  (C to calibrate)"
        return [
            ("Profile",     self._current_profile_name()),
            ("Theme",       branding.active_name()),
            ("Camera",      cam),
            ("Sensitivity", f"{self.cfg.sensitivity:.1f}×"),
            ("Calibrated",  calib),
        ]

    def _refresh_dashboard(self):
        updated = {k: v for k, v in self._active_cfg_rows()}
        for key, lbl in getattr(self, "_dash_cfg_lbls", []):
            if key in updated:
                lbl.configure(text=updated[key])

    def _system_checks(self) -> list:
        checks = []
        v = sys.version_info
        checks.append(("Python", f"{v.major}.{v.minor}.{v.micro}", v >= (3, 9)))
        try:
            import cv2
            checks.append(("OpenCV", cv2.__version__, True))
        except ImportError:
            checks.append(("OpenCV", "Not installed", False))
        try:
            import mediapipe
            checks.append(("MediaPipe", mediapipe.__version__, True))
        except ImportError:
            checks.append(("MediaPipe", "Not installed", False))
        return checks

    # ── Tuning tab ───────────────────────────────────────────────────────────────
    def _build_tuning(self, tab):
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(scroll, text="Profile",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=branding.hx("muted")).pack(anchor="w", padx=10, pady=(10, 4))
        self.profile_var = ctk.StringVar(value=self._current_profile_name())
        self._build_profile_cards(scroll)

        ctk.CTkLabel(scroll, text="Quick Sensitivity",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=branding.hx("muted")).pack(anchor="w", padx=10, pady=(14, 4))
        self._build_sensitivity_bar(scroll)

        ctk.CTkLabel(scroll, text="Fine Tuning",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=branding.hx("muted")).pack(anchor="w", padx=10, pady=(14, 2))
        for field, (label, lo, hi, is_int) in self.SLIDERS.items():
            self._sliders[field] = self._slider(scroll, field, label, lo, hi, is_int)

    def _build_profile_cards(self, parent):
        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.pack(fill="x", padx=8, pady=(0, 4))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        current = self.profile_var.get()
        for i, name in enumerate(list(PROFILES.keys()) + ["Custom"]):
            r, c = divmod(i, 2)
            is_sel = (name == current)
            card = ctk.CTkFrame(
                grid,
                fg_color=branding.hx("primary") if is_sel else branding.hx("surface2"),
                corner_radius=12)
            card.grid(row=r, column=c, padx=4, pady=4, sticky="nsew")
            nl = ctk.CTkLabel(card, text=name,
                              font=ctk.CTkFont(size=12, weight="bold"),
                              text_color="#FFFFFF" if is_sel else branding.hx("text"))
            nl.pack(anchor="w", padx=10, pady=(10, 0))
            dl = ctk.CTkLabel(card, text=PROFILE_DESCS.get(name, "Custom"),
                              font=ctk.CTkFont(size=10),
                              text_color="#EEEEEE" if is_sel else branding.hx("muted"),
                              wraplength=158, justify="left")
            dl.pack(anchor="w", padx=10, pady=(0, 10))
            for w in (card, nl, dl):
                w.bind("<Button-1>", lambda e, n=name: self._on_profile_card(n))
            self._profile_card_btns[name] = (card, nl, dl)

    def _on_profile_card(self, name: str):
        for n, (card, nl, dl) in self._profile_card_btns.items():
            sel = (n == name)
            card.configure(fg_color=branding.hx("primary") if sel else branding.hx("surface2"))
            nl.configure(text_color="#FFFFFF" if sel else branding.hx("text"))
            dl.configure(text_color="#EEEEEE" if sel else branding.hx("muted"))
        self.profile_var.set(name)
        self._on_profile(name)

    def _build_sensitivity_bar(self, parent):
        bar = ctk.CTkFrame(parent, fg_color=branding.hx("surface2"), corner_radius=10)
        bar.pack(fill="x", padx=10)
        btn_row = ctk.CTkFrame(bar, fg_color="transparent")
        btn_row.pack(fill="x", padx=8, pady=8)
        for col, (icon, val, tip) in enumerate(SENS_PRESETS):
            btn_row.columnconfigure(col, weight=1)
            b = ctk.CTkButton(btn_row, text=icon, width=44, height=38,
                              fg_color=branding.hx("surface"),
                              hover_color=branding.hx("primary"),
                              font=ctk.CTkFont(size=18), corner_radius=8,
                              command=lambda v=val: self._set_sensitivity(v))
            b.grid(row=0, column=col, padx=2)
            ctk.CTkLabel(btn_row, text=tip, font=ctk.CTkFont(size=8),
                         text_color=branding.hx("muted")).grid(row=1, column=col)

    def _set_sensitivity(self, val: float):
        w = self._sliders.get("sensitivity")
        if w:
            w["slider"].set(val)
            w["label"].configure(text=self._fmt(val, False))
        self.profile_var.set("Custom")
        self._on_profile_card("Custom")

    # ── Camera tab ───────────────────────────────────────────────────────────────
    def _build_camera(self, tab):
        ctk.CTkLabel(tab, text="Camera source").pack(anchor="w", padx=12, pady=(14, 2))
        self.cam_var = ctk.StringVar(value="Auto-detect")
        self.cam_menu = ctk.CTkOptionMenu(
            tab, values=["Auto-detect"], variable=self.cam_var,
            fg_color=branding.hx("surface2"), button_color=branding.hx("primary"))
        self.cam_menu.pack(fill="x", padx=12)
        ctk.CTkButton(tab, text="🔍  Scan for cameras", height=34,
                      fg_color=branding.hx("surface2"), hover_color=branding.hx("primary"),
                      command=self._scan_cameras).pack(fill="x", padx=12, pady=10)
        self.cam_info = ctk.CTkLabel(
            tab,
            text="Auto-detect picks the first working webcam.\n"
                 "Scan to choose a specific one, then Start preview →",
            text_color=branding.hx("muted"), justify="left")
        self.cam_info.pack(anchor="w", padx=12)
        if self.cfg.camera_index >= 0:
            self.cam_info.configure(text=f"Saved camera index: {self.cfg.camera_index}")

    # ── Options tab ──────────────────────────────────────────────────────────────
    def _build_options(self, tab):
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(scroll, text="Theme",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=branding.hx("muted")).pack(anchor="w", padx=8, pady=(10, 4))
        self._build_theme_swatches(scroll)
        self.theme_var = ctk.StringVar(value=branding.active_name())
        ctk.CTkOptionMenu(scroll, values=list(branding.THEMES), variable=self.theme_var,
                          command=self._on_theme, fg_color=branding.hx("surface2"),
                          button_color=branding.hx("primary")).pack(fill="x", padx=8, pady=(0, 10))

        ctk.CTkLabel(scroll, text="Display",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=branding.hx("muted")).pack(anchor="w", padx=8, pady=(4, 2))
        self.flip_var   = ctk.BooleanVar(value=self.cfg.flip)
        self.lm_var     = ctk.BooleanVar(value=self.cfg.show_landmarks)
        self.help_var   = ctk.BooleanVar(value=self.cfg.show_help)
        self.fps_var    = ctk.BooleanVar(value=self.cfg.show_fps)
        self.stats_var  = ctk.BooleanVar(value=self.cfg.show_stats)
        self.top_var    = ctk.BooleanVar(value=self.cfg.always_on_top)
        for text, var in [
            ("Mirror image (flip)", self.flip_var),
            ("Show hand skeleton", self.lm_var),
            ("Start with help overlay", self.help_var),
            ("Show FPS counter", self.fps_var),
            ("Show session stats", self.stats_var),
            ("Keep window always on top", self.top_var),
        ]:
            ctk.CTkSwitch(scroll, text=text, variable=var,
                          progress_color=branding.hx("primary")).pack(anchor="w", padx=8, pady=4)

        ctk.CTkLabel(scroll, text="Input",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=branding.hx("muted")).pack(anchor="w", padx=8, pady=(10, 2))
        self.mid_var   = ctk.BooleanVar(value=self.cfg.enable_middle_click)
        self.sound_var = ctk.BooleanVar(value=self.cfg.sound_feedback)
        for text, var in [
            ("Middle click (thumb + ring)", self.mid_var),
            ("Sound feedback (click sounds, macOS)", self.sound_var),
        ]:
            ctk.CTkSwitch(scroll, text=text, variable=var,
                          progress_color=branding.hx("primary")).pack(anchor="w", padx=8, pady=4)

        ctk.CTkLabel(scroll, text="Scrolling",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=branding.hx("muted")).pack(anchor="w", padx=8, pady=(10, 2))
        self.hscroll_var = ctk.BooleanVar(value=self.cfg.horizontal_scroll)
        self.inertia_var = ctk.BooleanVar(value=self.cfg.scroll_inertia)
        for text, var in [
            ("Horizontal scroll", self.hscroll_var),
            ("Scroll inertia (momentum)", self.inertia_var),
        ]:
            ctk.CTkSwitch(scroll, text=text, variable=var,
                          progress_color=branding.hx("primary")).pack(anchor="w", padx=8, pady=4)

        ctk.CTkLabel(scroll, text="Comfort",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=branding.hx("muted")).pack(anchor="w", padx=8, pady=(10, 2))
        ctk.CTkLabel(scroll, text="Auto-pause when idle (seconds, 0 = off)",
                     text_color=branding.hx("text"),
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=8)
        idle_row = ctk.CTkFrame(scroll, fg_color="transparent")
        idle_row.pack(fill="x", padx=8)
        self.idle_lbl = ctk.CTkLabel(idle_row, text=str(int(self.cfg.idle_pause_secs)),
                                     text_color=branding.hx("accent"),
                                     font=ctk.CTkFont(size=12, weight="bold"))
        self.idle_lbl.pack(side="right")
        self.idle_slider = ctk.CTkSlider(
            scroll, from_=0, to=60, number_of_steps=60,
            progress_color=branding.hx("primary"),
            command=lambda v: self.idle_lbl.configure(text=str(int(float(v)))))
        self.idle_slider.set(self.cfg.idle_pause_secs)
        self.idle_slider.pack(fill="x", padx=8)

        ctk.CTkLabel(scroll, text="Guidance",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=branding.hx("muted")).pack(anchor="w", padx=8, pady=(10, 2))
        self.tutorial_var = ctk.BooleanVar(value=self.cfg.show_tutorial)
        self.coach_var = ctk.BooleanVar(value=self.cfg.coach_overlay)
        for text, var in [
            ("Show the walkthrough when Studio opens", self.tutorial_var),
            ("In-app getting-started tips (camera window)", self.coach_var),
        ]:
            ctk.CTkSwitch(scroll, text=text, variable=var,
                          progress_color=branding.hx("primary")).pack(anchor="w", padx=8, pady=4)
        ctk.CTkButton(scroll, text="▶  Replay the walkthrough now", height=32,
                      fg_color=branding.hx("surface2"), hover_color=branding.hx("primary"),
                      command=lambda: self._open_tutorial(force=True)).pack(
                          fill="x", padx=8, pady=(6, 4))

    def _build_theme_swatches(self, parent):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=(0, 6))
        self._swatch_btns = {}
        for name, palette in branding.THEMES.items():
            is_active = (name == branding.active_name())
            btn = ctk.CTkButton(
                row, text="", width=34, height=34,
                fg_color=str(palette["primary"]),
                border_width=3 if is_active else 0,
                border_color="#FFFFFF",
                hover_color=str(palette["secondary"]),
                corner_radius=17,
                command=lambda n=name: self._on_theme(n))
            btn.pack(side="left", padx=3)
            self._swatch_btns[name] = btn
        self._swatch_name_lbl = ctk.CTkLabel(
            row, text=branding.active_name(),
            text_color=branding.hx("accent"), font=ctk.CTkFont(size=11))
        self._swatch_name_lbl.pack(side="left", padx=10)

    # ── Gestures tab ─────────────────────────────────────────────────────────────
    def _build_gestures(self, tab):
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(scroll, text="Hand Gestures",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=branding.hx("accent")).pack(anchor="w", padx=8, pady=(8, 6))
        g_grid = ctk.CTkFrame(scroll, fg_color="transparent")
        g_grid.pack(fill="x", padx=4)
        g_grid.columnconfigure(0, weight=1)
        g_grid.columnconfigure(1, weight=1)
        for i, (icon, name, action) in enumerate(GESTURE_CARDS):
            r, c = divmod(i, 2)
            card = ctk.CTkFrame(g_grid, fg_color=branding.hx("surface2"), corner_radius=12)
            card.grid(row=r, column=c, padx=4, pady=4, sticky="nsew")
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=8, pady=8)
            ctk.CTkLabel(inner, text=icon,
                         font=ctk.CTkFont(size=26)).pack(side="left", padx=(0, 8))
            txt = ctk.CTkFrame(inner, fg_color="transparent")
            txt.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(txt, text=name, font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=branding.hx("text"), anchor="w").pack(anchor="w")
            ctk.CTkLabel(txt, text=action, font=ctk.CTkFont(size=10),
                         text_color=branding.hx("muted"), anchor="w",
                         wraplength=132, justify="left").pack(anchor="w")

        ctk.CTkLabel(scroll, text="Hotkeys",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=branding.hx("accent")).pack(anchor="w", padx=8, pady=(14, 6))
        hk_grid = ctk.CTkFrame(scroll, fg_color="transparent")
        hk_grid.pack(fill="x", padx=4)
        hk_grid.columnconfigure(0, weight=1)
        hk_grid.columnconfigure(1, weight=1)
        for i, (key, action) in enumerate(HOTKEY_CARDS):
            r, c = divmod(i, 2)
            card = ctk.CTkFrame(hk_grid, fg_color=branding.hx("surface2"), corner_radius=8)
            card.grid(row=r, column=c, padx=4, pady=3, sticky="nsew")
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=8, pady=6)
            key_badge = ctk.CTkLabel(inner, text=key,
                                     fg_color=branding.hx("primary"), corner_radius=4,
                                     font=ctk.CTkFont(family="Menlo", size=10, weight="bold"),
                                     text_color="#FFFFFF", width=66, padx=4)
            key_badge.pack(side="left", padx=(0, 8))
            ctk.CTkLabel(inner, text=action, font=ctk.CTkFont(size=10),
                         text_color=branding.hx("muted"), anchor="w").pack(side="left")

    # ── About tab ────────────────────────────────────────────────────────────────
    def _build_about(self, tab):
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        ctk.CTkLabel(scroll, text="◈  " + branding.APP_NAME,
                     font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=branding.hx("primary")).pack(pady=(18, 0))
        ctk.CTkLabel(scroll, text=f"Version {branding.VERSION}",
                     text_color=branding.hx("muted")).pack()
        ctk.CTkLabel(scroll, justify="center", text_color=branding.hx("text"),
                     text="\n" + branding.APP_BLURB).pack()
        ctk.CTkLabel(scroll, justify="center", text_color=branding.hx("muted"),
                     text="\nMediaPipe Tasks API · One Euro Filter · customtkinter\n").pack()
        ctk.CTkLabel(scroll, text=f"Created by {branding.AUTHOR}",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=branding.hx("accent")).pack(pady=(6, 2))
        b = ctk.CTkButton(scroll, text="★  Open GitHub Repo", height=36,
                          fg_color=branding.hx("primary"), hover_color=branding.hx("secondary"),
                          command=lambda: webbrowser.open(branding.REPO_URL))
        b.pack(pady=8)
        self._accents.append(("btn", b))
        ctk.CTkLabel(scroll, text="What's New in v3.1",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=branding.hx("accent")).pack(anchor="w", padx=14, pady=(14, 4))
        for line in [
            "🎨  Two new themes — Sunset & Ocean",
            "📊  Dashboard: system check, session chart & screenshots",
            "🃏  Profile cards replacing the old dropdown",
            "🚀  Quick sensitivity bar  🐢 → 🚀",
            "🔊  Sound feedback toggle (macOS afplay)",
            "✌️   Visual gesture & hotkey cards",
            "🎛️  Theme swatches with one-click switching",
            "🔍  Detection & tracking confidence sliders",
            "💡  Rotating tips in the preview pane",
            "✨  Cursor glow, toast accent bar, gradient header strip",
        ]:
            ctk.CTkLabel(scroll, text=line, font=ctk.CTkFont(size=11),
                         text_color=branding.hx("text"), anchor="w").pack(
                             anchor="w", padx=16, pady=2)
        ctk.CTkLabel(scroll, text="\nMIT License",
                     text_color=branding.hx("muted")).pack()

    # ── Preview pane ─────────────────────────────────────────────────────────────
    def _build_preview(self):
        frame = ctk.CTkFrame(self, fg_color=branding.hx("surface"), corner_radius=12)
        frame.grid(row=1, column=1, sticky="nsew", padx=(7, 14), pady=12)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        ph = ctk.CTkFrame(frame, fg_color=branding.hx("surface2"), height=38, corner_radius=0)
        ph.grid(row=0, column=0, sticky="new")
        ph.grid_propagate(False)
        ctk.CTkLabel(ph, text="◈  Live Preview",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=branding.hx("primary")).pack(side="left", padx=12, pady=8)
        self.hand_badge = ctk.CTkLabel(
            ph, text="  ○ No hand  ",
            fg_color=branding.hx("surface"), corner_radius=8,
            text_color=branding.hx("muted"), font=ctk.CTkFont(size=10))
        self.hand_badge.pack(side="right", padx=8, pady=7)

        self.preview = ctk.CTkLabel(
            frame,
            text="◈\n\nLive Preview\n\nPick a camera, then press  ▶ Start preview.\n"
                 "Tune Responsiveness / Smoothness and watch the\n"
                 "glowing dot track your fingertip — your real\n"
                 "mouse is never touched here.",
            font=ctk.CTkFont(size=14), text_color=branding.hx("muted"),
            fg_color=branding.hx("bg"), corner_radius=12)
        self.preview.grid(row=1, column=0, sticky="nsew", padx=12, pady=12)

        ctrl = ctk.CTkFrame(frame, fg_color="transparent")
        ctrl.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 4))
        self.start_btn = ctk.CTkButton(
            ctrl, text="▶  Start preview", height=38,
            fg_color=branding.hx("accent"), hover_color=branding.hx("secondary"),
            text_color="#06210C", font=ctk.CTkFont(weight="bold"),
            command=self._toggle_preview)
        self.start_btn.pack(side="left", expand=True, fill="x")
        self._accents.append(("start", self.start_btn))
        self.readout = ctk.CTkLabel(ctrl, text="",
                                    text_color=branding.hx("muted"),
                                    font=ctk.CTkFont(size=10))
        self.readout.pack(side="right", padx=10)

        self.tip_lbl = ctk.CTkLabel(frame, text="",
                                     text_color=branding.hx("muted"),
                                     font=ctk.CTkFont(size=10), wraplength=420)
        self.tip_lbl.grid(row=3, column=0, padx=12, pady=(0, 6))

    # ── Action bar ───────────────────────────────────────────────────────────────
    def _build_actions(self):
        bar = ctk.CTkFrame(self, fg_color=branding.hx("surface2"), corner_radius=12)
        bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 4))

        self.launch_btn = ctk.CTkButton(
            bar, text="◈  Launch AirMouse", height=48,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=branding.hx("primary"), hover_color=branding.hx("secondary"),
            corner_radius=10, command=self._launch)
        self.launch_btn.pack(side="left", expand=True, fill="x", padx=10, pady=8)
        self._accents.append(("launch", self.launch_btn))

        ctk.CTkButton(bar, text="⚙  Calibrate + Launch", height=48, width=196,
                      corner_radius=10,
                      fg_color=branding.hx("surface2"), hover_color=branding.hx("primary"),
                      command=lambda: self._launch(calibrate=True)).pack(
                          side="left", padx=(0, 6), pady=8)
        ctk.CTkButton(bar, text="💾  Save", width=92, height=48, corner_radius=10,
                      fg_color=branding.hx("surface2"), hover_color=branding.hx("primary"),
                      command=self._save_only).pack(side="left", padx=(0, 6), pady=8)
        ctk.CTkButton(bar, text="↺  Reset", width=92, height=48, corner_radius=10,
                      fg_color=branding.hx("surface2"), hover_color=branding.hx("danger"),
                      command=self._reset).pack(side="left", padx=(0, 10), pady=8)

    # ── Animated launch button ────────────────────────────────────────────────────
    def _start_anim(self):
        self._anim_t = 0.0
        self._anim_loop()

    def _anim_loop(self):
        try:
            self._anim_t += 0.04
            t = (math.sin(self._anim_t) + 1) / 2
            color = _lerp_color(branding.hx("primary"), branding.hx("secondary"), t)
            self.launch_btn.configure(fg_color=color)
            self.after(50, self._anim_loop)
        except Exception:
            pass

    # ── Rotating tips ─────────────────────────────────────────────────────────────
    def _rotate_tip(self):
        try:
            self.tip_lbl.configure(text=TIPS[self._tip_idx % len(TIPS)])
            self._tip_idx += 1
            self.after(6000, self._rotate_tip)
        except Exception:
            pass

    # ── Slider helper ─────────────────────────────────────────────────────────────
    def _slider(self, parent, field, label, lo, hi, is_int):
        value = getattr(self.cfg, field)
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(8, 0))
        head = ctk.CTkFrame(row, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text=label, font=ctk.CTkFont(size=11)).pack(side="left")
        val_lbl = ctk.CTkLabel(head, text=self._fmt(value, is_int),
                               text_color=branding.hx("accent"),
                               font=ctk.CTkFont(size=11, weight="bold"))
        val_lbl.pack(side="right")
        s = ctk.CTkSlider(row, from_=lo, to=hi, progress_color=branding.hx("primary"))
        s.set(value)
        s.pack(fill="x")

        def _on_move(v, lbl=val_lbl, ii=is_int):
            lbl.configure(text=self._fmt(v, ii))
            if not self._suppress:
                self.profile_var.set("Custom")
                self._on_profile_card("Custom")
        s.configure(command=_on_move)
        return {"slider": s, "label": val_lbl, "is_int": is_int}

    @staticmethod
    def _fmt(v, is_int):
        return (str(int(round(float(v)))) if is_int
                else f"{float(v):.3f}".rstrip("0").rstrip("."))

    # ── Profile + theme ───────────────────────────────────────────────────────────
    def _current_profile_name(self):
        for name in PROFILES:
            if self.cfg.matches_profile(name):
                return name
        return self.cfg.profile if self.cfg.profile in PROFILES else "Custom"

    def _on_profile(self, name: str):
        preset = PROFILES.get(name)
        if not preset:
            return
        self._suppress = True
        for field, value in preset.items():
            w = self._sliders.get(field)
            if w:
                w["slider"].set(value)
                w["label"].configure(text=self._fmt(value, w["is_int"]))
        self._suppress = False
        self._set_status(f"Profile: {name}")

    def _on_theme(self, name: str):
        branding.use(name)
        self.cfg.theme = name
        self.theme_var.set(name)
        self._apply_theme()
        self._set_status(f"Theme: {name}")

    def _apply_theme(self):
        self.configure(fg_color=branding.hx("bg"))
        self.badge.configure(
            text=f"  v{branding.VERSION}  ·  {branding.active_name()}  ",
            text_color=branding.hx("accent"))
        self.logo.configure(text_color=branding.hx("primary"))
        self._header_icon.configure(text_color=branding.hx("primary"),
                                    fg_color=branding.hx("surface2"))
        try:
            self._grad_strip.configure(bg=branding.hx("surface"))
            self._grad_strip.set_colors(branding.hx("primary"), branding.hx("accent"))
        except Exception:
            pass

        active = branding.active_name()
        for n, btn in self._swatch_btns.items():
            btn.configure(border_width=3 if n == active else 0)
        if hasattr(self, "_swatch_name_lbl"):
            self._swatch_name_lbl.configure(text=active, text_color=branding.hx("accent"))

        current = self.profile_var.get()
        for n, (card, nl, dl) in self._profile_card_btns.items():
            sel = (n == current)
            card.configure(fg_color=branding.hx("primary") if sel else branding.hx("surface2"))
            nl.configure(text_color="#FFFFFF" if sel else branding.hx("text"))
            dl.configure(text_color="#EEEEEE" if sel else branding.hx("muted"))

        for role, w in self._accents:
            try:
                if role == "start":
                    w.configure(fg_color=branding.hx("accent"),
                                hover_color=branding.hx("secondary"))
                elif role == "btn":
                    w.configure(fg_color=branding.hx("primary"),
                                hover_color=branding.hx("secondary"))
                elif role == "tabs":
                    w.configure(segmented_button_selected_color=branding.hx("primary"),
                                segmented_button_selected_hover_color=branding.hx("secondary"))
                elif role == "tut":
                    w.configure(fg_color=branding.hx("surface2"),
                                hover_color=branding.hx("primary"))
            except Exception:
                pass

    # ── Camera scan ───────────────────────────────────────────────────────────────
    def _scan_cameras(self):
        self.cam_info.configure(text="Scanning cameras…")
        self.cam_menu.configure(state="disabled")
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self):
        cams = list_cameras()
        options = ["Auto-detect"] + [f"Index {i}  ({w}x{h})" for i, w, h in cams]
        self._cam_map = {"Auto-detect": -1}
        for i, w, h in cams:
            self._cam_map[f"Index {i}  ({w}x{h})"] = i
        msg = (f"Found {len(cams)} camera(s)." if cams
               else "No cameras found — check connections/permissions.")
        self.after(0, lambda: (self.cam_menu.configure(values=options, state="normal"),
                               self.cam_info.configure(text=msg)))

    def _selected_camera_index(self):
        return self._cam_map.get(self.cam_var.get(), self.cfg.camera_index)

    # ── Live preview ──────────────────────────────────────────────────────────────
    def _toggle_preview(self):
        self._stop_preview() if self._preview_on else self._start_preview()

    def _start_preview(self):
        import time
        try:
            import cv2  # noqa: F401
            from src.camera import detect_camera, open_camera
            from src.hand_tracker import HandTracker
            from src.gesture import GestureEngine
            from src.filters import OneEuroFilter
        except Exception as exc:
            self._set_status(f"Preview needs OpenCV/Pillow: {exc}", error=True)
            return
        self._set_status("Starting camera…")
        self.update_idletasks()
        try:
            idx = detect_camera(self._selected_camera_index())
            self._cap, _, _ = open_camera(idx, 640, 480)
            self._tracker = HandTracker(1, self.cfg.detection_confidence,
                                        self.cfg.tracking_confidence)
            self._engine = GestureEngine(enable_middle_click=self.mid_var.get())
            self._fx = OneEuroFilter(self.cfg.oe_min_cutoff, self.cfg.oe_beta)
            self._fy = OneEuroFilter(self.cfg.oe_min_cutoff, self.cfg.oe_beta)
        except Exception as exc:
            self._set_status(f"Preview failed: {exc}", error=True)
            self._release_preview()
            return
        self._preview_on = True
        self._pfps_t = time.time()
        self.start_btn.configure(text="■  Stop preview", fg_color=branding.hx("danger"))
        self._set_status("Live preview running — your real mouse is not affected.")
        self._tick()

    def _tick(self):
        import time
        if not self._preview_on or self._cap is None:
            return
        import cv2
        from PIL import Image
        ok, frame = self._cap.read()
        if not ok:
            self._set_status("Camera frame lost.", error=True)
            self._stop_preview()
            return
        if self.flip_var.get():
            frame = cv2.flip(frame, 1)
        results, lms = self._tracker.process(frame)
        if self.lm_var.get():
            self._tracker.draw(frame, results)

        label = ""
        if lms:
            lm = lms[0]
            tx, ty = lm[8].x, lm[8].y
            self._engine.recognize(lm)
            label = self._engine.label
            self._fx.beta = self._fy.beta = float(self._sliders["oe_beta"]["slider"].get())
            self._fx.min_cutoff = self._fy.min_cutoff = float(
                self._sliders["oe_min_cutoff"]["slider"].get())
            sx, sy = self._fx(tx), self._fy(ty)
            H, W = frame.shape[:2]
            # Raw fingertip dot
            cv2.circle(frame, (int(tx * W), int(ty * H)), 5,
                       branding.bgr("muted"), 1, cv2.LINE_AA)
            # Smoothed glow rings
            for r, a in ((20, 0.08), (12, 0.14)):
                ov = frame.copy()
                cv2.circle(ov, (int(sx * W), int(sy * H)), r,
                           branding.bgr("accent"), -1, cv2.LINE_AA)
                cv2.addWeighted(ov, a, frame, 1 - a, 0, frame)
            cv2.circle(frame, (int(sx * W), int(sy * H)), 9,
                       branding.bgr("accent"), 2, cv2.LINE_AA)
            cv2.circle(frame, (int(sx * W), int(sy * H)), 3,
                       branding.bgr("accent"), -1, cv2.LINE_AA)
            if label:
                cv2.putText(frame, label,
                            (int(sx * W) + 14, int(sy * H) - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            branding.bgr("text"), 2, cv2.LINE_AA)

        # Update hand badge
        if lms:
            self.hand_badge.configure(
                text=f"  ✓ {label or 'Tracking'}  ",
                fg_color="#1A3320", text_color=branding.hx("success"))
        else:
            self.hand_badge.configure(
                text="  ○ No hand  ",
                fg_color=branding.hx("surface"), text_color=branding.hx("muted"))

        # FPS counter
        self._pfps_n += 1
        if time.time() - self._pfps_t >= 1.0:
            self._pfps, self._pfps_n, self._pfps_t = self._pfps_n, 0, time.time()
        self.readout.configure(
            text=f"{'tracking' if lms else 'no hand'}  ·  {self._pfps} fps")

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pw = max(360, self.preview.winfo_width() - 24)
        ph_px = int(pw * frame.shape[0] / frame.shape[1])
        img = Image.fromarray(rgb)
        ctkimg = ctk.CTkImage(light_image=img, dark_image=img, size=(pw, ph_px))
        self.preview.configure(image=ctkimg, text="")
        self.preview._img_ref = ctkimg
        self.after(15, self._tick)

    def _stop_preview(self):
        self._preview_on = False
        self._release_preview()
        self.start_btn.configure(text="▶  Start preview", fg_color=branding.hx("accent"))
        self.preview.configure(image=None, text="Preview stopped.")
        self.readout.configure(text="")
        self.hand_badge.configure(text="  ○ No hand  ",
                                  fg_color=branding.hx("surface"),
                                  text_color=branding.hx("muted"))

    def _release_preview(self):
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
        if self._tracker is not None:
            try:
                self._tracker.close()
            except Exception:
                pass
        self._cap = self._tracker = self._engine = None

    # ── Persistence + launch ──────────────────────────────────────────────────────
    def _collect(self):
        c = self.cfg
        for field, w in self._sliders.items():
            v = w["slider"].get()
            setattr(c, field, int(round(v)) if w["is_int"] else round(v, 3))
        c.camera_index    = self._cam_map.get(self.cam_var.get(), -1)
        c.theme           = self.theme_var.get()
        c.flip            = self.flip_var.get()
        c.show_landmarks  = self.lm_var.get()
        c.show_help       = self.help_var.get()
        c.show_fps        = self.fps_var.get()
        c.show_stats      = self.stats_var.get()
        c.always_on_top   = self.top_var.get()
        c.enable_middle_click = self.mid_var.get()
        c.sound_feedback  = self.sound_var.get()
        c.horizontal_scroll = self.hscroll_var.get()
        c.scroll_inertia  = self.inertia_var.get()
        c.idle_pause_secs = round(float(self.idle_slider.get()), 1)
        c.show_tutorial   = self.tutorial_var.get()
        c.coach_overlay   = self.coach_var.get()
        c.profile         = self.profile_var.get()
        c.save()

    def _save_only(self):
        self._collect()
        self._refresh_dashboard()
        self._set_status("Settings saved to config.json ✓", color=branding.hx("success"))

    def _reset(self):
        self.cfg = Config()
        self.cfg.save()
        branding.use(self.cfg.theme)
        self._suppress = True
        for field, w in self._sliders.items():
            val = getattr(self.cfg, field)
            w["slider"].set(val)
            w["label"].configure(text=self._fmt(val, w["is_int"]))
        self._suppress = False
        self.profile_var.set(self._current_profile_name())
        self.theme_var.set(branding.active_name())
        for var, val in (
            (self.flip_var,    self.cfg.flip),
            (self.lm_var,      self.cfg.show_landmarks),
            (self.help_var,    self.cfg.show_help),
            (self.fps_var,     self.cfg.show_fps),
            (self.stats_var,   self.cfg.show_stats),
            (self.top_var,     self.cfg.always_on_top),
            (self.mid_var,     self.cfg.enable_middle_click),
            (self.sound_var,   self.cfg.sound_feedback),
            (self.hscroll_var, self.cfg.horizontal_scroll),
            (self.inertia_var, self.cfg.scroll_inertia),
            (self.tutorial_var, self.cfg.show_tutorial),
            (self.coach_var,   self.cfg.coach_overlay),
        ):
            var.set(val)
        self.idle_slider.set(self.cfg.idle_pause_secs)
        self.idle_lbl.configure(text=str(int(self.cfg.idle_pause_secs)))
        self.cam_var.set("Auto-detect")
        self._apply_theme()
        self._refresh_dashboard()
        self._set_status("Reset to defaults")

    def _launch(self, calibrate=False):
        self._stop_preview()
        self._collect()
        self._set_status("Launching… (close the camera window to return here)")
        self.update()
        cmd = [sys.executable, str(ROOT / "AirMouse.py")]
        if calibrate:
            cmd.append("--calibrate")
        try:
            subprocess.Popen(cmd, cwd=str(ROOT))
            self.after(800, self.destroy)
        except Exception as exc:
            self._set_status(f"Failed: {exc}", error=True)

    # ── Onboarding / tutorial ─────────────────────────────────────────────────────
    def _open_tutorial(self, force=False):
        """Open (or focus) the getting-started walkthrough."""
        if self._tutorial_win is not None:
            try:
                if self._tutorial_win.winfo_exists():
                    self._tutorial_win.focus()
                    return
            except Exception:
                pass
        self._tutorial_win = TutorialOverlay(self, self._tutorial_steps(),
                                             self._tutorial_closed)

    def _tutorial_closed(self, dont_show: bool):
        """Called when the walkthrough is finished/closed. Persists the choice."""
        self._tutorial_win = None
        self.cfg.show_tutorial = not dont_show
        self.cfg.save()
        if hasattr(self, "tutorial_var"):
            self.tutorial_var.set(self.cfg.show_tutorial)
        self._set_status("You're all set — press Launch when ready"
                         if dont_show else "Walkthrough closed")

    def _open_privacy(self, pane: str):
        """Open the relevant macOS Privacy & Security pane (no-op elsewhere)."""
        import platform
        if platform.system() != "Darwin":
            self._set_status("Grant Camera + input permissions for your OS, then relaunch.")
            return
        url = {
            "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
            "camera": "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera",
        }.get(pane, "x-apple.systempreferences:com.apple.preference.security?Privacy")
        try:
            subprocess.Popen(["open", url])
            self._set_status("Opened System Settings → Privacy & Security")
        except Exception as exc:
            self._set_status(f"Couldn't open settings: {exc}", error=True)

    def _tutorial_steps(self):
        return [
            {
                "icon": "◈",
                "title": "Welcome to AirMouse",
                "body": [
                    "Control your laptop in the air — move the cursor, click,",
                    "scroll, drag and even type, using just your hand and a",
                    "webcam. Nothing to touch.",
                    "",
                    "This 30-second walkthrough shows how to grant access,",
                    "the core gestures, and how to start.",
                ],
            },
            {
                "icon": "🔐",
                "title": "1 · Grant access",
                "body": [
                    "AirMouse needs two permissions (System Settings →",
                    "Privacy & Security):",
                    "",
                    "   • Camera         — so it can see your hand",
                    "   • Accessibility  — so it can move the mouse & type",
                    "",
                    "Enable both for Terminal (or Python), then relaunch.",
                ],
                "action": ("Open Privacy & Security",
                           lambda: self._open_privacy("accessibility")),
            },
            {
                "icon": "✋",
                "title": "2 · The core gestures",
                "body": [
                    "   Index finger only       move the cursor",
                    "   Pinch thumb + index      left click  (twice = double)",
                    "   Pinch thumb + middle     right click",
                    "   Peace sign (2 fingers)   scroll — any direction",
                    "   Fist                     drag  (open hand to drop)",
                    "   Open palm (hold)         on-screen keyboard",
                    "   Thumbs-up (hold)         pause / resume",
                ],
            },
            {
                "icon": "🎛️",
                "title": "3 · Tune it to your hand",
                "body": [
                    "   • Tuning tab — pick a profile or drag the sliders.",
                    "   • Press ▶ Start preview to watch tracking live. Your",
                    "     real mouse is NEVER moved in preview, so it's a",
                    "     safe place to experiment.",
                    "   • Calibrate + Launch maps your comfortable reach",
                    "     to the whole screen.",
                ],
            },
            {
                "icon": "🚀",
                "title": "4 · Launch & in-app help",
                "body": [
                    "Press  ◈ Launch AirMouse  to start controlling your",
                    "laptop. While it's running:",
                    "",
                    "   H   full guide          /   show / hide tips",
                    "   C   calibrate           P   pause",
                    "   N   never show tips      Q   quit",
                    "",
                    "That's it — have fun going touch-free!",
                ],
            },
        ]

    # ── Helpers ───────────────────────────────────────────────────────────────────
    def _set_status(self, text, color=None, error=False):
        self.status.configure(
            text=text,
            text_color=branding.hx("danger") if error else (color or branding.hx("muted")))

    def _on_close(self):
        self._stop_preview()
        if self._tutorial_win is not None:
            try:
                self._tutorial_win.destroy()
            except Exception:
                pass
        self.destroy()


# ── Tutorial overlay ───────────────────────────────────────────────────────────────
class TutorialOverlay(ctk.CTkToplevel):
    """A modal, multi-step welcome walkthrough with a 'Don't show again' option."""

    def __init__(self, master, steps, on_close):
        super().__init__(master)
        self._steps = steps
        self._on_close = on_close
        self._i = 0
        self._closed = False
        self.title(f"{branding.APP_NAME} — Getting Started")
        self.geometry("580x500")
        self.resizable(False, False)
        self.configure(fg_color=branding.hx("surface"))
        self.dont_show = ctk.BooleanVar(value=False)
        try:
            self.transient(master)
        except Exception:
            pass
        self.protocol("WM_DELETE_WINDOW", self._finish)
        self._build()
        self._render()
        self.after(60, self._center)
        self.after(150, self._grab)

    def _grab(self):
        try:
            self.grab_set()
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _center(self):
        try:
            self.update_idletasks()
            m = self.master
            x = m.winfo_rootx() + (m.winfo_width() - self.winfo_width()) // 2
            y = m.winfo_rooty() + (m.winfo_height() - self.winfo_height()) // 3
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except Exception:
            pass

    def _build(self):
        self._grad = _GradientStrip(self, branding.hx("primary"), branding.hx("accent"),
                                    h=5, bg=branding.hx("surface"))
        self._grad.pack(fill="x")

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=28, pady=(16, 4))
        self._icon = ctk.CTkLabel(content, text="", font=ctk.CTkFont(size=42))
        self._icon.pack(anchor="w")
        self._title = ctk.CTkLabel(content, text="", anchor="w",
                                   font=ctk.CTkFont(size=21, weight="bold"),
                                   text_color=branding.hx("primary"))
        self._title.pack(anchor="w", pady=(2, 10))
        self._body = ctk.CTkLabel(content, text="", justify="left", anchor="w",
                                  font=ctk.CTkFont(size=13, family="Menlo"),
                                  text_color=branding.hx("text"))
        self._body.pack(anchor="w")
        self._action_btn = ctk.CTkButton(content, text="", height=34, corner_radius=8,
                                         fg_color=branding.hx("surface2"),
                                         hover_color=branding.hx("primary"))

        self._dots = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=15),
                                  text_color=branding.hx("muted"))
        self._dots.pack(pady=(2, 0))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=22, pady=(8, 16))
        ctk.CTkCheckBox(footer, text="Don't show this again", variable=self.dont_show,
                        checkbox_width=18, checkbox_height=18,
                        font=ctk.CTkFont(size=11), fg_color=branding.hx("primary"),
                        hover_color=branding.hx("secondary")).pack(side="left")
        self._next_btn = ctk.CTkButton(footer, text="Next  ›", width=100, height=34,
                                       fg_color=branding.hx("primary"),
                                       hover_color=branding.hx("secondary"),
                                       command=self._next)
        self._next_btn.pack(side="right")
        self._back_btn = ctk.CTkButton(footer, text="‹ Back", width=82, height=34,
                                       fg_color=branding.hx("surface2"),
                                       hover_color=branding.hx("primary"),
                                       command=self._back)
        self._back_btn.pack(side="right", padx=(0, 8))
        ctk.CTkButton(footer, text="Skip", width=62, height=34, fg_color="transparent",
                      hover_color=branding.hx("surface2"), text_color=branding.hx("muted"),
                      command=self._finish).pack(side="right", padx=(0, 8))

    def _render(self):
        step = self._steps[self._i]
        self._icon.configure(text=step["icon"])
        self._title.configure(text=step["title"])
        self._body.configure(text="\n".join(step["body"]))
        action = step.get("action")
        if action:
            label, cmd = action
            self._action_btn.configure(text=label, command=cmd)
            self._action_btn.pack(anchor="w", pady=(16, 0))
        else:
            self._action_btn.pack_forget()
        self._dots.configure(
            text="   ".join("●" if k == self._i else "○"
                            for k in range(len(self._steps))))
        self._back_btn.configure(state="normal" if self._i > 0 else "disabled")
        self._next_btn.configure(
            text="Finish  ✓" if self._i == len(self._steps) - 1 else "Next  ›")

    def _next(self):
        if self._i >= len(self._steps) - 1:
            self._finish()
        else:
            self._i += 1
            self._render()

    def _back(self):
        if self._i > 0:
            self._i -= 1
            self._render()

    def _finish(self):
        if self._closed:
            return
        self._closed = True
        dont = bool(self.dont_show.get())
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        if self._on_close:
            self._on_close(dont)


if __name__ == "__main__":
    Studio().mainloop()
