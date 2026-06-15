#!/usr/bin/env python3
"""
AirMouse — Control your laptop with hand gestures via webcam.

Gestures:
  Index finger only          → Move cursor
  Pinch thumb + index        → Left click  (pinch twice fast = double-click)
  Pinch thumb + middle       → Right click
  Peace sign (index + mid)   → Scroll (move hand up/down, left/right)
  Fist                       → Drag (hold and move)
  Open palm, hold            → Toggle virtual keyboard
  Thumbs-up, hold            → Pause / resume control

Hotkeys: H help · P pause · C calibrate · S screenshot · L landmarks
         F flip · +/- sensitivity · [ ] smoothing · Q/ESC quit

Run:  python AirMouse.py            (standalone)
      python AirMouse.py --help     (all options)
"""

import argparse
import logging
import sys
import time


def _check_deps():
    missing = [p for p in ("cv2", "mediapipe", "numpy")
               if _safe_import(p) is None]
    if missing:
        print("[AirMouse] Missing packages:", ", ".join(missing))
        print("           Run: pip install -r requirements.txt")
        sys.exit(1)


def _safe_import(name):
    try:
        return __import__(name)
    except ImportError:
        return None


def _parse_args():
    p = argparse.ArgumentParser(
        prog="AirMouse",
        description="Control your laptop with hand gestures via webcam.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--camera", type=int, default=None, metavar="N",
                   help="Force camera index (overrides auto-detect)")
    p.add_argument("--list-cameras", action="store_true",
                   help="List available cameras and exit")
    p.add_argument("--calibrate", action="store_true",
                   help="Run hand-range calibration on startup")
    p.add_argument("--no-flip", action="store_true", help="Disable mirror flip")
    p.add_argument("--flip", action="store_true", help="Force mirror flip on")
    p.add_argument("--no-landmarks", action="store_true",
                   help="Hide the hand skeleton overlay")
    p.add_argument("--help-overlay", action="store_true",
                   help="Start with the help overlay visible")
    p.add_argument("--sensitivity", type=float, default=None,
                   help="Override cursor sensitivity")
    p.add_argument("--reset-config", action="store_true",
                   help="Delete config.json and start fresh")
    return p.parse_args()


# ── calibration state machine ──────────────────────────────────────────────────

class _Calibrator:
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
        # require a sane span, else fall back
        if self.x1 - self.x0 > 0.15 and self.y1 - self.y0 > 0.15:
            return (self.x0, self.y0, self.x1, self.y1)
        return None


def main():
    args = _parse_args()
    _check_deps()

    import cv2
    from config import Config
    from src.camera import detect_camera, open_camera, list_cameras

    if args.list_cameras:
        cams = list_cameras()
        if not cams:
            print("No cameras found.")
        else:
            print("Available cameras:")
            for idx, w, h in cams:
                print(f"  index {idx}: {w}x{h}")
        return

    if args.reset_config:
        from pathlib import Path
        cfg_path = Path(__file__).parent / "config.json"
        cfg_path.unlink(missing_ok=True)
        print("[AirMouse] config.json reset.")

    cfg = Config.load()

    # CLI overrides
    if args.camera is not None:
        cfg.camera_index = args.camera
    if args.no_flip:
        cfg.flip = False
    if args.flip:
        cfg.flip = True
    if args.no_landmarks:
        cfg.show_landmarks = False
    if args.help_overlay:
        cfg.show_help = True
    if args.sensitivity is not None:
        cfg.sensitivity = args.sensitivity

    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S",
    )
    log = logging.getLogger("airmouse")

    _run(cfg, args, cv2, log)


