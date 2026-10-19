# Python Worker + D1

Runs prepared event inputs through the existing Python models, saving results in local D1. It supports qualification
EPA/pRidge totals and match forecasts, plus the complete single-event Monte Carlo: standings, alliance selection,
playoffs, judged awards and advancement. A native importer fetches one event's official FIRST qualification data
without Postgres. D1 can replay an imported season corpus to supply pre-event total EPA priors. Component ratings
and fitted simulation models are still prepared separately.

## Run locally

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Node.js 22 or later. From this directory:

```powershell
npm ci
uv sync --locked
uv run pywrangler d1 migrations apply canali-local --local
uv run pywrangler dev --ip 127.0.0.1 --port 8787
```

In another terminal, also in this directory:

```powershell
uv run python smoke.py
```

The smoke check uploads synthetic fixtures, computes ratings and forecasts, reads persisted results, repeats a
run, corrects a score and checks invalid-input handling. It also resumes a complete event simulation across HTTP
requests and compares the completed forecast with native Python. No source-data credentials, Cloudflare login, Docker or
remote database are needed. `wrangler.toml` contains a local database ID placeholder. Keep the explicit `--local`
flag on database commands.

The Worker has its own Python 3.14 environment; the existing workspace remains on Python 3.12. Pywrangler prepares
the WebAssembly dependencies separately in `python_modules/`, with versions recorded in `pylock.toml`. The custom
build copies the numerical modules and rule-pack parser from their existing source directories; edit those sources
rather than the ignored copies under `src/`. Package and runtime support must also be checked on Cloudflare before deployment.

## Event input

`fixtures/event.json` is a synthetic prepared event, not an upstream API payload. It supplies:

- Teams' pre-event EPA totals and prior qualification-match counts.
- Qualification matches in increasing ordinal order, with non-foul scores or two null scores for an unplayed match.
- EPA K/M schedules, a ridge penalty and fitted score-model coefficients.
- A random seed and the number of score draws per remaining match.

The EPA and pRidge calculations use the supplied priors; initialization, layoff adjustment and season normalization
must happen before preparing those inputs. One or two rated teams per alliance are supported. The prototype computes
total ratings only. Component rating updates, weekly calibration and regional season simulations have not
yet been ported.

## Import a FIRST event

Save `WAREHOUSE_FTC_EVENTS_USERNAME` and `WAREHOUSE_FTC_EVENTS_TOKEN` in `warehouse/.env`. From the repository root,
use the native workspace environment (Python 3.12), with the local Worker running and migrations applied:

```powershell
uv run python worker/import_event.py 2025 USNJCMPPKWY --parameters worker/fixtures/event.json --initial-epa 100
```

This example uses a completed 24-team division, explicit uniform EPA priors and the synthetic fixture's calibration.
It demonstrates ingestion and computation; its ratings are not season-calibrated estimates. For meaningful ratings,
provide a prepared event JSON with the correct pre-event `teams` priors, K/M schedules, ridge penalty and score model,
and omit `--initial-epa`. The importer replaces that file's `matches` with official qualification results.

The native command reuses the warehouse client's authentication, pagination, pacing and retry handling. Credentials
stay in the native process; the Worker receives event data and model parameters. It imports the team's roster and
qualification hybrid schedule, subtracts the opponent's committed foul points from each final alliance score, includes
surrogate teams and excludes no-shows from rating updates. It rejects incomplete scores, missing foul totals, duplicate stations,
roster mismatches and matches with an entirely absent alliance. Unplayed matches retain null scores. For divided
championships, choose the division's event code; the parent event may have no qualification schedule.

D1 atomically retains the latest source payloads and prepared input under a season-qualified key, such as
`2025-USNJCMPPKWY`. Repeating identical data and parameters preserves the revision and published result. A source or
parameter change increments the revision and hides the previous result until recomputed. Directly replacing prepared
inputs through `/events/{code}` clears their previous source attribution. Historical source versions are not retained.

The command also saves `source.json` and `result.json` in the ignored `var/worker-import/{season}-{code}/` directory.
The saved source document can be replayed with `PUT /imports/{season}-{code}` without another FIRST request. There is
no polling or scheduled ingestion yet. Source fetching runs natively; parsing, validation and rating computation run
inside the Python Worker. Complete event Monte Carlo snapshots still require separately prepared component ratings,
event progress and fitted models.

