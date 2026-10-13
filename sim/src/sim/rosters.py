"""Rosters for a region's events that have no published schedule, from a file written outside the repository."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class RosterEvent(BaseModel):
    """One event in a roster file.

    Attributes:
        teams: The event's teams, or None when its field comes from advancement.
        capacity: How many teams the event holds.
        slots: How many teams the event advances.
        first_championship_slots: Of ``slots``, how many go to FIRST Championship, at a regional championship.
    """

    model_config = ConfigDict(extra="forbid")

    teams: list[int] | None = None
    capacity: int | None = None
    slots: int | None = None
    first_championship_slots: int | None = None


class Rosters(BaseModel):
    """One season's sampled rosters for a region.

    Attributes:
        region: The region's code.
        season: The season's starting year.
        as_of: When the rosters were drawn.
        source: What drew them.
        events: Each event, keyed by its FTC Events code.
    """

    model_config = ConfigDict(extra="forbid")

    region: str
    season: int
    as_of: datetime
    source: str | None = None
    events: dict[str, RosterEvent]

    @classmethod
    def from_file(cls, path: Path) -> Rosters:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))
