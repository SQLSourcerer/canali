# Python Worker + D1

Runs prepared event inputs through the existing Python EPA update, pRidge estimator and score-sampling code, saving
the results in a local D1 database. This is the first slice of the hosting port, alongside the Postgres warehouse.

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

The smoke check uploads the synthetic fixture, computes ratings and forecasts, reads persisted results, repeats a
run, corrects a score and checks invalid-input handling. No source-data credentials, Cloudflare login, Docker or
remote database are needed. `wrangler.toml` contains a local database ID placeholder. Keep the explicit `--local`
flag on database commands.

The Worker has its own Python 3.14 environment; the existing workspace remains on Python 3.12. Pywrangler prepares
the WebAssembly dependencies separately in `python_modules/`, with versions recorded in `pylock.toml`. The custom
build copies the three numerical modules from their existing source directories; edit those sources rather than
the ignored copies under `src/`. Package and runtime support must also be checked on Cloudflare before deployment.

## Event input

`fixtures/event.json` is a synthetic prepared event, not an upstream API payload. It supplies:

- Teams' pre-event EPA totals and prior qualification-match counts.
- Qualification matches in increasing ordinal order, with non-foul scores or two null scores for an unplayed match.
- EPA K/M schedules, a ridge penalty and fitted score-model coefficients.
- A random seed and the number of score draws per remaining match.

The EPA and pRidge calculations use the supplied priors; initialization, layoff adjustment and season normalization
must happen before preparing those inputs. One or two rated teams per alliance are supported. The prototype computes
total ratings only. It does not yet port component ratings, ingestion, weekly calibration, event standings,
alliance selection, awards, advancement or regional season simulations.

## HTTP surface

| Request | Result |
| --- | --- |
| `GET /health` | Runtime package versions |
| `PUT /events/{code}` | Validate and save prepared inputs at a new revision |
| `POST /events/{code}/run` | Recompute from the supplied priors and save the current revision's result |
| `GET /events/{code}` | Read the current revision's completed result, or 404 |

Recomputing starts from the input priors so scores are not applied twice. An input correction invalidates the old
result. Publication checks the input revision in the write statement so an older computation cannot overwrite a
new revision. A concurrent input change returns 409 and requires another run.

Inputs are capped at 128 teams, 1,000 matches and 512,000 bytes. Monte Carlo draws use batches of 256 and retain only
outcome counts. Event input is buffered as one bounded JSON document; this does not yet test season-wide streaming.

This is an unauthenticated local development endpoint. Remote publication and public mutation endpoints are not
configured. Local success does not establish that the engine fits the production 128 MB memory limit.

## Tests

```powershell
uv run python prepare.py
uv run pytest
uv run ruff check src/entry.py src/compute.py prepare.py tests smoke.py
```

The unit tests check ratings against a closed-form ridge solution, simultaneous EPA updates, deterministic reruns
and invalid inputs. `smoke.py` additionally exercises the real local Worker and D1 binding.

Fresh FTC Events ingestion will need its username and token when that part is ported. Preserve those as local
secrets rather than putting credentials in fixtures or source files.
