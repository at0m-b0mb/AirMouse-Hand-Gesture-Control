"""
AirMouse Client — the CONTROLLED machine.

Run this on the computer you want the server to control. It connects to the
server, receives high-level commands (move / click / scroll / drag) and applies
them to THIS machine's mouse. No camera needed here.

    python AirMouse_Client.py <server_ip>                # be controlled
    python AirMouse_Client.py 192.168.1.20 --token hunter2
    python AirMouse_Client.py 192.168.1.20 --dry-run     # print, don't move (safe test)
    python AirMouse_Client.py 192.168.1.20 --retry       # auto-reconnect

Safety: this lets another machine move your mouse. Only connect to a server you
trust, prefer a --token, and press Esc on THIS machine (or Ctrl-C) to stop.
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time

from src import branding
from src import link_protocol as link


# ── Local input applier ──────────────────────────────────────────────────────────
class Applier:
    """Applies link commands to the local mouse, with movement smoothing."""

    def __init__(self, smooth: float = 0.35, dry_run: bool = False):
        self.dry_run = dry_run
        self.smooth = smooth
        self._sx = self._sy = None
        self._dragging = False
        self._init_backend()

    def _init_backend(self):
        self._backend = "none"
        self._kbd = self._Key = self._pag = None
        try:
            from pynput.keyboard import Controller as KbCtrl, Key
            from pynput.mouse import Button, Controller
            self._Button = Button
            self._m = Controller()
            self._Key = Key
            self._kbd = KbCtrl()
            self._backend = "pynput"
        except Exception:
            try:
                import pyautogui
                pyautogui.FAILSAFE = False
                pyautogui.PAUSE = 0
                self._pag = pyautogui
                self._backend = "pyautogui"
            except Exception:
                self._backend = "none"
        # Screen size
        try:
            import pyautogui as _pag
            self._sw, self._sh = _pag.size()
        except Exception:
            self._sw, self._sh = 1920, 1080

    # Wire key-id → pynput Key attribute / pyautogui key name.
    _KEY_NAME = {
        1: "backspace", 2: "enter", 3: "space", 4: "tab", 5: "esc",
        6: "up", 7: "down", 8: "left", 9: "right",
        10: "media_volume_up", 11: "media_volume_down",
        12: "media_volume_mute", 13: "media_play_pause",
    }
    _PYAUTOGUI_KEY = {
        1: "backspace", 2: "enter", 3: "space", 4: "tab", 5: "esc",
        6: "up", 7: "down", 8: "left", 9: "right",
        10: "volumeup", 11: "volumedown", 12: "volumemute", 13: "playpause",
    }

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def screen(self) -> tuple[int, int]:
        return self._sw, self._sh

    # ── primitive actions ────────────────────────────────────────────────────────
    def _btn(self, n):
        if self._backend == "pynput":
            return {link.BTN_LEFT: self._Button.left,
                    link.BTN_RIGHT: self._Button.right,
                    link.BTN_MIDDLE: self._Button.middle}.get(n, self._Button.left)
        return {link.BTN_LEFT: "left", link.BTN_RIGHT: "right",
                link.BTN_MIDDLE: "middle"}.get(n, "left")

    def move(self, nx, ny):
        tx = min(max(nx, 0.0), 1.0) * self._sw
        ty = min(max(ny, 0.0), 1.0) * self._sh
        if self._sx is None:
            self._sx, self._sy = tx, ty
        else:
            self._sx += (tx - self._sx) * self.smooth
            self._sy += (ty - self._sy) * self.smooth
        x, y = int(self._sx), int(self._sy)
        if self.dry_run:
            return
        if self._backend == "pynput":
            self._m.position = (x, y)
        elif self._backend == "pyautogui":
            self._pag.moveTo(x, y)

    def click(self, n, count=1):
        if self.dry_run:
            return
        if self._backend == "pynput":
            self._m.click(self._btn(n), count)
        elif self._backend == "pyautogui":
            self._pag.click(button=self._btn(n), clicks=count)

    def scroll(self, dx, dy):
        if self.dry_run:
            return
        if self._backend == "pynput":
            self._m.scroll(int(round(dx)), int(round(dy)))
        elif self._backend == "pyautogui":
            if dy:
                self._pag.scroll(int(round(dy)))
            if dx:
                self._pag.hscroll(int(round(dx)))

    def drag(self, down):
        if self.dry_run:
            self._dragging = down
            return
        if self._backend == "pynput":
            (self._m.press if down else self._m.release)(self._Button.left)
        elif self._backend == "pyautogui":
            (self._pag.mouseDown if down else self._pag.mouseUp)()
        self._dragging = down

    def release_all(self):
        if self._dragging:
            try:
                self.drag(False)
            except Exception:
                pass

    def key(self, codepoint):
        if self.dry_run:
            return
        try:
            ch = chr(int(codepoint))
        except (ValueError, OverflowError):
            return
        if self._backend == "pynput":
            self._kbd.type(ch)
        elif self._backend == "pyautogui":
            self._pag.typewrite(ch, interval=0)

    def tap(self, key_id):
        if key_id == link.SPECIAL_KEYS["SCRNSHOT"]:
            self._screenshot()
            return
        if self.dry_run:
            return
        if self._backend == "pynput":
            name = self._KEY_NAME.get(key_id)
            k = getattr(self._Key, name, None) if name else None
            if k is not None:
                self._kbd.press(k)
                self._kbd.release(k)
        elif self._backend == "pyautogui":
            name = self._PYAUTOGUI_KEY.get(key_id)
            if name:
                self._pag.press(name)

    def _screenshot(self):
        if self.dry_run:
            return
        try:
            from src import actions
            actions.screenshot()
        except Exception:
            pass

    # ── dispatch ──────────────────────────────────────────────────────────────────
    def apply(self, op, ax, ay, n) -> str:
        if op == link.OP_MOVE:
            self.move(ax, ay)
        elif op == link.OP_CLICK:
            self.click(n)
        elif op == link.OP_DOUBLE:
            self.click(n, 2)
        elif op == link.OP_SCROLL:
            self.scroll(ax, ay)
        elif op == link.OP_DRAG:
            self.drag(bool(n))
        elif op == link.OP_KEY:
            self.key(n)
            return f"type {chr(n)!r}" if 0 < n < 0x110000 else "type"
        elif op == link.OP_TAP:
            self.tap(n)
            return f"tap {link.KEY_ID_TO_NAME.get(n, n)}"
        elif op == link.OP_PAUSE:
            return "paused" if n else "resumed"
        return link.OP_NAMES.get(op, "?")


def _start_killswitch(stop: threading.Event) -> None:
    """Press Esc on this machine to stop being controlled (best-effort)."""
    try:
        from pynput import keyboard
    except Exception:
        return

    def on_press(key):
        if key == keyboard.Key.esc:
            print("\n[Client] Esc pressed — disconnecting.")
            stop.set()
            return False

    threading.Thread(target=lambda: keyboard.Listener(on_press=on_press).run(),
                     daemon=True).start()


def _session(ip: str, port: int, token: str, applier: Applier, stop: threading.Event) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(8.0)
    sock.connect((ip, port))
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    link.send_handshake(sock, token)
    sock.settimeout(None)
    print(f"[Client] ✓ Connected to {ip}:{port}. This machine can now be controlled.")
    print("[Client] Press Esc here (or Ctrl-C) to stop.\n")

    last_log = 0.0
    count = 0
    try:
        while not stop.is_set():
            raw = link.recv_exact(sock, link.FRAME_SIZE)
            op, ax, ay, n = link.unpack(raw)
            name = applier.apply(op, ax, ay, n)
            count += 1
            now = time.time()
            if op != link.OP_HEARTBEAT and now - last_log >= 0.25:
                tag = "[dry-run] " if applier.dry_run else ""
                extra = (f" ({link.BTN_NAMES.get(n, n)})"
                         if op in (link.OP_CLICK, link.OP_DOUBLE) else "")
                sys.stdout.write(f"\r[Client] {tag}{name}{extra}      ")
                sys.stdout.flush()
                last_log = now
    finally:
        applier.release_all()
        try:
            sock.close()
        except OSError:
            pass


def main() -> None:
    p = argparse.ArgumentParser(description="AirMouse Client — let a server control this machine.")
    p.add_argument("--version", action="version", version=f"AirMouse Client {branding.VERSION}")
    p.add_argument("server_ip", nargs="?", default="127.0.0.1", help="server IP address")
    p.add_argument("--port", type=int, default=link.DEFAULT_PORT)
    p.add_argument("--token", default="", help="shared secret (must match the server)")
    p.add_argument("--smooth", type=float, default=0.35, help="cursor smoothing 0..1 (higher = snappier)")
    p.add_argument("--dry-run", action="store_true", help="print commands without moving the mouse")
    p.add_argument("--retry", action="store_true", help="auto-reconnect if the link drops")
    p.add_argument("--no-killswitch", action="store_true", help="don't bind Esc to disconnect")
    args = p.parse_args()

    applier = Applier(smooth=args.smooth, dry_run=args.dry_run)
    print("╔══════════════════════════════════════════════════════╗")
    print("║  AirMouse Client — this machine will be controlled".ljust(55) + "║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"[Client] Input backend: {applier.backend}   screen: {applier.screen[0]}x{applier.screen[1]}")
    if applier.backend == "none" and not args.dry_run:
        print("[Client] ⚠ No pynput/pyautogui available — install one to apply input.")
    if args.dry_run:
        print("[Client] DRY-RUN: commands will be printed, the mouse won't move.")
    print(f"[Client] Connecting to {args.server_ip}:{args.port} ...\n")

    stop = threading.Event()
    if not args.no_killswitch and not args.dry_run:
        _start_killswitch(stop)

    backoff = 1.0
    try:
        while not stop.is_set():
            try:
                _session(args.server_ip, args.port, args.token, applier, stop)
                backoff = 1.0
            except (ConnectionError, OSError) as exc:
                print(f"\n[Client] Link lost: {exc}")
            if not args.retry or stop.is_set():
                break
            print(f"[Client] Reconnecting in {backoff:.0f}s ...")
            time.sleep(backoff)
            backoff = min(backoff * 1.6, 10.0)
    except KeyboardInterrupt:
        print("\n[Client] Interrupted.")
    finally:
        applier.release_all()
        print("[Client] Done.")


if __name__ == "__main__":
    main()
