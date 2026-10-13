"""What an event has published so far: its qualification schedule and results, its alliances and its playoff."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

from sim.event import EventProgress
from sim.playoff import Alliance
from sim.schedule import Schedule
from sim.standings import MatchResults, RankingRules
from warehouse.client import ScheduledMatchRow, Warehouse
from warehouse.rules.model import RulePack, to_column_name

ALLIANCES = ("RED", "BLUE")
PLAYOFF = "PLAYOFF"


def published_progress(
    warehouse: Warehouse, event_id: uuid.UUID, pack: RulePack
) -> tuple[Schedule, EventProgress] | None:
    """The event's published schedule and what has been played on it, or None before a schedule is published.

    A qualification match counts as played once both alliances have a final score and a breakdown. Playoff matches
    count once alliances are published.
    """
    rows = warehouse.event_schedule(event_id)
    if not rows:
        return None
    rules = RankingRules.from_pack(pack)
    names = sorted({*rules.bonus_rp, *rules.components})
    breakdowns = warehouse.breakdowns(pack.season, event_id, [to_column_name(n) for n in names])

    played = np.array(
        [r.score is not None and all((r.match_id, a) in breakdowns for a in ALLIANCES) for r in rows], dtype=bool
    )

    def values(name: str) -> npt.NDArray[np.float64]:
        column = to_column_name(name)
        return np.array(
            [[breakdowns.get((r.match_id, a), {}).get(column, 0.0) for a in ALLIANCES] for r in rows],
            dtype=np.float64,
        )

    schedule = Schedule(
        np.array([r.teams for r in rows], dtype=np.int64), np.array([r.surrogate for r in rows], dtype=bool)
    )
    results = MatchResults(
        score=np.array([r.score or (0.0, 0.0) for r in rows], dtype=np.float64),
        bonus={name: values(name) > 0 for name in rules.bonus_rp},
        components={name: values(name) for name in rules.components},
        dq=np.array([r.dq for r in rows], dtype=bool),
    )
    alliances = warehouse.event_alliances(event_id) or None
    decided = None
    if alliances is not None:
        decided = _playoff_winners(warehouse.event_schedule(event_id, level=PLAYOFF), alliances)
    return schedule, EventProgress(played, results, alliances, decided)


def _playoff_winners(rows: Sequence[ScheduledMatchRow], alliances: Sequence[Alliance]) -> dict[tuple[int, int], int]:
    """The winning seed of each decisive playoff game, keyed by series and its place among the series' decisive games.

    A tied game is replayed in the same series, so it is skipped.
    """
    seed_of = {team: seed for seed, alliance in enumerate(alliances, start=1) for team in alliance}
    winners: dict[tuple[int, int], int] = {}
    decisive: dict[int, int] = {}
    for r in sorted(rows, key=lambda r: (r.series, r.match_number)):
        if r.score is None or r.score[0] == r.score[1]:
            continue
        side = r.teams[0] if r.score[0] > r.score[1] else r.teams[1]
        seeds = {seed_of.get(t, 0) for t in side}
        if len(seeds) != 1 or 0 in seeds:
            raise ValueError(f"playoff series {r.series} game {r.match_number}: {side} is not one published alliance")
        decisive[r.series] = decisive.get(r.series, 0) + 1
        winners[(r.series, decisive[r.series])] = seeds.pop()
    return winners
