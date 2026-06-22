# Contributing to AirMouse

Thanks for your interest! AirMouse is a hand-gesture laptop controller built on
MediaPipe + OpenCV with a customtkinter control center.

## Getting set up

```bash
git clone https://github.com/at0m-b0mb/AirMouse-Hand-Gesture-Control.git
cd AirMouse-Hand-Gesture-Control
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
```

## Before opening a PR

```bash
ruff check .     # lint
pytest           # run the test suite
```

Both must pass — CI runs them on Python 3.10–3.12. The tests cover the
pure-logic modules (protocol, filter, stats, config, branding, gestures) and
need no webcam, so they run anywhere.

## Guidelines

- **Match the surrounding style** — small, focused functions; concise comments
  that explain *why*, not *what*.
- **Keep colours in `src/branding.py`** — it's the single source of truth for
  both the GUI (hex) and the HUD (BGR). Don't hard-code colours elsewhere.
- **Never deserialize network data with `pickle`.** The remote-control link uses
  fixed-size `struct` frames in `src/link_protocol.py` on purpose — keep it that way.
- **Add a test** when you change pure logic, and a line to `CHANGELOG.md`.
- Don't run the camera/GUI in automated checks — they loop forever; use the
  unit tests or `python AirMouse.py --doctor` instead.

## Reporting bugs

Run `python AirMouse.py --doctor` and paste the output into the issue — it
captures your Python version, dependencies, model and camera status.
