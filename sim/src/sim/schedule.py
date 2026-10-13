"""The qualification schedule an event plays."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations

import numpy as np
import numpy.typing as npt

RED = 0
BLUE = 1
STATIONS_PER_MATCH = 4


@dataclass(frozen=True, slots=True)
class Schedule:
    """A qualification schedule.

    Attributes:
        stations: Team at each station, shaped ``(match, alliance, station)``.
        surrogate: True if the appearance is a surrogate's.
    """

    stations: npt.NDArray[np.int64]
    surrogate: npt.NDArray[np.bool_]

    def __post_init__(self) -> None:
        if self.stations.ndim != 3 or self.stations.shape[1] != 2:
            raise ValueError(f"stations must be shaped (match, alliance, station), got {self.stations.shape}")
        if self.surrogate.shape != self.stations.shape:
            raise ValueError(f"surrogate is shaped {self.surrogate.shape}, stations {self.stations.shape}")

    @property
    def n_matches(self) -> int:
        return int(self.stations.shape[0])


# A team plays at most one surrogate match, and it is always the team's 3rd.
SURROGATE_APPEARANCE = 3
SHAPE_SWEEPS = 200


def generated_schedule(
    teams: Sequence[int], matches_per_team: int, rng: np.random.Generator, *, seed: int = 0
) -> Schedule:
    """A schedule for a field without a published one: ``teams`` shuffled into the shape for its size.

    Each team plays ``matches_per_team`` counted matches. The last match is filled out with surrogate appearances,
    each by a different team.
    """
    stations, surrogate = _shape(len(teams), matches_per_team, seed)
    order = rng.permutation(np.asarray(teams, dtype=np.int64))
    return Schedule(order[stations], surrogate.copy())


@lru_cache(maxsize=256)
def _shape(n_teams: int, matches_per_team: int, seed: int) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.bool_]]:
    """Slot indices at each station, and which appearances are surrogates, for one field size.

    Any relabelling of a valid shape is valid, so one shape serves every field of this size.
    """
    if n_teams < STATIONS_PER_MATCH or matches_per_team > n_teams - STATIONS_PER_MATCH + 1:
        raise ValueError(f"{matches_per_team} matches per team can't be scheduled for {n_teams} teams")
    rng = np.random.default_rng(seed)
    n_matches = -(-n_teams * matches_per_team // STATIONS_PER_MATCH)
    extra = n_matches * STATIONS_PER_MATCH - n_teams * matches_per_team
    pool = np.r_[np.repeat(np.arange(n_teams), matches_per_team), rng.choice(n_teams, extra, replace=False)]
    grid = _spread(rng.permutation(pool).reshape(n_matches, STATIONS_PER_MATCH), rng)

    surrogate = np.zeros(grid.shape, dtype=bool)
    seen = np.zeros(n_teams, dtype=np.int64)
    for m, j in np.ndindex(grid.shape):
        seen[grid[m, j]] += 1
        surrogate[m, j] = grid[m, j] in pool[n_teams * matches_per_team :] and seen[grid[m, j]] == SURROGATE_APPEARANCE
    shape = (n_matches, 2, STATIONS_PER_MATCH // 2)
    return grid.reshape(shape).astype(np.int64), surrogate.reshape(shape)


def _spread(grid: npt.NDArray[np.int64], rng: np.random.Generator) -> npt.NDArray[np.int64]:
    """Swap slots between matches until no team is in a match twice, preferring fewer repeat partners, then fewer
    repeat meetings."""
    half = grid.shape[1] // 2

    def cost(rows: npt.NDArray[np.int64]) -> int:
        repeats = sum(len(r) - len(set(r.tolist())) for r in rows)
        partners = Counter(tuple(sorted(r[i : i + half].tolist())) for r in rows for i in (0, half))
        meetings = Counter(tuple(sorted(p)) for r in rows for p in combinations(r.tolist(), 2))
        return 1000 * repeats + 10 * sum(c - 1 for c in partners.values()) + sum(c - 1 for c in meetings.values())

    best = cost(grid)
    n_matches, width = grid.shape
    for _ in range(SHAPE_SWEEPS * n_matches):
        a, b = rng.choice(n_matches, 2, replace=False)
        i, j = rng.integers(width, size=2)
        grid[a, i], grid[b, j] = grid[b, j], grid[a, i]
        trial = cost(grid)
        if trial <= best:
            best = trial
        else:
            grid[a, i], grid[b, j] = grid[b, j], grid[a, i]
    if best >= 1000:
        raise ValueError("couldn't place every team in distinct matches")
    return grid
