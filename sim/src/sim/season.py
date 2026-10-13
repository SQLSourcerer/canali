"""A region's season played through: its qualifiers in date order, then the championship they feed."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date

import numpy as np

from sim.award_model import INSPIRE
from sim.event import EventField, EventModels, EventOutcome, EventProgress, Slots, simulate_event
from sim.inputs import event_field, event_slots
from sim.predictor import Entry, Predictor
from sim.progress import PublishedEvent, published_event
from sim.rosters import Rosters
from sim.schedule import Schedule, generated_schedule
from warehouse.client import EventRow, Warehouse
from warehouse.rules.model import RulePack
from warehouse.tier import EventTier, tier_for

MATCHES_PER_TEAM = 5


@dataclass(frozen=True, slots=True)
class SeasonEvent:
    """One event of the season, as read before any iteration.

    Attributes:
        event: The event.
        field: Its teams' traits; ratings are set each time it is played.
        teams: Its field, empty for a championship whose field comes from advancement.
        schedule: Its published schedule, or None.
        progress: What it has published, or None.
        ratings: Ratings read with its progress, for the teams it has rated.
        slots: How many teams it advances, 0 when none.
        first_championship: Of ``slots``, how many go to FIRST Championship, at a regional championship.
        capacity: How many teams it holds, None when unknown.
        offers: Its real offers in slot order, once its advancement is published.
        points: Its real advancement points, once published.
    """

    event: EventRow
    field: EventField
    teams: tuple[int, ...]
    schedule: Schedule | None
    progress: EventProgress | None
    ratings: dict[int, dict[str, float]]
    slots: int
    first_championship: int | None
    capacity: int | None
    offers: tuple[int, ...] = ()
    points: dict[int, float] | None = None

    @property
    def date(self) -> date:
        assert self.event.date_start is not None
        return self.event.date_start

    @property
    def done(self) -> bool:
        return bool(self.offers)


@dataclass(frozen=True, slots=True)
class Season:
    """A region's season: its qualifiers in date order and the championship they feed."""

    qualifiers: tuple[SeasonEvent, ...]
    championship: SeasonEvent
    entry: Entry


@dataclass(frozen=True, slots=True)
class SeasonOutcome:
    """One playing of a season.

    Attributes:
        attended: Teams in the championship's field.
        advanced: Teams given a championship slot by a qualifier.
        first_championship: Teams the championship sends to FIRST Championship.
        premier: Teams the championship sends to a Premier event.
    """

    attended: frozenset[int]
    advanced: frozenset[int]
    first_championship: frozenset[int]
    premier: frozenset[int]


def read_season(
    warehouse: Warehouse, pack: RulePack, predictor: Predictor, rosters: Rosters, *, before: date | None = None
) -> Season:
    """The season the roster file names, each event read from the warehouse as it stands, or as it stood before
    ``before``: events starting from then are read as unplayed."""
    events = {e.event_code: e for e in warehouse.events(rosters.season)}
    missing = sorted(set(rosters.events) - set(events))
    if missing:
        raise ValueError(f"{rosters.season} has no events {missing}")
    chosen = sorted((events[code] for code in rosters.events), key=lambda e: (e.date_start or date.max, e.event_code))
    championships = [e for e in chosen if rosters.events[e.event_code].teams is None]
    if len(championships) != 1:
        raise ValueError(f"the roster file names {len(championships)} events without teams, not one championship")

    def played(e: EventRow) -> bool:
        return before is None or (e.date_start is not None and e.date_start < before)

    unplayed = PublishedEvent(0, {})
    published = {
        e.event_code: published_event(warehouse, e.event_id, pack, predictor) if played(e) else unplayed for e in chosen
    }
    fields: dict[str, tuple[int, ...]] = {}
    for e in chosen:
        schedule = published[e.event_code].schedule
        roster = rosters.events[e.event_code].teams
        if schedule is not None:
            fields[e.event_code] = tuple(sorted({int(t) for t in np.unique(schedule.stations)}))
        else:
            fields[e.event_code] = tuple(roster or ())
    everyone = sorted({t for teams in fields.values() for t in teams})
    cutoff = next((e.event_ordinal for e in chosen if not played(e)), None)
    entry = predictor.season_entry(warehouse, rosters.season, everyone, before_ordinal=cutoff)

    def season_event(e: EventRow) -> SeasonEvent:
        if e.date_start is None:
            raise ValueError(f"{e.event_code} has no start date")
        state = published[e.event_code]
        teams = fields[e.event_code]
        traits = teams or tuple(everyone)
        base = {t: entry.entering(t, e.date_start) for t in traits}
        slots = event_slots(warehouse, e, rosters.events[e.event_code])
        offers = tuple(warehouse.event_offers(e.event_id)) if played(e) else ()
        return SeasonEvent(
            event=e,
            field=event_field(warehouse, e, traits, base, before=before),
            teams=teams,
            schedule=state.schedule,
            progress=state.progress,
            ratings=state.ratings,
            slots=0 if slots is None else slots.count,
            first_championship=None if slots is None else slots.first_championship,
            capacity=rosters.events[e.event_code].capacity,
            offers=offers,
            points=warehouse.event_points(e.event_id) if offers else None,
        )

    qualifiers = tuple(season_event(e) for e in chosen if e is not championships[0])
    championship = season_event(championships[0])
    total = sum(q.slots for q in qualifiers)
    if championship.capacity is not None and total > championship.capacity:
        raise ValueError(f"qualifiers advance {total} teams into a championship of {championship.capacity}")
    return Season(qualifiers, championship, entry)


