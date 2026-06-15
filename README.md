# AirMouse — Hand Gesture Control

Control your laptop **entirely with your hand** — no keyboard, no mouse, no touchpad. AirMouse uses your webcam and real-time hand tracking (MediaPipe) to turn gestures into precise cursor movement, clicks, scrolling, dragging, and typing through an on-screen virtual keyboard.

[![Demo](demo/AirMouse_Demo.png)](demo/AirMouse_Demo.mp4)

---

## Features

| Feature | Description |
|---|---|
| **Cursor control** | Index fingertip → tracks across the full screen |
| **Left click** | Pinch thumb + index finger |
| **Right click** | Pinch thumb + middle finger |
| **Scroll** | Peace sign (index + middle up), move hand up/down |
| **Drag** | Fist to start, open hand to release |
| **Virtual keyboard** | Hold open palm 1 s to toggle; pinch keys to type |
| **Auto camera** | Scans all ports on first run, saves to config.json |
| **Full screen mapping** | Detects screen resolution — central 76% of frame → 100% of screen |
| **Smooth cursor** | Exponential moving average filter to eliminate jitter |
| **Client/Server mode** | Stream gestures from one machine, control another on same network |

---

## Gesture Reference

```
Hand pose                   Action
──────────────────────────  ────────────────────────────────
Index finger pointing       Move cursor
Pinch thumb + index         Left click
Pinch thumb + middle        Right click
Index + middle up (peace)   Scroll — move hand up/down
Fist (all fingers curled)   Drag — fist to grab, open to drop
Open palm, hold 1 second    Toggle virtual keyboard
Q or ESC                    Quit
```

**In keyboard mode:**
- Hand cursor hovers over the on-screen QWERTY layout (lower half of camera window)
- Pinch to press the highlighted key
- `⇧ SHIFT` auto-resets after one character
- Hold open palm for 1 s again to return to mouse mode

---

## Installation

```bash
git clone https://github.com/at0m-b0mb/AirMouse-Hand-Gesture-Control.git
cd AirMouse-Hand-Gesture-Control
pip install -r requirements.txt
```

> **Note:** `autopy` has been replaced with `pynput` — it is no longer required and has been removed from requirements.

### macOS permissions (required)

Grant both in **System Settings → Privacy & Security**:
- **Camera** → Terminal (or your Python interpreter)
- **Accessibility** → Terminal (needed for mouse/keyboard control)

---

## Usage

### Standalone mode (one machine)

```bash
python AirMouse.py
```

On first run the hand-tracking model (~8 MB) is downloaded automatically. Camera index is auto-detected and saved to `config.json`.

### Client / Server mode (two machines on the same network)

Run on the machine you want to **control** (the server):
```bash
python AirMouse_Server.py
```

Run on the machine with the **camera** (the client):
```bash
python AirMouse_Client.py <server_ip>
```

---

## Configuration

`config.json` is auto-created on first run. Edit it to tune behaviour:

| Key | Default | Description |
|---|---|---|
| `camera_index` | auto | Webcam index; set manually if auto-detection picks the wrong one |
| `smoothing` | 0.18 | EMA alpha for cursor (0 = frozen, 1 = raw/jittery) |
| `sensitivity` | 1.3 | Cursor speed multiplier |
| `cursor_margin` | 0.12 | Edge fraction ignored; central 76% of frame → full screen |
| `dead_zone` | 0.008 | Minimum movement to update cursor |
| `click_threshold` | 0.06 | Pinch distance to trigger click (relative to hand size) |
| `click_cooldown` | 0.38 | Minimum seconds between clicks |
| `scroll_speed` | 3 | Lines per scroll tick |
| `keyboard_toggle_hold` | 1.0 | Seconds of open palm to toggle keyboard |
| `flip` | true | Mirror the camera image |
| `detection_confidence` | 0.75 | MediaPipe detection threshold |
| `tracking_confidence` | 0.5 | MediaPipe tracking threshold |

---

## Architecture

```
AirMouse.py              Standalone entry point — camera loop, gesture dispatch, HUD
AirMouse_Client.py       Client: streams landmark data to AirMouse_Server.py
AirMouse_Server.py       Server: drives mouse from streamed landmark data
config.py                Config dataclass + JSON persistence (config.json)
src/
  camera.py              Auto-detect camera port, warm-up, open at target resolution
  hand_tracker.py        MediaPipe HandLandmarker (Tasks API) — auto-downloads model
  gesture.py             Classify 21 landmarks → Gesture enum (move/click/scroll/drag)
  mouse.py               pynput mouse/keyboard with EMA smoothing; pyautogui fallback
  virtual_keyboard.py    QWERTY overlay rendered into the OpenCV camera frame
```

---

## Troubleshooting

**Cursor won't move / clicks don't fire**
→ Grant Accessibility to Terminal in System Settings → Privacy & Security → Accessibility.

**Camera not found**
→ Grant Camera access. Set `camera_index` in `config.json` to `0`, `1`, or `2` manually.

**Jittery cursor**
→ Lower `smoothing` (e.g. `0.10`). Ensure good lighting.

**Cursor doesn't reach screen edges**
→ Lower `cursor_margin` (e.g. `0.08`) or raise `sensitivity`.

---

## Requirements

- Python 3.10+
- Webcam
- macOS / Linux / Windows

---

## License

MIT — educational and personal use.
