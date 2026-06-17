#!/usr/bin/env python3
"""
AirMouse Control Center — a polished GUI to configure and launch AirMouse.

Pick a camera, choose a tuning profile or fine-tune every setting with sliders,
toggle features, read the gesture cheat-sheet, then Launch. Everything is saved
to config.json so the standalone `python AirMouse.py` picks it up too.

Run:  python launcher.py

Requires customtkinter (pip install customtkinter). If it isn't installed,
just run `python AirMouse.py` directly instead.
"""
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

try:
    import customtkinter as ctk
except ImportError:
    print("customtkinter not installed. Run: pip install customtkinter")
    print("Or launch directly with: python AirMouse.py")
    sys.exit(1)

from config import Config, PROFILES
from src.camera import list_cameras

ROOT = Path(__file__).parent
REPO_URL = "https://github.com/at0m-b0mb/AirMouse-Hand-Gesture-Control"
VERSION = "2.0"

ACCENT = "#5aa0ff"
MUTED = "#8a8a8a"

GESTURE_GUIDE = """HAND GESTURES
─────────────────────────────────────────────
Index finger pointing      Move cursor
Pinch thumb + index        Left click  (twice = double-click)
Pinch thumb + middle       Right click
Pinch thumb + ring         Middle click  (enable in Options)
Peace sign (index + mid)   Scroll — move up/down, left/right
Fist (fingers curled)      Drag — fist to grab, open to drop
Open palm, hold ~1s        Toggle virtual keyboard
Thumbs-up, hold ~0.7s      Pause / resume control

VIRTUAL KEYBOARD
─────────────────────────────────────────────
Move your hand to hover a key, pinch to press it.
Function row adds arrows, Esc, volume, mute,
play/pause and screenshot. Caps & Shift supported,
with a live text-preview bar.

HOTKEYS (while running)
─────────────────────────────────────────────
H  help overlay        S  screenshot
P  pause / resume      L  toggle skeleton
C  calibrate range     F  toggle mirror
G  toggle FPS          T  toggle always-on-top
+ / -  sensitivity     [ / ]  smoothing
Q / ESC  quit (saves your settings)
"""


