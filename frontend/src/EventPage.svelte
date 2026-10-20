<script lang="ts">
  import { onMount } from "svelte";
  import {
    percent,
    rankedTeams,
    scenarioSnapshot,
    formatDate,
    type Forecast,
    type PublishedEvent,
  } from "./model";

  let { event }: { event: PublishedEvent } = $props();
  let team = $state("");
  let strength = $state(100);
  let iterations = $state(1000);
  let running = $state(false);
  let progress = $state(0);
  let message = $state("");
  let simulationError = $state("");
  let custom = $state<Forecast | null>(null);
  let customLabel = $state("");
  let viewingCustom = $state(false);
  let worker: Worker | null = null;
  const shown = $derived(viewingCustom && custom ? custom : event.forecast);
  const rows = $derived(shown ? rankedTeams(shown) : []);
  const total = $derived(
    event ? Object.keys(event.snapshot.field.predicted).length : 0,
  );
  const played = $derived(
    event?.snapshot.progress?.played.filter(Boolean).length ?? 0,
  );
  const scheduled = $derived(event?.snapshot.schedule?.stations.length ?? null);

  onMount(() => {
    team = rankedTeams(event.forecast)[0][0];
    return () => {
      worker?.terminate();
    };
  });

  function runScenario() {
    if (!event || running) return;
    simulationError = "";
    try {
      const snapshot = scenarioSnapshot(
        $state.snapshot(event.snapshot),
        team,
        strength,
        iterations,
      );
      const label = `Team ${team} · ${strength}% of published strength`;
      running = true;
      progress = 0;
      message = worker
        ? "Starting your simulation…"
        : "Preparing your first simulation…";
      worker ??= new Worker(
        new URL("./simulation.worker.ts", import.meta.url),
        { type: "module" },
      );
      worker.onerror = () => {
        running = false;
        simulationError =
          "The simulation worker stopped. Try again, or use a device with more available memory.";
        worker?.terminate();
        worker = null;
      };
      worker.onmessage = ({ data }) => {
        if (data.kind === "loading") message = data.message;
        if (data.kind === "error") {
          running = false;
          simulationError = data.message;
        }
        if (data.kind === "progress") {
          progress = data.iterations;
          message = `${progress.toLocaleString()} of ${iterations.toLocaleString()} simulations`;
          if (data.status === "complete") {
            custom = data.result;
            customLabel = label;
            viewingCustom = true;
            running = false;
          } else if (data.status === "exhausted") {
            simulationError =
              "The simulation reached its limit without a result.";
            running = false;
          }
        }
      };
      worker.postMessage({
        snapshot,
        engineUrl: event.engine_url,
        engineHash: event.engine_sha256,
      });
    } catch (error) {
      running = false;
      simulationError = error instanceof Error ? error.message : String(error);
    }
  }

  function cancel() {
    worker?.terminate();
    worker = null;
    running = false;
    message = "Simulation cancelled.";
  }

  function delta(value: number, baseline: number): string {
    const difference = (value - baseline) * 100;
    return `${difference > 0 ? "+" : ""}${difference.toFixed(1)} pp`;
  }
</script>

<svelte:head
  ><title>{event ? `${event.name} · Canali` : "Canali · FTC forecasts"}</title
  ></svelte:head
>

