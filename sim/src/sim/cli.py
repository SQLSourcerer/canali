"""``sim`` command line."""

from __future__ import annotations

from typing import Annotated

import numpy as np
import typer

from sim.convergence import TOLERANCE
from sim.inputs import event_field, event_models, event_slots
from sim.predictor import predictor_for
from sim.progress import published_event
from sim.runner import EventSummary, fixed_field, generated_field, run_event
from sim.writer import write_event_summary
from warehouse.client import EventRow, Warehouse
from warehouse.rules.loader import discover

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)

PREDICTOR = Annotated[str, typer.Option(help="The predictor and its model version, such as an EPA model version")]
WRITE = Annotated[bool, typer.Option(help="Persist the run to derived.event_sim_run, replacing one at this match")]


def _echo(message: str) -> None:
    typer.echo(message)


def _event(warehouse: Warehouse, season: int, event_code: str) -> EventRow:
    for event in warehouse.events(season):
        if event.event_code == event_code:
            return event
    raise typer.BadParameter(f"no {season} event with code {event_code}")


@app.command("version")
def version() -> None:
    """The sim version every run is stored under."""
    from sim import __version__

    _echo(__version__)


@app.command("event")
def event(
    season: int,
    event_code: Annotated[str, typer.Argument(help="The event to simulate")],
    *,
    predictor: PREDICTOR,
    through: Annotated[int | None, typer.Option(help="Simulate from this match ordinal, not the latest")] = None,
    teams: Annotated[str | None, typer.Option(help="Comma-separated field, for an event with no schedule")] = None,
    matches_per_team: Annotated[int, typer.Option(help="Qualification matches per team in a generated schedule")] = 5,
    tolerance: Annotated[float, typer.Option(help="Largest standard error the run stops at")] = TOLERANCE,
    seed: Annotated[int | None, typer.Option(help="Random seed")] = None,
    write: WRITE = False,
) -> None:
    """Simulate one event from its published progress and print each team's chances."""
    pack = next((p for p in discover() if p.season == season), None)
    if pack is None:
        raise typer.BadParameter(f"no rule pack for {season}")
    try:
        chosen = predictor_for(predictor)
    except ValueError as e:
        raise typer.BadParameter(str(e), param_hint="--predictor") from e

    with Warehouse() as warehouse:
        row = _event(warehouse, season, event_code)
        published = published_event(warehouse, row.event_id, pack, chosen, through=through)
        if published.schedule is None:
            if teams is None:
                raise typer.BadParameter(f"{event_code} has no schedule; name its field", param_hint="--teams")
            field_teams = [int(t) for t in teams.split(",") if t.strip()]
        elif teams is not None:
            raise typer.BadParameter(f"{event_code}'s schedule sets its field", param_hint="--teams")
        else:
            field_teams = sorted({int(t) for t in np.unique(published.schedule.stations)})
        field = event_field(warehouse, row, field_teams, published.ratings)
        slots = event_slots(warehouse, row)
        models = event_models(warehouse, row, chosen)

        draw = (
            generated_field(field, field_teams, matches_per_team)
            if published.schedule is None
            else fixed_field(field, published.schedule)
        )
        rng = np.random.default_rng(seed)
        summary = run_event(draw, pack, models, rng, slots=slots, progress=published.progress, tolerance=tolerance)
        _report(event_code, published.as_of_match, summary)
        if write:
            sim_run_id = write_event_summary(warehouse, row.event_id, chosen.version, published.as_of_match, summary)
            _echo(f"        sim_run {sim_run_id}")


def _report(event_code: str, as_of_match: int, summary: EventSummary) -> None:
    _echo(
        f"{event_code} as of match {as_of_match}: {summary.iterations} iterations, "
        f"standard error {summary.standard_error:.4f}"
    )
    _echo(f"{'team':>6} {'rank':>6} {'captain':>8} {'picked':>7} {'win':>6} {'advance':>8} {'FIRST':>6}")

    def key(team: int) -> tuple[float, float]:
        t = summary.teams[team]
        return (-(t.p_advance or 0.0), t.mean_rank or 0.0)

    for team in sorted(summary.teams, key=key):
        t = summary.teams[team]
        advance = "" if t.p_advance is None else f"{t.p_advance:8.3f}"
        first = "" if t.p_advance_first_championship is None else f"{t.p_advance_first_championship:6.3f}"
        _echo(
            f"{team:>6} {t.mean_rank or 0.0:6.2f} {t.p_captain:8.3f} {t.p_selected:7.3f} {t.p_win:6.3f} "
            f"{advance:>8} {first:>6}"
        )
