"""Tests for MouseController's pure coordinate mapping.

src.mouse guards its pynput/pyautogui imports, so the module imports cleanly
without a backend — we can construct a controller and exercise the maths only.
"""
from src.mouse import MouseController


def make_ctrl(w=1000, h=800, margin=0.1, calib=None):
    return MouseController(w, h, use_one_euro=True, cursor_margin=margin, calib=calib)


def test_map_axis_clamps_to_bounds():
    c = make_ctrl()
    # below the active range → 0
    assert c._map_axis(-1.0, 0.1, 0.9, 1000) == 0
    # above the active range → size-1
    assert c._map_axis(2.0, 0.1, 0.9, 1000) == 999


def test_map_axis_midpoint():
    c = make_ctrl()
    # centre of the active band maps to ~centre of the axis
    mid = c._map_axis(0.5, 0.1, 0.9, 1000)
    assert 480 <= mid <= 520


def test_map_uses_margin_when_uncalibrated():
    c = make_ctrl(w=1000, h=800, margin=0.1)
    # left/top edge of the active band → (0, 0)
    assert c._map(0.1, 0.1) == (0, 0)
    # right/bottom edge of the band → bottom-right pixel
    assert c._map(0.9, 0.9) == (999, 799)


def test_map_uses_calibration_box_when_set():
    calib = (0.2, 0.2, 0.8, 0.8)
    c = make_ctrl(w=1000, h=800, calib=calib)
    assert c._map(0.2, 0.2) == (0, 0)
    assert c._map(0.8, 0.8) == (999, 799)
    mid = c._map(0.5, 0.5)
    assert 480 <= mid[0] <= 520 and 380 <= mid[1] <= 420


def test_output_never_leaves_screen():
    c = make_ctrl(w=640, h=480, margin=0.05)
    for nx, ny in [(-5, -5), (5, 5), (0.5, 0.5), (0.0, 1.0)]:
        x, y = c._map(nx, ny)
        assert 0 <= x <= 639 and 0 <= y <= 479


def test_initial_cursor_is_centered():
    c = make_ctrl(w=1000, h=800)
    assert c.last_xy == (500, 400)


def test_drag_state_toggles(monkeypatch):
    # Stub the backend so the test never emits a real mouse press/release.
    import src.mouse as m
    monkeypatch.setattr(m, "_do_press", lambda: None)
    monkeypatch.setattr(m, "_do_release", lambda: None)
    c = make_ctrl()
    assert c.dragging is False
    c.start_drag()
    assert c.dragging is True
    c.stop_drag()
    assert c.dragging is False
