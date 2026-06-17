"""AirMouseApp — the camera loop, gesture dispatch, HUD and hotkeys.

AirMouse.py is now a thin CLI that builds a Config and runs this class. Keeping
the loop here makes the app importable and the entry point tiny.
"""
from __future__ import annotations

import logging
import time

from src import actions, branding, hud
from src.camera import detect_camera, open_camera
from src.gesture import Gesture, GestureEngine
from src.hand_tracker import HandTracker
from src.mouse import MouseController
from src.stats import SessionStats
from src.virtual_keyboard import VirtualKeyboard

_TAP_KEYS = {"BKSP": "backspace", "ENTER": "enter", "SPACE": "space", "TAB": "tab",
             "ESC": "esc", "UP": "up", "DOWN": "down", "LEFT": "left", "RIGHT": "right"}
_MEDIA = {"VOL_UP", "VOL_DOWN", "MUTE", "PLAY"}

WIN = "AirMouse"


class Calibrator:
    """Capture the comfortable hand-movement box over a few seconds."""
    DURATION = 5.0

    def __init__(self):
        self.active = False
        self._t0 = 0.0
        self.x0 = self.y0 = 1.0
        self.x1 = self.y1 = 0.0

    def start(self):
        self.active = True
        self._t0 = time.time()
        self.x0 = self.y0 = 1.0
        self.x1 = self.y1 = 0.0

    def feed(self, nx, ny):
        self.x0 = min(self.x0, nx); self.y0 = min(self.y0, ny)
        self.x1 = max(self.x1, nx); self.y1 = max(self.y1, ny)

    @property
    def remaining(self) -> float:
        return max(0.0, self.DURATION - (time.time() - self._t0))

    def result(self):
        if self.x1 - self.x0 > 0.15 and self.y1 - self.y0 > 0.15:
            return (self.x0, self.y0, self.x1, self.y1)
        return None


