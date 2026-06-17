#!/usr/bin/env python3
"""
AirMouse Studio — a beautiful control center for AirMouse.

A two-pane GUI: tune everything on the left, watch a LIVE webcam preview on the
right (hand skeleton + a raw-vs-smoothed cursor dot so you can dial in smoothing
without touching your real mouse). Pick a profile, theme, camera and options,
then Launch. Settings are written to config.json for `python AirMouse.py` too.

Run:  python launcher.py     (needs customtkinter + Pillow)
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
from src import branding
from src.camera import list_cameras

ROOT = Path(__file__).parent

GESTURE_GUIDE = """HAND GESTURES
─────────────────────────────────────────────
Index finger pointing      Move cursor
Pinch thumb + index        Left click  (twice = double-click)
Pinch thumb + middle       Right click
Pinch thumb + ring         Middle click  (enable in Options)
Peace sign (index + mid)   Scroll — up/down, left/right
Fist (fingers curled)      Drag — fist to grab, open to drop
Open palm, hold ~1s        Toggle virtual keyboard
Thumbs-up, hold ~0.7s      Pause / resume control

VIRTUAL KEYBOARD
─────────────────────────────────────────────
Hover a key, pinch to press. Function row adds
arrows, Esc, volume, mute, play/pause, screenshot.
Caps & Shift supported, with a live preview bar.

