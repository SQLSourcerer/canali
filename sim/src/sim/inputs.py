"""What an event's sim needs from the warehouse beyond its published progress: the field, the slots and the models."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date

from sim.award_corpus import decayed_history, placings_by_team
from sim.award_model import INSPIRE
from sim.constants import MEASURED_AWARD_MODELS, MEASURED_PICK_MODELS
from sim.event import EventField, EventModels, Slots
from sim.fit import refit_cutoff, season_models
from sim.predictor import Predictor
from sim.rosters import RosterEvent
from warehouse.client import EventRow, Warehouse
from warehouse.tier import EventTier, tier_for


def event_field(
    warehouse: Warehouse,
    event: EventRow,
    teams: Sequence[int],
    ratings: Mapping[int, Mapping[str, float]],
    *,
    before: date | None = None,
) -> EventField:
    """``teams`` at ``event`` with ``ratings``, and what rated events before it, and before ``before`` when given, say
    of them."""
    if event.date_start is None:
        raise ValueError(f"{event.event_code} has no start date")
    unrated = sorted(set(teams) - set(ratings))
    if unrated:
        raise ValueError(f"{event.event_code}: no rating for {unrated}")
    start = event.date_start if before is None else min(event.date_start, before)
    earlier = {
        e.event_id
        for e in warehouse.events(event.season)
        if e.date_start is not None and e.date_start < start and tier_for(e.event_type) is not None
    }
    seats: dict[tuple[object, int], set[int]] = defaultdict(set)
    for slot in warehouse.alliances(event.season):
        if slot.event_id in earlier:
            seats[(slot.event_id, slot.seed)].add(slot.team_number)
    allied: dict[int, set[int]] = defaultdict(set)
    for members in seats.values():
        for t in members:
            allied[t] |= members - {t}

    seasons = warehouse.team_seasons(event.season)
    by_team = placings_by_team(warehouse, event.season)
    return EventField(
        event_type=event.event_type,
        predicted={t: dict(ratings[t]) for t in teams},
        allied={t: frozenset(allied[t]) for t in teams if t in allied},
        city={t: seasons[t].city for t in teams if t in seasons},
        team_age={
            t: float(event.season - rookie)
            for t in teams
            if t in seasons and (rookie := seasons[t].rookie_year) is not None
        },
        history=decayed_history(by_team, teams, event.season, start),
        rookie=frozenset(t for t in teams if t in seasons and seasons[t].rookie_year == event.season),
        inspire_won_before=frozenset(
            t
            for t in teams
            for p in by_team.get(t, ())
            if p.season == event.season and p.award == INSPIRE and p.place == 1 and p.start < start
        ),
    )


def event_slots(warehouse: Warehouse, event: EventRow, roster: RosterEvent | None = None) -> Slots | None:
    """The slots the event offers, passing over teams already given one, or None when it offers none.

    Published counts come first; before an event's are published, ``roster``'s stand in.
    """
    advancement = warehouse.event_advancement(event.season).get(event.event_id)
    if advancement is not None:
        count, first = advancement.slots, advancement.slots_first_championship
    elif roster is not None and roster.slots is not None:
        count, first = roster.slots, roster.first_championship_slots or 0
    else:
        return None
    if count == 0:
        return None
    return Slots(
        count,
        warehouse.advanced_before(event.event_id),
        first if tier_for(event.event_type) is EventTier.RCMP else None,
    )


def event_models(warehouse: Warehouse, event: EventRow, predictor: Predictor) -> EventModels:
    """The season's models as refit for the event's week, with the pick and award models measured on the
    predictor."""
    if event.date_start is None:
        raise ValueError(f"{event.event_code} has no start date")
    version = predictor.version
    if version not in MEASURED_PICK_MODELS or version not in MEASURED_AWARD_MODELS:
        raise ValueError(f"no pick and award models are measured on {version}")
    return EventModels(
        season_models(warehouse, event.season, predictor, before=refit_cutoff(event.date_start)),
        MEASURED_PICK_MODELS[version],
        MEASURED_AWARD_MODELS[version],
    )
