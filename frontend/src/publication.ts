import type { EventListing } from "./model";

export const CATALOG_URL = "/generated/catalog.json";
export const CATALOG_REFRESH_MS = 60_000;

export async function readPublication<T>(
  url: string,
  signal?: AbortSignal,
  fetcher: typeof fetch = fetch,
): Promise<T> {
  const response = await fetcher(url, {
    cache: url === CATALOG_URL ? "no-cache" : "default",
    signal,
  });
  if (!response.ok || !response.headers.get("content-type")?.includes("application/json"))
    throw new Error("Published data is unavailable. Please try again later.");
  return response.json();
}

export function forecastChanged(current: EventListing, next: EventListing | null): boolean {
  return next === null || current.forecast_url !== next.forecast_url;
}
