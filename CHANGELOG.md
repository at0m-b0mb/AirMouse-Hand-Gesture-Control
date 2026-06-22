# Changelog

All notable changes to AirMouse are documented here.
This project follows [Semantic Versioning](https://semver.org/).

## [3.2] — 2026-06-21

### Added
- **Remote control** — drive another computer with your hand over the LAN. The
  server (controller) tracks your hand and broadcasts high-level commands to one
  or many clients; token auth, `--demo`/`--dry-run` test modes, auto-reconnect,
  and an Esc kill-switch. New safe `src/link_protocol.py` (fixed-size `struct`
  frames + SHA-256 handshake — never pickle).
- **Guided walkthrough** in AirMouse Studio — first-run onboarding for
  permissions, gestures and launch, with a **? Tutorial** replay button and a
  *Don't show again* opt-out.
- **In-app coach card** in the camera window (`/` to toggle, `N` to hide for good).
- **`--doctor`** diagnostics (`python AirMouse.py --doctor`) — checks Python,
  dependencies, the model file, cameras and permissions.
- **`--version`** flag on `AirMouse.py`, the server and the client.
- **Test suite** (`tests/`, pytest) covering the protocol, One Euro filter,
  session stats, config validation, branding and the gesture engine.
- **Continuous integration** (GitHub Actions) running ruff + pytest on 3.10–3.12.
- **`Config.validate()`** clamps every tunable so a hand-edited or stale
  `config.json` can't put the app into a broken state.
- Two new themes — **Sunset** and **Ocean**.
- `LICENSE` (MIT), `CHANGELOG.md`, `CONTRIBUTING.md`, `pyproject.toml`.

### Changed
- The network mode was reframed so the **server is the controller** and the
  **client is the controlled machine** (was the reverse), with a high-level
  command protocol instead of raw landmark streaming.
- Richer HUD: cursor glow rings, toast accent bar, frosted status bar.

## [3.1]

### Added
- AirMouse Studio dashboard (system check, last-session chart, quick stats),
  profile cards, quick sensitivity bar, theme swatches, animated launch button.
- Sound feedback on gesture clicks (macOS).
- Session stats persisted to `last_session.json`.

## [3.0]

- One Euro Filter cursor smoothing, tuning profiles, themed HUD, virtual
  keyboard, calibration, and the customtkinter control center.
