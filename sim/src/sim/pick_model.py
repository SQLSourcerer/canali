"""How likely a captain is to pick each team still available."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from sim.conditional_logit import choice_probabilities

Floats = npt.NDArray[np.float64]

PICK_FEATURES = ("predictor_z", "rank_pct", "captain_x_rank", "partner", "allied_before", "same_city", "team_age")

TEAM_AGE_CAP = 3.0


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
        return choice_probabilities(features, self.coefficients)


@dataclass(frozen=True, slots=True)
class PickField:
    """An event's teams with alliance selection relavent attributes in qualification rank order.

    Attributes:
        teams: Team numbers.
        rating: Each team's predicted points once qualification is over.
        partners: Each team's qualification partners.
        allied: Each team's alliance partners at earlier events this season.
        city: Each team's city, None when unknown.
        team_age: Each team's seasons since its rookie year.
    """

    teams: tuple[int, ...]
    rating: Floats
    partners: Mapping[int, frozenset[int]]
    allied: Mapping[int, frozenset[int]]
    city: Mapping[int, str | None]
    team_age: Mapping[int, float]

    def features(self, captain: int, candidates: Sequence[int]) -> Floats:
        """Each candidate's traits for this captain in ``PICK_FEATURES`` order, shaped ``(candidate, feature)``."""
        index = {t: i for i, t in enumerate(self.teams)}
        z = (self.rating - self.rating.mean()) / (self.rating.std() or 1.0)
        rank_pct = 1.0 - np.arange(len(self.teams)) / max(len(self.teams) - 1, 1)
        partners = self.partners.get(captain, frozenset())
        allied = self.allied.get(captain, frozenset())
        city = self.city.get(captain)
        return np.array(
            [
                [
                    z[index[t]],
                    rank_pct[index[t]],
                    rank_pct[index[captain]] * rank_pct[index[t]],
                    float(t in partners),
                    float(t in allied),
                    float(city is not None and self.city.get(t) == city),
                    min(self.team_age.get(t, 0.0), TEAM_AGE_CAP),
                ]
                for t in candidates
            ],
            dtype=np.float64,
        )