def _run(cfg, args, cv2, log):
    import numpy as np
    from src.camera import detect_camera, open_camera
    from src.hand_tracker import HandTracker
    from src.gesture import GestureEngine, Gesture
    from src.mouse import MouseController
    from src.virtual_keyboard import VirtualKeyboard
    from src import actions, hud

    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        sw, sh = pyautogui.size()
    except Exception:
        sw, sh = 1920, 1080

    print("╔══════════════════════════════════════════════╗")
    print("║    AirMouse — Gesture Laptop Controller      ║")
    print("╚══════════════════════════════════════════════╝")
    log.info("Screen %dx%d", sw, sh)

    cam_idx = detect_camera(cfg.camera_index)
    if cfg.camera_index < 0:
        cfg.camera_index = cam_idx
        cfg.save()
    cap, cam_w, cam_h = open_camera(cam_idx, cfg.cam_width, cfg.cam_height)

    tracker = HandTracker(cfg.max_hands, cfg.detection_confidence, cfg.tracking_confidence)
    engine = GestureEngine(cfg.keyboard_toggle_hold, cfg.pause_toggle_hold,
                           cfg.click_threshold, cfg.click_release,
                           cfg.double_click_window, cfg.click_cooldown)
    calib = (cfg.calib_x0, cfg.calib_y0, cfg.calib_x1, cfg.calib_y1) if cfg.is_calibrated else None
    mouse = MouseController(sw, sh, cfg.use_one_euro, cfg.oe_min_cutoff, cfg.oe_beta,
                            cfg.smoothing, cfg.sensitivity, cfg.dead_zone,
                            cfg.cursor_margin, calib)
    kbd = VirtualKeyboard(cam_w, cam_h, cfg.key_press_cooldown)
    toast = hud.Toast()
    ripples = hud.Ripples()
    calibrator = _Calibrator()

    show_help = cfg.show_help
    if args.calibrate:
        calibrator.start()

    _print_gestures()
    win = "AirMouse"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, cam_w, cam_h)

    fps = fps_count = 0
    fps_t = time.time()
    had_hand = False

    while True:
        ok, frame = cap.read()
        if not ok:
            log.error("Camera frame lost — exiting.")
            break
        if cfg.flip:
            frame = cv2.flip(frame, 1)

        results, lm_lists = tracker.process(frame)
        if cfg.show_landmarks:
            tracker.draw(frame, results)

        if lm_lists:
            lm = lm_lists[0]
            nx, ny = engine.cursor_pos(lm)

            if not had_hand:
                mouse.warp_filter()      # avoid a jump when the hand re-appears
                had_hand = True

            if calibrator.active:
                calibrator.feed(nx, ny)
            else:
                _handle_frame(engine, mouse, kbd, actions, hud, toast, ripples,
                              cfg, lm, nx, ny, cam_w, cam_h)
        else:
            had_hand = False
            mouse.stop_drag()
            mouse.reset_scroll()

        # ── overlays ──────────────────────────────────────────────────────────
        if engine.in_keyboard_mode and not calibrator.active:
            frame = kbd.draw(frame)
        ripples.draw(frame)

        fps_count += 1
        if time.time() - fps_t >= 1.0:
            fps, fps_count, fps_t = fps_count, 0, time.time()

        hud.draw_status_bar(frame, fps, engine, mouse.sens, cfg.is_calibrated)
        if lm_lists and not engine.in_keyboard_mode and not calibrator.active:
            hud.draw_gesture_label(frame, engine.label, nx, ny)
        hud.draw_hints(frame, engine)
        toast.draw(frame)

        if calibrator.active:
            box = (calibrator.x0, calibrator.y0, calibrator.x1, calibrator.y1)
            hud.draw_calibration(
                frame,
                f"Move your hand to all 4 corners…  {calibrator.remaining:0.1f}s",
                box if calibrator.x1 > calibrator.x0 else None)
            if calibrator.remaining <= 0:
                res = calibrator.result()
                calibrator.active = False
                if res:
                    cfg.calib_x0, cfg.calib_y0, cfg.calib_x1, cfg.calib_y1 = res
                    cfg.save()
                    mouse.calib = res
                    toast.show("Calibration saved ✓")
                    log.info("Calibration: %s", res)
                else:
                    toast.show("Calibration too small — kept previous")

        if show_help:
            hud.draw_help(frame)

        cv2.imshow(win, frame)

        # ── hotkeys ──────────────────────────────────────────────────────────
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), ord("Q"), 27):
            break
        elif key in (ord("h"), ord("H")):
            show_help = not show_help
        elif key in (ord("p"), ord("P")):
            engine.toggle_pause()
            toast.show("Paused" if engine.paused else "Resumed")
        elif key in (ord("c"), ord("C")):
            calibrator.start()
            toast.show("Calibrating…")
        elif key in (ord("s"), ord("S")):
            path = actions.screenshot(cfg.screenshot_dir)
            toast.show("Screenshot saved" if path else "Screenshot failed")
        elif key in (ord("l"), ord("L")):
            cfg.show_landmarks = not cfg.show_landmarks
            toast.show(f"Landmarks {'on' if cfg.show_landmarks else 'off'}")
        elif key in (ord("f"), ord("F")):
            cfg.flip = not cfg.flip
            toast.show(f"Flip {'on' if cfg.flip else 'off'}")
        elif key in (ord("+"), ord("=")):
            mouse.sens = round(min(3.0, mouse.sens + 0.1), 2)
            cfg.sensitivity = mouse.sens
            toast.show(f"Sensitivity {mouse.sens:.1f}")
        elif key in (ord("-"), ord("_")):
            mouse.sens = round(max(0.3, mouse.sens - 0.1), 2)
            cfg.sensitivity = mouse.sens
            toast.show(f"Sensitivity {mouse.sens:.1f}")
        elif key == ord("["):
            cfg.oe_beta = round(max(0.001, cfg.oe_beta - 0.004), 3)
            mouse._fx.beta = mouse._fy.beta = cfg.oe_beta
            toast.show(f"Smoothing softer (beta {cfg.oe_beta:.3f})")
        elif key == ord("]"):
            cfg.oe_beta = round(min(0.1, cfg.oe_beta + 0.004), 3)
            mouse._fx.beta = mouse._fy.beta = cfg.oe_beta
            toast.show(f"Smoothing snappier (beta {cfg.oe_beta:.3f})")

    mouse.stop_drag()
    cfg.save()
    tracker.close()
    cap.release()
    cv2.destroyAllWindows()
    print("\n[AirMouse] Session ended. Settings saved to config.json")


