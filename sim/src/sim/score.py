"""An alliance's score drawn around its predicted score."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean

import numpy as np
import numpy.typing as npt
from scipy import optimize, stats

Floats = npt.NDArray[np.float64]
Ints = npt.NDArray[np.int64]

MIN_FIT_PREDICTION = 5.0

# Bounds on intercept, slope, log dispersion, log of dof above 2, and log skew.
FIT_BOUNDS = ((-50.0, 50.0), (0.2, 3.0), (np.log(0.5), np.log(300.0)), (np.log(0.5), np.log(500.0)), (-1.5, 1.5))


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

    def log_density(self, mu: Floats, score: Floats) -> Floats:
        """Log density of each ``score`` around its predicted score, before rounding."""
        scale = self.scale(mu)
        z = (np.asarray(score, dtype=np.float64) - self.location(mu)) / scale
        skewed = np.where(z < 0, z * self.skew, z / self.skew)
        density = stats.t.logpdf(skewed, self.dof) + np.log(2.0 / (self.skew + 1.0 / self.skew)) - np.log(scale)
        return np.asarray(density, dtype=np.float64)


def _from_vector(w: Floats, rows: int = 0) -> ScoreModel:
    return ScoreModel(
        intercept=float(w[0]),
        slope=float(w[1]),
        dispersion=float(np.exp(w[2])),
        dof=2.0 + float(np.exp(w[3])),
        skew=float(np.exp(w[4])),
        rows=rows,
    )


def _to_vector(model: ScoreModel) -> Floats:
    return np.array(
        [model.intercept, model.slope, np.log(model.dispersion), np.log(model.dof - 2.0), np.log(model.skew)]
    )


def fit_score_model(mu: Floats, score: Floats, *, start: ScoreModel | None = None) -> ScoreModel:
    """The model that maximizes the likelihood of these rows, those predicted below ``MIN_FIT_PREDICTION`` left out."""
    keep = np.asarray(mu, dtype=np.float64) > MIN_FIT_PREDICTION
    mu, score = np.asarray(mu, dtype=np.float64)[keep], np.asarray(score, dtype=np.float64)[keep]
    if len(mu) == 0:
        raise ValueError("no rows to fit a score model on")
    first = start or ScoreModel(intercept=0.0, slope=1.0, dispersion=10.0, dof=10.0, skew=1.0)

    def loss(w: Floats) -> float:
        return -float(_from_vector(w).log_density(mu, score).sum())

    w = optimize.minimize(loss, _to_vector(first), method="L-BFGS-B", bounds=FIT_BOUNDS).x
    return _from_vector(w, rows=len(mu))


def provisional_score_model(previous: Sequence[ScoreModel]) -> ScoreModel:
    """The stand-in until a season has enough rows: earlier seasons' models averaged."""
    if not previous:
        raise ValueError("no earlier season's score model to stand in")
    return ScoreModel(
        intercept=fmean(m.intercept for m in previous),
        slope=fmean(m.slope for m in previous),
        dispersion=fmean(m.dispersion for m in previous),
        dof=fmean(m.dof for m in previous),
        skew=fmean(m.skew for m in previous),
        provisional=True,
    )


def resolve_score_model(mu: Floats, score: Floats, *, min_rows: int, previous: Sequence[ScoreModel]) -> ScoreModel:
    """The season's model from its rows so far, or the earlier seasons' until it has ``min_rows``."""
    if len(mu) < min_rows:
        return provisional_score_model(previous)
    return fit_score_model(mu, score, start=provisional_score_model(previous) if previous else None)
