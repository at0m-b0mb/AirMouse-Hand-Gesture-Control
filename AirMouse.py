#!/usr/bin/env python3
"""
AirMouse — Control your laptop with hand gestures via webcam.

Gestures:
  Index finger only          → Move cursor
  Pinch thumb + index        → Left click  (pinch twice fast = double-click)
  Pinch thumb + middle       → Right click
  Pinch thumb + ring         → Middle click  (opt-in: --middle-click)
  Peace sign (index + mid)   → Scroll (move hand up/down, left/right)
  Fist                       → Drag (hold and move)
  Open palm, hold            → Toggle virtual keyboard
  Thumbs-up, hold            → Pause / resume control

Hotkeys: H help · P pause · Space freeze · C calibrate · S screenshot
         L landmarks · G fps · I stats · Y theme · T on-top · F flip
         +/- sensitivity · [ ] smoothing · Q/ESC quit

Run:  python AirMouse.py            (standalone)
      python launcher.py            (GUI control center)
      python AirMouse.py --help     (all options)
"""

import argparse
import logging
import sys


def _safe_import(name):
    try:
        return __import__(name)
    except ImportError:
        return None


def _check_deps():
    missing = [p for p in ("cv2", "mediapipe", "numpy") if _safe_import(p) is None]
    if missing:
        print("[AirMouse] Missing packages:", ", ".join(missing))
        print("           Run: pip install -r requirements.txt")
        sys.exit(1)


def _doctor() -> int:
    """Print a health report: deps, model, cameras, permissions. Returns exit code."""
    import platform
    from pathlib import Path

    try:
        from src import branding
        version = branding.VERSION
    except Exception:
        version = "?"

    ok = True
    print(f"AirMouse {version} — diagnostics\n")
    print(f"  Python    : {sys.version.split()[0]}  ({platform.python_implementation()})")
    print(f"  Platform  : {platform.system()} {platform.release()}\n")

    print("  Dependencies")
    checks = [
        ("opencv-python", "cv2", True),
        ("mediapipe", "mediapipe", True),
        ("numpy", "numpy", True),
        ("pynput", "pynput", True),
        ("pyautogui", "pyautogui", False),
        ("certifi", "certifi", False),
        ("customtkinter", "customtkinter", False),
        ("pillow", "PIL", False),
    ]
    for label, mod, required in checks:
        m = _safe_import(mod)
        ver = getattr(m, "__version__", "") if m else ""
        if m:
            print(f"    ✓ {label:<14} {ver}")
        else:
            tag = "MISSING (required)" if required else "missing (optional)"
            print(f"    {'✗' if required else '–'} {label:<14} {tag}")
            if required:
                ok = False

    print("\n  Hand-tracking model")
    model = Path(__file__).parent / "hand_landmarker.task"
    if model.exists():
        print(f"    ✓ present  ({model.stat().st_size // (1024*1024)} MB)")
    else:
        print("    – not downloaded yet (fetched automatically on first run)")

    print("\n  Cameras")
    try:
        from src.camera import list_cameras
        cams = list_cameras()
        if cams:
            for idx, w, h in cams:
                print(f"    ✓ index {idx}: {w}x{h}")
        else:
            print("    ✗ none detected — check the connection / camera permission")
            ok = False
    except Exception as exc:
        print(f"    ✗ probe failed: {exc}")
        ok = False

    if platform.system() == "Darwin":
        print("\n  macOS permissions (System Settings → Privacy & Security)")
        print("    • Camera        → enable for Terminal / your Python")
        print("    • Accessibility → enable for Terminal / your Python (mouse + keys)")

    print("\n" + ("All good — you're ready to fly. ✦" if ok
                  else "Some required checks failed — see ✗ above."))
    return 0 if ok else 1


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
    p.add_argument("--profile", type=str, default=None, metavar="NAME",
                   help="Apply a tuning profile (Balanced, Precision, Fast, "
                        "Presentation, Gaming, Accessibility)")
    p.add_argument("--theme", type=str, default=None, metavar="NAME",
                   help="Visual theme (Aurora, Cyber, Mono)")
    p.add_argument("--always-on-top", action="store_true",
                   help="Keep the AirMouse window above other windows")
    p.add_argument("--middle-click", action="store_true",
                   help="Enable the thumb+ring pinch middle-click gesture")
    p.add_argument("--no-landmarks", action="store_true",
                   help="Hide the hand skeleton overlay")
    p.add_argument("--help-overlay", action="store_true",
                   help="Start with the help overlay visible")
    p.add_argument("--sensitivity", type=float, default=None,
                   help="Override cursor sensitivity")
    p.add_argument("--reset-config", action="store_true",
                   help="Delete config.json and start fresh")
    p.add_argument("--doctor", action="store_true",
                   help="Run diagnostics (deps, model, cameras, permissions) and exit")
    p.add_argument("--version", action="store_true",
                   help="Print the AirMouse version and exit")
    return p.parse_args()


def main():
    args = _parse_args()

    if args.version:
        from src import branding
        print(f"AirMouse {branding.VERSION}")
        return
    if args.doctor:
        sys.exit(_doctor())

    _check_deps()

    from config import Config, PROFILES
    from src import branding
    from src.camera import list_cameras

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
        (Path(__file__).parent / "config.json").unlink(missing_ok=True)
        print("[AirMouse] config.json reset.")

    cfg = Config.load()

    # ── CLI overrides ──────────────────────────────────────────────────────────
    if args.profile:
        if not cfg.apply_profile(args.profile):
            print(f"[AirMouse] Unknown profile '{args.profile}'. "
                  f"Choices: {', '.join(PROFILES)}")
            sys.exit(1)
    if args.theme:
        if args.theme in branding.THEMES:
            cfg.theme = args.theme
        else:
            print(f"[AirMouse] Unknown theme '{args.theme}'. "
                  f"Choices: {', '.join(branding.THEMES)}")
            sys.exit(1)
    if args.camera is not None:
        cfg.camera_index = args.camera
    if args.no_flip:
        cfg.flip = False
    if args.flip:
        cfg.flip = True
    if args.always_on_top:
        cfg.always_on_top = True
    if args.middle_click:
        cfg.enable_middle_click = True
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

    from src.app import AirMouseApp
    AirMouseApp(cfg, calibrate_on_start=args.calibrate).run()


if __name__ == "__main__":
    main()
