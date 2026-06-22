"""
AirMouse Server — the CONTROLLER.

Run this on the machine with your webcam. It tracks your hand, turns gestures
into high-level commands (move / click / scroll / drag) and broadcasts them to
every connected client. One server can drive many clients at once.

    python AirMouse_Server.py                 # control connected clients
    python AirMouse_Server.py --token hunter2  # require a shared secret
    python AirMouse_Server.py --demo           # no camera — send a test pattern
    python AirMouse_Server.py --no-window      # headless (no preview window)

On the machine you want to control, run:
    python AirMouse_Client.py <this-server-ip> [--token hunter2]

The link uses a fixed-size struct protocol with a token handshake — never
pickle — so peers can't run code on each other. See src/link_protocol.py.
"""
from __future__ import annotations

import argparse
import math
import socket
import threading
import time

from src import branding
from src import link_protocol as link

WIN = "AirMouse Server (controller)"


# ── Client hub: tracks connected clients and broadcasts commands ──────────────────
class ClientHub:
    def __init__(self):
        self._clients: list[tuple[socket.socket, str]] = []
        self._lock = threading.Lock()

    def add(self, conn: socket.socket, addr: str) -> None:
        with self._lock:
            self._clients.append((conn, addr))

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._clients)

    @property
    def addrs(self) -> list[str]:
        with self._lock:
            return [a for _, a in self._clients]

    def broadcast(self, payload: bytes) -> None:
        """Send to all clients; quietly drop any that have gone away."""
        dead = []
        with self._lock:
            for item in self._clients:
                conn, addr = item
                try:
                    conn.sendall(payload)
                except OSError:
                    dead.append(item)
            for item in dead:
                self._clients.remove(item)
                try:
                    item[0].close()
                except OSError:
                    pass
        for _, addr in dead:
            print(f"[Server] Client {addr} disconnected. "
                  f"({self.count} still connected)")

    def close_all(self) -> None:
        with self._lock:
            for conn, _ in self._clients:
                try:
                    conn.close()
                except OSError:
                    pass
            self._clients.clear()


def _accept_loop(srv: socket.socket, hub: ClientHub, token: str, stop: threading.Event):
    while not stop.is_set():
        try:
            conn, addr = srv.accept()
        except OSError:
            break
        who = f"{addr[0]}:{addr[1]}"
        try:
            conn.settimeout(5.0)
            ok = link.verify_handshake(conn, token)
            conn.settimeout(None)
        except Exception:
            ok = False
        if not ok:
            print(f"[Server] Rejected {who} (bad token or handshake).")
            try:
                conn.close()
            except OSError:
                pass
            continue
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        hub.add(conn, who)
        print(f"[Server] ✓ Client connected: {who}   ({hub.count} total)")


