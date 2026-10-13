"""``sim`` command line."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated

import numpy as np
import typer

from sim.convergence import TOLERANCE
from sim.inputs import event_models
from sim.pipeline import simulate_published_event
from sim.predictor import predictor_for
from sim.rosters import Rosters
from sim.runner import EventSummary
from sim.season import read_season, run_season
from sim.writer import write_event_summary, write_season_summary
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
    rosters: Annotated[Path | None, typer.Option(help="A season's roster file, for an event with no schedule")] = None,
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

    field_teams = _named_field(season, event_code, teams, rosters)
    roster = None if rosters is None else Rosters.from_file(rosters).events.get(event_code)
    with Warehouse() as warehouse:
        row = _event(warehouse, season, event_code)
        try:
            published, summary = simulate_published_event(
                warehouse,
                row,
                pack,
                chosen,
                np.random.default_rng(seed),
                through=through,
                teams=field_teams,
                roster=roster,
                matches_per_team=matches_per_team,
                tolerance=tolerance,
            )
        except ValueError as e:
            raise typer.BadParameter(str(e), param_hint="--teams/--rosters") from e
        _report(event_code, published.as_of_match, summary)
        if write:
            sim_run_id = write_event_summary(warehouse, row.event_id, chosen.version, published.as_of_match, summary)
            _echo(f"        sim_run {sim_run_id}")


@app.command("season")
def season(
    season: int,
    *,
    predictor: PREDICTOR,
    rosters: Annotated[Path, typer.Option(help="The region's roster file, naming every event of its season")],
    before: Annotated[str | None, typer.Option(help="Play the season from this date, YYYY-MM-DD, not today")] = None,
    matches_per_team: Annotated[int, typer.Option(help="Qualification matches per team in a generated schedule")] = 5,
    tolerance: Annotated[float, typer.Option(help="Largest standard error the run stops at")] = TOLERANCE,
    seed: Annotated[int | None, typer.Option(help="Random seed")] = None,
    write: Annotated[
        bool, typer.Option(help="Persist the run to derived.season_sim_run, replacing one since the last event began")
    ] = False,
) -> None:
    """Simulate a region's season from its roster file and print each team's chances."""
    pack = next((p for p in discover() if p.season == season), None)
    if pack is None:
        raise typer.BadParameter(f"no rule pack for {season}")
    try:
        chosen = predictor_for(predictor)
    except ValueError as e:
        raise typer.BadParameter(str(e), param_hint="--predictor") from e
    sample = Rosters.from_file(rosters)
    if sample.season != season:
        raise typer.BadParameter(f"{rosters} is for {sample.season}, not {season}", param_hint="--rosters")
    cutoff = None if before is None else date.fromisoformat(before)
    as_of = cutoff or date.today()

    with Warehouse() as warehouse:
        state = read_season(warehouse, pack, chosen, sample, before=cutoff)
        upcoming = next((q for q in state.qualifiers if not q.done), state.championship)
        models = event_models(warehouse, upcoming.event, chosen)
        summary = run_season(
            state, pack, models, np.random.default_rng(seed), tolerance=tolerance, matches_per_team=matches_per_team
        )
        started = state.events_started(as_of)
        _echo(
            f"{sample.region} {season} as of {as_of}, {started} events started: {summary.iterations} seasons, "
            f"standard error {summary.standard_error:.4f}"
        )
        _echo(f"{'team':>6} {'attend':>7} {'premier':>8} {'FIRST':>6}")
        for team in sorted(summary.teams, key=lambda t: -summary.teams[t].p_attend_rcmp):
            t = summary.teams[team]
            _echo(f"{team:>6} {t.p_attend_rcmp:7.3f} {t.p_premier:8.3f} {t.p_cmp:6.3f}")
        if write:
            sim_run_id = write_season_summary(
                warehouse, season, sample.region, chosen.version, summary, events_started=started, as_of=as_of
            )
            _echo(f"        sim_run {sim_run_id}")


def _named_field(season: int, event_code: str, teams: str | None, rosters: Path | None) -> list[int] | None:
    """The field named by ``--teams`` or found in a ``--rosters`` file, None when neither names one."""
    if teams is not None and rosters is not None:
        raise typer.BadParameter("name the field once", param_hint="--teams/--rosters")
    if teams is not None:
        return [int(t) for t in teams.split(",") if t.strip()]
    if rosters is None:
        return None
    sample = Rosters.from_file(rosters)
    event = sample.events.get(event_code)
    if sample.season != season or event is None or event.teams is None:
        raise typer.BadParameter(f"{rosters} has no {season} roster for {event_code}", param_hint="--rosters")
    return event.teams


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
