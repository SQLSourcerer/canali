import test from "node:test";
import assert from "node:assert/strict";
import {
  scenarioSnapshot,
  rankedTeams,
  percent,
  type Snapshot,
} from "../src/model.ts";

test("what-if scales only the chosen team and preserves official results and source inputs", () => {
  const source = {
    field: { predicted: { "1": { auto: 20, teleop: 80 }, "2": { auto: 10 } } },
    progress: { played: [true, false] },
    seed: 42,
  } as unknown as Snapshot;
  const changed = scenarioSnapshot(source, "1", 110, 1000);
  assert.equal(changed.field.predicted["1"].auto, 22);
  assert.equal(changed.field.predicted["1"].teleop, 88);
  assert.deepEqual(changed.field.predicted["2"], source.field.predicted["2"]);
  assert.deepEqual(changed.progress, source.progress);
  assert.equal(source.field.predicted["1"].auto, 20);
  assert.equal(changed.seed, source.seed);
  assert.equal(changed.min_iterations, changed.max_iterations);
  assert.throws(() => scenarioSnapshot(source, "3", 100, 1000));
  assert.throws(() => scenarioSnapshot(source, "1", NaN, 1000));
  assert.throws(() => scenarioSnapshot(source, "1", 100, 1e6));
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
