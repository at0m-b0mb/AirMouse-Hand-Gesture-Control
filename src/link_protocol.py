"""AirMouse Link — the tiny, safe wire protocol shared by the controller
(``AirMouse_Server.py``) and the controlled machine (``AirMouse_Client.py``).

Design goals:
  • **Safe** — every frame is a fixed-size ``struct`` packet. We never use
    ``pickle``/``eval`` on network data, so a hostile peer can't run code on you.
  • **Simple** — high-level *commands* (move / click / scroll / drag) travel the
    wire, not raw landmarks. The controller does all the hand-tracking; the
    controlled machine just applies ready-made actions.
  • **Screen-independent** — cursor moves are sent as 0..1 fractions, so a laptop
    can drive a 4K monitor and vice-versa.

Wire format
-----------
Handshake (once, client → server):  MAGIC(4) + version(1) + token_digest(32)
Command frame (server → client):    opcode(1) + ax(f32) + ay(f32) + n(i32) = 13 B
"""
from __future__ import annotations

import hashlib
import hmac
import socket
import struct

MAGIC = b"AML1"
PROTO_VERSION = 1
DEFAULT_PORT = 12345

# ── Command opcodes ────────────────────────────────────────────────────────────
OP_HEARTBEAT = 0   # keep-alive; ax/ay/n unused
OP_MOVE      = 1   # ax, ay = cursor position as 0..1 fractions of the screen
OP_CLICK     = 2   # n = button (BTN_LEFT / BTN_RIGHT / BTN_MIDDLE)
OP_DOUBLE    = 3   # n = button (usually BTN_LEFT)
OP_SCROLL    = 4   # ax, ay = scroll delta (right+, up+)
OP_DRAG      = 5   # n = 1 → press & hold,  n = 0 → release
OP_PAUSE     = 6   # n = 1 → controller paused,  n = 0 → resumed (informational)
OP_KEY       = 7   # n = Unicode codepoint to type (the virtual keyboard)
OP_TAP       = 8   # n = special/media key id (see SPECIAL_KEYS / MEDIA_KEYS)

BTN_LEFT, BTN_RIGHT, BTN_MIDDLE = 0, 1, 2

# Special & media keys carried by OP_TAP. Ids are stable wire constants — only
# ever append, never renumber.
SPECIAL_KEYS = {
    "BKSP": 1, "ENTER": 2, "SPACE": 3, "TAB": 4, "ESC": 5,
    "UP": 6, "DOWN": 7, "LEFT": 8, "RIGHT": 9, "SCRNSHOT": 14,
}
MEDIA_KEYS = {"VOL_UP": 10, "VOL_DOWN": 11, "MUTE": 12, "PLAY": 13}
KEY_ID_TO_NAME = {v: k for k, v in {**SPECIAL_KEYS, **MEDIA_KEYS}.items()}

OP_NAMES = {
    OP_HEARTBEAT: "heartbeat", OP_MOVE: "move", OP_CLICK: "click",
    OP_DOUBLE: "double-click", OP_SCROLL: "scroll", OP_DRAG: "drag",
    OP_PAUSE: "pause", OP_KEY: "key", OP_TAP: "tap",
}
BTN_NAMES = {BTN_LEFT: "left", BTN_RIGHT: "right", BTN_MIDDLE: "middle"}

_FMT = "!Bffi"                       # opcode, ax, ay, n
FRAME_SIZE = struct.calcsize(_FMT)   # = 13 bytes

_HS_FMT = "!4sB32s"                  # magic, version, sha256 digest
HS_SIZE = struct.calcsize(_HS_FMT)   # = 37 bytes


# ── Framing ─────────────────────────────────────────────────────────────────────
def pack(op: int, ax: float = 0.0, ay: float = 0.0, n: int = 0) -> bytes:
    return struct.pack(_FMT, op, float(ax), float(ay), int(n))


def unpack(raw: bytes) -> tuple[int, float, float, int]:
    return struct.unpack(_FMT, raw)          # (op, ax, ay, n)


def recv_exact(conn: socket.socket, size: int) -> bytes:
    """Read exactly ``size`` bytes or raise ConnectionError on disconnect."""
    buf = b""
    while len(buf) < size:
        chunk = conn.recv(size - len(buf))
        if not chunk:
            raise ConnectionError("peer disconnected")
        buf += chunk
    return buf


# ── Handshake / auth ──────────────────────────────────────────────────────────────
def _digest(token: str) -> bytes:
    """A 32-byte fingerprint of the shared token (never the token itself)."""
    return hashlib.sha256(("airmouse-link:" + (token or "")).encode()).digest()


def send_handshake(conn: socket.socket, token: str) -> None:
    conn.sendall(struct.pack(_HS_FMT, MAGIC, PROTO_VERSION, _digest(token)))


def verify_handshake(conn: socket.socket, token: str) -> bool:
    """Server-side: read the client's handshake and check magic + token."""
    raw = recv_exact(conn, HS_SIZE)
    magic, ver, digest = struct.unpack(_HS_FMT, raw)
    if magic != MAGIC or ver != PROTO_VERSION:
        return False
    return hmac.compare_digest(digest, _digest(token))   # constant-time compare


# ── Convenience ───────────────────────────────────────────────────────────────────
def lan_ip() -> str:
    """Best-effort LAN IP for display. Opens a UDP socket but sends nothing."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()
