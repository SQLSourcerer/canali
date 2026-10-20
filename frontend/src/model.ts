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
  team: string,
  strength: number,
  iterations: number,
): Snapshot {
  if (!source.field.predicted[team])
    throw new Error("Choose a team in this event.");
  if (!Number.isFinite(strength) || strength < 50 || strength > 150)
    throw new Error("Strength must be 50–150%.");
  if (![1000, 5000].includes(iterations))
    throw new Error("Choose 1,000 or 5,000 simulations.");
  const copy = structuredClone(source);
  copy.field.predicted[team] = Object.fromEntries(
    Object.entries(copy.field.predicted[team]).map(([name, value]) => [
      name,
      (value * strength) / 100,
    ]),
  );
  copy.min_iterations = iterations;
  copy.max_iterations = iterations;
  // Fixed-size exploratory runs still report their Monte Carlo standard error.
  copy.tolerance = 0.5;
  return copy;
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
