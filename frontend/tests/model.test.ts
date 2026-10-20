import test from "node:test";
import assert from "node:assert/strict";
import {
  scenarioSnapshot,
  rankedTeams,
  percent,
  scenarioUrl,
  scenarioFromUrl,
  forecastChange,
  type PublishedEvent,
  type Snapshot,
} from "../src/model.ts";

test("what-if scales multiple chosen teams and preserves official results and source inputs", () => {
  const source = {
    field: {
      predicted: {
        "1": { auto: 20, teleop: 80 },
        "2": { auto: 10 },
        "3": { auto: 12 },
      },
    },
    progress: { played: [true, false] },
    seed: 42,
  } as unknown as Snapshot;
  const changed = scenarioSnapshot(source, { "1": 110, "2": 50 }, 1000);
  assert.equal(changed.field.predicted["1"].auto, 22);
  assert.equal(changed.field.predicted["1"].teleop, 88);
  assert.equal(changed.field.predicted["2"].auto, 5);
  assert.deepEqual(changed.field.predicted["3"], source.field.predicted["3"]);
  assert.deepEqual(changed.progress, source.progress);
  assert.equal(source.field.predicted["1"].auto, 20);
  assert.equal(changed.seed, source.seed);
  assert.equal(changed.min_iterations, changed.max_iterations);
  assert.throws(() => scenarioSnapshot(source, { "4": 100 }, 1000));
  assert.throws(() => scenarioSnapshot(source, { constructor: 100 }, 1000));
  assert.throws(() => scenarioSnapshot(source, { "1": NaN }, 1000));
  assert.throws(() => scenarioSnapshot(source, { "1": 100 }, 1e6));
  assert.deepEqual(scenarioSnapshot(source, {}, 1000).field, source.field);
});

test("scenario links round-trip inputs and reject malformed or mismatched publications", () => {
  const event = {
    source_snapshot_sha256: "snapshot1",
    engine_sha256: "engine1",
    snapshot: {
      field: { predicted: { "1": { auto: 10 }, "2": { auto: 20 } } },
    },
  } as unknown as PublishedEvent;
  const url = new URL(
    scenarioUrl("https://example.test/events/2025/A#notes", event, {
      strengths: { "1": 110, "2": 100 },
      iterations: 5000,
    }),
  );
  assert.equal(url.pathname, "/events/2025/A");
  assert.equal(url.hash, "");
  assert.deepEqual(scenarioFromUrl(url.search, event), {
    strengths: { "1": 110 },
    iterations: 5000,
  });
  assert.equal(scenarioFromUrl("", event), null);
  assert.throws(() => scenarioFromUrl("?scenario=%7Bbad", event), /invalid/);
  assert.throws(
    () => scenarioFromUrl(url.search, { ...event, engine_sha256: "engine2" }),
    /different/,
  );
  assert.throws(
    () =>
      scenarioFromUrl(url.search, {
        ...event,
        source_snapshot_sha256: "snapshot2",
      }),
    /different/,
  );
  const packet = JSON.parse(url.searchParams.get("scenario")!);
  for (const strengths of [
    null,
    [],
    { "1": 155 },
    { "1": "110" },
    { "1": 107 },
    { "99": 110 },
  ]) {
    url.searchParams.set("scenario", JSON.stringify({ ...packet, strengths }));
    assert.throws(() => scenarioFromUrl(url.search, event));
  }
  url.searchParams.set(
    "scenario",
    JSON.stringify({ ...packet, iterations: 1e9 }),
  );
  assert.throws(() => scenarioFromUrl(url.search, event));
  url.searchParams.set("scenario", JSON.stringify({ ...packet, v: 2 }));
  assert.throws(() => scenarioFromUrl(url.search, event), /invalid/);
});

test("comparison labels distinguish rank and percentage-point changes without negative zero", () => {
  assert.equal(forecastChange(2, 3.2), "-1.2");
  assert.equal(forecastChange(0.35, 0.2, true), "+15.0 pp");
  assert.equal(forecastChange(0.199999, 0.2, true), "0.0 pp");
  assert.equal(forecastChange(null, 2), "—");
});

test("ranking handles absent means, deterministic ties and unavailable probabilities", () => {
  const entries = rankedTeams({
    teams: {
      "10": { mean_rank: 2 },
      "2": { mean_rank: 2 },
      "1": { mean_rank: null },
    },
  } as any);
  assert.deepEqual(
    entries.map(([team]) => team),
    ["2", "10", "1"],
  );
  assert.equal(percent(null), "—");
  assert.equal(percent(0), "0.0%");
});
