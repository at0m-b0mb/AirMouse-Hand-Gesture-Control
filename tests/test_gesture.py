"""Tests for the gesture recognition engine using synthetic hand landmarks.

Image coordinates: y grows downward, so a finger pointing 'up' has its
tip.y < pip.y. We build a full 21-point hand and toggle finger poses.
"""
import pytest

from src.gesture import Gesture, GestureEngine


class _P:
    __slots__ = ("x", "y")

    def __init__(self, x, y):
        self.x = x
        self.y = y


def make_hand(index=False, middle=False, ring=False, pinky=False,
              thumb_up=False, pinch_index=False, pinch_middle=False):
    """Build a 21-landmark hand with the requested pose."""
    pts = [_P(0.5, 0.5) for _ in range(21)]
    pts[0] = _P(0.50, 0.95)     # wrist
    pts[9] = _P(0.55, 0.70)     # middle MCP — sets hand size with the wrist
    pts[5] = _P(0.50, 0.70)     # index MCP
    pts[17] = _P(0.65, 0.70)    # pinky MCP
    pts[2] = _P(0.40, 0.80)     # thumb MCP
    pts[3] = _P(0.38, 0.78)     # thumb IP

    def finger(tip_i, pip_i, x, up):
        pts[pip_i] = _P(x, 0.60)
        pts[tip_i] = _P(x, 0.45 if up else 0.75)

    finger(8, 6, 0.50, index)
    finger(12, 10, 0.55, middle)
    finger(16, 14, 0.60, ring)
    finger(20, 18, 0.65, pinky)

    pts[4] = _P(0.36, 0.50) if thumb_up else _P(0.34, 0.82)   # thumb tip
    if pinch_index:
        pts[4] = _P(pts[8].x, pts[8].y)
    if pinch_middle:
        pts[4] = _P(pts[12].x, pts[12].y)
    return pts


def test_index_only_is_move():
    eng = GestureEngine()
    assert eng.recognize(make_hand(index=True)) == Gesture.MOVE


def test_open_palm_first_frame_is_move():
    eng = GestureEngine()
    g = eng.recognize(make_hand(index=True, middle=True, ring=True, pinky=True))
    assert g == Gesture.MOVE          # palm hold hasn't elapsed yet


def test_peace_sign_is_scroll():
    eng = GestureEngine()
    assert eng.recognize(make_hand(index=True, middle=True)) == Gesture.SCROLL


def test_fist_is_drag():
    eng = GestureEngine()
    assert eng.recognize(make_hand()) == Gesture.DRAG


def test_pinch_index_is_left_click():
    eng = GestureEngine()
    assert eng.recognize(make_hand(pinch_index=True)) == Gesture.LEFT_CLICK


def test_pinch_middle_is_right_click():
    eng = GestureEngine()
    assert eng.recognize(make_hand(pinch_middle=True)) == Gesture.RIGHT_CLICK


def test_left_click_is_edge_triggered():
    eng = GestureEngine()
    first = eng.recognize(make_hand(pinch_index=True))
    second = eng.recognize(make_hand(pinch_index=True))   # still pinched
    assert first == Gesture.LEFT_CLICK
    assert second != Gesture.LEFT_CLICK                   # no repeat until release


def test_middle_click_requires_opt_in():
    off = GestureEngine(enable_middle_click=False)
    on = GestureEngine(enable_middle_click=True)
    # thumb-ring pinch
    hand = make_hand()
    hand[4] = type(hand[16])(hand[16].x, hand[16].y)      # thumb tip onto ring tip
    assert off.recognize(hand) != Gesture.MIDDLE_CLICK
    assert on.recognize(hand) == Gesture.MIDDLE_CLICK


def test_thumbs_up_holds_then_returns_none():
    eng = GestureEngine()
    g = eng.recognize(make_hand(thumb_up=True))
    assert g == Gesture.NONE
    assert "humb" in eng.label or eng.paused


def test_degenerate_hand_is_none():
    eng = GestureEngine()
    flat = [type(make_hand()[0])(0.5, 0.5) for _ in range(21)]   # zero hand size
    assert eng.recognize(flat) == Gesture.NONE


def test_cursor_pos_tracks_index_tip():
    eng = GestureEngine()
    hand = make_hand(index=True)
    assert eng.cursor_pos(hand) == pytest.approx((hand[8].x, hand[8].y))
