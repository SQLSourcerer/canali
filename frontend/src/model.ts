export type TeamSummary = {
  mean_rank: number | null;
  p_captain: number;
  p_selected: number;
  p_win: number;
  p_advance: number | null;
};

export type Forecast = {
  iterations: number;
  standard_error: number;
  teams: Record<string, TeamSummary>;
};
export type Snapshot = {
  field: {
    predicted: Record<string, Record<string, number>>;
    [key: string]: unknown;
  };
  rule_pack: { season: number; game: string };
  schedule: { stations: number[][][] } | null;
  progress: { played: boolean[] } | null;
  slots: unknown;
  seed: number;
  min_iterations: number;
  max_iterations: number;
  tolerance: number;
  [key: string]: unknown;
};
export type EventListing = {
  code: string;
  season: number;
  name: string;
  label: string;
  date_start: string | null;
  date_end: string | null;
  city: string;
  venue: string;
  type: string;
  source_url: string | null;
  published_at?: string;
  status: "complete" | "running" | "exhausted" | "unpublished";
  forecast_url: string | null;
  played?: number;
  scheduled?: number | null;
};
export type Catalog = {
  season: number;
  region: string;
  region_name: string;
  published_at: string;
  events: EventListing[];
};
export type PublishedEvent = Omit<
  EventListing,
  "status" | "forecast_url" | "published_at"
> & {
  published_at: string;
  teams: Record<string, string>;
  source_revision: number | null;
  source_snapshot_sha256: string;
  engine_url: string;
  engine_sha256: string;
  snapshot: Snapshot;
  forecast: Forecast;
};

export function formatDate(value: string | null): string {
  return value
    ? new Date(`${value}T12:00:00`).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "Date not set";
}

export function statusLabel(status: EventListing["status"]): string {
  return {
    complete: "Forecast available",
    running: "Computing forecast",
    exhausted: "More simulations needed",
    unpublished: "Not published",
  }[status];
}

export function routeFor(
  path: string,
  catalog: Catalog,
): EventListing | "season" | null {
  const clean = path.replace(/\/$/, "") || "/";
  if (clean === "/" || clean === `/seasons/${catalog.season}/${catalog.region}`)
    return "season";
  return (
    catalog.events.find((e) => clean === `/events/${e.season}/${e.code}`) ??
    null
  );
}

export function scenarioSnapshot(
  source: Snapshot,
  strengths: Record<string, number>,
  iterations: number,
): Snapshot {
  const adjustments = scenarioStrengths(source, strengths);
  scenarioIterations(iterations);
  const copy = structuredClone(source);
  for (const [team, strength] of Object.entries(adjustments)) {
    copy.field.predicted[team] = Object.fromEntries(
      Object.entries(copy.field.predicted[team]).map(([name, value]) => [
        name,
        (value * strength) / 100,
      ]),
    );
  }
  copy.min_iterations = iterations;
  copy.max_iterations = iterations;
  // Fixed-size exploratory runs still report their Monte Carlo standard error.
  copy.tolerance = 0.5;
  return copy;
}

export type Scenario = {
  strengths: Record<string, number>;
  iterations: number;
};

function scenarioIterations(iterations: number) {
  if (![1000, 5000].includes(iterations))
    throw new Error("Choose 1,000 or 5,000 simulations.");
  return iterations;
}

function scenarioStrengths(
  source: Snapshot,
  strengths: Record<string, number>,
) {
  if (!strengths || typeof strengths !== "object" || Array.isArray(strengths))
    throw new Error("Scenario adjustments must be a set of team strengths.");
  const normalized: Record<string, number> = {};
  for (const [team, strength] of Object.entries(strengths)) {
    if (!Object.hasOwn(source.field.predicted, team))
      throw new Error("Choose teams in this event.");
    if (
      !Number.isFinite(strength) ||
      strength < 50 ||
      strength > 150 ||
      strength % 5 !== 0
    )
      throw new Error("Strength must be 50–150% in steps of 5%.");
    if (strength !== 100) normalized[team] = strength;
  }
  return normalized;
}

export function scenarioUrl(
  href: string,
  event: PublishedEvent,
  scenario: Scenario,
): string {
  scenarioIterations(scenario.iterations);
  const url = new URL(href);
  url.hash = "";
  url.searchParams.set(
    "scenario",
    JSON.stringify({
      v: 1,
      snapshot: event.source_snapshot_sha256,
      engine: event.engine_sha256,
      strengths: scenarioStrengths(event.snapshot, scenario.strengths),
      iterations: scenario.iterations,
    }),
  );
  return url.href;
}

export function scenarioFromUrl(
  search: string,
  event: PublishedEvent,
): Scenario | null {
  const value = new URLSearchParams(search).get("scenario");
  if (value === null) return null;
  let shared;
  try {
    if (value.length > 16000) throw new Error("too long");
    shared = JSON.parse(value);
    if (!shared || shared.v !== 1) throw new Error("unknown format");
  } catch {
    throw new Error(
      "This scenario link is invalid. Start a new scenario below.",
    );
  }
  if (
    shared.snapshot !== event.source_snapshot_sha256 ||
    shared.engine !== event.engine_sha256
  )
    throw new Error(
      "This link uses a different version of the published forecast. Start a new scenario below.",
    );
  return {
    strengths: scenarioStrengths(event.snapshot, shared.strengths),
    iterations: scenarioIterations(shared.iterations),
  };
}

export function forecastChange(
  value: number | null,
  baseline: number | null,
  probability = false,
): string {
  if (value === null || baseline === null) return "—";
  const difference =
    Math.round((value - baseline) * (probability ? 1000 : 10)) / 10;
  return `${difference > 0 ? "+" : ""}${difference.toFixed(1)}${probability ? " pp" : ""}`;
}

export function rankedTeams(forecast: Forecast): [string, TeamSummary][] {
  return Object.entries(forecast.teams).sort(
    ([a, left], [b, right]) =>
      (left.mean_rank ?? Infinity) - (right.mean_rank ?? Infinity) ||
      Number(a) - Number(b),
  );
}

export function percent(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}
