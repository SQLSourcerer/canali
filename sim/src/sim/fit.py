"""The score model and RP curves fitted on a season's qualification rows before a weekly cutoff.

Below ``INIT_WINDOW`` alliance-rows every model stands in from earlier seasons; from there each is refit in full.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, timedelta

import numpy as np
import numpy.typing as npt
from scipy.special import ndtri

from sim.constants import MEASURED_RP_CURVES, MEASURED_SCORE_MODELS, RP_CAP_MIN_ROWS, RP_STAND_INS
from sim.match import SeasonModels
from sim.predictor import Predictor
from sim.rp_probability import CLIP, RpCurve, fit_correlation, resolve_curve
from sim.rp_source import RpSource, rp_sources
from sim.score import MIN_FIT_PREDICTION, ScoreModel, resolve_score_model
from sim.standings import Tiebreaker
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
        match_ids: Each row's match.
        event_types: Each row's event type.
        predicted: The alliance's predicted points per component, summed over its rated teams, keyed by column name.
        observed: The alliance's breakdown values, keyed by column name.
        score: The alliance's no-foul score.
        official: The alliance's official score, fouls included.
    """

    match_ids: tuple[uuid.UUID, ...]
    event_types: tuple[str | None, ...]
    predicted: dict[str, Floats]
    observed: dict[str, Floats]
    score: Floats
    official: Floats

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

    def matches(self) -> tuple[npt.NDArray[np.int64], Floats]:
        """Row indices of each match with both alliances, shaped ``(match, alliance)``, and the first alliance's
        official result: 1 for a win, a half for a tie, 0 for a loss."""
        by_match: dict[uuid.UUID, list[int]] = defaultdict(list)
        for i, match_id in enumerate(self.match_ids):
            by_match[match_id].append(i)
        pairs = np.array([rows for rows in by_match.values() if len(rows) == 2], dtype=np.int64).reshape(-1, 2)
        first, second = self.official[pairs[:, 0]], self.official[pairs[:, 1]]
        return pairs, np.where(first > second, 1.0, np.where(first == second, 0.5, 0.0))


def _tiebreaker_components(pack: RulePack) -> list[str]:
    return [t.component for t in map(Tiebreaker.parse, pack.ranking.tiebreakers) if t.component is not None]


def _breakdown_columns(pack: RulePack) -> list[str]:
    names = {name for bonus in pack.ranking.bonus_rp for name in (bonus.component, *bonus.sum_of)}
    names |= {name for source in rp_sources(pack).values() for name in source.points_from}
    names |= set(_tiebreaker_components(pack))
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
        match_ids=tuple(row.match_id for row, _ in rows),
        event_types=tuple(row.event_type for row, _ in rows),
        predicted={
            name: np.array([sum(team.get(name, 0.0) for team in row.components) for row, _ in rows]) for name in names
        },
        observed={column: np.array([values[column] for _, values in rows]) for column in columns},
        score=np.array([row.score_no_foul for row, _ in rows]),
        official=np.array([row.score for row, _ in rows]),
    )


def _stand_in_curves(version: str, season: int, component: str) -> list[RpCurve]:
    measured = MEASURED_RP_CURVES.get(version, {})
    stand_ins = RP_STAND_INS.get(season, {}).get(component, ())
    return [measured[s][c] for s, c in stand_ins if c in measured.get(s, {})]


def _correlated(
    curves: dict[str, RpCurve], rows: SeasonRows, pack: RulePack, sources: dict[str, RpSource], score: ScoreModel
) -> dict[str, RpCurve]:
    """Each curve with its correlation fitted on the alliances' observed no-foul scores, one per shared source."""
    mu = rows.predicted_sum()
    keep = mu > MIN_FIT_PREDICTION
    latent = ndtri(np.clip(score.cdf(mu[keep], rows.score[keep]), CLIP, 1.0 - CLIP))
    groups: dict[RpSource, list[str]] = defaultdict(list)
    for bonus in pack.ranking.bonus_rp:
        groups[sources[bonus.component]].append(bonus.component)
    bonuses = {bonus.component: bonus for bonus in pack.ranking.bonus_rp}
    fitted = dict(curves)
    for source, components in groups.items():
        points = rows.predicted_sum(source.points_from)[keep]
        thresholds = [
            np.array([bonuses[c].threshold(e) for e in rows.event_types], dtype=np.float64)[keep] for c in components
        ]
        rho = fit_correlation(
            [curves[c].probability(points, t) for c, t in zip(components, thresholds, strict=True)],
            [(rows.observed_sum((c,)) > 0)[keep] for c in components],
            latent,
        )
        fitted.update({c: replace(curves[c], correlation=rho) for c in components})
    return fitted


def resolve_models(rows: SeasonRows, pack: RulePack, version: str) -> SeasonModels:
    """The score model, result noise and every bonus RP curve and correlation from these rows, or below
    ``INIT_WINDOW`` rows their stand-ins measured on the predictor at ``version``"""
    mu = rows.predicted_sum()
    pairs, outcome = rows.matches()
    score = resolve_score_model(
        mu,
        rows.score,
        match_mu=mu[pairs],
        outcome=outcome,
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
    if len(rows) >= INIT_WINDOW and curves:
        curves = _correlated(curves, rows, pack, sources, score)
    total = float(rows.score.sum())
    shares = {
        name: float(rows.observed_sum((name,)).sum()) / total if total > 0 else 1.0
        for name in _tiebreaker_components(pack)
    }
    return SeasonModels(score=score, rp_curves=curves, tiebreaker_shares=shares)


def season_models(warehouse: Warehouse, season: int, predictor: Predictor, *, before: date | None) -> SeasonModels:
    """A season's models fitted on events that started before ``before``, or on the whole season when None."""
    pack = next((p for p in discover() if p.season == season), None)
    if pack is None:
        raise ValueError(f"no rule pack for {season}")
    return resolve_models(load_rows(warehouse, pack, predictor, before=before), pack, predictor.version)
