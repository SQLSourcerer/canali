"""``live`` command line."""

from __future__ import annotations

from typing import Annotated

import numpy as np
import typer

from live.batch import weekly_batch
from warehouse.client import Warehouse

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)


def _echo(message: str) -> None:
    typer.echo(message)


@app.command("run")
def run(
    tick_s: Annotated[float, typer.Option(help="Seconds between reads of the match signal")] = 5.0,
    restart_s: Annotated[float, typer.Option(help="Seconds to wait before starting again after a crash")] = 30.0,
    seed: Annotated[int | None, typer.Option(help="Random seed")] = None,
) -> None:
    """Carry the poller's match signals through the cascade until stopped, starting again after a crash."""
    import signal
    import threading

    from live.loop import Live
    from warehouse.poll.loop import supervise

    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())

    rng = np.random.default_rng(seed)
    with Warehouse() as warehouse:

        def make() -> Live:
            return Live(warehouse, rng, tick_s=tick_s)

        restarts = supervise(make, stop.is_set, restart_s, sleep=stop.wait, name="live")
    _echo(f"stopped after {restarts} restart{'' if restarts == 1 else 's'}")


@app.command("batch")
def batch(season: int) -> None:
    """Run the weekly batch on a season now."""
    with Warehouse() as warehouse:
        result = weekly_batch(warehouse, season)
    _echo(f"epa run {result.epa_run}, pridge run {result.pridge_run}")
    _echo(f"reseeded: {', '.join(result.reseeded) or 'none'}")
