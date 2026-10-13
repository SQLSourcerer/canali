"""One event simulated from its published state: the field, slots and models read, the sim run to convergence."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from sim.convergence import TOLERANCE
from sim.inputs import event_field, event_models, event_slots
from sim.predictor import Predictor
from sim.progress import PublishedEvent, published_event
from sim.rosters import RosterEvent
from sim.runner import EventSummary, fixed_field, generated_field, run_event
from sim.season import MATCHES_PER_TEAM
from warehouse.client import EventRow, Warehouse
from warehouse.rules.model import RulePack


def simulate_published_event(
    warehouse: Warehouse,
    event: EventRow,
    pack: RulePack,
    predictor: Predictor,
    rng: np.random.Generator,
    *,
    through: int | None = None,
    teams: Sequence[int] | None = None,
    roster: RosterEvent | None = None,
    matches_per_team: int = MATCHES_PER_TEAM,
    tolerance: float = TOLERANCE,
) -> tuple[PublishedEvent, EventSummary]:
    """The event as published through ``through``, or its latest match, and its sim run to convergence.

    ``teams`` is the field of an event with no published schedule, and must be None once one is published.
    """
    published = published_event(warehouse, event.event_id, pack, predictor, through=through)
    if published.schedule is None:
        if teams is None:
            raise ValueError(f"{event.event_code} has no schedule; name its field")
        field_teams = list(teams)
    elif teams is not None:
        raise ValueError(f"{event.event_code}'s schedule sets its field")
    else:
        field_teams = sorted({int(t) for t in np.unique(published.schedule.stations)})
    field = event_field(warehouse, event, field_teams, published.ratings)
    draw = (
        generated_field(field, field_teams, matches_per_team)
        if published.schedule is None
        else fixed_field(field, published.schedule)
    )
    summary = run_event(
        draw,
        pack,
        event_models(warehouse, event, predictor),
        rng,
        slots=event_slots(warehouse, event, roster),
        progress=published.progress,
        tolerance=tolerance,
    )
    return published, summary
