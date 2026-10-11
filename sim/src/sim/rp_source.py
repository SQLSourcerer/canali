"""How a bonus RP's quantity is recovered from the points a metric rates.

A recovery maps a team's points ``P`` to the quantity ``Q`` in RP thresholds, non-decreasing in ``P``, and turns a
quantity threshold into a points threshold.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, Self

import numpy as np
import numpy.typing as npt

Floats = npt.NDArray[np.float64]

# Doublings the bisection's upper bound may take before the threshold is judged unreachable.
MAX_DOUBLINGS = 64


class Recovery(Protocol):
    """A non-decreasing map from points to an RP's quantity."""

    def recover(self, points: Floats) -> Floats: ...

    def fit(self, points: Floats, quantity: Floats) -> Recovery:
        """Refit on the cadence's rows; a fixed recovery returns itself."""
        ...

    def points_threshold(self, threshold: float) -> float:
        """The fewest points whose recovered quantity reaches ``threshold``."""
        ...


class Fixed:
    __slots__ = ()

    def fit(self, points: Floats, quantity: Floats) -> Self:  # noqa: ARG002
        return self


@dataclass(frozen=True, slots=True)
class Identity(Fixed):
    """The quantity is the points."""

    def recover(self, points: Floats) -> Floats:
        return np.asarray(points, dtype=np.float64)

    def points_threshold(self, threshold: float) -> float:
        return float(threshold)


@dataclass(frozen=True, slots=True)
class FloorDivide(Fixed):
    """The quantity is whole multiples of ``divisor`` points."""

    divisor: float

    def recover(self, points: Floats) -> Floats:
        return np.floor(np.asarray(points, dtype=np.float64) / self.divisor)

    def points_threshold(self, threshold: float) -> float:
        return float(self.divisor * threshold)


@dataclass(frozen=True, slots=True)
class Ratio:
    """The quantity is a fitted share of the points: ``ratio = sum(Q) / sum(P)``."""

    ratio: float | None = None

    def _ratio(self) -> float:
        if self.ratio is None:
            raise ValueError("Ratio recovery is not fitted")
        return self.ratio

    def recover(self, points: Floats) -> Floats:
        return self._ratio() * np.asarray(points, dtype=np.float64)

    def fit(self, points: Floats, quantity: Floats) -> Ratio:
        total = float(np.sum(points))
        if total <= 0:
            raise ValueError("Ratio recovery needs positive total points")
        return Ratio(float(np.sum(quantity)) / total)

    def points_threshold(self, threshold: float) -> float:
        return float(threshold / self._ratio())


@dataclass(frozen=True, slots=True)
class FromFunction(Fixed):
    """The quantity is any non-decreasing, vectorised ``function`` of the points."""

    function: Callable[[Floats], Floats]

    def recover(self, points: Floats) -> Floats:
        return np.asarray(self.function(np.asarray(points, dtype=np.float64)), dtype=np.float64)

    def points_threshold(self, threshold: float) -> float:
        """The smallest whole number of points reaching ``threshold``, by bisection."""

        def reaches(p: int) -> bool:
            return bool(self.recover(np.array([p], dtype=np.float64))[0] >= threshold)

        if reaches(0):
            return 0.0
        high = 1
        for _ in range(MAX_DOUBLINGS):
            if reaches(high):
                break
            high *= 2
        else:
            raise ValueError(f"no points reach {threshold}")
        low = high // 2
        while high - low > 1:
            mid = (low + high) // 2
            if reaches(mid):
                high = mid
            else:
                low = mid
        return float(high)
