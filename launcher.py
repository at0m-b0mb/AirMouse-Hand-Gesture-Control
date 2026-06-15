#!/usr/bin/env python3
"""
AirMouse Launcher — a small GUI to pick your camera, tune settings with
sliders, and launch AirMouse. Settings are written to config.json.

Run:  python launcher.py

Requires customtkinter (pip install customtkinter). If it isn't installed,
just run `python AirMouse.py` directly instead.
"""
import subprocess
import sys
from pathlib import Path

try:
    import customtkinter as ctk
except ImportError:
    print("customtkinter not installed. Run: pip install customtkinter")
    print("Or launch directly with: python AirMouse.py")
    sys.exit(1)

from config import Config
from src.camera import list_cameras

ROOT = Path(__file__).parent


class Launcher(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("AirMouse Launcher")
        self.geometry("440x620")
        self.resizable(False, False)

        self.cfg = Config.load()
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="AirMouse",
                     font=ctk.CTkFont(size=30, weight="bold")).pack(pady=(22, 0))
        ctk.CTkLabel(self, text="Gesture Laptop Controller",
                     text_color="#7a7a7a").pack()

        body = ctk.CTkFrame(self)
        body.pack(fill="both", expand=True, padx=20, pady=18)

        # Camera picker
        ctk.CTkLabel(body, text="Camera").pack(anchor="w", padx=16, pady=(16, 2))
        cams = list_cameras()
        options = ([f"Auto-detect"] +
                   [f"Index {i}  ({w}x{h})" for i, w, h in cams]) or ["Auto-detect"]
        self._cam_map = {"Auto-detect": -1}
        for i, w, h in cams:
            self._cam_map[f"Index {i}  ({w}x{h})"] = i
        self.cam_var = ctk.StringVar(value=options[0])
        ctk.CTkOptionMenu(body, values=options, variable=self.cam_var).pack(
            fill="x", padx=16)

        # Sliders
        self.sens = self._slider(body, "Sensitivity", 0.3, 3.0, self.cfg.sensitivity)
        self.beta = self._slider(body, "Responsiveness", 0.001, 0.06, self.cfg.oe_beta)
        self.margin = self._slider(body, "Edge reach", 0.02, 0.25, self.cfg.cursor_margin)
        self.scroll = self._slider(body, "Scroll speed", 1, 10, self.cfg.scroll_speed)

        # Toggles
        self.flip_var = ctk.BooleanVar(value=self.cfg.flip)
        self.lm_var = ctk.BooleanVar(value=self.cfg.show_landmarks)
        self.help_var = ctk.BooleanVar(value=self.cfg.show_help)
        tog = ctk.CTkFrame(body, fg_color="transparent")
        tog.pack(fill="x", padx=16, pady=(8, 4))
        ctk.CTkSwitch(tog, text="Mirror", variable=self.flip_var).pack(side="left", padx=4)
        ctk.CTkSwitch(tog, text="Skeleton", variable=self.lm_var).pack(side="left", padx=4)
        ctk.CTkSwitch(tog, text="Help", variable=self.help_var).pack(side="left", padx=4)

        # Buttons
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=(0, 18))
        ctk.CTkButton(btns, text="▶  Launch AirMouse", height=42,
                      font=ctk.CTkFont(size=15, weight="bold"),
                      command=self._launch).pack(fill="x", pady=4)
        ctk.CTkButton(btns, text="Calibrate then launch", height=34,
                      fg_color="#333", hover_color="#444",
                      command=lambda: self._launch(calibrate=True)).pack(fill="x", pady=4)

        self.status = ctk.CTkLabel(self, text="", text_color="#7a7a7a")
        self.status.pack()

    def _slider(self, parent, label, lo, hi, value):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(10, 0))
        head = ctk.CTkFrame(row, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text=label).pack(side="left")
        val_lbl = ctk.CTkLabel(head, text=f"{value:.3f}".rstrip("0").rstrip("."),
                               text_color="#5aa0ff")
        val_lbl.pack(side="right")
        s = ctk.CTkSlider(row, from_=lo, to=hi)
        s.set(value)
        s.pack(fill="x")
        s.configure(command=lambda v: val_lbl.configure(
            text=f"{float(v):.3f}".rstrip("0").rstrip(".")))
        return s

    def _save(self):
        c = self.cfg
        c.camera_index = self._cam_map.get(self.cam_var.get(), -1)
        c.sensitivity = round(self.sens.get(), 2)
        c.oe_beta = round(self.beta.get(), 3)
        c.cursor_margin = round(self.margin.get(), 3)
        c.scroll_speed = int(self.scroll.get())
        c.flip = self.flip_var.get()
        c.show_landmarks = self.lm_var.get()
        c.show_help = self.help_var.get()
        c.save()

    def _launch(self, calibrate=False):
        self._save()
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
    Launcher().mainloop()
