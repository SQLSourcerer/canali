"""The weekly batch.

Updates metrics for all events we didn't watch live.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping
from dataclasses import dataclass

import structlog

from epa.constants import MODEL_VERSION as EPA_VERSION
from epa.pipeline import MODEL_NAME as EPA_MODEL
from epa.pipeline import persist, prior_norms, replay_live_event
from epa.pipeline import run_season as run_epa_season
from epa.replay import TAG_PRE_EVENT
from live.cascade import persist_epa, refit_pridge
from pridge.pipeline import run_season as run_pridge_season
from pridge.prior import EpaPriorSource
from warehouse.client import EventRow, Warehouse
from warehouse.poll.sweep import last_swept

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class BatchResult:
    """One weekly batch.

    Attributes:
        epa_run: The EPA batch run.
        pridge_run: The pRidge batch run.
        reseeded: The codes of the live events whose seed moved.
    """

    epa_run: uuid.UUID
    pridge_run: uuid.UUID | None
    reseeded: tuple[str, ...]


def batch_due(warehouse: Warehouse, season: int) -> bool:
    """Whether the season's latest sweep finished after its batch run."""
    with warehouse.engine.connect() as conn:
        swept = last_swept(conn, season)
    if swept is None:
        return False
    finished = warehouse.batch_finished_at(EPA_MODEL, season, EPA_VERSION)
    return finished is None or finished < swept


def weekly_batch(warehouse: Warehouse, season: int) -> BatchResult:
    """Refit EPA then pRidge over the season, then rerun each live event whose opening metrics moved."""
    previous, second = prior_norms(warehouse, season, EPA_VERSION)
    run = run_epa_season(
        warehouse, season, previous_norm=previous, second_norm=second, listed=warehouse.team_seasons(season)
    )
    epa_run = persist(warehouse, run.result.rows, season=season, scope=f"season:{season}", notes=run.notes())
    log.info("batch.epa", season=season, rows=len(run.result.rows))

    source = EpaPriorSource.for_season(warehouse, season, EPA_VERSION)
    pridge = run_pridge_season(warehouse, season, source, write=True)
    log.info("batch.pridge", season=season, fitted=pridge.fitted, skipped=len(pridge.skipped))

    live = warehouse.live_fit_events(EPA_MODEL, season, EPA_VERSION)
    reseeded = tuple(
        event.event_code
        for event in warehouse.events(season)
        if event.event_id in live and reseed(warehouse, event, EPA_VERSION)
    )
    log.info("batch.reseeded", season=season, events=list(reseeded))
    return BatchResult(epa_run=epa_run, pridge_run=pridge.fit_run_id, reseeded=reseeded)


def reseed(warehouse: Warehouse, event: EventRow, epa_version: str) -> bool:
    """Replay a live event against the current batch run, rewriting its metrics if its intial value moved."""
    rows = replay_live_event(warehouse, event.season, event.event_id, model_version=epa_version).rows
    seeded = {row.team_number: row.components for row in rows if row.tag == TAG_PRE_EVENT}
    live_run = warehouse.live_fit_run(EPA_MODEL, event.event_id, epa_version)
    stored = {} if live_run is None else warehouse.event_epa(live_run, event.event_id, through=0)
    if _same_seed(seeded, stored):
        return False
    persist_epa(warehouse, event, rows, epa_version)
    refit_pridge(warehouse, event, epa_version, from_match=1)
    return True


def _same_seed(a: Mapping[int, Mapping[str, float]], b: Mapping[int, Mapping[str, float]]) -> bool:
    return a.keys() == b.keys() and all(
        a[team].keys() == b[team].keys() and all(math.isclose(a[team][k], b[team][k]) for k in a[team]) for team in a
    )
