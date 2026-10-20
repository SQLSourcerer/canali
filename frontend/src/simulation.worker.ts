/// <reference lib="webworker" />

// Kept separate from the page bundle; Python and numerical packages load on demand.
const RUNTIME = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
let busy = false;
let runtime: any;

async function initialize(engineUrl: string, expectedHash: string) {
  self.postMessage({
    kind: "loading",
    message: "Downloading Python and numerical libraries…",
  });
  const { loadPyodide } = await import(
    /* @vite-ignore */ `${RUNTIME}pyodide.mjs`
  );
  const py = await loadPyodide({ indexURL: RUNTIME });
  await py.loadPackage(["numpy", "scipy", "pydantic"]);
  const response = await fetch(engineUrl);
  if (!response.ok)
    throw new Error("The simulation engine could not be downloaded.");
  const archive = new Uint8Array(await response.arrayBuffer());
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", archive));
  const actualHash = Array.from(digest, (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  if (actualHash !== expectedHash)
    throw new Error(
      "The simulation engine changed. Reload the page and try again.",
    );
  py.unpackArchive(archive, "zip", { extractDir: "/canali" });
  py.runPython(`import sys, json
sys.path.insert(0, '/canali')
from snapshot import EventSnapshot
from forecast import advance
checkpoint = None
`);
  return py;
}

self.onmessage = async ({ data }) => {
  if (busy) return;
  busy = true;
  try {
    runtime ??= await initialize(data.engineUrl, data.engineHash);
    runtime.globals.set("snapshot_json", JSON.stringify(data.snapshot));
    runtime.runPython(
      "snapshot = EventSnapshot.model_validate_json(snapshot_json)\ncheckpoint = None",
    );
    while (true) {
      const raw = runtime.runPython(
        "checkpoint, report = advance(snapshot, checkpoint)\njson.dumps(report)",
      );
      const report = JSON.parse(raw);
      self.postMessage({ kind: "progress", ...report });
      if (report.status !== "running") break;
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  } catch (error) {
    self.postMessage({
      kind: "error",
      message: error instanceof Error ? error.message : String(error),
    });
  } finally {
    busy = false;
  }
};