<main>
  <p class="breadcrumb">
    <a href={`/seasons/${event.season}/USPA`}
      >Pennsylvania / {event.season}–{String(event.season + 1).slice(2)}</a
    >
    / {event.type}
  </p>
  <section class="event-heading" aria-labelledby="event-title">
    <div>
      <p class="eyebrow">
        FTC / {event.snapshot.rule_pack.season}–{String(
          event.snapshot.rule_pack.season + 1,
        ).slice(2)} / {event.snapshot.rule_pack.game}
      </p>
      <h1 id="event-title">{event.name}</h1>
      <p class="intro">
        {event.city}{event.venue ? ` · ${event.venue}` : ""} · {formatDate(
          event.date_start,
        )}
      </p>
    </div>
    <div class="published">
      <span class="status-dot" aria-hidden="true"></span> Published snapshot<br
      /><span
        >{new Date(event.published_at).toLocaleString(undefined, {
          dateStyle: "medium",
          timeStyle: "short",
        })}</span
      >
    </div>
  </section>

  <p class="data-label"><span aria-hidden="true">◈</span> {event.label}</p>

  <section class="metrics" aria-label="Event summary">
    <div>
      <span class="eyebrow">THE FIELD</span><strong
        >{total}<small>teams</small></strong
      >
    </div>
    <div>
      <span class="eyebrow">QUALIFICATION PROGRESS</span><strong
        >{played}<small
          >{scheduled === null
            ? "schedule not published"
            : `of ${scheduled} matches played`}</small
        ></strong
      >
    </div>
    <div>
      <span class="eyebrow">SIMULATIONS</span><strong
        >{shown.iterations.toLocaleString()}<small
          >{viewingCustom ? "your scenario" : "shared forecast"}</small
        ></strong
      >
    </div>
  </section>

  <div class="workspace">
    <section
      id="forecast"
      class="forecast-panel"
      aria-labelledby="forecast-title"
    >
      <div class="panel-heading">
        <div>
          <p class="eyebrow">THE OUTLOOK</p>
          <h2 id="forecast-title">Qualification & beyond</h2>
        </div>
        <span class="count-badge">{total} teams</span>
      </div>
      <div class="view-tabs" aria-label="Forecast view">
        <button
          class:chosen={!viewingCustom}
          aria-pressed={!viewingCustom}
          onclick={() => (viewingCustom = false)}>Shared forecast</button
        >
        <button
          class:chosen={viewingCustom}
          aria-pressed={viewingCustom}
          disabled={!custom}
          onclick={() => (viewingCustom = true)}
          >Your scenario {#if custom}<span aria-hidden="true">↗</span
            >{/if}</button
        >
      </div>
      {#if viewingCustom}<p class="scenario-label">
          {customLabel} · calculated on your device
        </p>{/if}
      <div class="table-scroll">
        <table>
          <caption class="sr-only"
            >{viewingCustom ? "Custom" : "Shared"} team forecast, ordered by average
            qualification rank</caption
          >
          <thead
            ><tr
              ><th scope="col">Team</th><th scope="col">Avg. rank</th><th
                scope="col">Captain</th
              ><th scope="col">Picked</th><th scope="col">Win event</th><th
                scope="col">Advance</th
              >{#if viewingCustom}<th scope="col">Win change</th>{/if}</tr
            ></thead
          >
          <tbody>
            {#each rows as [number, summary] (number)}
              <tr class:selected={team === number}>
                <th scope="row"
                  ><button
                    class="team-button"
                    title={event.teams[number]}
                    disabled={running}
                    onclick={() => (team = number)}
                    ><span class="team-symbol" aria-hidden="true">↗</span>
                    {number}<span class="team-name">{event.teams[number]}</span
                    ></button
                  ></th
                >
                <td class="rank-value"
                  >{summary.mean_rank?.toFixed(1) ?? "—"}</td
                >
                <td>{percent(summary.p_captain)}</td><td
                  >{percent(summary.p_selected)}</td
                >
                <td class="win-value">{percent(summary.p_win)}</td><td
                  >{percent(summary.p_advance)}</td
                >
                {#if viewingCustom}<td class="delta"
                    >{delta(
                      summary.p_win,
                      event.forecast.teams[number].p_win,
                    )}</td
                  >{/if}
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <p class="table-note">
        Average rank is a simulation average, not a current standing. Select a
        team to explore a scenario.
      </p>
    </section>

    <aside class="scenario-panel" aria-labelledby="scenario-title">
      <div class="scenario-icon" aria-hidden="true">↗</div>
      <p class="eyebrow">CHANGE AN ASSUMPTION</p>
      <h2 id="scenario-title">What if?</h2>
      <p class="scenario-intro">
        Explore how a team’s performance could change the event.
      </p>
      <form
        onsubmit={(e) => {
          e.preventDefault();
          runScenario();
        }}
      >
        <label for="team">Team</label>
        <select id="team" bind:value={team} disabled={running}
          >{#each Object.keys(event.snapshot.field.predicted).sort((a, b) => Number(a) - Number(b)) as number}<option
              value={number}>{number} · {event.teams[number]}</option
            >{/each}</select
        >
        <div class="strength-label">
          <label for="strength">Predicted strength</label><output for="strength"
            >{strength}%</output
          >
        </div>
        <input
          id="strength"
          type="range"
          min="50"
          max="150"
          step="5"
          bind:value={strength}
          disabled={running}
        />
        <div class="range-labels">
          <span>50%</span><span>Published: 100%</span><span>150%</span>
        </div>
        <p class="field-note">
          Scales this team’s scoring components equally. Played matches stay
          fixed.
        </p>
        <label for="iterations">Simulations</label>
        <select id="iterations" bind:value={iterations} disabled={running}
          ><option value={1000}>1,000 · quick exploration</option><option
            value={5000}>5,000 · more precision</option
          ></select
        >
        <button class="run-button" type="submit" disabled={running}
          >{running ? "Simulating…" : "Run on my device"}<span
            aria-hidden="true">↗</span
          ></button
        >
        {#if running}<progress
            max={iterations}
            value={progress}
            aria-label="Simulation progress"
          ></progress><button
            class="cancel-button"
            type="button"
            onclick={cancel}>Cancel simulation</button
          >{/if}
      </form>
      <p class="progress-message" role="status" aria-live="polite">
        {message}
      </p>
      {#if simulationError}<p class="error-message" role="alert">
          {simulationError}
        </p>{/if}
      <div class="device-note">
        <span aria-hidden="true">⊙</span>
        <p>
          Calculations stay on this device. Your first run downloads Python and
          its numerical libraries; this may take a moment.
        </p>
      </div>
    </aside>
  </div>

  <section id="notes" class="reading-notes" aria-labelledby="notes-title">
    <div>
      <p class="eyebrow">READING THE FORECAST</p>
      <h2 id="notes-title">Probabilities, not promises.</h2>
    </div>
    <div>
      <p>
        <strong>Captain / Picked</strong> estimate alliance selection.
        <strong>Win event</strong>
        estimates a playoff victory. <strong>Advance</strong> is shown only when advancement
        slots are supplied.
      </p>
      <p>
        Judged awards and selection behavior are modeled assumptions. Smaller
        differences may be simulation noise: this result’s largest tracked
        standard error is <strong
          >{(shown.standard_error * 100).toFixed(1)} percentage points</strong
        >.
      </p>
    </div>
  </section>
</main>