HOTKEYS (while running)
─────────────────────────────────────────────
H  help overlay      P / Space  pause / freeze
C  calibrate         S  screenshot
G  FPS   I  stats    L  skeleton   F  mirror
Y  cycle theme       T  always-on-top
+ / -  sensitivity   [ / ]  smoothing
Q / ESC  quit (saves your settings)
"""


class Studio(ctk.CTk):
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
        self.cfg = Config.load()
        branding.use(self.cfg.theme)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(f"{branding.APP_NAME} Studio")
        self.geometry("1000x720")
        self.minsize(900, 660)
        self.configure(fg_color=branding.hx("bg"))

        self._suppress = False
        self._cam_map = {"Auto-detect": -1}
        self._sliders: dict = {}
        self._accents: list = []     # widgets recoloured on theme change
        # preview state
        self._preview_on = False
        self._cap = None
        self._tracker = None
        self._engine = None
        self._fx = self._fy = None
        self._pfps = 0
        self._pfps_n = 0
        self._pfps_t = 0.0

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── layout ──────────────────────────────────────────────────────────────────
    def _build(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_controls()
        self._build_preview()
        self._build_actions()

        self.status = ctk.CTkLabel(self, text="Ready", text_color=branding.hx("muted"))
        self.status.grid(row=3, column=0, columnspan=2, pady=(0, 8))

    def _build_header(self):
        bar = ctk.CTkFrame(self, fg_color=branding.hx("surface"), corner_radius=0)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=10)

        self.logo = ctk.CTkLabel(inner, text="◓ " + branding.APP_NAME,
                                 font=ctk.CTkFont(size=26, weight="bold"),
                                 text_color=branding.hx("primary"))
        self.logo.pack(side="left")
        ctk.CTkLabel(inner, text="  " + branding.APP_TAGLINE,
                     text_color=branding.hx("muted")).pack(side="left")
        self.badge = ctk.CTkLabel(inner, text=f"v{branding.VERSION}  ·  {branding.active_name()}",
                                  text_color=branding.hx("accent"))
        self.badge.pack(side="right")

    def _build_controls(self):
        tabs = ctk.CTkTabview(self, anchor="w", width=430,
                              fg_color=branding.hx("surface"),
                              segmented_button_selected_color=branding.hx("primary"),
                              segmented_button_selected_hover_color=branding.hx("secondary"))
        tabs.grid(row=1, column=0, sticky="nsew", padx=(14, 7), pady=12)
        self._tabs = tabs
        self._accents.append(("tabs", tabs))
        for name in ("Tuning", "Camera", "Options", "Gestures", "About"):
            tabs.add(name)
        self._build_tuning(tabs.tab("Tuning"))
        self._build_camera(tabs.tab("Camera"))
        self._build_options(tabs.tab("Options"))
        self._build_gestures(tabs.tab("Gestures"))
        self._build_about(tabs.tab("About"))

    def _build_tuning(self, tab):
        head = ctk.CTkFrame(tab, fg_color="transparent")
        head.pack(fill="x", padx=10, pady=(12, 2))
        ctk.CTkLabel(head, text="Profile").pack(side="left")
        self.profile_var = ctk.StringVar(value=self._current_profile_name())
        ctk.CTkOptionMenu(head, values=list(PROFILES) + ["Custom"],
                          variable=self.profile_var, command=self._on_profile,
                          fg_color=branding.hx("surface2"),
                          button_color=branding.hx("primary")).pack(side="right")
        for field, (label, lo, hi, is_int) in self.SLIDERS.items():
            self._sliders[field] = self._slider(tab, field, label, lo, hi, is_int)

    def _build_camera(self, tab):
        ctk.CTkLabel(tab, text="Camera source").pack(anchor="w", padx=12, pady=(14, 2))
        self.cam_var = ctk.StringVar(value="Auto-detect")
        self.cam_menu = ctk.CTkOptionMenu(tab, values=["Auto-detect"], variable=self.cam_var,
                                          fg_color=branding.hx("surface2"),
                                          button_color=branding.hx("primary"))
        self.cam_menu.pack(fill="x", padx=12)
        ctk.CTkButton(tab, text="🔍  Scan for cameras", height=34,
                      fg_color=branding.hx("surface2"), hover_color=branding.hx("primary"),
                      command=self._scan_cameras).pack(fill="x", padx=12, pady=10)
        self.cam_info = ctk.CTkLabel(
            tab, text="Auto-detect picks the first working webcam.\n"
                      "Scan to choose a specific one, then Start preview →",
            text_color=branding.hx("muted"), justify="left")
        self.cam_info.pack(anchor="w", padx=12)
        if self.cfg.camera_index >= 0:
            self.cam_info.configure(text=f"Saved camera index: {self.cfg.camera_index}")

    def _build_options(self, tab):
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(scroll, text="Theme").pack(anchor="w", padx=8, pady=(6, 0))
        self.theme_var = ctk.StringVar(value=branding.active_name())
        ctk.CTkOptionMenu(scroll, values=list(branding.THEMES), variable=self.theme_var,
                          command=self._on_theme, fg_color=branding.hx("surface2"),
                          button_color=branding.hx("primary")).pack(fill="x", padx=8, pady=(0, 8))

        self.flip_var = ctk.BooleanVar(value=self.cfg.flip)
        self.lm_var = ctk.BooleanVar(value=self.cfg.show_landmarks)
        self.help_var = ctk.BooleanVar(value=self.cfg.show_help)
        self.fps_var = ctk.BooleanVar(value=self.cfg.show_fps)
        self.stats_var = ctk.BooleanVar(value=self.cfg.show_stats)
        self.top_var = ctk.BooleanVar(value=self.cfg.always_on_top)
        self.mid_var = ctk.BooleanVar(value=self.cfg.enable_middle_click)
        self.hscroll_var = ctk.BooleanVar(value=self.cfg.horizontal_scroll)
        self.inertia_var = ctk.BooleanVar(value=self.cfg.scroll_inertia)
        for text, var in [
            ("Mirror image (flip)", self.flip_var),
            ("Show hand skeleton", self.lm_var),
            ("Start with help overlay", self.help_var),
            ("Show FPS counter", self.fps_var),
            ("Show session stats", self.stats_var),
            ("Keep window always on top", self.top_var),
            ("Middle click (thumb + ring)", self.mid_var),
            ("Horizontal scroll", self.hscroll_var),
            ("Scroll inertia (momentum)", self.inertia_var),
        ]:
            ctk.CTkSwitch(scroll, text=text, variable=var,
                          progress_color=branding.hx("primary")).pack(anchor="w", padx=8, pady=6)

        ctk.CTkLabel(scroll, text="Auto-pause when idle (seconds, 0 = off)").pack(
            anchor="w", padx=8, pady=(10, 0))
        self.idle_lbl = ctk.CTkLabel(scroll, text=str(int(self.cfg.idle_pause_secs)),
                                     text_color=branding.hx("accent"))
        self.idle_lbl.pack(anchor="e", padx=8)
        self.idle_slider = ctk.CTkSlider(scroll, from_=0, to=60, number_of_steps=60,
                                         progress_color=branding.hx("primary"),
                                         command=lambda v: self.idle_lbl.configure(
                                             text=str(int(float(v)))))
        self.idle_slider.set(self.cfg.idle_pause_secs)
        self.idle_slider.pack(fill="x", padx=8)

    def _build_gestures(self, tab):
        box = ctk.CTkTextbox(tab, wrap="none", fg_color=branding.hx("surface2"),
                             font=ctk.CTkFont(family="Menlo", size=12))
        box.pack(fill="both", expand=True, padx=8, pady=8)
        box.insert("1.0", GESTURE_GUIDE)
        box.configure(state="disabled")

    def _build_about(self, tab):
        ctk.CTkLabel(tab, text=branding.APP_NAME,
                     font=ctk.CTkFont(size=24, weight="bold"),
                     text_color=branding.hx("primary")).pack(pady=(18, 0))
        ctk.CTkLabel(tab, text=f"Version {branding.VERSION}",
                     text_color=branding.hx("muted")).pack()
        ctk.CTkLabel(tab, justify="center", text_color=branding.hx("text"),
                     text="\n" + branding.APP_BLURB +
                          "\n\nMediaPipe hand tracking · One Euro Filter\n").pack()
        ctk.CTkLabel(tab, text=f"Created by {branding.AUTHOR}",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=branding.hx("accent")).pack(pady=(6, 2))
        b = ctk.CTkButton(tab, text="★  Open GitHub repo", height=36,
                          fg_color=branding.hx("primary"), hover_color=branding.hx("secondary"),
                          command=lambda: webbrowser.open(branding.REPO_URL))
        b.pack(pady=8)
        self._accents.append(("btn", b))
        ctk.CTkLabel(tab, text="MIT License", text_color=branding.hx("muted")).pack()

    def _build_preview(self):
        frame = ctk.CTkFrame(self, fg_color=branding.hx("surface"))
        frame.grid(row=1, column=1, sticky="nsew", padx=(7, 14), pady=12)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        self.preview = ctk.CTkLabel(
            frame, text="◓\n\nLive preview\n\nPick a camera, then press Start preview.\n"
                        "Tune Responsiveness / Smoothness and watch the\n"
                        "bright dot track your fingertip — your real mouse\n"
                        "is never touched here.",
            font=ctk.CTkFont(size=14), text_color=branding.hx("muted"),
            fg_color=branding.hx("bg"), corner_radius=12)
        self.preview.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

        ctrl = ctk.CTkFrame(frame, fg_color="transparent")
        ctrl.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        self.start_btn = ctk.CTkButton(ctrl, text="▶  Start preview", height=38,
                                       fg_color=branding.hx("accent"),
                                       hover_color=branding.hx("secondary"),
                                       text_color="#06210C",
                                       font=ctk.CTkFont(weight="bold"),
                                       command=self._toggle_preview)
        self.start_btn.pack(side="left", expand=True, fill="x")
        self._accents.append(("start", self.start_btn))
        self.readout = ctk.CTkLabel(ctrl, text="", text_color=branding.hx("muted"))
        self.readout.pack(side="right", padx=10)

    def _build_actions(self):
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 4))
        self.launch_btn = ctk.CTkButton(bar, text="▶  Launch AirMouse", height=44,
                                        font=ctk.CTkFont(size=15, weight="bold"),
                                        fg_color=branding.hx("primary"),
                                        hover_color=branding.hx("secondary"),
                                        command=self._launch)
        self.launch_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self._accents.append(("launch", self.launch_btn))
        ctk.CTkButton(bar, text="Calibrate + launch", height=44, width=160,
                      fg_color=branding.hx("surface2"), hover_color=branding.hx("primary"),
                      command=lambda: self._launch(calibrate=True)).pack(side="left", padx=6)
        ctk.CTkButton(bar, text="Save", width=80, height=44,
                      fg_color=branding.hx("surface2"), hover_color=branding.hx("primary"),
                      command=self._save_only).pack(side="left", padx=6)
        ctk.CTkButton(bar, text="Reset", width=80, height=44,
                      fg_color=branding.hx("surface2"), hover_color=branding.hx("danger"),
                      command=self._reset).pack(side="left", padx=(6, 0))

    # ── slider helper ────────────────────────────────────────────────────────────
    def _slider(self, parent, field, label, lo, hi, is_int):
        value = getattr(self.cfg, field)
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(10, 0))
        head = ctk.CTkFrame(row, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text=label).pack(side="left")
        val_lbl = ctk.CTkLabel(head, text=self._fmt(value, is_int),
                               text_color=branding.hx("accent"))
        val_lbl.pack(side="right")
        s = ctk.CTkSlider(row, from_=lo, to=hi, progress_color=branding.hx("primary"))
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
        return str(int(round(float(v)))) if is_int else f"{float(v):.3f}".rstrip("0").rstrip(".")

    # ── profile + theme ──────────────────────────────────────────────────────────
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
        self._set_status(f"Profile: {name}")

    def _on_theme(self, name):
        branding.use(name)
        self.cfg.theme = name
        self._apply_theme()
        self._set_status(f"Theme: {name}")

    def _apply_theme(self):
        """Recolour the prominent accent widgets so theme changes are visible live."""
        self.configure(fg_color=branding.hx("bg"))
        self.badge.configure(text=f"v{branding.VERSION}  ·  {branding.active_name()}",
                             text_color=branding.hx("accent"))
        self.logo.configure(text_color=branding.hx("primary"))
        for role, w in self._accents:
            try:
                if role == "launch":
                    w.configure(fg_color=branding.hx("primary"),
                                hover_color=branding.hx("secondary"))
                elif role == "start":
                    w.configure(fg_color=branding.hx("accent"),
                                hover_color=branding.hx("secondary"))
                elif role == "btn":
                    w.configure(fg_color=branding.hx("primary"),
                                hover_color=branding.hx("secondary"))
                elif role == "tabs":
                    w.configure(segmented_button_selected_color=branding.hx("primary"),
                                segmented_button_selected_hover_color=branding.hx("secondary"))
            except Exception:
                pass

    # ── camera scan ──────────────────────────────────────────────────────────────
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

    # ── live preview ─────────────────────────────────────────────────────────────
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
        import numpy as np  # noqa: F401
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
            cv2.circle(frame, (int(tx * W), int(ty * H)), 6, branding.bgr("muted"), 1, cv2.LINE_AA)
            cv2.circle(frame, (int(sx * W), int(sy * H)), 11, branding.bgr("accent"), 2, cv2.LINE_AA)
            if label:
                cv2.putText(frame, label, (int(sx * W) + 14, int(sy * H) - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, branding.bgr("text"), 2, cv2.LINE_AA)

        # tracking fps
        self._pfps_n += 1
        if time.time() - self._pfps_t >= 1.0:
            self._pfps, self._pfps_n, self._pfps_t = self._pfps_n, 0, time.time()
        self.readout.configure(text=f"{'tracking' if lms else 'no hand'}  ·  {self._pfps} fps")

        # render to the label
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pw = max(360, self.preview.winfo_width() - 24)
        ph = int(pw * frame.shape[0] / frame.shape[1])
        img = Image.fromarray(rgb)
        ctkimg = ctk.CTkImage(light_image=img, dark_image=img, size=(pw, ph))
        self.preview.configure(image=ctkimg, text="")
        self.preview._img_ref = ctkimg  # keep a reference alive
        self.after(15, self._tick)

    def _stop_preview(self):
        self._preview_on = False
        self._release_preview()
        self.start_btn.configure(text="▶  Start preview", fg_color=branding.hx("accent"))
        self.preview.configure(image=None, text="Preview stopped.")
        self.readout.configure(text="")

    def _release_preview(self):
        try:
            if self._cap is not None:
                self._cap.release()
        except Exception:
            pass
        try:
            if self._tracker is not None:
                self._tracker.close()
        except Exception:
            pass
        self._cap = self._tracker = self._engine = None

    # ── persistence + launch ─────────────────────────────────────────────────────
    def _collect(self):
        c = self.cfg
        for field, w in self._sliders.items():
            v = w["slider"].get()
            setattr(c, field, int(round(v)) if w["is_int"] else round(v, 3))
        c.camera_index = self._cam_map.get(self.cam_var.get(), -1)
        c.theme = self.theme_var.get()
        c.flip = self.flip_var.get()
        c.show_landmarks = self.lm_var.get()
        c.show_help = self.help_var.get()
        c.show_fps = self.fps_var.get()
        c.show_stats = self.stats_var.get()
        c.always_on_top = self.top_var.get()
        c.enable_middle_click = self.mid_var.get()
        c.horizontal_scroll = self.hscroll_var.get()
        c.scroll_inertia = self.inertia_var.get()
        c.idle_pause_secs = round(float(self.idle_slider.get()), 1)
        c.profile = self.profile_var.get()
        c.save()

    def _save_only(self):
        self._collect()
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
        for var, val in ((self.flip_var, self.cfg.flip), (self.lm_var, self.cfg.show_landmarks),
                         (self.help_var, self.cfg.show_help), (self.fps_var, self.cfg.show_fps),
                         (self.stats_var, self.cfg.show_stats), (self.top_var, self.cfg.always_on_top),
                         (self.mid_var, self.cfg.enable_middle_click),
                         (self.hscroll_var, self.cfg.horizontal_scroll),
                         (self.inertia_var, self.cfg.scroll_inertia)):
            var.set(val)
        self.idle_slider.set(self.cfg.idle_pause_secs)
        self.idle_lbl.configure(text=str(int(self.cfg.idle_pause_secs)))
        self.cam_var.set("Auto-detect")
        self._apply_theme()
        self._set_status("Reset to defaults")

    def _launch(self, calibrate=False):
        self._stop_preview()        # free the camera for the standalone app
        self._collect()
        self._set_status("Launching… (close the camera window to return)")
        self.update()
        cmd = [sys.executable, str(ROOT / "AirMouse.py")]
        if calibrate:
            cmd.append("--calibrate")
        try:
            subprocess.Popen(cmd, cwd=str(ROOT))
            self.after(800, self.destroy)
        except Exception as exc:
            self._set_status(f"Failed: {exc}", error=True)

    # ── helpers ──────────────────────────────────────────────────────────────────
    def _set_status(self, text, color=None, error=False):
        self.status.configure(text=text,
                              text_color=branding.hx("danger") if error
                              else (color or branding.hx("muted")))

    def _on_close(self):
        self._stop_preview()
        self.destroy()


if __name__ == "__main__":
    Studio().mainloop()
