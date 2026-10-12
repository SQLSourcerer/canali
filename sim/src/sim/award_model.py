"""How likely each team is to win a judged award."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

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
