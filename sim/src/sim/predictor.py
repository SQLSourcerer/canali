"""The model whose predicted points the score model and RP curves are fitted on."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from warehouse.client import PreMatchRatingRow, Warehouse

EPA_MODEL = "epa"


class Entry(Protocol):
    """Each team's rating as the season so far leaves it."""

    def entering(self, team: int, event_date: date, *, first_event: date | None = None) -> dict[str, float]:
        """The team's predicted points per component at an event on ``event_date``."""
        ...


class Predictor(Protocol):
    """Where predicted points come from.

    ``version`` names the predictor and its model version, and keys the measured constants fitted on it.
    """

    @property
    def version(self) -> str: ...

    def pre_match(self, warehouse: Warehouse, season: int, *, before: date | None) -> list[PreMatchRatingRow]:
        """Every qualification alliance-row of events that started before ``before``, empty if none is rated yet."""
        ...

    def qualification_end(
        self, warehouse: Warehouse, season: int, *, before: date | None
    ) -> dict[tuple[uuid.UUID, int], dict[str, float]]:
        """Each team's predicted points per component after its event's qualification, keyed by event and team."""
        ...

    def event_ratings(
        self, warehouse: Warehouse, season: int, event_id: uuid.UUID, *, through: int
    ) -> dict[int, dict[str, float]]:
        """Each team's predicted points per component at one event after its first ``through`` matches, before the
        event at 0."""
        ...

    def season_entry(
        self, warehouse: Warehouse, season: int, teams: Sequence[int], *, before_ordinal: int | None = None
    ) -> Entry:
        """Each of ``teams``' rating as the season before ``before_ordinal`` leaves it, or the whole season so far when
        None, for events it hasn't played."""
        ...


@dataclass(frozen=True, slots=True)
class EpaEntry:
    """EPA's ratings entering an event: a team's latest rating, boosted for the days since its last real event, or
    since its first simulated one before it has played."""

    series: dict[int, dict[str, float]]
    last_played: dict[int, date]
    boost_per_day: float
    cap_days: float

    def entering(self, team: int, event_date: date, *, first_event: date | None = None) -> dict[str, float]:
        previous = self.last_played.get(team, first_event)
        series = self.series[team]
        days = 0 if previous is None else (event_date - previous).days
        points = self.boost_per_day * min(max(days, 0), self.cap_days)
        if not points:
            return dict(series)
        weights = {name: max(value, 0.0) for name, value in series.items()}
        mass = sum(weights.values())
        return {
            name: value + points * (weights[name] / mass if mass > 0 else 1.0 / len(series))
            for name, value in series.items()
        }


@dataclass(frozen=True, slots=True)
class EpaPredictor:
    """EPA at one model version, read from its season batch runs."""

    epa_version: str

    @property
    def version(self) -> str:
        return self.epa_version

    def pre_match(self, warehouse: Warehouse, season: int, *, before: date | None) -> list[PreMatchRatingRow]:
        run = self._run(warehouse, season)
        return [] if run is None else warehouse.pre_match_epa(run, before=before)

    def qualification_end(
        self, warehouse: Warehouse, season: int, *, before: date | None
    ) -> dict[tuple[uuid.UUID, int], dict[str, float]]:
        run = self._run(warehouse, season)
        return {} if run is None else warehouse.qualification_end_epa(run, before=before)

    def event_ratings(
        self, warehouse: Warehouse, season: int, event_id: uuid.UUID, *, through: int
    ) -> dict[int, dict[str, float]]:
        run = self._run(warehouse, season)
        return {} if run is None else warehouse.event_epa(run, event_id, through=through)

    def season_entry(
        self, warehouse: Warehouse, season: int, teams: Sequence[int], *, before_ordinal: int | None = None
    ) -> Entry:
        run = self._run(warehouse, season)
        if run is None:
            raise ValueError(f"no {season} {EPA_MODEL} run at {self.epa_version} to start the season from")
        notes = warehouse.fit_run_notes(run)
        if "init_sigma" not in notes:
            raise ValueError(f"the {season} {EPA_MODEL} run at {self.epa_version} predates its layoff notes; rerun it")
        rows = warehouse.entry_epa(run, teams=teams, before_ordinal=before_ordinal)
        unrated = sorted(set(teams) - set(rows))
        if unrated:
            raise ValueError(f"the {season} {EPA_MODEL} run has no rating for {unrated}")
        layoff = notes.get("layoff") or {}
        return EpaEntry(
            series={t: r.components for t, r in rows.items()},
            last_played={t: r.last_played for t, r in rows.items() if r.last_played is not None},
            boost_per_day=float(layoff.get("sigma_per_30d", 0.0)) * float(notes["init_sigma"]) / 30.0,
            cap_days=float(layoff.get("cap_days", 0.0)),
        )

    def _run(self, warehouse: Warehouse, season: int) -> uuid.UUID | None:
        if self.epa_version not in warehouse.model_versions(EPA_MODEL):
            raise ValueError(f"no completed {EPA_MODEL} run at version {self.epa_version}")
        return warehouse.batch_fit_run(EPA_MODEL, season, self.epa_version)


def predictor_for(version: str) -> Predictor:
    """The predictor ``version`` names."""
    if version.startswith(f"{EPA_MODEL}-"):
        return EpaPredictor(version)
    raise ValueError(f"no predictor is named by {version!r}")
