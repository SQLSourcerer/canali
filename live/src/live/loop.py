"""The live loop."""

from __future__ import annotations

import datetime as dt
import time
import uuid
from collections.abc import Callable

import numpy as np
import structlog

from epa.constants import MODEL_VERSION as EPA_VERSION
from live.batch import batch_due, weekly_batch
from live.cascade import cascade
from warehouse.client import EventRow, Warehouse
from warehouse.poll.signal import MatchSignal, advance, cursor, signals_after
from warehouse.poll.watch import latest_season

log = structlog.get_logger(__name__)

CONSUMER = "live"
BATCH_RETRY = dt.timedelta(hours=1)


class Live:
    """Carries match signals through the cascade and runs the weekly batch when due."""

    def __init__(
        self,
        warehouse: Warehouse,
        rng: np.random.Generator,
        *,
        tick_s: float = 5.0,
        clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
    ) -> None:
        self.warehouse = warehouse
        self.rng = rng
        self.tick_s = tick_s
        self.clock = clock
        self.pending: dict[uuid.UUID, int] = {}
        self.batch_blocked_until: dt.datetime | None = None

    def tick(self) -> None:
        self.consume()
        self.batch()

    def consume(self) -> None:
        with self.warehouse.engine.connect() as conn:
            signals = signals_after(conn, cursor(conn, CONSUMER))
        if not signals:
            return
        signalled = pending_from(signals)
        for event_id, from_match in signalled.items():
            self.pending[event_id] = min(from_match, self.pending.get(event_id, from_match))
        events = self._events({s.season for s in signals})
        for event_id in signalled:
            event = events.get(event_id)
            if event is None:
                log.warning("live.event_unrated", event_id=str(event_id))
                del self.pending[event_id]
                continue
            self._cascade(event, self.pending[event_id])
        with self.warehouse.engine.begin() as conn:
            advance(conn, CONSUMER, signals[-1].signal_id)

    def batch(self) -> None:
        now = self.clock()
        if self.batch_blocked_until is not None and now < self.batch_blocked_until:
            return
        with self.warehouse.engine.connect() as conn:
            season = latest_season(conn)
        if not batch_due(self.warehouse, season):
            return
        try:
            result = weekly_batch(self.warehouse, season)
        except Exception:
            log.exception("live.batch_failed", season=season)
            self.batch_blocked_until = now + BATCH_RETRY
            return
        self.batch_blocked_until = None
        log.info("live.batch", season=season, reseeded=list(result.reseeded))

    def run(self, should_stop: Callable[[], bool], *, sleep: Callable[[float], object] = time.sleep) -> None:
        while not should_stop():
            self.tick()
            sleep(self.tick_s)

    def _cascade(self, event: EventRow, from_match: int) -> None:
        try:
            cascade(self.warehouse, event, from_match=from_match, epa_version=EPA_VERSION, rng=self.rng)
        except Exception:
            log.exception("live.cascade_failed", code=event.event_code, from_match=from_match)
            return
        del self.pending[event.event_id]

    def _events(self, seasons: set[int]) -> dict[uuid.UUID, EventRow]:
        return {e.event_id: e for season in sorted(seasons) for e in self.warehouse.events(season)}


def pending_from(signals: list[MatchSignal]) -> dict[uuid.UUID, int]:
    """Each signalled event's earliest signalled rated match, in order of its first signal."""
    earliest: dict[uuid.UUID, int] = {}
    for s in signals:
        if s.event_match_ordinal is not None:
            earliest[s.event_id] = min(s.event_match_ordinal, earliest.get(s.event_id, s.event_match_ordinal))
    return earliest