def simulate_season(
    season: Season,
    pack: RulePack,
    models: EventModels,
    rng: np.random.Generator,
    *,
    matches_per_team: int = MATCHES_PER_TEAM,
) -> SeasonOutcome:
    """Play the season once."""
    run = _Iteration(season.entry, pack, models, rng, matches_per_team)
    for qualifier in season.qualifiers:
        if qualifier.done:
            run.advance(qualifier.offers)
            for team, p in (qualifier.points or {}).items():
                run.points[team].append(p)
            continue
        slots = Slots(qualifier.slots, frozenset(run.advanced)) if qualifier.slots else None
        outcome = run.play(qualifier, qualifier.teams, slots)
        if outcome.offers is not None:
            run.advance(outcome.offers.advancing)
        if outcome.awards.get(INSPIRE) and tier_for(qualifier.event.event_type) is EventTier.REGULAR:
            run.inspire.add(outcome.awards[INSPIRE][0])

    championship = season.championship
    if championship.done:
        first = championship.first_championship or 0
        return SeasonOutcome(
            attended=frozenset(championship.teams or run.advanced),
            advanced=frozenset(run.advanced),
            first_championship=frozenset(championship.offers[:first]),
            premier=frozenset(championship.offers[first:]),
        )
    field = championship.teams or _championship_field(run.advanced, run.points, championship.capacity, rng)
    slots = Slots(championship.slots, frozenset(), championship.first_championship) if championship.slots else None
    outcome = run.play(championship, field, slots)
    return SeasonOutcome(
        attended=frozenset(field),
        advanced=frozenset(run.advanced),
        first_championship=frozenset(() if outcome.offers is None else outcome.offers.advancing),
        premier=frozenset(() if outcome.offers is None else outcome.offers.premier),
    )


class _Iteration:
    """What one playing of the season carries from event to event."""

    def __init__(
        self, entry: Entry, pack: RulePack, models: EventModels, rng: np.random.Generator, matches_per_team: int
    ) -> None:
        self.entry, self.pack, self.models, self.rng = entry, pack, models, rng
        self.matches_per_team = matches_per_team
        self.advanced: list[int] = []
        self.inspire: set[int] = set()
        self.first_seen: dict[int, date] = {}
        self.points: dict[int, list[float]] = defaultdict(list)

    def advance(self, teams: Iterable[int]) -> None:
        self.advanced += [t for t in teams if t not in self.advanced]

    def play(self, event: SeasonEvent, teams: tuple[int, ...], slots: Slots | None) -> EventOutcome:
        ratings = {
            t: event.ratings.get(t) or self.entry.entering(t, event.date, first_event=self.first_seen.get(t))
            for t in teams
        }
        for t in teams:
            self.first_seen.setdefault(t, event.date)
        field = replace(
            event.field, predicted=ratings, inspire_won_before=event.field.inspire_won_before | self.inspire
        )
        schedule = event.schedule or generated_schedule(list(teams), self.matches_per_team, self.rng)
        outcome = simulate_event(
            field, schedule, self.pack, self.models, self.rng, slots=slots, progress=event.progress
        )
        for team, p in outcome.points.items():
            self.points[team].append(float(p.total))
        return outcome


def _championship_field(
    advanced: list[int], points: Mapping[int, list[float]], capacity: int | None, rng: np.random.Generator
) -> tuple[int, ...]:
    """Every advanced team, then the rest by average points per event, ties at random, up to ``capacity``."""
    field = list(advanced)
    if capacity is not None and capacity > len(field):
        rest = [t for t in points if t not in set(field)]
        draw = dict(zip(rest, rng.random(len(rest)), strict=True))
        rest.sort(key=lambda t: (-float(np.mean(points[t])), draw[t]))
        field += rest[: capacity - len(field)]
    return tuple(field)