# ── Command translation from gestures ─────────────────────────────────────────────
class Controller:
    """Turns a stream of gestures into link commands and broadcasts them."""

    def __init__(self, hub: ClientHub, scroll_speed: int, enable_middle: bool):
        self.hub = hub
        self.scroll_speed = scroll_speed
        self.enable_middle = enable_middle
        self._dragging = False
        self._scroll_prev = None
        self._was_paused = False
        self.last_event = "—"

    def _send(self, *args) -> None:
        self.hub.broadcast(link.pack(*args))

    def handle(self, gesture, engine, lm) -> None:
        from src.gesture import Gesture

        # Pause is informational — tell clients, then stop driving them.
        if engine.paused != self._was_paused:
            self._was_paused = engine.paused
            self._send(link.OP_PAUSE, 0, 0, 1 if engine.paused else 0)
            self.last_event = "paused" if engine.paused else "resumed"
        if engine.paused:
            self._end_drag()
            return

        nx, ny = engine.cursor_pos(lm)

        if gesture == Gesture.MOVE:
            self._end_drag()
            self._scroll_prev = None
            self._send(link.OP_MOVE, nx, ny, 0)
            self.last_event = "move"
        elif gesture == Gesture.LEFT_CLICK:
            self._end_drag()
            self._send(link.OP_CLICK, 0, 0, link.BTN_LEFT)
            self.last_event = "left click"
        elif gesture == Gesture.DOUBLE_CLICK:
            self._end_drag()
            self._send(link.OP_DOUBLE, 0, 0, link.BTN_LEFT)
            self.last_event = "double click"
        elif gesture == Gesture.RIGHT_CLICK:
            self._end_drag()
            self._send(link.OP_CLICK, 0, 0, link.BTN_RIGHT)
            self.last_event = "right click"
        elif gesture == Gesture.MIDDLE_CLICK:
            self._end_drag()
            self._send(link.OP_CLICK, 0, 0, link.BTN_MIDDLE)
            self.last_event = "middle click"
        elif gesture == Gesture.SCROLL:
            self._end_drag()
            ax, ay = engine.scroll_anchor(lm)
            if self._scroll_prev is not None:
                px, py = self._scroll_prev
                dx = (ax - px) * self.scroll_speed * 40.0
                dy = (py - ay) * self.scroll_speed * 40.0      # up = positive
                if abs(dx) > 0.05 or abs(dy) > 0.05:
                    self._send(link.OP_SCROLL, dx, dy, 0)
                    self.last_event = "scroll"
            self._scroll_prev = (ax, ay)
        elif gesture == Gesture.DRAG:
            self._scroll_prev = None
            self._send(link.OP_MOVE, nx, ny, 0)
            if not self._dragging:
                self._dragging = True
                self._send(link.OP_DRAG, 0, 0, 1)
                self.last_event = "drag start"
            else:
                self.last_event = "dragging"
        else:
            self._end_drag()

    def no_hand(self) -> None:
        self._end_drag()
        self._scroll_prev = None
        self.hub.broadcast(link.pack(link.OP_HEARTBEAT))

    def _end_drag(self) -> None:
        if self._dragging:
            self._dragging = False
            self._send(link.OP_DRAG, 0, 0, 0)


# ── Camera loop (the real thing) ──────────────────────────────────────────────────
def _run_camera(hub: ClientHub, args) -> None:
    import cv2
    from src.camera import detect_camera, open_camera
    from src.hand_tracker import HandTracker
    from src.gesture import GestureEngine

    branding.use(args.theme)
    cam_idx = detect_camera(args.camera)
    cap, cam_w, cam_h = open_camera(cam_idx)
    tracker = HandTracker()
    engine = GestureEngine(enable_middle_click=args.middle_click)
    ctrl = Controller(hub, args.scroll_speed, args.middle_click)

    if not args.no_window:
        cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WIN, cam_w, cam_h)

    print("[Server] Camera ready. Show your hand to control connected clients.")
    print("[Server] Press Q in the preview window (or Ctrl-C) to stop.\n")

    fps = fps_n = 0
    fps_t = time.time()
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("[Server] Camera frame lost — stopping.")
                break
            if not args.no_flip:
                frame = cv2.flip(frame, 1)

            results, lms = tracker.process(frame)
            if not args.no_window:
                tracker.draw(frame, results)

            if lms:
                lm = lms[0]
                g = engine.recognize(lm)
                ctrl.handle(g, engine, lm)
            else:
                ctrl.no_hand()

            fps_n += 1
            if time.time() - fps_t >= 1.0:
                fps, fps_n, fps_t = fps_n, 0, time.time()

            if not args.no_window:
                _draw_overlay(cv2, frame, hub, ctrl, engine, fps)
                cv2.imshow(WIN, frame)
                if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
                    break
            else:
                time.sleep(0.005)
    finally:
        tracker.close()
        cap.release()
        if not args.no_window:
            cv2.destroyAllWindows()