## Replay season EPA priors

From the repository root, using the native workspace environment and a running local Worker:

```powershell
uv run python worker/replay_season.py 2025 --events USNJUCM1,USNJUCM2,USNJCMPPKWY
uv run python worker/import_event.py 2025 USNJCMPPKWY --parameters worker/fixtures/event.json --season-priors
```

The first command imports the selected events' metadata, teams and qualification schedules, then calls
`POST /seasons/2025/step` until replay finishes. Repeating the command updates changed sources and resumes from the
remaining cursor. An interrupted replay can also continue by calling `/step` directly, without fetching FIRST again.
Source documents are saved in the ignored `var/worker-season/2025/` directory.

This is a replay of the **imported qualification corpus**. The example includes three events and omits the rest of
those teams' season histories; it is a parity check, not a complete season rating. Supply every relevant event code
for a full qualification corpus. Playoff contributions, component EPA and end-of-season percentile normalization
are outside this slice. Event ordering matches the warehouse: start date, then event code, with match numbers in order.

The Worker calls the existing native `replay_season` engine with a total-only partition and the versioned EPA constants.
It computes initialization from the first 4,000 scored alliance rows in the imported corpus. Until that window fills,
it uses the same provisional scale as the native pipeline: the average measured initialization scale. Rookie seeding,
K/M schedules, qualification match counts and the capped layoff boost all use the shared implementation.

For carryover, pass `--config path/to/config.json` containing optional `previous_norm` and `second_norm` objects, mapping
team numbers to normalized prior-season ratings. Without those inputs, every team enters without prior-season history.
Producing those normalized prior-season ratings is not automated here. Configuration changes restart replay.

Each step rates one event, retaining at most 128 teams and 1,000 matches in Worker memory. Initialization reads at most
4,000 alliance scores; D1 performs that prefix query. Team history stays in indexed D1 rows, and the Worker reads only
the current event's teams' preceding ratings. An event step saves its ratings and cursor in one D1 transaction. This
bounds buffering independently of the total number of season matches; production memory and CPU still need measurement.

Changed event data deletes ratings from the affected event onward. A changed initialization scale restarts the whole
corpus because every team's starting rating depends on it. Engine changes also restart replay. Concurrent stale steps
return HTTP 409. Unchanged uploads preserve the revision and completed prefix.

`--season-priors` reads each team's rating **before** the target event, including its layoff adjustment, even if the
event has already been replayed. The event must be registered in the season corpus, and preceding events must be
processed. These priors replace the parameter file's teams and K/M schedules; the file still supplies the ridge penalty
and score-model coefficients, which must be calibrated separately. The synthetic fixture's coefficients remain for
demonstration only. EPA priors can be negative, as in the native engine.

Results computed with season priors carry a season revision. Any season revision or engine change hides those results
and prevents recomputation with stale priors. Finish the season replay and rerun `import_event.py --season-priors` to
refresh them. The revision check is conservative: adding a later event also invalidates existing linked results.

## Complete event forecasts

`fixtures/forecast.json` contains synthetic teams and published progress, with the repository's 2025 rules and fitted
model coefficients. It illustrates the snapshot accepted by `/forecasts/{code}`:

- `rule_pack`: the season's rules, ranking points, tiebreakers, playoff brackets and advancement point tables.
- `field`: component predictions, prior alliance partners, cities, ages, award history and eligibility.
- `models`: fitted score, RP, selection and award coefficients; no season-wide calibration is performed by the Worker.
- `schedule`: qualification stations and optional surrogate flags, or null to generate a schedule each iteration.
- `progress`: played-match flags, official scores, bonus RPs, tiebreaker components and optional disqualifications,
  seated alliances and decided playoff games. Omit it for an unplayed event.
- `slots`: advancement counts and already-advanced teams, or null if the event offers no slots.
- `seed`, `tolerance`, `min_iterations`, `max_iterations`: reproducibility, convergence and the total work budget.

The caller supplies the component ratings to simulate; these are not automatically connected to the separate
qualification-total calculation. Integer team keys are represented as strings in JSON. RP curve recoveries use
`{"kind": "identity"}`, `{"kind": "ratio", "value": 0.25}`, or `{"kind": "floor_divide", "value": 20}`.

