"""Tests for the AirMouse remote-control wire protocol."""
import socket

import pytest

from src import link_protocol as link


def test_frame_size_is_fixed():
    assert link.FRAME_SIZE == 13
    assert len(link.pack(link.OP_MOVE, 0.1, 0.2, 0)) == link.FRAME_SIZE


@pytest.mark.parametrize("op,ax,ay,n", [
    (link.OP_MOVE, 0.25, 0.75, 0),
    (link.OP_CLICK, 0.0, 0.0, link.BTN_RIGHT),
    (link.OP_SCROLL, -1.5, 2.0, 0),
    (link.OP_DRAG, 0.0, 0.0, 1),
])
def test_pack_unpack_roundtrip(op, ax, ay, n):
    op2, ax2, ay2, n2 = link.unpack(link.pack(op, ax, ay, n))
    assert op2 == op and n2 == n
    assert ax2 == pytest.approx(ax, abs=1e-6)
    assert ay2 == pytest.approx(ay, abs=1e-6)


def test_handshake_accepts_matching_token():
    a, b = socket.socketpair()
    try:
        link.send_handshake(a, "s3cret")
        assert link.verify_handshake(b, "s3cret") is True
    finally:
        a.close(); b.close()


def test_handshake_rejects_wrong_token():
    a, b = socket.socketpair()
    try:
        link.send_handshake(a, "s3cret")
        assert link.verify_handshake(b, "nope") is False
    finally:
        a.close(); b.close()


def test_handshake_rejects_garbage():
    a, b = socket.socketpair()
    try:
        a.sendall(b"\x00" * link.HS_SIZE)
        assert link.verify_handshake(b, "") is False
    finally:
        a.close(); b.close()


def test_digest_is_not_the_token_and_is_stable():
    d1 = link._digest("hunter2")
    d2 = link._digest("hunter2")
    assert d1 == d2 and len(d1) == 32
    assert b"hunter2" not in d1


def test_recv_exact_raises_on_disconnect():
    a, b = socket.socketpair()
    a.close()
    with pytest.raises(ConnectionError):
        link.recv_exact(b, 4)
    b.close()


def test_lan_ip_returns_dotted_quad():
    ip = link.lan_ip()
    parts = ip.split(".")
    assert len(parts) == 4 and all(p.isdigit() for p in parts)


def test_key_codepoint_roundtrips():
    # 'A' over the wire
    op, _, _, n = link.unpack(link.pack(link.OP_KEY, 0, 0, ord("A")))
    assert op == link.OP_KEY and chr(n) == "A"
    # a non-ASCII codepoint survives int32
    op, _, _, n = link.unpack(link.pack(link.OP_KEY, 0, 0, ord("é")))
    assert chr(n) == "é"


def test_special_and_media_key_ids_are_unique():
    ids = list(link.SPECIAL_KEYS.values()) + list(link.MEDIA_KEYS.values())
    assert len(ids) == len(set(ids)), "key ids must be unique across the wire"


def test_key_id_reverse_map_is_consistent():
    for name, kid in {**link.SPECIAL_KEYS, **link.MEDIA_KEYS}.items():
        assert link.KEY_ID_TO_NAME[kid] == name


def test_tap_opcode_roundtrips():
    op, _, _, n = link.unpack(link.pack(link.OP_TAP, 0, 0, link.SPECIAL_KEYS["ENTER"]))
    assert op == link.OP_TAP
    assert link.KEY_ID_TO_NAME[n] == "ENTER"
