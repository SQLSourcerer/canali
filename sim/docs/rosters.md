# Rosters

Some events don't publish thier team lists until the weeks before the event. The sim can read an external supplier's
estimation of the event roster and read it via `Rosters` in `sim/rosters.py`.

## The file

```json
{
  "region": "USPA",
  "season": 2026,
  "as_of": "2026-10-13T07:14:00+00:00",
  "source": "roster.py seed 0",
  "events": {
    "USPAYOQ1": {"teams": [20223, 29403, 14382], "capacity": 24, "slots": 3},
    "USPACMP": {"capacity": 40, "slots": 15, "first_championship_slots": 6}
  }
}
```

| Key | Holds |
| --- | --- |
| `region` | The region's code |
| `season` | The season's starting year |
| `as_of` | When the rosters were drawn |
| `source` | What drew them; optional, free text |
| `events` | Each event, keyed by its FTC Events code |
| `teams` | The event's teams; left out when its field comes from advancement, as at a championship |
| `capacity` | How many teams the event holds; optional |
| `slots` | How many teams the event advances, used until FTC Events publishes the event's own; optional |
| `first_championship_slots` | Of `slots`, how many go to FIRST Championship, at a regional championship; optional |

Any other key is rejected. A file is one best guess for the event's roster.

## Using one

```
uv run sim event SEASON CODE --predictor ... --rosters FILE
```

The sim takes the event's teams from the file and makes up a fresh match schedule for them each time it plays the
event through. To list the teams by hand instead, use `--teams` with their numbers; use one option or the other, not
both. Once the real schedule is out, the sim uses the teams on it, and neither option is accepted.
