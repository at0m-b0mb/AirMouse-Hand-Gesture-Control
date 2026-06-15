#!/usr/bin/env python3
"""
AirMouse — Standalone gesture-controlled laptop interface.

Gestures:
  Index finger only          → Move cursor (full screen)
  Pinch (thumb + index)      → Left click
  Pinch (thumb + middle)     → Right click
  Peace sign (index + mid)   → Scroll (move hand up/down)
  Fist                       → Drag (hold and move)
  Open palm, hold 1 s        → Toggle virtual keyboard
  Q / ESC                    → Quit

Configuration is stored in config.json (auto-created on first run).
Run: python AirMouse.py
"""

import sys
import time


def _check_deps():
    missing = []
    for pkg in ("cv2", "mediapipe", "numpy"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print("[AirMouse] Missing packages:", ", ".join(missing))
        print("           Run: pip install -r requirements.txt")
        sys.exit(1)


_check_deps()

import cv2
import numpy as np

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
    _get_screen_size = pyautogui.size
except Exception:
    def _get_screen_size():
        return (1920, 1080)

from config import Config
from src.camera import detect_camera, open_camera
from src.hand_tracker import HandTracker
from src.gesture import GestureEngine, Gesture
from src.mouse import MouseController
from src.virtual_keyboard import VirtualKeyboard


def _draw_hud(frame: np.ndarray, fps: int, engine: GestureEngine) -> None:
    h, w = frame.shape[:2]
    in_kb = engine.in_keyboard_mode

    cv2.rectangle(frame, (0, 0), (w, 34), (12, 12, 12), -1)
    label = "KEYBOARD MODE" if in_kb else "MOUSE MODE"
    color = (70, 220, 70) if in_kb else (70, 150, 255)
    cv2.putText(frame, label, (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA)
    cv2.putText(frame, f"FPS {fps}", (w - 88, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (150, 150, 150), 1, cv2.LINE_AA)

    p = engine.palm_progress
    if 0 < p < 1.0:
        cv2.rectangle(frame, (0, 34), (int(w * p), 40), (60, 220, 170), -1)
        cv2.putText(frame, "Hold to toggle keyboard...", (10, 56),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (60, 220, 170), 1, cv2.LINE_AA)

    if in_kb:
        hint = "Pinch = press key  |  Open palm 1 s = exit keyboard  |  Q = quit"
    else:
        hint = "Index=move  Pinch=click  R-pinch=right  Peace=scroll  Fist=drag  Palm=keyboard"
    cv2.putText(frame, hint, (6, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (120, 120, 120), 1, cv2.LINE_AA)


def main() -> None:
    print("╔══════════════════════════════════════════════╗")
    print("║    AirMouse — Gesture Laptop Controller      ║")
    print("╚══════════════════════════════════════════════╝\n")

    cfg = Config.load()

    sw, sh = _get_screen_size()
    print(f"[Screen]  {sw}x{sh} px")

    cam_idx = detect_camera(cfg.camera_index)
    if cfg.camera_index < 0:
        cfg.camera_index = cam_idx
        cfg.save()

    cap, cam_w, cam_h = open_camera(cam_idx)

    tracker = HandTracker(max_hands=cfg.max_hands,
                          det_conf=cfg.detection_confidence,
                          track_conf=cfg.tracking_confidence)
    engine  = GestureEngine(keyboard_toggle_hold=cfg.keyboard_toggle_hold,
                            click_threshold=cfg.click_threshold,
                            click_cooldown=cfg.click_cooldown)
    mouse   = MouseController(screen_w=sw, screen_h=sh,
                              smoothing=cfg.smoothing, sensitivity=cfg.sensitivity,
                              dead_zone=cfg.dead_zone, cursor_margin=cfg.cursor_margin)
    kbd     = VirtualKeyboard(frame_w=cam_w, frame_h=cam_h)

    print("\n[Gestures]")
    print("  Index finger only          → Move cursor")
    print("  Pinch  (thumb + index)     → Left click")
    print("  Pinch  (thumb + middle)    → Right click")
    print("  Peace sign (index + mid)   → Scroll up/down")
    print("  Fist                       → Drag")
    print("  Open palm, hold 1 s        → Toggle virtual keyboard")
    print("  Q / ESC                    → Quit\n")

    cv2.namedWindow("AirMouse", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("AirMouse", cam_w, cam_h)

    fps = fps_count = 0
    fps_t = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[Error] Camera frame lost.")
            break

        if cfg.flip:
            frame = cv2.flip(frame, 1)

        results, lm_lists = tracker.process(frame)
        if cfg.show_landmarks:
            tracker.draw(frame, results)

        in_kb = engine.in_keyboard_mode

        if lm_lists:
            lm = lm_lists[0]
            gesture = engine.recognize(lm)
            nx, ny = engine.cursor_pos(lm)

            if in_kb:
                kbd.update_hover(nx, ny)
                if gesture == Gesture.LEFT_CLICK:
                    action = kbd.try_press(nx, ny)
                    if action:
                        char = kbd.resolve_char(action)
                        mouse.type_char(char)
                        if kbd.shift and action not in {"BKSP", "ENTER", "SPACE", "TAB"}:
                            kbd.shift = False
                frame = kbd.draw(frame)
            else:
                if gesture == Gesture.MOVE:
                    mouse.stop_drag()
                    mouse.move(nx, ny)
                elif gesture == Gesture.LEFT_CLICK:
                    mouse.stop_drag()
                    mouse.left_click()
                elif gesture == Gesture.RIGHT_CLICK:
                    mouse.stop_drag()
                    mouse.right_click()
                elif gesture == Gesture.SCROLL:
                    mouse.stop_drag()
                    mouse.scroll(engine.scroll_y(lm), cfg.scroll_speed)
                elif gesture == Gesture.DRAG:
                    mouse.move(nx, ny)
                    mouse.start_drag()
                else:
                    mouse.stop_drag()
                    mouse.reset_scroll()
        else:
            mouse.stop_drag()
            mouse.reset_scroll()

        fps_count += 1
        if time.time() - fps_t >= 1.0:
            fps = fps_count
            fps_count = 0
            fps_t = time.time()

        _draw_hud(frame, fps, engine)
        cv2.imshow("AirMouse", frame)
        if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
            break

    mouse.stop_drag()
    tracker.close()
    cap.release()
    cv2.destroyAllWindows()
    print("\n[AirMouse] Session ended.")


if __name__ == "__main__":
    main()
