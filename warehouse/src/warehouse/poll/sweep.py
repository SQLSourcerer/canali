"""The weekly sweep.

Runs on Mondays inside the poller from ``warehouse ingest sweep``.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Collection

from sqlalchemy import Connection, func, select
from sqlalchemy.dialects.postgresql import insert

from warehouse.schema import core, raw
from warehouse.tier import RATED_EVENT_TYPES

MONDAY = 0


def sweep_due(now: dt.datetime, last_swept: dt.date | None, at: dt.time, tz: dt.tzinfo) -> bool:
    local = now.astimezone(tz)
    return local.weekday() == MONDAY and local.time() >= at and last_swept != local.date()


def sweep_targets(conn: Connection, season: int, watched: Collection[uuid.UUID], today: dt.date) -> list[str]:
    """Codes of the season's unwatched rated events whose last day fell in the seven days before ``today``."""
    e = core.event.c
    last_day = func.coalesce(e.date_end, e.date_start)
    rows = conn.execute(
        select(e.code)
        .where(
            e.season == season,
            e.type.in_(RATED_EVENT_TYPES),
            last_day >= today - dt.timedelta(days=7),
            last_day < today,
            e.event_id.not_in(list(watched)),
        )
        .order_by(e.date_start, e.code)
    )
    return [str(r.code) for r in rows]


def mark_swept(conn: Connection, season: int, day: dt.date) -> None:
    stmt = insert(raw.sweep).values(season=season, swept_on=day, finished_at_utc=func.now())
    conn.execute(
        stmt.on_conflict_do_update(
            index_elements=["season", "swept_on"], set_={"finished_at_utc": stmt.excluded.finished_at_utc}
        )
    )


def last_swept(conn: Connection, season: int) -> dt.datetime | None:
    """When the season's latest sweep finished."""
    s = raw.sweep.c
    return conn.execute(select(func.max(s.finished_at_utc)).where(s.season == season)).scalar()