def _draw_overlay(cv2, frame, hub: ClientHub, ctrl: "Controller", engine, fps) -> None:
    h, w = frame.shape[:2]
    ov = frame.copy()
    cv2.rectangle(ov, (0, 0), (w, 40), branding.bgr("surface"), -1)
    cv2.addWeighted(ov, 0.9, frame, 0.1, 0, frame)
    n = hub.count
    dot = branding.bgr("success") if n else branding.bgr("warning")
    cv2.circle(frame, (16, 20), 6, dot, -1, cv2.LINE_AA)
    cv2.putText(frame, f"{n} client(s)", (30, 26), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, branding.bgr("text"), 2, cv2.LINE_AA)
    cv2.putText(frame, engine.label or ctrl.last_event, (170, 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, branding.bgr("accent"), 2, cv2.LINE_AA)
    cv2.putText(frame, f"{fps} fps", (w - 90, 26), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, branding.bgr("muted"), 1, cv2.LINE_AA)
    cv2.line(frame, (0, 40), (w, 40), branding.bgr("primary"), 2, cv2.LINE_AA)
    if n == 0:
        cv2.putText(frame, "Waiting for a client to connect...",
                    (16, h - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    branding.bgr("muted"), 1, cv2.LINE_AA)


# ── Demo loop (no camera) — a moving cursor + periodic clicks for testing ─────────
def _run_demo(hub: ClientHub, stop: threading.Event) -> None:
    print("[Server] DEMO mode — broadcasting a test pattern (no camera).")
    print("[Server] Connected clients will see the cursor circle and click.\n")
    t0 = time.time()
    next_click = t0 + 3.0
    while not stop.is_set():
        t = time.time() - t0
        nx = 0.5 + 0.25 * math.cos(t * 1.5)
        ny = 0.5 + 0.25 * math.sin(t * 1.5)
        hub.broadcast(link.pack(link.OP_MOVE, nx, ny, 0))
        if time.time() >= next_click:
            hub.broadcast(link.pack(link.OP_CLICK, 0, 0, link.BTN_LEFT))
            next_click = time.time() + 3.0
            print("[Server] demo: left click")
        time.sleep(1 / 60)


# ── Entry point ───────────────────────────────────────────────────────────────────
def main() -> None:
    p = argparse.ArgumentParser(description="AirMouse Server — control other machines with your hand.")
    p.add_argument("--version", action="version", version=f"AirMouse Server {branding.VERSION}")
    p.add_argument("--port", type=int, default=link.DEFAULT_PORT, help="TCP port to listen on")
    p.add_argument("--token", default="", help="shared secret clients must match")
    p.add_argument("--camera", type=int, default=-1, help="camera index (-1 = auto)")
    p.add_argument("--scroll-speed", type=int, default=4)
    p.add_argument("--middle-click", action="store_true", help="enable thumb+ring middle click")
    p.add_argument("--theme", default="Aurora")
    p.add_argument("--no-flip", action="store_true", help="don't mirror the camera")
    p.add_argument("--no-window", action="store_true", help="run headless (no preview)")
    p.add_argument("--demo", action="store_true", help="no camera — broadcast a test pattern")
    args = p.parse_args()

    ip = link.lan_ip()
    print("╔══════════════════════════════════════════════════════╗")
    print(f"║  {branding.APP_NAME} Server — the controller".ljust(55) + "║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"[Server] Listening on  0.0.0.0:{args.port}")
    print(f"[Server] This machine's LAN IP:  {ip}")
    print("[Server] On the machine you want to control, run:")
    tok = f" --token {args.token}" if args.token else ""
    print(f"             python AirMouse_Client.py {ip} --port {args.port}{tok}")
    if not args.token:
        print("[Server] ⚠ No --token set: anyone on this network who knows the IP")
        print("           can connect. Use --token <secret> on both sides to lock it.")
    print()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.port))
    srv.listen(8)

    hub = ClientHub()
    stop = threading.Event()
    acc = threading.Thread(target=_accept_loop, args=(srv, hub, args.token, stop), daemon=True)
    acc.start()

    try:
        if args.demo:
            _run_demo(hub, stop)
        else:
            _run_camera(hub, args)
    except KeyboardInterrupt:
        print("\n[Server] Interrupted.")
    finally:
        stop.set()
        hub.close_all()
        try:
            srv.close()
        except OSError:
            pass
        print("[Server] Stopped.")


if __name__ == "__main__":
    main()
