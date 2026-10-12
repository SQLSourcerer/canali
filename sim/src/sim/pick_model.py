"""How likely a captain is to pick each team still available."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy import optimize

Floats = npt.NDArray[np.float64]

PICK_FEATURES = ("predictor_z", "rank_pct", "captain_x_rank", "partner", "allied_before", "same_city", "team_age")


@dataclass(frozen=True, slots=True)
class PickModel:
    """How much each trait raises a team's chance of being picked.

    Attributes:
        coefficients: The weight on each trait, in ``PICK_FEATURES`` order.
        decisions: Picks the model was fitted on.
        seasons: Seasons the picks came from.
    """

    coefficients: tuple[float, ...]
    decisions: int = 0
    seasons: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if len(self.coefficients) != len(PICK_FEATURES):
            raise ValueError(f"{len(self.coefficients)} coefficients for {len(PICK_FEATURES)} features")

    def probabilities(self, features: Floats) -> Floats:
        """The chance the captain picks each candidate, from features shaped ``(candidate, feature)``."""
        eta = np.asarray(features, dtype=np.float64) @ np.asarray(self.coefficients)
        weights = np.exp(eta - eta.max())
        return np.asarray(weights / weights.sum(), dtype=np.float64)


def fit_coefficients(features: Sequence[Floats], chosen: Sequence[int]) -> Floats:
    """The weights, one per trait, under which the picks that happened were most likely."""
    if not features:
        raise ValueError("no picks to fit a pick model on")
    x = np.vstack(features).astype(np.float64)
    sizes = np.array([len(f) for f in features])
    starts = np.r_[0, np.cumsum(sizes)[:-1]]
    picked = starts + np.asarray(chosen)

    def loss(b: Floats) -> tuple[float, Floats]:
        eta = x @ b
        peak = np.maximum.reduceat(eta, starts)
        weights = np.exp(eta - np.repeat(peak, sizes))
        total = np.add.reduceat(weights, starts)
        p = weights / np.repeat(total, sizes)
        expected = np.add.reduceat(p[:, None] * x, starts)
        nll = -float(np.sum(eta[picked] - np.log(total) - peak))
        return nll, -(x[picked] - expected).sum(axis=0)

    return np.asarray(optimize.minimize(loss, np.zeros(x.shape[1]), jac=True, method="BFGS").x, dtype=np.float64)