class ControlCenter(ctk.CTk):
    # tuning fields edited by sliders → (label, lo, hi, is_int)
    SLIDERS = {
        "sensitivity":   ("Sensitivity", 0.3, 3.0, False),
        "oe_beta":       ("Responsiveness", 0.001, 0.06, False),
        "oe_min_cutoff": ("Smoothness", 0.3, 2.0, False),
        "cursor_margin": ("Edge margin", 0.02, 0.25, False),
        "scroll_speed":  ("Scroll speed", 1, 10, True),
        "click_threshold": ("Click sensitivity", 0.03, 0.09, False),
    }

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("AirMouse Control Center")
        self.geometry("520x760")
        self.minsize(500, 700)

        self.cfg = Config.load()
        self._suppress = False           # suppress slider→"Custom" callback
        self._cam_map = {"Auto-detect": -1}
        self._sliders: dict = {}
        self._build()

    # ── layout ──────────────────────────────────────────────────────────────
    def _build(self):
        ctk.CTkLabel(self, text="AirMouse",
                     font=ctk.CTkFont(size=32, weight="bold")).pack(pady=(18, 0))
        ctk.CTkLabel(self, text="Gesture Laptop Controller  ·  Control Center",
                     text_color=MUTED).pack()

        tabs = ctk.CTkTabview(self, anchor="w")
        tabs.pack(fill="both", expand=True, padx=16, pady=(12, 6))
        for name in ("Tuning", "Camera", "Options", "Gestures", "About"):
            tabs.add(name)
        self._build_tuning(tabs.tab("Tuning"))
        self._build_camera(tabs.tab("Camera"))
        self._build_options(tabs.tab("Options"))
        self._build_gestures(tabs.tab("Gestures"))
        self._build_about(tabs.tab("About"))

        # bottom action bar
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=16, pady=(0, 6))
        ctk.CTkButton(btns, text="▶  Launch AirMouse", height=44,
                      font=ctk.CTkFont(size=15, weight="bold"),
                      command=self._launch).pack(fill="x", pady=(0, 6))
        row = ctk.CTkFrame(btns, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkButton(row, text="Calibrate then launch", height=34,
                      fg_color="#2b2b2b", hover_color="#3a3a3a",
                      command=lambda: self._launch(calibrate=True)).pack(
                          side="left", expand=True, fill="x", padx=(0, 4))
        ctk.CTkButton(row, text="Save", width=70, height=34,
                      fg_color="#2b2b2b", hover_color="#3a3a3a",
                      command=self._save_only).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Reset", width=70, height=34,
                      fg_color="#3a2b2b", hover_color="#4a3a3a",
                      command=self._reset).pack(side="left", padx=(4, 0))

        self.status = ctk.CTkLabel(self, text="Ready", text_color=MUTED)
        self.status.pack(pady=(0, 8))

    def _build_tuning(self, tab):
        head = ctk.CTkFrame(tab, fg_color="transparent")
        head.pack(fill="x", padx=10, pady=(12, 4))
        ctk.CTkLabel(head, text="Profile").pack(side="left")
        self.profile_var = ctk.StringVar(value=self._current_profile_name())
        ctk.CTkOptionMenu(head, values=list(PROFILES) + ["Custom"],
                          variable=self.profile_var,
                          command=self._on_profile).pack(side="right")

        for field, (label, lo, hi, is_int) in self.SLIDERS.items():
            self._sliders[field] = self._slider(tab, field, label, lo, hi, is_int)

    def _build_camera(self, tab):
        ctk.CTkLabel(tab, text="Camera source").pack(anchor="w", padx=12, pady=(14, 2))
        self.cam_var = ctk.StringVar(value="Auto-detect")
        self.cam_menu = ctk.CTkOptionMenu(tab, values=["Auto-detect"],
                                          variable=self.cam_var)
        self.cam_menu.pack(fill="x", padx=12)
        ctk.CTkButton(tab, text="🔍  Scan for cameras", height=34,
                      fg_color="#2b2b2b", hover_color="#3a3a3a",
                      command=self._scan_cameras).pack(fill="x", padx=12, pady=10)
        self.cam_info = ctk.CTkLabel(
            tab, text="Auto-detect picks the first working webcam.\n"
                      "Scan to choose a specific one.",
            text_color=MUTED, justify="left")
        self.cam_info.pack(anchor="w", padx=12)
        # if a camera index was previously saved, reflect it
        if self.cfg.camera_index >= 0:
            self.cam_info.configure(text=f"Saved camera index: {self.cfg.camera_index}")

    def _build_options(self, tab):
        self.flip_var = ctk.BooleanVar(value=self.cfg.flip)
        self.lm_var = ctk.BooleanVar(value=self.cfg.show_landmarks)
        self.help_var = ctk.BooleanVar(value=self.cfg.show_help)
        self.fps_var = ctk.BooleanVar(value=self.cfg.show_fps)
        self.top_var = ctk.BooleanVar(value=self.cfg.always_on_top)
        self.mid_var = ctk.BooleanVar(value=self.cfg.enable_middle_click)
        self.hscroll_var = ctk.BooleanVar(value=self.cfg.horizontal_scroll)

        rows = [
            ("Mirror image (flip)", self.flip_var),
            ("Show hand skeleton", self.lm_var),
            ("Start with help overlay", self.help_var),
            ("Show FPS counter", self.fps_var),
            ("Keep window always on top", self.top_var),
            ("Middle click (thumb + ring pinch)", self.mid_var),
            ("Horizontal scroll", self.hscroll_var),
        ]
        for text, var in rows:
            ctk.CTkSwitch(tab, text=text, variable=var).pack(
                anchor="w", padx=16, pady=8)

    def _build_gestures(self, tab):
        box = ctk.CTkTextbox(tab, wrap="none",
                             font=ctk.CTkFont(family="Menlo", size=12))
        box.pack(fill="both", expand=True, padx=8, pady=8)
        box.insert("1.0", GESTURE_GUIDE)
        box.configure(state="disabled")

    def _build_about(self, tab):
        ctk.CTkLabel(tab, text="AirMouse", font=ctk.CTkFont(size=22, weight="bold")
                     ).pack(pady=(18, 0))
        ctk.CTkLabel(tab, text=f"Version {VERSION}", text_color=MUTED).pack()
        ctk.CTkLabel(
            tab, justify="center", text_color="#b8b8b8",
            text="\nControl your laptop entirely with hand gestures\n"
                 "via your webcam — cursor, clicks, scroll, drag,\n"
                 "and an on-screen virtual keyboard.\n\n"
                 "MediaPipe hand tracking · One Euro Filter\n",
        ).pack()
        ctk.CTkLabel(tab, text="Created by at0m-b0mb",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(6, 2))
        ctk.CTkButton(tab, text="★  Open GitHub repo", height=36,
                      command=lambda: webbrowser.open(REPO_URL)).pack(pady=8)
        ctk.CTkLabel(tab, text="MIT License", text_color=MUTED).pack()

    # ── slider helper ─────────────────────────────────────────────────────────
    def _slider(self, parent, field, label, lo, hi, is_int):
        value = getattr(self.cfg, field)
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(10, 0))
        head = ctk.CTkFrame(row, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text=label).pack(side="left")
        val_lbl = ctk.CTkLabel(head, text=self._fmt(value, is_int), text_color=ACCENT)
        val_lbl.pack(side="right")
        s = ctk.CTkSlider(row, from_=lo, to=hi)
        s.set(value)
        s.pack(fill="x")

        def _on_move(v, lbl=val_lbl, ii=is_int):
            lbl.configure(text=self._fmt(v, ii))
            if not self._suppress:
                self.profile_var.set("Custom")
        s.configure(command=_on_move)
        return {"slider": s, "label": val_lbl, "is_int": is_int}

    @staticmethod
    def _fmt(v, is_int):
        if is_int:
            return str(int(round(float(v))))
        return f"{float(v):.3f}".rstrip("0").rstrip(".")

    # ── profile handling ───────────────────────────────────────────────────────
    def _current_profile_name(self):
        for name in PROFILES:
            if self.cfg.matches_profile(name):
                return name
        return self.cfg.profile if self.cfg.profile in PROFILES else "Custom"

    def _on_profile(self, name):
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
        self.status.configure(text=f"Profile: {name}", text_color=MUTED)

    # ── camera scan (threaded so the UI stays responsive) ───────────────────────
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
        # UI updates back on the main thread
        self.after(0, lambda: self._apply_scan(options, msg))

    def _apply_scan(self, options, msg):
        self.cam_menu.configure(values=options, state="normal")
        self.cam_info.configure(text=msg)

    # ── persistence + launch ────────────────────────────────────────────────────
    def _collect(self):
        c = self.cfg
        for field, w in self._sliders.items():
            v = w["slider"].get()
            setattr(c, field, int(round(v)) if w["is_int"] else round(v, 3))
        c.camera_index = self._cam_map.get(self.cam_var.get(), -1)
        c.flip = self.flip_var.get()
        c.show_landmarks = self.lm_var.get()
        c.show_help = self.help_var.get()
        c.show_fps = self.fps_var.get()
        c.always_on_top = self.top_var.get()
        c.enable_middle_click = self.mid_var.get()
        c.horizontal_scroll = self.hscroll_var.get()
        c.profile = self.profile_var.get()
        c.save()

    def _save_only(self):
        self._collect()
        self.status.configure(text="Settings saved to config.json ✓",
                              text_color="#5fd38a")

    def _reset(self):
        self.cfg = Config()
        self.cfg.save()
        # refresh every widget from defaults
        self._suppress = True
        for field, w in self._sliders.items():
            val = getattr(self.cfg, field)
            w["slider"].set(val)
            w["label"].configure(text=self._fmt(val, w["is_int"]))
        self._suppress = False
        self.profile_var.set(self._current_profile_name())
        for var, val in ((self.flip_var, self.cfg.flip),
                         (self.lm_var, self.cfg.show_landmarks),
                         (self.help_var, self.cfg.show_help),
                         (self.fps_var, self.cfg.show_fps),
                         (self.top_var, self.cfg.always_on_top),
                         (self.mid_var, self.cfg.enable_middle_click),
                         (self.hscroll_var, self.cfg.horizontal_scroll)):
            var.set(val)
        self.cam_var.set("Auto-detect")
        self.status.configure(text="Reset to defaults", text_color=MUTED)

    def _launch(self, calibrate=False):
        self._collect()
        self.status.configure(text="Launching… (close the camera window to return)")
        self.update()
        cmd = [sys.executable, str(ROOT / "AirMouse.py")]
        if calibrate:
            cmd.append("--calibrate")
        try:
            subprocess.Popen(cmd, cwd=str(ROOT))
            self.after(800, self.destroy)
        except Exception as exc:
            self.status.configure(text=f"Failed: {exc}", text_color="#ff6b6b")


if __name__ == "__main__":
    ControlCenter().mainloop()
