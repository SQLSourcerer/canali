"""One event's newly scored matches carried through EPA, pRidge and the event sim, in that order."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import numpy as np
import structlog

from epa.pipeline import persist, replay_live_event
from pridge.pipeline import load_event, run_live
from pridge.prior import EpaPriorSource
from sim.pipeline import simulate_published_event
from sim.predictor import EpaPredictor
from sim.writer import write_event_summary
from warehouse.client import EventRow, Warehouse
from warehouse.rules.loader import discover

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CascadeResult:
    """One pass over an event.

    Attributes:
        epa_run: The event's live EPA run.
        pridge_fits: The match indexes pRidge refitted.
        as_of_match: The match the sim started from.
        sim_run: The event sim run written.
    """

    epa_run: uuid.UUID
    pridge_fits: tuple[int, ...]
    as_of_match: int
    sim_run: uuid.UUID


def cascade(
    warehouse: Warehouse, event: EventRow, *, from_match: int, epa_version: str, rng: np.random.Generator
) -> CascadeResult:
    """Rate ``event`` live with EPA at ``epa_version``, refit pRidge from match ``from_match`` on, then simulate the
    event from its latest match with EPA as the predictor."""
    epa_rows = replay_live_event(warehouse, event.season, event.event_id, model_version=epa_version).rows
    epa_run = persist(
        warehouse,
        epa_rows,
        season=event.season,
        scope=f"event:{event.event_id}",
        event_id=event.event_id,
        model_version=epa_version,
    )
    log.info("live.epa", code=event.event_code, rows=len(epa_rows))

    source = EpaPriorSource.for_season(warehouse, event.season, epa_version)
    fits = run_live(warehouse, load_event(warehouse, event.event_id, event.season, source), from_match=from_match)
    log.info("live.pridge", code=event.event_code, fits=len(fits))

    pack = next((p for p in discover() if p.season == event.season), None)
    if pack is None:
        raise ValueError(f"no rule pack for {event.season}")
    predictor = EpaPredictor(epa_version)
    published, summary = simulate_published_event(warehouse, event, pack, predictor, rng)
    sim_run = write_event_summary(warehouse, event.event_id, predictor.version, published.as_of_match, summary)
    log.info("live.sim", code=event.event_code, as_of_match=published.as_of_match, iterations=summary.iterations)

    return CascadeResult(
        epa_run=epa_run,
        pridge_fits=tuple(f.as_of_match for f in fits),
        as_of_match=published.as_of_match,
        sim_run=sim_run,
    )
