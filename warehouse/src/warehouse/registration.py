"""Load event registration snapshots into ``core.registration_*``."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Connection, delete, insert

from warehouse.schema import core


class Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team_number: int | None
    name: str | None = None
    priority: str | None = None


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str | None
    name: str
    type: str | None = None
    date_start: date | None = None
    source_url: str | None = None
    capacity: int | None = None
    closed: bool | None = None
    teams: list[Entry] | None = None
    held: list[Entry] = []
    waitlist: list[Entry] | None = None


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal[1]
    region: str
    season: int
    as_of: datetime
    events: list[Event]


def snapshot_files(paths: list[Path]) -> list[Path]:
    """The JSON files named, and every one under a named directory."""
    return sorted({f for p in paths for f in (p.rglob("*.json") if p.is_dir() else [p])})


def load_file(conn: Connection, path: Path) -> tuple[Snapshot, uuid.UUID]:
    """Load one snapshot file, replacing the snapshot with its region, season and time."""
    snapshot = Snapshot.model_validate(json.loads(path.read_text(encoding="utf-8")))
    table = core.registration_snapshot
    conn.execute(
        delete(table).where(
            table.c.region_code == snapshot.region,
            table.c.season == snapshot.season,
            table.c.as_of_utc == snapshot.as_of,
        )
    )
    snapshot_id = uuid.uuid4()
    conn.execute(
        insert(table).values(
            snapshot_id=snapshot_id,
            region_code=snapshot.region,
            season=snapshot.season,
            as_of_utc=snapshot.as_of,
            source_file=path.name,
            loaded_at_utc=datetime.now(UTC),
        )
    )
    events = [
        {
            "snapshot_id": snapshot_id,
            "event_ordinal": ordinal,
            "event_code": event.code,
            "name": event.name,
            "event_type": event.type,
            "date_start": event.date_start,
            "source_url": event.source_url,
            "capacity": event.capacity,
            "closed": event.closed,
            "teams_known": event.teams is not None,
            "waitlist_known": event.waitlist is not None,
        }
        for ordinal, event in enumerate(snapshot.events, start=1)
    ]
    entries = [
        {
            "snapshot_id": snapshot_id,
            "event_ordinal": ordinal,
            "status": status,
            "position": position,
            "team_number": entry.team_number,
            "name": entry.name,
            "priority": entry.priority,
        }
        for ordinal, event in enumerate(snapshot.events, start=1)
        for status, listed in (("registered", event.teams), ("held", event.held), ("waitlist", event.waitlist))
        for position, entry in enumerate(listed or [], start=1)
    ]
    if events:
        conn.execute(insert(core.registration_event), events)
    if entries:
        conn.execute(insert(core.registration_team), entries)
    return snapshot, snapshot_id
