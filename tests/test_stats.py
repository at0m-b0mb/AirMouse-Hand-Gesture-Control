"""Tests for SessionStats counters, derived values and persistence."""
import math

from src.stats import SessionStats


def test_counts_and_total_clicks():
    s = SessionStats()
    s.left_click(); s.left_click()
    s.right_click()
    s.middle_click()
    s.double_click()
    assert s.left_clicks == 2
    assert s.total_clicks == 4          # left + right + middle (double excluded)
    assert s.double_clicks == 1


def test_cursor_travel_is_euclidean():
    s = SessionStats()
    s.moved_to(0, 0)
    s.moved_to(3, 4)                    # +5
    s.moved_to(3, 4)                    # +0
    assert math.isclose(s.distance_px, 5.0, abs_tol=1e-9)


def test_uptime_str_format():
    s = SessionStats()
    s.started -= 75                    # pretend 75 s elapsed
    assert s.uptime_str() == "1:15"


def test_summary_has_expected_keys():
    s = SessionStats()
    summary = s.summary()
    for key in ("Uptime", "Left clicks", "Scrolls", "Keys typed", "Cursor travel"):
        assert key in summary


def test_save_and_load_roundtrip(tmp_path):
    s = SessionStats()
    s.left_click(); s.scroll(); s.key()
    path = tmp_path / "last_session.json"
    s.save_to_file(path)
    loaded = SessionStats.load_from_file(path)
    assert loaded is not None
    assert loaded["Left clicks"] == 1
    assert loaded["Scrolls"] == 1
    assert "saved_at" in loaded


def test_load_missing_file_returns_none(tmp_path):
    assert SessionStats.load_from_file(tmp_path / "nope.json") is None


def test_load_corrupt_file_returns_none(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json")
    assert SessionStats.load_from_file(bad) is None
