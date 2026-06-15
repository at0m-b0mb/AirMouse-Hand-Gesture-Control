"""
AirMouse Server — receives gesture data from AirMouse_Client.py over TCP
and drives the local mouse.

Run on the machine whose mouse you want to control:
    python AirMouse_Server.py [port]

Protocol: each frame is exactly 17 bytes:
    1 byte  - has_hand (0 or 1)
    4 bytes - cursor_x  (big-endian float32)
    4 bytes - cursor_y  (big-endian float32)
    4 bytes - dist_index_thumb (float32)
    4 bytes - dist_middle_thumb (float32)

Using struct instead of pickle intentionally — never deserialize
untrusted data with pickle over a network socket.
"""

import socket
import struct
import time

try:
    from pynput.mouse import Button, Controller as MouseCtrl
    _mouse = MouseCtrl()
    def _move(x, y):   _mouse.position = (x, y)
    def _lclick():     _mouse.click(Button.left)
    def _rclick():     _mouse.click(Button.right)
except ImportError:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
    def _move(x, y):   pyautogui.moveTo(x, y)
    def _lclick():     pyautogui.click()
    def _rclick():     pyautogui.rightClick()

try:
    import pyautogui as _pag
    _pag.FAILSAFE = False
    def _screen_size(): return _pag.size()
except Exception:
    def _screen_size(): return (1920, 1080)

_FMT        = "!B4f"   # 1 bool + 4 floats = 17 bytes
_FRAME_SIZE = struct.calcsize(_FMT)

DEFAULT_PORT    = 12345
CLICK_THRESHOLD = 0.05
SMOOTH          = 0.20
CLICK_COOLDOWN  = 0.40


def _recv_exact(conn: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Client disconnected")
        buf += chunk
    return buf


def main(port: int = DEFAULT_PORT) -> None:
    sw, sh = _screen_size()
    print(f"[Server] Screen {sw}x{sh}")
    print(f"[Server] Listening on 0.0.0.0:{port} ...")
    print("[Server] Connect AirMouse_Client.py from the camera machine.\n")

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(1)

    conn, addr = srv.accept()
    print(f"[Server] Connected from {addr}")

    prev_x = prev_y = 0.0
    last_click = 0.0

    try:
        while True:
            raw = _recv_exact(conn, _FRAME_SIZE)
            has_hand, cx, cy, d_idx, d_mid = struct.unpack(_FMT, raw)

            if not has_hand:
                continue

            tx = min(max(sw * cx, 0), sw - 1)
            ty = min(max(sh * cy, 0), sh - 1)
            sx = prev_x + (tx - prev_x) * SMOOTH
            sy = prev_y + (ty - prev_y) * SMOOTH
            _move(int(sx), int(sy))
            prev_x, prev_y = sx, sy

            now = time.time()
            if now - last_click > CLICK_COOLDOWN:
                if d_idx < CLICK_THRESHOLD:
                    _lclick()
                    last_click = now
                elif d_mid < CLICK_THRESHOLD:
                    _rclick()
                    last_click = now

    except ConnectionError:
        pass
    finally:
        conn.close()
        srv.close()
        print("[Server] Connection closed.")


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    main(port)
