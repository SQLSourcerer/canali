"""The model whose predicted points the score model and RP curves are fitted on."""

from __future__ import annotations

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


@dataclass(frozen=True, slots=True)
class EpaPredictor:
    """EPA at one model version, read from its season batch runs."""

    epa_version: str

    @property
    def version(self) -> str:
        return self.epa_version

    def pre_match(self, warehouse: Warehouse, season: int, *, before: date | None) -> list[PreMatchRatingRow]:
        if self.epa_version not in warehouse.model_versions(EPA_MODEL):
            raise ValueError(f"no completed {EPA_MODEL} run at version {self.epa_version}")
        run = warehouse.batch_fit_run(EPA_MODEL, season, self.epa_version)
        return [] if run is None else warehouse.pre_match_epa(run, before=before)
