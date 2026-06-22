"""Tests for the One Euro Filter (deterministic via explicit timestamps)."""
from src.filters import OneEuroFilter


def test_first_sample_passes_through():
    f = OneEuroFilter()
    assert f(0.42, timestamp=0.0) == 0.42


def test_smooths_toward_target_not_instant():
    f = OneEuroFilter(min_cutoff=1.0, beta=0.0)
    f(0.0, timestamp=0.0)
    out = f(1.0, timestamp=1 / 60)        # big jump, one frame later
    assert 0.0 < out < 1.0                # moved toward target but not all the way


def test_converges_when_held_steady():
    f = OneEuroFilter(min_cutoff=1.0, beta=0.01)
    t = 0.0
    for _ in range(200):
        t += 1 / 60
        out = f(0.8, timestamp=t)
    assert abs(out - 0.8) < 1e-2


def test_reset_clears_state():
    f = OneEuroFilter()
    f(0.5, timestamp=0.0)
    f(0.9, timestamp=0.1)
    f.reset()
    assert f(0.123, timestamp=0.0) == 0.123   # behaves like a fresh filter


def test_handles_zero_dt_without_crashing():
    f = OneEuroFilter()
    f(0.1, timestamp=5.0)
    out = f(0.2, timestamp=5.0)               # dt == 0 → guarded internally
    assert isinstance(out, float)


def test_higher_beta_is_more_responsive():
    slow = OneEuroFilter(min_cutoff=1.0, beta=0.0)
    fast = OneEuroFilter(min_cutoff=1.0, beta=1.0)
    for f in (slow, fast):
        f(0.0, timestamp=0.0)
    t = 0.0
    for _ in range(5):
        t += 1 / 60
        slow_out = slow(1.0, timestamp=t)
        fast_out = fast(1.0, timestamp=t)
    assert fast_out >= slow_out               # responsive filter tracks faster
