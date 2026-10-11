"""The score model and RP curves fitted on a season's qualification rows before a weekly cutoff.

Below ``INIT_WINDOW`` alliance-rows every model stands in from earlier seasons; from there each is refit in full.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import numpy.typing as npt

from sim.constants import MEASURED_RP_CURVES, MEASURED_SCORE_MODELS, RP_CAP_MIN_ROWS, RP_STAND_INS
from sim.predictor import Predictor
from sim.rp_probability import RpCurve, resolve_curve
from sim.rp_source import rp_sources
from sim.score import ScoreModel, resolve_score_model
from warehouse.client import Warehouse
from warehouse.constants import INIT_WINDOW
from warehouse.rules.loader import discover
from warehouse.rules.model import RulePack, to_column_name

Floats = npt.NDArray[np.float64]


def refit_cutoff(today: date) -> date:
    return today - timedelta(days=today.weekday())


@dataclass(frozen=True, slots=True)
class SeasonRows:
    """A season's qualification alliance-rows in event-sequential order.

    Attributes:
        event_types: Each row's event type.
        predicted: The alliance's predicted points per component, summed over its rated teams, keyed by column name.
        observed: The alliance's breakdown values, keyed by column name.
        score: The alliance's no-foul score.
    """

    event_types: tuple[str | None, ...]
    predicted: dict[str, Floats]
    observed: dict[str, Floats]
    score: Floats

    def __len__(self) -> int:
        return len(self.score)

    def predicted_sum(self, names: tuple[str, ...] | None = None) -> Floats:
        """The predicted points summed over rule-pack ``names``, or over every component."""
        if len(self) == 0:
            return np.zeros(0)
        columns = list(self.predicted) if names is None else [to_column_name(n) for n in names]
        missing = sorted(set(columns) - set(self.predicted))
        if missing:
            raise ValueError(f"predictions lack {missing}")
        return np.sum([self.predicted[c] for c in columns], axis=0) if columns else np.zeros(len(self))

    def observed_sum(self, names: tuple[str, ...]) -> Floats:
        if len(self) == 0:
            return np.zeros(0)
        return np.sum([self.observed[to_column_name(n)] for n in names], axis=0)


@dataclass(frozen=True, slots=True)
class SeasonModels:
    """What a season's sim plays its matches with."""

    score: ScoreModel
    rp_curves: dict[str, RpCurve]


def _breakdown_columns(pack: RulePack) -> list[str]:
    names = {name for bonus in pack.ranking.bonus_rp for name in (bonus.component, *bonus.sum_of)}
    names |= {name for source in rp_sources(pack).values() for name in source.points_from}
    return sorted(to_column_name(name) for name in names)


def load_rows(warehouse: Warehouse, pack: RulePack, predictor: Predictor, *, before: date | None) -> SeasonRows:
    """The predictor's pre-match predictions joined to the breakdowns the bonus RPs read."""
    predicted = predictor.pre_match(warehouse, pack.season, before=before)
    columns = _breakdown_columns(pack)
    breakdowns = warehouse.season_breakdowns(pack.season, columns) if predicted else {}
    rows = [
        (row, breakdowns.get((row.match_id, row.alliance), {}))
        for row in predicted
        if not columns or (row.match_id, row.alliance) in breakdowns
    ]
    names = sorted({name for row, _ in rows for team in row.components for name in team})
    return SeasonRows(
        event_types=tuple(row.event_type for row, _ in rows),
        predicted={
            name: np.array([sum(team.get(name, 0.0) for team in row.components) for row, _ in rows]) for name in names
        },
        observed={column: np.array([values[column] for _, values in rows]) for column in columns},
        score=np.array([row.score_no_foul for row, _ in rows]),
    )


def _stand_in_curves(version: str, season: int, component: str) -> list[RpCurve]:
    measured = MEASURED_RP_CURVES.get(version, {})
    stand_ins = RP_STAND_INS.get(season, {}).get(component, ())
    return [measured[s][c] for s, c in stand_ins if c in measured.get(s, {})]


def resolve_models(rows: SeasonRows, pack: RulePack, version: str) -> SeasonModels:
    """The score model and every bonus RP curve from these rows, or below ``INIT_WINDOW`` rows their stand-ins measured
    on the predictor at ``version``."""
    score = resolve_score_model(
        rows.predicted_sum(),
        rows.score,
        min_rows=INIT_WINDOW,
        previous=[model for s, model in MEASURED_SCORE_MODELS.get(version, {}).items() if s < pack.season],
    )
    sources = rp_sources(pack)
    curves: dict[str, RpCurve] = {}
    for bonus in pack.ranking.bonus_rp:
        source = sources[bonus.component]
        stand_ins = _stand_in_curves(version, pack.season, bonus.component)
        if len(rows) < INIT_WINDOW and not stand_ins:
            raise ValueError(f"{pack.season} {bonus.component}: below {INIT_WINDOW} rows with no curve to stand in")
        curves[bonus.component] = resolve_curve(
            rows.predicted_sum(source.points_from),
            np.array([bonus.threshold(event_type) for event_type in rows.event_types], dtype=np.float64),
            rows.observed_sum((bonus.component,)) > 0,
            source=source,
            observed_points=rows.observed_sum(source.points_from),
            observed_quantity=rows.observed_sum(tuple(bonus.sum_of)),
            min_rows=INIT_WINDOW,
            min_bucket_rows=RP_CAP_MIN_ROWS,
            previous=stand_ins,
        )
    return SeasonModels(score=score, rp_curves=curves)


def season_models(warehouse: Warehouse, season: int, predictor: Predictor, *, before: date | None) -> SeasonModels:
    """A season's models fitted on events that started before ``before``, or on the whole season when None."""
    pack = next((p for p in discover() if p.season == season), None)
    if pack is None:
        raise ValueError(f"no rule pack for {season}")
    return resolve_models(load_rows(warehouse, pack, predictor, before=before), pack, predictor.version)
