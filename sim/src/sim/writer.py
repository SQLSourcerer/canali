"""Event and season sim summaries written to the warehouse."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import date

from sim import __version__
from sim.runner import EventSummary
from sim.season import SeasonSummary
from warehouse.client import Warehouse


def write_event_summary(
    warehouse: Warehouse, event_id: uuid.UUID, predictor: str, as_of_match: int, summary: EventSummary
) -> uuid.UUID:
    """Write the summary as the event's run at ``as_of_match``, replacing one already there for this predictor and
    sim version."""
    run = {
        "event_id": event_id,
        "predictor": predictor,
        "sim_version": __version__,
        "as_of_match": as_of_match,
        "n_iterations": summary.iterations,
        "achieved_mcse": summary.standard_error,
    }
    results = [{**asdict(team), "team_number": number} for number, team in summary.teams.items()]
    return warehouse.write_event_sim(run, results)


def write_season_summary(
    warehouse: Warehouse,
    season: int,
    region: str,
    predictor: str,
    summary: SeasonSummary,
    *,
    events_started: int,
    as_of: date,
) -> uuid.UUID:
    """Write the summary as the region's season run with ``events_started`` events begun, replacing one already there
    for this predictor and sim version."""
    run = {
        "season": season,
        "region_code": region,
        "predictor": predictor,
        "sim_version": __version__,
        "events_started": events_started,
        "as_of_date": as_of,
        "n_iterations": summary.iterations,
        "achieved_mcse": summary.standard_error,
    }
    results = [{**asdict(team), "team_number": number} for number, team in summary.teams.items()]
    return warehouse.write_season_sim(run, results)
