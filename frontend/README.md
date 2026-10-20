# Canali frontend

Vite + Svelte 5, served as static files. The event page reads a published forecast and snapshot; viewing shared
results does not load Python or call the private computation Worker. The Pennsylvania season page lists competitions
from FIRST, with dates, venues, event filters and forecast availability. Stable URLs use `/seasons/2025/USPA` and
`/events/2025/USPAHAQ1`. A custom scenario loads Pyodide in a module
Web Worker and runs the same Python simulator on the visitor's device.

## Run locally

From the repository root, prepare the synthetic demonstration and shared engine archive:

```powershell
uv run python frontend/prepare.py
cd frontend
npm ci
npm run dev
```

Open the local address printed by Vite. The default event has synthetic team numbers, model coefficients and
published progress, visibly labeled as demonstration data. It is not a calibrated prediction of a real event.
The root Python environment needs the existing project dependencies. Use Node.js 22.18 or later.

## Publish from D1

The native publisher fetches public competition metadata from FIRST and reads forecasts through the private Worker's
authenticated `/forecasts/{season}-{code}/export` route. FIRST credentials remain in the existing warehouse settings.
Set the benchmark token in the command terminal, using the same value as the Worker's secret:

```powershell
$env:CANALI_BENCHMARK_TOKEN = Read-Host 'Benchmark token' -MaskInput
uv run python frontend/publish.py 2025 --region USPA --base-url https://canali-benchmark.mjhanson.workers.dev --label "Historical replay · demo models, uniform priors, no advancement assumptions"
```

For local D1, use a loopback `--base-url`, such as `http://127.0.0.1:8787`. The token is unnecessary with the default
local Worker. The publisher does not ingest matches, rate events, assemble snapshots or start simulations; those
steps must already have run through the existing Worker commands. The publication label is required so provisional
model assumptions and historical cutoffs stay visible.

The export query joins each input to its matching revision and engine checkpoint in one D1 statement, with the same
season-revision guards used by result reads. Running or exhausted runs expose status without a publishable snapshot.
The publisher validates the local engine version, snapshot, result roster and FIRST team roster, then publishes team
names with the frozen inputs and forecast. It records the source revision and snapshot hash. Missing forecasts remain
listed as not published; a source or engine correction removes them from the next catalog until recomputed.
Publication is a snapshot: an already deployed static forecast remains visible until the next export and deploy.

`public/generated/catalog.json` points to content-addressed event JSON and engine TAR files. The catalog is replaced
only after the export succeeds; authentication, engine or roster failures leave the existing catalog intact. Immutable
asset URLs keep a browser's custom simulation tied to the published forecast it loaded. Re-exporting never recomputes
the Monte Carlo. Old hashed assets can be removed from the local generated directory when no retained catalog uses
them. The default publisher includes scrimmages, qualifiers, championships and off-season events, excluding kickoffs.

## Prepare a standalone demonstration

The exporter can use a frozen snapshot and its completed Worker report, such as the files produced by
`worker/assemble_forecast.py --run`. From the repository root:

```powershell
uv run python frontend/prepare.py --snapshot var/worker-forecast/2025-USNJCMPPKWY/snapshot.json --result var/worker-forecast/2025-USNJCMPPKWY/result.json --name "Parkway Division" --label "Historical replay · sample model coefficients"
```

Provide the report for that exact snapshot; the exporter validates the snapshot and checks that result teams match,
but the current Worker report does not carry a snapshot hash. Omitting `--result` computes a matching result natively.
Keep the label explicit about historical cutoffs and provisional or demonstration models. The exporter clears the
snapshot's local season-revision dependency, bundles only the simulator and rule-pack modules, and writes
`public/generated/catalog.json` and content-addressed event/engine assets. Generated assets are ignored by Git. Rebuild them when Python sources
or published inputs change; the archive hash prevents silently running a different engine against a cached snapshot.

Engine packaging writes a deterministic, uncompressed `engine-<hash>.tar`. Cloudflare's static `_headers` rule sets
`Content-Encoding: br` and `Content-Type: application/x-tar`, causing Cloudflare to apply HTTP Brotli compression.
The browser decodes the response before JavaScript reads it; the SHA-256 hash covers the decoded TAR bytes,
which Pyodide extracts directly. Vite dev/preview serves the same TAR without HTTP compression. No build-time
encoder, custom server handler or browser decoder is needed. The production delivery path requires a browser
that supports Brotli HTTP decoding. Deployment checks should verify both the wire encoding and decoded hash.

## Deploy

The public deployment is [canali-frontend.mjhanson.workers.dev](https://canali-frontend.mjhanson.workers.dev).

The frontend uses Cloudflare Workers Static Assets with a single-page application fallback for event URLs. From
`frontend/`, after exporting the catalog:

```powershell
npm ci
npm run check
npm test
npm run build
node ../worker/node_modules/wrangler/bin/wrangler.js deploy --config wrangler.toml
```

The deployment is named `canali-frontend`; it has no D1 binding or credentials. Its static asset set is published
together so event snapshots and engine files stay consistent. Generated forecasts are public, while mutation and
export endpoints on the Python backend remain private. No Cloudflare account token, benchmark bearer token or FIRST
credential belongs in frontend code, Vite environment variables or published JSON. Export/build/deploy is currently
an operator command, rather than a scheduled publication process.

## Custom simulations

The first run downloads Pyodide 314.0.7, NumPy, SciPy and Pydantic from the pinned jsDelivr distribution. The page
remains responsive during downloads and computation. A team-strength adjustment scales that team's scoring components
proportionally between 50% and 150%; official played results and other team ratings remain fixed. The caller chooses
1,000 or 5,000 iterations. Fixed-size exploratory runs report the simulator's standard error rather than promising a
particular convergence tolerance. The random seed stays fixed to support comparisons.

The Python Worker and browser use the same `snapshot.py`, `forecast.advance` and simulator sources. Python is loaded
only after the visitor requests a custom simulation. Progress arrives after each bounded batch. Cancel terminates the
Web Worker, including an in-progress Python call; a later run reloads the runtime. Completed scenarios stay in page
memory, separate from the shared forecast, and are discarded on reload. Browser memory and speed depend on the device;
mobile performance is not yet characterized. No cross-origin-isolation headers or shared-memory interrupt support are
required. Network access is needed for the first runtime download.

The table supplies the first useful view without a chart dependency. Use TanStack Charts if a later slice adds
rank distributions or rating histories.

## Checks

```powershell
npm run check
npm test
npm run build
```

From the repository root, Python publication and D1 export tests can be run with:

```powershell
uv run pytest -c worker/pyproject.toml worker/tests frontend/tests/test_publication.py --basetemp var/frontend/test-tmp
```

Model tests check scenario isolation, bounds, stable ranking and missing values. Browser verification should include
an unchanged 100% scenario, changed strength, cancellation, another run after cancellation, and a narrow viewport.
After packaging changes, also compare browser results with the native result for an identical snapshot and seed.
Route tests distinguish season, event and unknown URLs. Publication tests check deterministic engine bundles,
matching revisions and rosters, missing forecasts and preservation of the existing catalog on failure. D1 export
tests reject obsolete inputs, engines and season dependencies, and withhold unfinished snapshots.
