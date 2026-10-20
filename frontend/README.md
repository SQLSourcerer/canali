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
remains responsive during downloads and computation. Each team-strength adjustment scales that team's scoring components
proportionally between 50% and 150% in steps of 5%. Adjustments accumulate across teams; individual resets restore a
team to 100%, and resetting the scenario clears all adjustments and custom results. Official played results and
unadjusted team ratings remain fixed. The caller chooses
1,000 or 5,000 iterations. Fixed-size exploratory runs report the simulator's standard error rather than promising a
particular convergence tolerance. The random seed stays fixed to support comparisons.

"Improve individual components" adds 0–100 whole predicted points to selected scoring components after the team's
overall percentage adjustment. It can improve a component whose published rating is zero. Component changes accumulate
across teams and are included in resets, labels and shared links. They affect the existing score, RP and award models;
the models are not refitted. Qualification tiebreaker components still use the score model's season-wide proportions.

The custom table shows changes in average rank, captain probability and event-win probability relative to the shared
forecast. Lower ranks are better; probability changes use percentage points. Editing inputs leaves the last completed
result visible with a notice until another run completes, and its label retains the adjustments used for that run.

"Share these inputs" copies a URL containing the team adjustments and simulation count, with a selectable link if
clipboard access is unavailable. Links identify the exact source snapshot and simulation engine. Opening one loads
the inputs for review without downloading Python or starting a run. A link for a changed snapshot or engine is rejected
with an explanation; forecasts remain available for browsing. Links share inputs, not computed results, and may stop
working after a publication changes. Scenario links are public and contain no credentials.

## Playoff partner comparisons

Choose a captain, two possible partners and an assumed alliance seed. Each trial simulates the remaining qualification
matches with the event model, keeping played results fixed. For each candidate it reserves the proposed pair, forms
the other alliances from the remaining teams in simulated qualification order using the pick model, inserts the pair
at the chosen seed, then plays the event's full playoff bracket using its score and foul models. The alternative partner
can therefore join an opposing alliance. Published alliance selection is replaced for this hypothetical comparison.

The results estimate winning the playoff, reaching the final and average playoff finish, conditional on that pair
and seed. They do not estimate whether a team becomes a captain, whether the partner is available at its pick, or
advancement and awards. Playoff scores add team ratings; robot-role compatibility and scoring synergy are not modeled.
Opposing alliances can change with the proposed partner. The display retains the exact inputs
used for the last completed run and marks results when the draft changes. The iteration count and all component and
team adjustments apply to both alternatives. "Share this comparison" includes these inputs and the pairing setup.

Comparisons support two-team playoff alliances and snapshots from before any playoff matches were played. Refusing
later snapshots avoids discarding actual playoff results. Both alternatives reuse the same qualification trial and
start their selection/playoff draws with the same per-trial random seed. Each probability reports its Monte Carlo
standard error; small differences can still be noise.

`partner_comparison.py` is included in the immutable browser TAR and runs through the same lazy-loaded Web Worker as
event forecasts. Its counters and RNG state advance in bounded batches. There is no additional server compute or
backend route. It currently obtains qualification trials through the complete event simulator, which also performs
an unused baseline playoff; a shared qualification helper would reduce work if larger comparisons become slow.

The Python Worker and browser use the same `snapshot.py`, `forecast.advance` and simulator sources. Python is loaded
only after the visitor requests a custom simulation. Progress arrives after each bounded batch. Cancel terminates the
Web Worker, including an in-progress Python call; a later run reloads the runtime. Completed scenarios stay in page
memory, separate from the shared forecast, and are discarded on reload. Browser memory and speed depend on the device;
mobile performance is not yet characterized. No cross-origin-isolation headers or shared-memory interrupt support are
required. Network access is needed for the first runtime download.

The table supplies the first useful view without a chart dependency. Use TanStack Charts if a later slice adds
rank distributions or rating histories.

## Autonomous LEAVE comparisons

For DECODE events with a published schedule, the autonomous LEAVE panel compares an entered current success rate
with an improved rate for one team. Both rates are assumptions supplied by the visitor; current reliability is not
inferred from EPA. This panel uses published team strengths independently of the generic component adjustments.
It reports expected added points per remaining appearance, paired average qualification ranks and their difference's
Monte Carlo standard error. Remaining matches are sorted by Movement RP probability gain and show alliance points,
Movement RP probability and total RP, including win/tie points. Surrogate appearances are marked and excluded from
the team's ranking score. Played results remain fixed; a team with no remaining matches is rejected.

`auto_leave.py` samples robot LEAVE outcomes explicitly (3 points each). Other robots' probabilities are their
leave component EPA divided by 3, clipped to 0–1. It estimates alliance BASE outcomes by interpolating between
adjacent legal totals, 0/5/10/15/30, with the mean equal to the summed base EPA clipped to 0–30. This is a simple
assumed distribution, not a fit to observed robot states. BASE and LEAVE draws are independent. The Movement RP
is awarded by comparing sampled BASE plus LEAVE points with the event tier's rule-pack threshold.
See [DECODE manual section 10.5.4](https://ftc-resources.firstinspires.org/ftc/archive/2026/game/cm-html/DECODE_Competition_Manual_TU32.htm).

Other points use the existing score distribution with leave and base components removed, then the sampled action
points are added back. AUTO tiebreaker points use the remaining autonomous share plus sampled LEAVE points;
BASE is accounted for separately. Other bonus RPs retain their existing models. Every trial shares all other
outcomes, including random ranking tiebreakers, between the two alternatives. Identical rates give identical
results. These comparisons use a different action model from the shared forecast, so their current-rate baseline
can differ from it. They estimate qualification impact only; playoff and alliance-selection probabilities are not
part of this comparison. Model assumptions can matter more than the displayed sampling error.

The helper is packaged in the browser TAR and runs in bounded batches through Pyodide. The page permits one
simulation at a time and releases the comparison's runtime on completion or cancellation. This first version has
no shareable LEAVE-scenario links and supports only DECODE.

## Checks

```powershell
npm run check
npm test
npm run build
```

From the repository root, Python publication and D1 export tests can be run with:

```powershell
uv run pytest -c worker/pyproject.toml worker/tests frontend/tests --basetemp var/frontend/test-tmp
```

Model tests check multi-team/component isolation, bounds, URL round trips, snapshot and engine matching, comparison labels,
stable ranking and missing values. Browser verification should include an unchanged 100% scenario, multiple changed
teams, individual and whole-scenario resets, sharing and reopening inputs, stale links, cancellation, another run
after cancellation, and a narrow viewport. Partner tests check reserved teams and seeds, unique alliance membership,
checkpoint continuation, candidate-order invariance and invalid requests. Browser verification also covers component
and partner link round trips and comparison results against the native helper.
After packaging changes, also compare browser results with the native result for an identical snapshot and seed.
Route tests distinguish season, event and unknown URLs. Publication tests check deterministic engine bundles,
matching revisions and rosters, missing forecasts and preservation of the existing catalog on failure. D1 export
tests reject obsolete inputs, engines and season dependencies, and withhold unfinished snapshots.
