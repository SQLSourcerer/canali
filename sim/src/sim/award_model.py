"""How likely each team is to win a judged award."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from sim.conditional_logit import choice_probabilities
from warehouse.tier import EventTier

Floats = npt.NDArray[np.float64]

AWARD_NAMES: Mapping[int, str] = {
    1: "JudgesChoice",
    3: "Promote",
    4: "Control",
    5: "Motivate",
    6: "Design",
    7: "Innovate",
    8: "Connect",
    9: "Think",
    11: "Inspire",
    25: "Reach",
    26: "Sustain",
}
INSPIRE = "Inspire"
MODELLED_AWARDS = ("Inspire", "Think", "Connect", "Reach", "Sustain", "Design", "Innovate", "Control")
MACHINE_AWARDS = frozenset({"Design", "Control", "Innovate"})
TEAM_ATTRIBUTE_AWARDS = frozenset({"Connect", "Think", "JudgesChoice", "Reach", "Sustain", "Motivate", "Promote"})

INSPIRE_PLACED = "InspirePlaced"

# Awards fitted per tier; every other award has one model across tiers.
TIER_SPLIT_AWARDS = frozenset({INSPIRE})

HISTORY_DECAY = 0.6

AWARD_TRAITS = (
    "predictor_z",
    "predictor_auto_z",
    "own_history",
    "other_history",
    "machine_history",
    "team_attribute_history",
    "inspire_history",
    "team_age",
    "rookie",
    "captain",
    "first_pick",
    "seed_score",
)

_SELECTION = ("team_age", "rookie", "captain", "first_pick", "seed_score")
AWARD_TERMS: Mapping[str, tuple[str, ...]] = {
    "Inspire": ("predictor_z", "predictor_auto_z", "inspire_history", "other_history", *_SELECTION),
    "Think": ("predictor_z", "inspire_history", "own_history", "other_history", *_SELECTION),
    "Connect": ("inspire_history", "own_history", "other_history", *_SELECTION),
    "Reach": ("team_attribute_history", "other_history", *_SELECTION),
    "Sustain": ("team_attribute_history", "other_history", *_SELECTION),
    "Design": ("predictor_z", "machine_history", "own_history", "inspire_history", *_SELECTION),
    "Innovate": ("predictor_z", "machine_history", "own_history", "inspire_history", *_SELECTION),
    "Control": (
        "predictor_z",
        "predictor_auto_z",
        "machine_history",
        "own_history",
        "inspire_history",
        *_SELECTION,
    ),
}


@dataclass(frozen=True, slots=True)
class AwardModel:
    """How much each trait raises a team's chance of an award.

    Attributes:
        award: The award's name.
        coefficients: The weight on each of the award's ``AWARD_TERMS``.
        stage: The tier the model is for, or None for every tier.
        decisions: Winners the model was fitted on.
        seasons: Seasons the winners came from.
    """

    award: str
    coefficients: tuple[float, ...]
    stage: EventTier | None = None
    decisions: int = 0
    seasons: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        terms = AWARD_TERMS[self.award]
        if len(self.coefficients) != len(terms):
            raise ValueError(f"{self.award}: {len(self.coefficients)} coefficients for {len(terms)} terms")

    def probabilities(self, features: Floats) -> Floats:
        """Each candidate's chance of the award, from features in ``AWARD_TRAITS`` order."""
        return choice_probabilities(np.asarray(features)[:, term_columns(self.award)], self.coefficients)


def model_for(models: Sequence[AwardModel], award: str, stage: EventTier) -> AwardModel:
    """The model for ``award`` at ``stage``, its tier's own if it has one."""
    fitted = [m for m in models if m.award == award and m.stage in {stage, None}]
    if not fitted:
        raise KeyError(f"no {award} model for {stage.name}")
    return min(fitted, key=lambda m: m.stage is None)


def term_columns(award: str) -> list[int]:
    """Where each of the award's terms sits in ``AWARD_TRAITS``."""
    return [AWARD_TRAITS.index(t) for t in AWARD_TERMS[award]]


@dataclass(frozen=True, slots=True)
class AwardField:
    """An event's teams with award relevant attributes once alliances are selected.

    Attributes:
        teams: Team numbers.
        rating: Each team's predicted points once qualification is over.
        auto_rating: The autonomous part of ``rating``.
        history: Each team's decayed first places per award, and Inspire placings under ``INSPIRE_PLACED``.
        team_age: Each team's seasons since its rookie year.
        rookie: Teams in their rookie season.
        alliances: Playoff alliances in seed order, captain first.
    """

    teams: tuple[int, ...]
    rating: Floats
    auto_rating: Floats
    history: Mapping[int, Mapping[str, float]]
    team_age: Mapping[int, float]
    rookie: frozenset[int]
    alliances: Sequence[tuple[int, ...]]

    def features(self, award: str, candidates: Sequence[int]) -> Floats:
        """Each candidate's traits for ``award`` in ``AWARD_TRAITS`` order, shaped ``(candidate, trait)``."""
        index = {t: i for i, t in enumerate(self.teams)}
        z = _z(self.rating)
        auto_z = _z(self.auto_rating)
        seat: dict[int, tuple[int, int]] = {
            t: (seed, slot) for seed, alliance in enumerate(self.alliances) for slot, t in enumerate(alliance)
        }
        spread = max(len(self.alliances) - 1, 1)
        rows = []
        for t in candidates:
            h = self.history.get(t, {})
            total = sum(v for k, v in h.items() if k != INSPIRE_PLACED)
            seed, slot = seat.get(t, (-1, -1))
            rows.append(
                [
                    z[index[t]],
                    auto_z[index[t]],
                    h.get(award, 0.0),
                    total - h.get(award, 0.0),
                    sum(h.get(a, 0.0) for a in MACHINE_AWARDS - {award}),
                    sum(h.get(a, 0.0) for a in TEAM_ATTRIBUTE_AWARDS - {award}),
                    h.get(INSPIRE_PLACED, 0.0),
                    self.team_age.get(t, 0.0),
                    float(t in self.rookie),
                    float(slot == 0),
                    float(slot == 1),
                    1.0 - seed / spread if seed >= 0 else 0.0,
                ]
            )
        return np.array(rows, dtype=np.float64)


def _z(values: Floats) -> Floats:
    return np.asarray((values - values.mean()) / (values.std() or 1.0), dtype=np.float64)
