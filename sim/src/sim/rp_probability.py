"""Bonus ranking point probability."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import fmean

import numpy as np
import numpy.typing as npt
from scipy.optimize import minimize
from scipy.special import ndtr

from warehouse.rules.model import BonusRp, to_column_name

Floats = npt.NDArray[np.float64]

HALF_STEP = 0.5
BUCKETS = 10
LOWEST_CAP_BUCKET_INDEX = 6
CLIP = 1e-9


@dataclass(frozen=True, slots=True)
class RpCurve:
    """A generic model on an alliance's summed RP component EPA to estimate RP probability.

    Requires a point-based RP threshold, and is meant to be a reasonable first aproximation from coarse data.

    Attributes:
        shift: Points added to the summed EPA.
        log_sd: Log of the spread at a summed EPA of zero.
        log_sd_slope: Growth of the log spread per point of summed EPA.
        cap: The highest probability the curve gives.
        rows: Alliance-rows the curve was fitted on.
        provisional: True when earlier seasons stand in.
    """

    shift: float
    log_sd: float
    log_sd_slope: float
    cap: float = 1.0
    rows: int = 0
    provisional: bool = False

    def uncapped(self, epa_sum: Floats, threshold: float | Floats) -> Floats:
        mean = np.asarray(epa_sum, dtype=np.float64) + self.shift
        sd = np.exp(self.log_sd + self.log_sd_slope * np.asarray(epa_sum, dtype=np.float64))
        return np.asarray(ndtr((mean - (np.asarray(threshold, dtype=np.float64) - HALF_STEP)) / sd), dtype=np.float64)

    def probability(self, epa_sum: Floats, threshold: float | Floats) -> Floats:
        """The chance each alliance reaches ``threshold``."""
        return np.minimum(self.uncapped(epa_sum, threshold), self.cap)


def epa_sum(bonus: BonusRp, *teams: Mapping[str, float]) -> float:
    """The alliance's EPA on the components ``bonus`` sums, from each team's EPA components keyed by column name."""
    columns = [to_column_name(name) for name in bonus.sum_of]
    missing = sorted({c for c in columns for team in teams if c not in team})
    if missing:
        raise ValueError(f"{bonus.component}: EPA does not rate {missing}")
    return float(sum(team[c] for team in teams for c in columns))


def log_loss(predicted: Floats, earned: npt.NDArray[np.bool_]) -> float:
    p = np.clip(predicted, CLIP, 1.0 - CLIP)
    return float(-np.mean(np.where(earned, np.log(p), np.log(1.0 - p))))


def top_bucket_cap(predicted: Floats, earned: npt.NDArray[np.bool_], *, min_rows: int) -> float:
    """The earned rate in the highest probability bucket with at least ``min_rows`` rows, or 1 when none has."""
    bucket = np.minimum((predicted * BUCKETS).astype(np.int64), BUCKETS - 1)
    for b in range(BUCKETS - 1, LOWEST_CAP_BUCKET_INDEX - 1, -1):
        rows = bucket == b
        if rows.sum() >= min_rows:
            return float(earned[rows].mean())
    return 1.0


def fit_curve(
    epa_sums: Floats,
    thresholds: Floats,
    earned: npt.NDArray[np.bool_],
    *,
    min_bucket_rows: int,
    start: RpCurve | None = None,
) -> RpCurve:
    """The curve that minimizes log loss on these rows, then its cap from the same rows."""
    if len(epa_sums) == 0:
        raise ValueError("no rows to fit an RP curve on")
    first = start or RpCurve(shift=0.0, log_sd=float(np.log(np.std(epa_sums) + 1.0)), log_sd_slope=0.0)

    def loss(w: Floats) -> float:
        return log_loss(RpCurve(w[0], w[1], w[2]).uncapped(epa_sums, thresholds), earned)

    w = minimize(
        loss, np.array([first.shift, first.log_sd, first.log_sd_slope]), method="Nelder-Mead", options={"maxiter": 4000}
    ).x
    curve = RpCurve(shift=float(w[0]), log_sd=float(w[1]), log_sd_slope=float(w[2]), rows=len(epa_sums))
    cap = top_bucket_cap(curve.uncapped(epa_sums, thresholds), earned, min_rows=min_bucket_rows)
    return RpCurve(curve.shift, curve.log_sd, curve.log_sd_slope, cap=cap, rows=curve.rows)


def provisional_curve(previous: Sequence[RpCurve]) -> RpCurve:
    """The stand-in until a season has enough rows: the average of earlier seasons' curves."""
    if not previous:
        raise ValueError("no earlier season's RP curve to stand in")
    return RpCurve(
        shift=fmean(c.shift for c in previous),
        log_sd=fmean(c.log_sd for c in previous),
        log_sd_slope=fmean(c.log_sd_slope for c in previous),
        cap=fmean(c.cap for c in previous),
        provisional=True,
    )


def resolve_curve(
    epa_sums: Floats,
    thresholds: Floats,
    earned: npt.NDArray[np.bool_],
    *,
    min_rows: int,
    min_bucket_rows: int,
    previous: Sequence[RpCurve],
) -> RpCurve:
    """The season's curve from its rows so far, or the earlier seasons' until it has ``min_rows``."""
    if len(epa_sums) < min_rows:
        return provisional_curve(previous)
    return fit_curve(epa_sums, thresholds, earned, min_bucket_rows=min_bucket_rows)
