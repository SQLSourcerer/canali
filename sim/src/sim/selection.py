"""Alliance selection."""

from __future__ import annotations

import numpy as np

from sim.pick_model import PickField, PickModel
from sim.playoff import Alliance
from warehouse.rules.model import Structure
from warehouse.tier import EventTier, tier_for

ALLIANCE_SIZE = 2
CMP_ALLIANCE_SIZE = 3


def alliance_count(structure: Structure, n_teams: int) -> int:
    """Number of playoff alliances for a field, from the rule pack's recommended brackets."""
    for bracket in structure.alliance_brackets:
        if bracket.min_teams <= n_teams <= bracket.max_teams:
            return bracket.alliances
    raise ValueError(f"no alliance bracket covers a {n_teams}-team field")


def alliance_size(event_type: str | None) -> int:
    """Teams per alliance: three at FIRST Championship, two everywhere else."""
    return CMP_ALLIANCE_SIZE if tier_for(event_type) is EventTier.CMP else ALLIANCE_SIZE


def select_alliances(
    field: PickField, model: PickModel, n_alliances: int, size: int, rng: np.random.Generator
) -> list[Alliance]:
    """The alliances in seed order.

    Each captain is the best-ranked team not yet on an alliance and picks with the model. Secon round picks in reverse
    seed order.
    """
    if n_alliances * size > len(field.teams):
        raise ValueError(f"{n_alliances} alliances of {size} need more than {len(field.teams)} teams")
    taken: set[int] = set()

    def pick(captain: int) -> int:
        pool = [t for t in field.teams if t not in taken]
        team = pool[rng.choice(len(pool), p=model.probabilities(field.features(captain, pool)))]
        taken.add(team)
        return team

    alliances: list[list[int]] = []
    for _ in range(n_alliances):
        captain = next(t for t in field.teams if t not in taken)
        taken.add(captain)
        alliances.append([captain, pick(captain)])
    for _ in range(size - ALLIANCE_SIZE):
        for alliance in reversed(alliances):
            alliance.append(pick(alliance[0]))
    return [tuple(a) for a in alliances]