Each `/step` request advances at most 32 event iterations and checks a two-second elapsed-time budget between
iterations. A single iteration is not interrupted. D1 stores counts and the exact random-generator state, so a new
request or restarted process can resume the run. Individual simulated outcomes are discarded.

The response has `status`, `iterations`, `standard_error` and `result`. A running forecast returns HTTP 202 with no
published result. Once the shared simulator's convergence criterion is met it returns `complete` with HTTP 200 and
the same team summary as the native runner. Hitting `max_iterations` first returns `exhausted`, also with HTTP 200,
and no published result. Repeating a terminal step returns the saved report without further computation.

Results include rank distributions and captain, selection, playoff-win and advancement probabilities. Judged awards
are simulated as part of advancement; the existing summary does not expose separate award-win probabilities.

Input revisions invalidate previous checkpoints and results. The build also fingerprints the engine sources and
WebAssembly dependency lock so changed code or packages cannot resume incompatible counts. Atomic step checks reject concurrent stale writes with
HTTP 409; clients can reread the status and retry. Only the latest run for an event is retained.

## HTTP surface

| Request | Result |
| --- | --- |
| `GET /health` | Runtime package versions |
| `PUT /seasons/{year}` | Configure normalized prior-season inputs; changed configuration restarts replay |
| `GET /seasons/{year}` | Read the revision, event cursor and initialization scale |
| `PUT /seasons/{year}/events/{code}` | Import official event metadata, teams and qualification schedule |
| `POST /seasons/{year}/step` | Rate one event and checkpoint, or report the imported corpus complete |
| `GET /seasons/{year}/priors/{code}` | Read roster priors, K/M schedules and their season revision |
| `PUT /imports/{season}-{code}` | Atomically import FIRST payloads and explicit model parameters |
| `GET /imports/{season}-{code}` | Read the current imported source payloads and parameters, or 404 |
| `PUT /events/{code}` | Validate and save prepared inputs at a new revision |
| `POST /events/{code}/run` | Recompute from the supplied priors and save the current revision's result |
| `GET /events/{code}` | Read the current revision's completed result, or 404 |
| `PUT /forecasts/{code}` | Validate and save a complete event snapshot at a new revision |
| `POST /forecasts/{code}/step` | Advance or resume one bounded Monte Carlo batch |
| `GET /forecasts/{code}` | Read current progress or the completed event forecast, or 404 |

Recomputing starts from the input priors so scores are not applied twice. An input correction invalidates the old
result. Publication checks the input revision in the write statement so an older computation cannot overwrite a
new revision. A concurrent input change returns 409 and requires another run.

Inputs are capped at 128 teams, 1,000 matches and 512,000 bytes. Rule-pack bracket coverage can impose a smaller team
limit. Independent match forecasts use score-draw batches of 256. Event input is buffered as one bounded JSON document.
Season replay keeps a bounded initialization prefix and one event in memory, rather than buffering all season matches.

This is an unauthenticated local development endpoint. Remote publication and public mutation endpoints are not
configured. Local success does not establish that the engine fits the production 128 MB memory limit.

## Tests

```powershell
uv run python prepare.py
uv run pytest
uv run ruff check src/entry.py src/compute.py src/snapshot.py src/forecast.py src/forecast_store.py src/first_event.py src/season.py prepare.py tests smoke.py import_event.py replay_season.py
```

The unit tests check ratings against a closed-form ridge solution, simultaneous EPA updates, deterministic reruns
and invalid inputs. Event tests compare JSON checkpoint/resume with the native runner, generated schedules and fixed
published alliances. SQL tests reject duplicate writes and obsolete revisions and engines. `smoke.py` additionally
exercises the real local Worker and D1 binding, including unchanged imports, source corrections and clearing obsolete
source attribution. Import tests cover foul subtraction, missing results, station order, no-shows and surrogates.
Season tests compare event checkpoints with one native replay, exercise the initialization window, and verify suffix
invalidation, configuration and engine resets, stale-write rejection and prior revision checks. The smoke check also
replays a synthetic season through real local D1, compares native pre-event and post-event EPA, and corrects an earlier score.
