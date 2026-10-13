"""Judged awards: one decision per award's winner, plus Inspire's 2nd and 3rd places, over the eligible teams."""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
import numpy.typing as npt

from sim.award_model import (
    AUTO_PREFIX,
    AWARD_NAMES,
    HISTORY_DECAY,
    INSPIRE,
    INSPIRE_PLACED,
    MODELLED_AWARDS,
    TIER_SPLIT_AWARDS,
    AwardField,
    AwardModel,
    term_columns,
)
from sim.conditional_logit import fit_coefficients
from sim.predictor import Predictor
from warehouse.client import AwardRow, EventRow, Warehouse
from warehouse.tier import EventTier, tier_for

Floats = npt.NDArray[np.float64]

HISTORY_FROM = 2022

INSPIRE_EXCLUSIVE_FROM = 2024

MIN_FIELD = 4
MIN_POOL = 3
STAGES = (EventTier.REGULAR, EventTier.RCMP)


@dataclass(frozen=True, slots=True)
class AwardDecision:
    """Place one team for an award from eligible teams.

    Attributes:
        event_id: The event.
        event_date: The event's first day.
        season: The event's season.
        stage: The event's tier.
        award: The award's name.
        place: 1 for the winner, then 2 and 3 for Inspire.
        candidates: Teams eligible for this place.
        chosen: Index of the placed team in ``candidates``.
        features: Each candidate's values in ``award_model.AWARD_TRAITS`` order, shaped ``(candidate, trait)``.
    """

    event_id: uuid.UUID
    event_date: date
    season: int
    stage: EventTier
    award: str
    place: int
    candidates: tuple[int, ...]
    chosen: int
    features: Floats


@dataclass(frozen=True, slots=True)
class Placing:
    """One team's place in one award at a rated event."""

    start: date
    season: int
    team: int
    award: str
    place: int


def placings_by_team(warehouse: Warehouse, season: int) -> dict[int, list[Placing]]:
    """Every modelled award placing at rated events from ``HISTORY_FROM`` through ``season``, by team."""
    by_team: dict[int, list[Placing]] = defaultdict(list)
    for s in range(HISTORY_FROM, season + 1):
        dated = {e.event_id: e for e in warehouse.events(s) if e.date_start is not None}
        for a in warehouse.awards(s):
            event = dated.get(a.event_id)
            if event is None or a.award_code not in AWARD_NAMES or tier_for(event.event_type) is None:
                continue
            assert event.date_start is not None
            award = AWARD_NAMES[a.award_code]
            by_team[a.team_number].append(Placing(event.date_start, s, a.team_number, award, a.place))
    return by_team


def award_decisions(warehouse: Warehouse, season: int, predictor: Predictor) -> list[AwardDecision]:
    """Every modelled award winner and Inspire place at a season's REGULAR and RCMP events."""
    by_team = placings_by_team(warehouse, season)
    dated = {e.event_id: e for e in warehouse.events(season) if e.date_start is not None}
    events = list(dated.values())
    by_event: dict[uuid.UUID, list[AwardRow]] = defaultdict(list)
    for a in warehouse.awards(season):
        if a.event_id in dated and a.award_code in AWARD_NAMES:
            by_event[a.event_id].append(a)
    ratings = predictor.qualification_end(warehouse, season, before=None)
    teams = warehouse.team_seasons(season)
    seats: dict[uuid.UUID, dict[int, list[tuple[str, int]]]] = defaultdict(lambda: defaultdict(list))
    for slot in warehouse.alliances(season):
        seats[slot.event_id][slot.seed].append((slot.role, slot.team_number))

    decisions: list[AwardDecision] = []
    for event in events:
        stage = tier_for(event.event_type)
        if stage not in STAGES or not by_event.get(event.event_id):
            continue
        assert stage is not None and event.date_start is not None
        field = tuple(sorted({t for m in warehouse.event_matches(event.event_id) for t in m.team_numbers}))
        if len(field) < MIN_FIELD or any((event.event_id, t) not in ratings for t in field):
            continue
        components = [ratings[(event.event_id, t)] for t in field]
        role_order = {"captain": 0, "round1": 1, "round2": 2}
        award_field = AwardField(
            teams=field,
            rating=np.array([sum(c.values()) for c in components]),
            auto_rating=np.array([sum(v for k, v in c.items() if k.startswith(AUTO_PREFIX)) for c in components]),
            history=decayed_history(by_team, field, season, event.date_start),
            rookie=frozenset(t for t in field if t in teams and teams[t].rookie_year == season),
            alliances=[
                tuple(t for _, t in sorted(members, key=lambda m: role_order[m[0]]))
                for _, members in sorted(seats[event.event_id].items())
            ],
        )
        inspire_won_before = {
            t
            for t in field
            for p in by_team.get(t, ())
            if p.season == season and p.award == INSPIRE and p.place == 1 and p.start < event.date_start
        }
        decisions += _event_decisions(
            event, stage, season, by_event[event.event_id], field=award_field, inspire_won_before=inspire_won_before
        )
    return decisions


