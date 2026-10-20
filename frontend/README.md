# Canali frontend

Vite + Svelte 5, served as static files. The event page reads a published forecast and snapshot; viewing shared
results does not load Python or call the private computation Worker. A custom scenario loads Pyodide in a module
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

## Publish a prepared event

The exporter can use a frozen snapshot and its completed Worker report, such as the files produced by
`worker/assemble_forecast.py --run`. From the repository root:

```powershell
uv run python frontend/prepare.py --snapshot var/worker-forecast/2025-USNJCMPPKWY/snapshot.json --result var/worker-forecast/2025-USNJCMPPKWY/result.json --name "Parkway Division" --label "Historical replay · sample model coefficients"
```

Provide the report for that exact snapshot; the exporter validates the snapshot and checks that result teams match,
but the current Worker report does not carry a snapshot hash. Omitting `--result` computes a matching result natively.
Keep the label explicit about historical cutoffs and provisional or demonstration models. The exporter clears the
snapshot's local season-revision dependency, bundles only the simulator and rule-pack modules, and writes
`public/generated/event.json` and `engine.zip`. Generated assets are ignored by Git. Rebuild them when Python sources
or published inputs change; the archive hash prevents silently running a different engine against a cached snapshot.

`npm run build` produces `dist/`, suitable for Cloudflare Workers Static Assets or Pages. Publish the entire directory
together so the snapshot and its engine stay consistent. This slice does not deploy the frontend or automate event
publication. It exposes one frozen event at a time. No Cloudflare account token, benchmark bearer token or FIRST
credential belongs in frontend code, Vite environment variables or published JSON.

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

Model tests check scenario isolation, bounds, stable ranking and missing values. Browser verification should include
an unchanged 100% scenario, changed strength, cancellation, another run after cancellation, and a narrow viewport.
After packaging changes, also compare browser results with the native result for an identical snapshot and seed.
