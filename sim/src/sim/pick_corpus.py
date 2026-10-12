"""Alliance selection: one decision per pick, over the teams still available.

Covers every rated event with a selection, ranked by its published qualification rankings. An event is left out when
it has no rankings, a team lacks a rating, or the rankings do not reproduce its captains.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
import numpy.typing as npt

from sim.predictor import Predictor
from warehouse.client import AlliancePickRow, EventRow, MatchRow, TeamSeasonRow, Warehouse
from warehouse.tier import tier_for

Floats = npt.NDArray[np.float64]

PICK_FEATURES = ("predictor_z", "rank_pct", "captain_x_rank", "partner", "allied_before", "same_city", "team_age")


@dataclass(frozen=True, slots=True)
class PickDecision:
    """Pick once from available teams.

    Attributes:
        event_id: The event.
        event_date: The event's first day.
        captain: The picking captain.
        candidates: Teams the captain could pick.
        chosen: Index of the picked team in ``candidates``.
        features: Each candidate's values in ``PICK_FEATURES`` order, shaped ``(candidate, feature)``.
    """

    event_id: uuid.UUID
    event_date: date
    captain: int
    candidates: tuple[int, ...]
    chosen: int
    features: Floats


def pick_decisions(
    warehouse: Warehouse, season: int, predictor: Predictor, *, before: date | None
) -> list[PickDecision]:
    """Every pick at rated events that started before ``before``, or the whole season when None."""
    events = [
        (e, e.date_start)
        for e in warehouse.events(season)
        if e.date_start is not None and (before is None or e.date_start < before)
    ]
    picks: dict[uuid.UUID, list[AlliancePickRow]] = defaultdict(list)
    for pick in warehouse.alliance_picks(season):
        picks[pick.event_id].append(pick)
    ranks = warehouse.ranks(season)
    ratings = predictor.qualification_end(warehouse, season, before=before)
    teams = warehouse.team_seasons(season)
    history = [(start, _alliances(picks[e.event_id])) for e, start in events if picks.get(e.event_id)]

    decisions: list[PickDecision] = []
    for event, event_start in events:
        rank = ranks.get(event.event_id)
        if tier_for(event.event_type) is None or not picks.get(event.event_id) or not rank:
            continue
        if any((event.event_id, t) not in ratings for t in rank):
            continue
        matches = warehouse.event_matches(event.event_id)
        allied: dict[int, set[int]] = defaultdict(set)
        for start, alliances in history:
            if start < event_start:
                for members in alliances:
                    for t in members:
                        allied[t] |= members - {t}
        decisions += _event_decisions(
            event,
            event_start,
            picks[event.event_id],
            rank=rank,
            matches=matches,
            ratings=ratings,
            teams=teams,
            allied=allied,
            season=season,
        )
    return decisions


def _alliances(picks: Sequence[AlliancePickRow]) -> list[set[int]]:
    members: dict[int, set[int]] = defaultdict(set)
    for p in picks:
        if p.action in ("CAPTAIN", "ACCEPT") and p.alliance_number is not None:
            members[p.alliance_number].add(p.team_number)
    return list(members.values())


def _event_decisions(
    event: EventRow,
    event_start: date,
    picks: Sequence[AlliancePickRow],
    *,
    rank: dict[int, int],
    matches: Sequence[MatchRow],
    ratings: dict[tuple[uuid.UUID, int], float],
    teams: dict[int, TeamSeasonRow],
    allied: dict[int, set[int]],
    season: int,
) -> list[PickDecision]:
    """The event's picks, or none when its ranks do not reproduce its captains."""
    field = sorted(rank, key=rank.__getitem__)
    n = len(field)
    rating = np.array([ratings[(event.event_id, t)] for t in field])
    predictor_z = dict(zip(field, (rating - rating.mean()) / (rating.std() or 1.0), strict=True))
    rank_pct = {t: 1.0 - (r - 1) / max(n - 1, 1) for t, r in rank.items()}
    partners: dict[int, set[int]] = defaultdict(set)
    for m in matches:
        for t in m.team_numbers:
            partners[t] |= set(m.team_numbers) - {t}

    def city(t: int) -> str | None:
        return teams[t].city if t in teams else None

    def age(t: int) -> float:
        rookie = teams[t].rookie_year if t in teams else None
        return float(season - rookie) if rookie is not None else 0.0

    captains: list[int] = []
    captain_of: dict[int, int] = {}
    taken: set[int] = set()
    declined: set[int] = set()
    found: list[tuple[int, list[int], int]] = []
    for p in picks:
        if p.action == "REMOVE":
            taken.add(p.team_number)
        elif p.action == "DECLINE":
            declined.add(p.team_number)
        elif p.action == "CAPTAIN":
            free = [t for t in field if t not in taken and t not in captains]
            if not free or p.team_number != min(free, key=rank.__getitem__):
                return []
            captains.append(p.team_number)
            if p.alliance_number is not None:
                captain_of[p.alliance_number] = p.team_number
        elif p.action == "ACCEPT":
            captain = captain_of.get(p.alliance_number) if p.alliance_number is not None else None
            pool = [t for t in field if t not in taken and t not in declined and t not in captains]
            if captain is not None and p.team_number in pool and len(pool) > 1:
                found.append((captain, pool, p.team_number))
            taken.add(p.team_number)

    decisions = []
    for captain, pool, chosen in found:
        features = np.array(
            [
                [
                    predictor_z[t],
                    rank_pct[t],
                    rank_pct[captain] * rank_pct[t],
                    float(t in partners[captain]),
                    float(t in allied[captain]),
                    float(city(t) is not None and city(t) == city(captain)),
                    age(t),
                ]
                for t in pool
            ]
        )
        decisions.append(PickDecision(event.event_id, event_start, captain, tuple(pool), pool.index(chosen), features))
    return decisions
