# Live

Keeps ratings and predictions current while an event is running. Each time the poller sees a new match score, live
updates the teams' EPA and pRidge ratings and re-runs the event sim. Once a week, after the poller has collected the
past week's other events, it also refits the ratings for the whole season.

## Quick start

```
uv sync --all-packages  # install everything in the .venv
uv run warehouse poll   # watch events for new scores, until stopped
uv run live run         # update ratings and predictions as scores arrive, until stopped
uv run live batch 2025  # refit the season's ratings now, without waiting for the weekly scheduled run
```

Run `warehouse poll` and `live run` at the same time, in separate terminals. Each restarts itself after a crash.

## Command surface

| Command | Does |
| --- | --- |
| `run` | Update ratings and predictions for each new score the poller finds, and refit the season once a week, until stopped |
| `batch` | Refit one season's ratings now |

`run` takes `--tick-s`, how many seconds to wait between checks for new scores, `--restart-s`, how many seconds to
wait before starting again after a crash, and `--seed`, which makes the sim's random draws repeatable.

## Each new score

Each tick reads the signals past the cursor and groups them by event. Each signalled event then runs, in order:

1. EPA: the event's EPA is recalculated from its first match, starting from each team's rating from the last weekly
   batch, and replaces what was saved for the event before.
2. pRidge: the event's pRidge ratings are refit after each match, starting at the earliest newly scored match, or
   earlier if a previous update was cut short, and replace what was saved from that match on.
3. The sim: the rest of the event is simulated from the latest match, using EPA, and saved under that match.

Live then records which scores it has handled, in `raw.signal_cursor`, so it does not handle them again. If an event's
update fails, live tries again when that event's next score arrives. Every update replaces what it saved before, so
repeating one after a restart gives the same result.

## The weekly batch

Once a week, after the poller's Monday sweep has collected the past week's other events, live refits the current
season. It also runs straight away if the season has never been refit. It does not wait for running events to finish.

1. EPA: every team's EPA is recalculated over the whole season, replacing the last weekly results.
2. pRidge: every event's pRidge ratings are refit, replacing the last weekly results.
3. Events live has followed: if the new weekly EPA changes the ratings teams brought into one of them, that event's
   EPA and pRidge are redone from its first match. Its saved sims are left as they were.

If the refit fails, live waits `BATCH_RETRY` before trying again.

## Versions

The updates and the batch run on the installed EPA and pRidge `MODEL_VERSION` and the installed sim version.

## Layout

```
src/live/
  cascade.py    updates one event's EPA, pRidge and sim after new scores
  batch.py      the weekly refit, and redoing followed events it changes
  loop.py       checks for new scores, updates their events, and starts the weekly refit
  cli.py        the `live` command
```
