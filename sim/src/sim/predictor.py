"""The model whose predicted points the score model and RP curves are fitted on."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from warehouse.client import PreMatchRatingRow, Warehouse

EPA_MODEL = "epa"


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

    def _run(self, warehouse: Warehouse, season: int) -> uuid.UUID | None:
        if self.epa_version not in warehouse.model_versions(EPA_MODEL):
            raise ValueError(f"no completed {EPA_MODEL} run at version {self.epa_version}")
        return warehouse.batch_fit_run(EPA_MODEL, season, self.epa_version)
