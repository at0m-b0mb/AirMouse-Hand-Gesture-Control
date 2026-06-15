"""Signal filters for smooth cursor control.

The One Euro Filter (Casiet, Roussel & Lécuyer, CHI 2012) is the de-facto
standard for low-latency interactive pointing: it smooths heavily when the
hand is still (killing jitter) and barely at all when the hand moves fast
(killing lag). Far better than a fixed-alpha EMA.
"""
import math
import time
from typing import Optional


def _alpha(cutoff: float, dt: float) -> float:
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class _LowPass:
    def __init__(self) -> None:
        self.y: Optional[float] = None

    def __call__(self, value: float, alpha: float) -> float:
        if self.y is None:
            self.y = value
        else:
            self.y = alpha * value + (1.0 - alpha) * self.y
        return self.y


class OneEuroFilter:
    """One-dimensional One Euro Filter.

    min_cutoff : lower  → smoother when still (more lag at low speed)
    beta       : higher → more responsive when moving fast (less lag)
    d_cutoff   : cutoff for the derivative path (usually 1.0)
    """

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.007, d_cutoff: float = 1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x = _LowPass()
        self._dx = _LowPass()
        self._prev: Optional[float] = None
        self._t: Optional[float] = None

    def reset(self) -> None:
        self._x = _LowPass()
        self._dx = _LowPass()
        self._prev = None
        self._t = None

    def __call__(self, value: float, timestamp: Optional[float] = None) -> float:
        value = float(value)
        now = timestamp if timestamp is not None else time.time()
        if self._t is None or self._prev is None:
            self._t = now
            self._prev = value
            self._x(value, 1.0)
            return value

        dt = now - self._t
        if dt <= 0:
            dt = 1e-3
        self._t = now

        dvalue = (value - self._prev) * (1.0 / dt)
        edvalue = self._dx(dvalue, _alpha(self.d_cutoff, dt))
        cutoff = self.min_cutoff + self.beta * abs(edvalue)
        self._prev = value
        return self._x(value, _alpha(cutoff, dt))
