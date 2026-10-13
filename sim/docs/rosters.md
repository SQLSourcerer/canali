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
    "USPAYOQ1": [20223, 29403, 14382],
    "USPAYOQ2": [16354, 20201, 22311]
  }
}
```

| Key | Holds |
| --- | --- |
| `region` | The region's code |
| `season` | The season's starting year |
| `as_of` | When the rosters were drawn |
| `source` | What drew them; optional, free text |
| `events` | Each event's teams, keyed by its FTC Events code |

Any other key is rejected. A file is one best guess for the event's roster.

## Using one

```
uv run sim event SEASON CODE --predictor ... --rosters FILE
```

The sim takes the event's teams from the file and makes up a fresh match schedule for them each time it plays the
event through. To list the teams by hand instead, use `--teams` with their numbers; use one option or the other, not
both. Once the real schedule is out, the sim uses the teams on it, and neither option is accepted.