class AirMouseApp:
    def __init__(self, cfg, calibrate_on_start: bool = False):
        self.cfg = cfg
        self.calibrate_on_start = calibrate_on_start
        self.log = logging.getLogger("airmouse")
        self.frozen = False
        self.show_help = cfg.show_help
        self.stats = SessionStats()
        self.toast = hud.Toast()
        self.ripples = hud.Ripples()
        self.calib = Calibrator()
        branding.use(cfg.theme)

    # ── setup ───────────────────────────────────────────────────────────────────
    def run(self):
        import cv2

        try:
            import pyautogui
            pyautogui.FAILSAFE = False
            sw, sh = pyautogui.size()
        except Exception:
            sw, sh = 1920, 1080

        self._banner()
        self.log.info("Screen %dx%d  ·  theme %s", sw, sh, branding.active_name())

        cam_idx = detect_camera(self.cfg.camera_index)
        if self.cfg.camera_index < 0:
            self.cfg.camera_index = cam_idx
            self.cfg.save()
        cap, cam_w, cam_h = open_camera(cam_idx, self.cfg.cam_width, self.cfg.cam_height)
        self.cam_w, self.cam_h = cam_w, cam_h

        self.tracker = HandTracker(self.cfg.max_hands, self.cfg.detection_confidence,
                                   self.cfg.tracking_confidence)
        self.engine = GestureEngine(self.cfg.keyboard_toggle_hold, self.cfg.pause_toggle_hold,
                                    self.cfg.click_threshold, self.cfg.click_release,
                                    self.cfg.double_click_window, self.cfg.click_cooldown,
                                    self.cfg.enable_middle_click)
        calib = ((self.cfg.calib_x0, self.cfg.calib_y0, self.cfg.calib_x1, self.cfg.calib_y1)
                 if self.cfg.is_calibrated else None)
        self.mouse = MouseController(sw, sh, self.cfg.use_one_euro, self.cfg.oe_min_cutoff,
                                     self.cfg.oe_beta, self.cfg.smoothing, self.cfg.sensitivity,
                                     self.cfg.dead_zone, self.cfg.cursor_margin, calib,
                                     self.cfg.scroll_inertia, self.cfg.scroll_friction)
        self.kbd = VirtualKeyboard(cam_w, cam_h, self.cfg.key_press_cooldown)
        if self.calibrate_on_start:
            self.calib.start()

        cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WIN, cam_w, cam_h)
        self._set_topmost(cv2, self.cfg.always_on_top)

        self._loop(cv2, cap)

        self.mouse.stop_drag()
        self.cfg.save()
        self.tracker.close()
        cap.release()
        cv2.destroyAllWindows()
        print("\n[AirMouse] Session ended. Settings saved to config.json")

    # ── main loop ───────────────────────────────────────────────────────────────
    def _loop(self, cv2, cap):
        fps = fps_count = 0
        fps_t = time.time()
        had_hand = False
        last_hand_t = time.time()

        while True:
            ok, frame = cap.read()
            if not ok:
                self.log.error("Camera frame lost — exiting.")
                break
            if self.cfg.flip:
                frame = cv2.flip(frame, 1)

            results, lm_lists = self.tracker.process(frame)
            if self.cfg.show_landmarks:
                self.tracker.draw(frame, results)

            g = None
            if lm_lists:
                last_hand_t = time.time()
                lm = lm_lists[0]
                nx, ny = self.engine.cursor_pos(lm)
                if not had_hand:
                    self.mouse.warp_filter()
                    had_hand = True
                if self.calib.active:
                    self.calib.feed(nx, ny)
                elif not self.frozen:
                    g = self._handle_frame(lm, nx, ny)
            else:
                had_hand = False
                self.mouse.stop_drag()
                self.mouse.reset_scroll()
                self._maybe_idle_pause(last_hand_t)

            # scroll inertia glide (when not actively scrolling)
            if g != Gesture.SCROLL and not self.frozen:
                if self.mouse.apply_inertia():
                    self.stats.scroll()

            self._draw(cv2, frame, fps, lm_lists, nx if lm_lists else 0.0,
                       ny if lm_lists else 0.0)

            fps_count += 1
            if time.time() - fps_t >= 1.0:
                fps, fps_count, fps_t = fps_count, 0, time.time()

            cv2.imshow(WIN, frame)
            if self._hotkeys(cv2):
                break

    # ── per-frame drawing ───────────────────────────────────────────────────────
    def _draw(self, cv2, frame, fps, lm_lists, nx, ny):
        if self.engine.in_keyboard_mode and not self.calib.active:
            self.kbd.draw(frame)          # draws onto frame in place
        self.ripples.draw(frame)

        hud.draw_status_bar(frame, fps, self.engine, self.mouse.sens,
                            self.cfg.is_calibrated, self.cfg.show_fps, self.frozen)
        if self.cfg.show_stats:
            hud.draw_stats(frame, self.stats.hud_line())
        if lm_lists and not self.engine.in_keyboard_mode and not self.calib.active:
            hud.draw_gesture_label(frame, self.engine.label, nx, ny)
        hud.draw_hints(frame, self.engine)
        hud.draw_watermark(frame)
        self.toast.draw(frame)

        if self.calib.active:
            box = (self.calib.x0, self.calib.y0, self.calib.x1, self.calib.y1)
            hud.draw_calibration(
                frame, f"Move your hand to all 4 corners…  {self.calib.remaining:0.1f}s",
                box if self.calib.x1 > self.calib.x0 else None)
            if self.calib.remaining <= 0:
                self._finish_calibration()

        if self.show_help:
            hud.draw_help(frame)

    # ── gesture dispatch ────────────────────────────────────────────────────────
    def _handle_frame(self, lm, nx, ny):
        g = self.engine.recognize(lm)
        cw, ch = self.cam_w, self.cam_h

        if self.engine.in_keyboard_mode:
            self.kbd.update_hover(nx, ny)
            if g in (Gesture.LEFT_CLICK, Gesture.DOUBLE_CLICK):
                action = self.kbd.try_press(nx, ny)
                if action:
                    self._dispatch_key(action)
                    if self.kbd.shift and action not in ("SHIFT", "CAPS") and len(action) == 1:
                        self.kbd.shift = False
                self.ripples.add(int(nx * cw), int(ny * ch), branding.bgr("success"))
            return g

        if g == Gesture.MOVE:
            self.mouse.stop_drag(); self.mouse.move(nx, ny)
            self.stats.moved_to(*self.mouse.last_xy)
        elif g == Gesture.LEFT_CLICK:
            self.mouse.stop_drag(); self.mouse.left_click(); self.stats.left_click()
            self.ripples.add(int(nx * cw), int(ny * ch), branding.bgr("success"))
        elif g == Gesture.DOUBLE_CLICK:
            self.mouse.stop_drag(); self.mouse.double_click(); self.stats.double_click()
            self.ripples.add(int(nx * cw), int(ny * ch), branding.bgr("accent"))
        elif g == Gesture.RIGHT_CLICK:
            self.mouse.stop_drag(); self.mouse.right_click(); self.stats.right_click()
            self.ripples.add(int(nx * cw), int(ny * ch), branding.bgr("secondary"))
        elif g == Gesture.MIDDLE_CLICK:
            self.mouse.stop_drag(); self.mouse.middle_click(); self.stats.middle_click()
            self.ripples.add(int(nx * cw), int(ny * ch), branding.bgr("warning"))
        elif g == Gesture.SCROLL:
            self.mouse.stop_drag()
            ax, ay = self.engine.scroll_anchor(lm)
            if self.mouse.scroll(ax, ay, self.cfg.scroll_speed, self.cfg.horizontal_scroll):
                self.stats.scroll()
        elif g == Gesture.DRAG:
            was = self.mouse.dragging
            self.mouse.move(nx, ny); self.mouse.start_drag()
            if not was and self.mouse.dragging:
                self.stats.drag()
        else:
            self.mouse.stop_drag(); self.mouse.reset_scroll()
        return g

    def _dispatch_key(self, action):
        if action in _MEDIA:
            actions.media(action)
        elif action == "SCRNSHOT":
            path = actions.screenshot(self.cfg.screenshot_dir)
            self.stats.screenshot()
            self.toast.show("Screenshot saved" if path else "Screenshot failed")
        elif action in _TAP_KEYS:
            self.mouse.tap_key(_TAP_KEYS[action]); self.kbd.note_preview(action); self.stats.key()
        elif len(action) == 1:
            self.mouse.type_char(self.kbd.resolve_char(action))
            self.kbd.note_preview(action); self.stats.key()

    # ── comfort / helpers ───────────────────────────────────────────────────────
    def _maybe_idle_pause(self, last_hand_t):
        if (self.cfg.idle_pause_secs > 0 and not self.engine.paused
                and time.time() - last_hand_t > self.cfg.idle_pause_secs):
            self.engine.toggle_pause()
            self.toast.show("Idle — paused (thumbs-up or P to resume)")

    def _finish_calibration(self):
        res = self.calib.result()
        self.calib.active = False
        if res:
            (self.cfg.calib_x0, self.cfg.calib_y0,
             self.cfg.calib_x1, self.cfg.calib_y1) = res
            self.cfg.save()
            self.mouse.calib = res
            self.toast.show("Calibration saved ✓")
            self.log.info("Calibration: %s", res)
        else:
            self.toast.show("Calibration too small — kept previous")

    def _set_topmost(self, cv2, on):
        try:
            cv2.setWindowProperty(WIN, cv2.WND_PROP_TOPMOST, 1 if on else 0)
        except Exception:
            if on:
                self.log.warning("Always-on-top not supported by this OpenCV build.")

    def _cycle_theme(self):
        names = list(branding.THEMES)
        nxt = names[(names.index(branding.active_name()) + 1) % len(names)]
        branding.use(nxt)
        self.cfg.theme = nxt
        self.toast.show(f"Theme: {nxt}")

    # ── hotkeys ─────────────────────────────────────────────────────────────────
    def _hotkeys(self, cv2) -> bool:
        key = cv2.waitKey(1) & 0xFF
        if key == 255:
            return False
        cfg, mouse, engine, toast = self.cfg, self.mouse, self.engine, self.toast
        if key in (ord("q"), ord("Q"), 27):
            return True
        elif key in (ord("h"), ord("H")):
            self.show_help = not self.show_help
        elif key in (ord("p"), ord("P")):
            engine.toggle_pause(); toast.show("Paused" if engine.paused else "Resumed")
        elif key == 32:  # Space
            self.frozen = not self.frozen
            toast.show("Cursor frozen" if self.frozen else "Cursor active")
        elif key in (ord("c"), ord("C")):
            self.calib.start(); toast.show("Calibrating…")
        elif key in (ord("s"), ord("S")):
            path = actions.screenshot(cfg.screenshot_dir); self.stats.screenshot()
            toast.show("Screenshot saved" if path else "Screenshot failed")
        elif key in (ord("l"), ord("L")):
            cfg.show_landmarks = not cfg.show_landmarks
            toast.show(f"Landmarks {'on' if cfg.show_landmarks else 'off'}")
        elif key in (ord("g"), ord("G")):
            cfg.show_fps = not cfg.show_fps
            toast.show(f"FPS {'on' if cfg.show_fps else 'off'}")
        elif key in (ord("i"), ord("I")):
            cfg.show_stats = not cfg.show_stats
            toast.show(f"Stats {'on' if cfg.show_stats else 'off'}")
        elif key in (ord("y"), ord("Y")):
            self._cycle_theme()
        elif key in (ord("t"), ord("T")):
            cfg.always_on_top = not cfg.always_on_top
            self._set_topmost(cv2, cfg.always_on_top)
            toast.show(f"Always-on-top {'on' if cfg.always_on_top else 'off'}")
        elif key in (ord("f"), ord("F")):
            cfg.flip = not cfg.flip
            toast.show(f"Flip {'on' if cfg.flip else 'off'}")
        elif key in (ord("+"), ord("=")):
            mouse.sens = round(min(3.0, mouse.sens + 0.1), 2); cfg.sensitivity = mouse.sens
            toast.show(f"Sensitivity {mouse.sens:.1f}")
        elif key in (ord("-"), ord("_")):
            mouse.sens = round(max(0.3, mouse.sens - 0.1), 2); cfg.sensitivity = mouse.sens
            toast.show(f"Sensitivity {mouse.sens:.1f}")
        elif key == ord("["):
            cfg.oe_beta = round(max(0.001, cfg.oe_beta - 0.004), 3)
            mouse._fx.beta = mouse._fy.beta = cfg.oe_beta
            toast.show(f"Smoothing softer (beta {cfg.oe_beta:.3f})")
        elif key == ord("]"):
            cfg.oe_beta = round(min(0.1, cfg.oe_beta + 0.004), 3)
            mouse._fx.beta = mouse._fy.beta = cfg.oe_beta
            toast.show(f"Smoothing snappier (beta {cfg.oe_beta:.3f})")
        return False

    # ── console banner ──────────────────────────────────────────────────────────
    def _banner(self):
        print("╔══════════════════════════════════════════════╗")
        print(f"║   {branding.APP_NAME} {branding.VERSION} — {branding.APP_TAGLINE}".ljust(47) + "║")
        print("╚══════════════════════════════════════════════╝")
        print("\n[Gestures]")
        print("  Index finger only          → Move cursor")
        print("  Pinch  (thumb + index)     → Left click  (twice = double-click)")
        print("  Pinch  (thumb + middle)    → Right click")
        print("  Pinch  (thumb + ring)      → Middle click  (if enabled)")
        print("  Peace sign (index + mid)   → Scroll up/down/left/right")
        print("  Fist                       → Drag")
        print("  Open palm, hold            → Toggle virtual keyboard")
        print("  Thumbs-up, hold            → Pause / resume")
        print("\n[Hotkeys] H help · P pause · Space freeze · C calibrate · S shot · "
              "L landmarks · G fps · I stats · Y theme · T on-top · F flip · "
              "+/- sens · [ ] smooth · Q quit\n")
