import assert from "node:assert/strict";
import test from "node:test";
import { CATALOG_URL, forecastChanged, readPublication } from "../src/publication.ts";
import type { EventListing } from "../src/model.ts";

test("catalog checks revalidate while immutable snapshots use the browser cache", async () => {
  const requests: [string, RequestInit][] = [];
  const fetcher = async (url: string, init: RequestInit) => {
    requests.push([url, init]);
    return Response.json({ ok: true });
  };
  await readPublication(CATALOG_URL, undefined, fetcher as typeof fetch);
  await readPublication("/generated/event-abc.json", undefined, fetcher as typeof fetch);
  assert.equal(requests[0][1].cache, "no-cache");
  assert.equal(requests[1][1].cache, "default");
  assert.ok(requests.every(([url]) => url.startsWith("/generated/")));
});

test("new and withdrawn forecasts are noticed without changing the loaded listing", () => {
  const current = { forecast_url: "/generated/event-old.json" } as EventListing;
  const before = structuredClone(current);
  assert.equal(forecastChanged(current, { ...current }), false);
  assert.equal(forecastChanged(current, { ...current, forecast_url: "/generated/event-new.json" }), true);
  assert.equal(forecastChanged(current, { ...current, forecast_url: null }), true);
  assert.equal(forecastChanged(current, null), true);
  assert.equal(forecastChanged({ ...current, forecast_url: null }, current), true);
  assert.deepEqual(current, before);
});

test("failed refreshes reject instead of returning a replacement publication", async () => {
  const fetcher = async () => new Response("unavailable", { status: 503 });
  await assert.rejects(readPublication(CATALOG_URL, undefined, fetcher as typeof fetch), /unavailable/);
});
