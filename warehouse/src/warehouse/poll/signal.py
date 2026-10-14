"""The change signal: each newly scored or replayed match of a watched event."""

from __future__ import annotations

import uuid
from typing import NamedTuple

from sqlalchemy import Connection, func, select, text
from sqlalchemy.dialects.postgresql import insert

from warehouse.schema import raw


class MatchSignal(NamedTuple):
    signal_id: int
    event_id: uuid.UUID
    season: int
    event_match_ordinal: int | None


def signals_after(conn: Connection, after: int) -> list[MatchSignal]:
    sql = text(
        """
        WITH pending AS (
            SELECT signal_id, event_id, match_id FROM raw.match_signal WHERE signal_id > :after
        ),
        rated AS (
            SELECT DISTINCT match_id, event_match_ordinal FROM pub.v_match_rating_input
            WHERE event_id IN (SELECT event_id FROM pending)
        )
        SELECT p.signal_id, p.event_id, e.season, r.event_match_ordinal
        FROM pending p
        JOIN core.event e ON e.event_id = p.event_id
        LEFT JOIN rated r ON r.match_id = p.match_id
        ORDER BY p.signal_id
        """
    )
    return [
        MatchSignal(r.signal_id, uuid.UUID(str(r.event_id)), r.season, r.event_match_ordinal)
        for r in conn.execute(sql, {"after": after})
    ]


def cursor(conn: Connection, consumer: str) -> int:
    """The last signal ``consumer`` carried through, 0 before its first."""
    c = raw.signal_cursor.c
    found = conn.execute(select(c.signal_id).where(c.consumer == consumer)).scalar()
    return 0 if found is None else int(found)


def advance(conn: Connection, consumer: str, signal_id: int) -> None:
    stmt = insert(raw.signal_cursor).values(consumer=consumer, signal_id=signal_id, updated_at_utc=func.now())
    conn.execute(
        stmt.on_conflict_do_update(
            index_elements=["consumer"],
            set_={"signal_id": stmt.excluded.signal_id, "updated_at_utc": stmt.excluded.updated_at_utc},
        )
    )
