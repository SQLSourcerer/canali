"""What an event has published so far: its qualification schedule and results, its alliances, its playoff, and each
team's ratings as of the same match."""

from __future__ import annotations

import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from sim.event import EventProgress
from sim.playoff import Alliance
from sim.predictor import Predictor
from sim.schedule import Schedule
from sim.standings import MatchResults, RankingRules
from warehouse.client import ScheduledMatchRow, Warehouse
from warehouse.rules.model import RulePack, to_column_name

ALLIANCES = ("RED", "BLUE")
PLAYOFF = "PLAYOFF"


@dataclass(frozen=True, slots=True)
class PublishedEvent:
    """An event as published through one match, and each team's ratings as they stood after it.

    Attributes:
        as_of_match: The event's matches played so far, as the warehouse orders them: qualification, then playoff.
        ratings: Each team's predicted points per component after those matches, keyed by team, then column name.
        schedule: The qualification schedule, None before one is published.
        progress: What has been played on it, None before a schedule is published.
    """

    as_of_match: int
    ratings: dict[int, dict[str, float]]
    schedule: Schedule | None = None
    progress: EventProgress | None = None


def published_event(
    warehouse: Warehouse,
    event_id: uuid.UUID,
    pack: RulePack,
    predictor: Predictor,
    *,
    through: int | None = None,
) -> PublishedEvent:
    """The event's schedule, results and ratings as of its latest played match, or its first ``through`` matches.

    A match's place in the event counts its scored matches, qualification first. A qualification match counts as
    played once both alliances have a final score and a breakdown. Playoff matches count once alliances are published
    and every qualification match is within ``through``.
    """
    limit = through if through is not None else sys.maxsize
    rows = warehouse.event_schedule(event_id)
    if not rows:
        return PublishedEvent(0, predictor.event_ratings(warehouse, pack.season, event_id, through=0))
    rules = RankingRules.from_pack(pack)
    names = sorted({*rules.bonus_rp, *rules.components})
    breakdowns = warehouse.breakdowns(pack.season, event_id, [to_column_name(n) for n in names])

    ordinal = _ordinals(rows)
    played = np.array(
        [
            r.score is not None and ordinal[i] <= limit and all((r.match_id, a) in breakdowns for a in ALLIANCES)
            for i, r in enumerate(rows)
        ],
        dtype=bool,
    )
    as_of = max((ordinal[i] for i in range(len(rows)) if played[i]), default=0)

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

    alliances = None
    decided = None
    if all(o <= limit for o in ordinal.values()) and len(ordinal) == len(rows):
        alliances = warehouse.event_alliances(event_id) or None
    if alliances is not None:
        playoff = [r for r in warehouse.event_schedule(event_id, level=PLAYOFF) if r.score is not None]
        playoff.sort(key=lambda r: (r.series, r.match_number))
        playoff = [r for n, r in enumerate(playoff, start=len(ordinal) + 1) if n <= limit]
        decided = _playoff_winners(playoff, alliances)
        as_of = max(as_of, len(ordinal) + len(playoff))

    return PublishedEvent(
        as_of_match=as_of,
        ratings=predictor.event_ratings(warehouse, pack.season, event_id, through=as_of),
        schedule=schedule,
        progress=EventProgress(played, results, alliances, decided),
    )


def _ordinals(rows: Sequence[ScheduledMatchRow]) -> dict[int, int]:
    """Each scored qualification match's place among the event's scored matches, keyed by its row."""
    scored = sorted((i for i, r in enumerate(rows) if r.score is not None), key=lambda i: rows[i].match_number)
    return {i: n for n, i in enumerate(scored, start=1)}


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