# ── per-frame action handling ──────────────────────────────────────────────────

_TAP_KEYS = {"BKSP": "backspace", "ENTER": "enter", "SPACE": "space", "TAB": "tab",
             "ESC": "esc", "UP": "up", "DOWN": "down", "LEFT": "left", "RIGHT": "right"}
_MEDIA = {"VOL_UP", "VOL_DOWN", "MUTE", "PLAY"}


def _dispatch_key(action, mouse, kbd, actions, toast, cfg):
    """Send a virtual-keyboard action to the real OS."""
    if action in _MEDIA:
        actions.media(action)
    elif action == "SCRNSHOT":
        path = actions.screenshot(cfg.screenshot_dir)
        toast.show("Screenshot saved" if path else "Screenshot failed")
    elif action in _TAP_KEYS:
        mouse.tap_key(_TAP_KEYS[action])
        kbd.note_preview(action)
    elif len(action) == 1:
        mouse.type_char(kbd.resolve_char(action))
        kbd.note_preview(action)


def _handle_frame(engine, mouse, kbd, actions, hud, toast, ripples,
                  cfg, lm, nx, ny, cam_w, cam_h):
    g = engine.recognize(lm)
    from src.gesture import Gesture

    if engine.in_keyboard_mode:
        kbd.update_hover(nx, ny)
        if g in (Gesture.LEFT_CLICK, Gesture.DOUBLE_CLICK):
            action = kbd.try_press(nx, ny)
            if action:
                _dispatch_key(action, mouse, kbd, actions, toast, cfg)
                if kbd.shift and action not in ("SHIFT", "CAPS") and len(action) == 1:
                    kbd.shift = False
            ripples.add(int(nx * cam_w), int(ny * cam_h), (60, 220, 120))
        return

    if g == Gesture.MOVE:
        mouse.stop_drag(); mouse.move(nx, ny)
    elif g == Gesture.LEFT_CLICK:
        mouse.stop_drag(); mouse.left_click()
        ripples.add(int(nx * cam_w), int(ny * cam_h), (60, 220, 120))
    elif g == Gesture.DOUBLE_CLICK:
        mouse.stop_drag(); mouse.double_click()
        ripples.add(int(nx * cam_w), int(ny * cam_h), (60, 220, 255))
    elif g == Gesture.RIGHT_CLICK:
        mouse.stop_drag(); mouse.right_click()
        ripples.add(int(nx * cam_w), int(ny * cam_h), (220, 120, 60))
    elif g == Gesture.SCROLL:
        mouse.stop_drag()
        ax, ay = engine.scroll_anchor(lm)
        mouse.scroll(ax, ay, cfg.scroll_speed, cfg.horizontal_scroll)
    elif g == Gesture.DRAG:
        mouse.move(nx, ny); mouse.start_drag()
    else:
        mouse.stop_drag(); mouse.reset_scroll()


def _print_gestures():
    print("\n[Gestures]")
    print("  Index finger only          → Move cursor")
    print("  Pinch  (thumb + index)     → Left click  (twice = double-click)")
    print("  Pinch  (thumb + middle)    → Right click")
    print("  Peace sign (index + mid)   → Scroll up/down/left/right")
    print("  Fist                       → Drag")
    print("  Open palm, hold            → Toggle virtual keyboard")
    print("  Thumbs-up, hold            → Pause / resume")
    print("\n[Hotkeys] H help · P pause · C calibrate · S shot · L landmarks · "
          "F flip · +/- sens · [ ] smooth · Q quit\n")


if __name__ == "__main__":
    main()
