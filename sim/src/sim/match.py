"""Qualification matches drawn from a season's models.

Each alliance takes one latent normal draw. Its no-foul score is the score model's quantile there, each bonus RP is
linked to it by the RP curve's correlation, and the tiebreakers are fixed shares of the no-foul score. The official
score adds the foul points each alliance receives, from the score model. The two alliances are drawn independently.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.special import ndtr

from sim.rp_probability import RpCurve, draw_bonus
from sim.rp_source import rp_sources
from sim.score import ScoreModel
from sim.standings import MatchResults
from warehouse.rules.model import RulePack, to_column_name

Floats = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class SeasonModels:
    """What a season's sim plays its matches with.

    Attributes:
        score: The no-foul score and the foul points.
        rp_curves: Each bonus RP's curve, keyed by rule-pack component.
        tiebreaker_shares: Each tiebreaker component as a share of the no-foul score, keyed by rule-pack name.
    """

    score: ScoreModel
    rp_curves: dict[str, RpCurve]
    tiebreaker_shares: dict[str, float]


def draw_matches(
    models: SeasonModels,
    pack: RulePack,
    predicted: Mapping[str, Floats],
    event_type: str | None,
    rng: np.random.Generator,
) -> MatchResults:
    """One draw of every match, from each alliance's predicted points per component keyed by column name.

    Every predicted array is shaped ``(match, alliance)``, and their sum is the alliance's predicted score.
    """
    total = np.sum([np.asarray(p, dtype=np.float64) for p in predicted.values()], axis=0)
    latent = rng.standard_normal(total.shape)
    no_foul = models.score.whole_points(models.score.quantile(total, ndtr(latent))).astype(np.float64)
    fouls = models.score.foul_points(total.shape, rng)

    sources = rp_sources(pack)
    probabilities = {}
    for bonus in pack.ranking.bonus_rp:
        columns = [to_column_name(name) for name in sources[bonus.component].points_from]
        missing = sorted(set(columns) - set(predicted))
        if missing:
            raise ValueError(f"{bonus.component}: predictions lack {missing}")
        points = np.sum([np.asarray(predicted[c], dtype=np.float64) for c in columns], axis=0)
        probabilities[bonus.component] = models.rp_curves[bonus.component].probability(
            points, bonus.threshold(event_type)
        )
    earned = draw_bonus(
        probabilities,
        sources,
        rng,
        latent=latent,
        correlations={component: curve.correlation for component, curve in models.rp_curves.items()},
    )

    return MatchResults(
        score=no_foul + fouls,
        bonus=earned,
        components={name: share * no_foul for name, share in models.tiebreaker_shares.items()},
    )