def measure_award_models(warehouse: Warehouse, seasons: Sequence[int], predictor: Predictor) -> list[AwardModel]:
    """One model per modelled award, or per award and tier for ``TIER_SPLIT_AWARDS``, fitted on every first place of
    ``seasons`` pooled."""
    winners = [d for s in seasons for d in award_decisions(warehouse, s, predictor) if d.place == 1]
    models: list[AwardModel] = []
    for award in MODELLED_AWARDS:
        stages: tuple[EventTier | None, ...] = STAGES if award in TIER_SPLIT_AWARDS else (None,)
        for stage in stages:
            fitted = [d for d in winners if d.award == award and stage in {d.stage, None}]
            if not fitted:
                continue
            columns = term_columns(award)
            coefficients = fit_coefficients([d.features[:, columns] for d in fitted], [d.chosen for d in fitted])
            models.append(
                AwardModel(
                    award,
                    tuple(float(c) for c in coefficients),
                    stage=stage,
                    decisions=len(fitted),
                    seasons=tuple(sorted({d.season for d in fitted})),
                )
            )
    return models


def decayed_history(
    by_team: dict[int, list[Placing]], field: Sequence[int], season: int, start: date
) -> dict[int, dict[str, float]]:
    """Each team's decayed award count from placings on earlier days."""
    history: dict[int, dict[str, float]] = {}
    for t in field:
        h: dict[str, float] = defaultdict(float)
        for p in by_team.get(t, ()):
            if p.start >= start or p.season > season:
                continue
            weight = HISTORY_DECAY ** (season - p.season)
            if p.award == INSPIRE:
                h[INSPIRE_PLACED] += weight
            if p.place == 1:
                h[p.award] += weight
        history[t] = dict(h)
    return history


def _event_decisions(
    event: EventRow,
    stage: EventTier,
    season: int,
    awards: Sequence[AwardRow],
    *,
    field: AwardField,
    inspire_won_before: set[int],
) -> list[AwardDecision]:
    assert event.date_start is not None
    first: dict[int, set[str]] = defaultdict(set)
    places: dict[str, dict[int, int]] = defaultdict(dict)
    for a in awards:
        name = AWARD_NAMES.get(a.award_code)
        if name is None:
            continue
        places[name][a.place] = a.team_number
        if a.place == 1:
            first[a.team_number].add(name)
    inspire_placed = set(places[INSPIRE].values())

    decisions = []
    for award in MODELLED_AWARDS:
        if 1 not in places[award]:
            continue
        pool = [
            t
            for t in field.teams
            if not first[t] - {award}
            and not (award != INSPIRE and season >= INSPIRE_EXCLUSIVE_FROM and t in inspire_placed)
        ]
        last_place = max(places[award]) if award == INSPIRE else 1
        for place in range(1, last_place + 1):
            locked = inspire_won_before if award == INSPIRE and stage is EventTier.REGULAR and place == 1 else set()
            eligible = [t for t in pool if t not in locked]
            chosen = places[award].get(place)
            if chosen is None or chosen not in eligible or len(eligible) < (MIN_POOL if place == 1 else 2):
                break
            decisions.append(
                AwardDecision(
                    event.event_id,
                    event.date_start,
                    season,
                    stage,
                    award,
                    place,
                    tuple(eligible),
                    eligible.index(chosen),
                    field.features(award, eligible),
                )
            )
            pool = [t for t in pool if t != chosen]
    return decisions
