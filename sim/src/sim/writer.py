"""An event sim's summary written to the warehouse."""

from __future__ import annotations

import uuid
from dataclasses import asdict

from sim import __version__
from sim.runner import EventSummary
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
