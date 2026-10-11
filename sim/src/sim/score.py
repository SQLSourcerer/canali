"""An alliance's score drawn around its predicted score."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

Floats = npt.NDArray[np.float64]
Ints = npt.NDArray[np.int64]


@dataclass(frozen=True, slots=True)
class ScoreModel:
    """A skewed Student-t on an alliance's score, its variance proportional to the predicted score.

    ``score = intercept + slope * mu + sqrt(dispersion * mu) * e``, with ``e`` a Fernandez-Steel skewed t, rounded to
    whole points and floored at zero. The two alliances of a match are drawn independently.

    Attributes:
        intercept: Points added to every alliance's location.
        slope: Location per predicted point.
        dispersion: Variance per predicted point.
        dof: Degrees of freedom of the t.
        skew: Ratio of the right tail's scale to the left's; 1 is symmetric.
        rows: Alliance-rows the model was fitted on.
        provisional: True when earlier seasons stand in.
    """

    intercept: float
    slope: float
    dispersion: float
    dof: float
    skew: float
    rows: int = 0
    provisional: bool = False

    def location(self, mu: Floats) -> Floats:
        return self.intercept + self.slope * np.asarray(mu, dtype=np.float64)

    def scale(self, mu: Floats) -> Floats:
        return np.sqrt(self.dispersion * np.maximum(np.asarray(mu, dtype=np.float64), 0.0))

    def standard(self, shape: tuple[int, ...], rng: np.random.Generator) -> Floats:
        """Standard skewed-t draws: positive with probability ``skew**2 / (1 + skew**2)``, stretched by ``skew``."""
        magnitude = np.abs(rng.standard_t(self.dof, shape))
        right = rng.random(shape) < self.skew**2 / (1.0 + self.skew**2)
        return np.where(right, magnitude * self.skew, -magnitude / self.skew)

    def sample(self, mu: Floats, rng: np.random.Generator) -> Ints:
        """One whole-point score per predicted score in ``mu``."""
        mu = np.asarray(mu, dtype=np.float64)
        score = self.location(mu) + self.scale(mu) * self.standard(mu.shape, rng)
        return np.maximum(np.rint(score), 0.0).astype(np.int64)
