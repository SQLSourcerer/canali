<script lang="ts">
  import { onMount } from "svelte";
  import EventPage from "./EventPage.svelte";
  import SeasonPage from "./SeasonPage.svelte";
  import {
    formatDate,
    routeFor,
    statusLabel,
    type Catalog,
    type EventListing,
    type PublishedEvent,
  } from "./model";

  let catalog = $state<Catalog | null>(null);
  let listing = $state<EventListing | null>(null);
  let event = $state<PublishedEvent | null>(null);
  let ready = $state(false);
  let error = $state("");
  let notFound = $state(false);
  const seasonUrl = $derived(
    catalog ? `/seasons/${catalog.season}/${catalog.region}` : "/",
  );

  onMount(() => {
    const controller = new AbortController();
    async function read(url: string) {
      const response = await fetch(url, {
        cache: "no-cache",
        signal: controller.signal,
      });
      if (
        !response.ok ||
        !response.headers.get("content-type")?.includes("application/json")
      )
        throw new Error(
          "Published data is unavailable. Please try again later.",
        );
      return response.json();
    }
    async function load() {
      catalog = await read("/generated/catalog.json");
      const selected = routeFor(location.pathname, catalog!);
      if (!selected) {
        notFound = true;
        return;
      }
      if (selected === "season") return;
      listing = selected;
      if (selected.forecast_url) {
        const published: PublishedEvent = await read(selected.forecast_url);
        if (
          published.code !== selected.code ||
          published.season !== selected.season
        )
          throw new Error("The published event does not match this URL.");
        event = published;
      }
    }
    load()
      .catch((e) => {
        if (e.name !== "AbortError") error = e.message;
      })
      .finally(() => (ready = true));
    return () => controller.abort();
  });
</script>

<svelte:head
  ><title
    >{listing ? `${listing.name} · Canali` : "Pennsylvania FTC · Canali"}</title
  ></svelte:head
>
<header class="site-header">
  <a class="brand" href={seasonUrl} aria-label="Canali season home"
    ><span class="brand-mark" aria-hidden="true">c/</span><span
      >canali<span class="brand-dot">.</span></span
    ></a
  >
  <nav aria-label="Main navigation">
    <a class="active" href={seasonUrl}>Pennsylvania events</a>{#if event}<a
        href="#notes">How to read this</a
      >{/if}
  </nav>
  <span class="header-caption">FIRST TECH CHALLENGE</span>
</header>
{#if error}
  <main class="empty">
    <p class="eyebrow">DATA UNAVAILABLE</p>
    <h1>We couldn’t load this page.</h1>
    <p role="alert">{error}</p>
    <button onclick={() => location.reload()}>Try again</button>
  </main>
{:else if !ready || !catalog}
  <main class="empty" aria-busy="true">
    <p class="eyebrow">CANALI / PENNSYLVANIA</p>
    <h1>Loading the season…</h1>
  </main>
{:else if notFound}
  <main class="empty">
    <p class="eyebrow">PAGE NOT FOUND</p>
    <h1>This event isn’t in the published season.</h1>
    <a href={seasonUrl}>Browse Pennsylvania events →</a>
  </main>
{:else if event}
  <EventPage {event} />
{:else if listing}
  <main class="empty">
    <p class="eyebrow">{listing.type} / {formatDate(listing.date_start)}</p>
    <h1>{listing.name}</h1>
    <p class="status-pill">{statusLabel(listing.status)}</p>
    <p>{listing.city} · {listing.venue}</p>
    <p>
      A forecast has not been published for this event. Check the official
      source for competition results.
    </p>
    <div class="event-links">
      <a href={seasonUrl}>← All events</a>{#if listing.source_url}<a
          href={listing.source_url}
          target="_blank"
          rel="noreferrer">Official event results ↗</a
        >{/if}
    </div>
  </main>
{:else}
  <SeasonPage {catalog} />
{/if}
<footer>
  <span
    >canali<span class="brand-dot">.</span>
    <span class="footer-description">A clearer view of an uncertain field.</span
    ></span
  ><span>Independent FTC statistics</span>
</footer>
