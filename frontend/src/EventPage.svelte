<script lang="ts">
  import { onMount } from "svelte";
  import {
    percent,
    rankedTeams,
    scenarioSnapshot,
    scenarioUrl,
    scenarioFromUrl,
    forecastChange,
    formatDate,
    type Forecast,
    type PublishedEvent,
  } from "./model";

  let { event }: { event: PublishedEvent } = $props();
  let team = $state("");
  let strengths = $state<Record<string, number>>({});
  let iterations = $state(1000);
  let running = $state(false);
  let progress = $state(0);
  let message = $state("");
  let simulationError = $state("");
  let custom = $state<Forecast | null>(null);
  let customLabel = $state("");
  let viewingCustom = $state(false);
  let customKey = $state("");
  let sharedLink = $state("");
  let shareMessage = $state("");
  let linkMessage = $state("");
  const draftKey = $derived(JSON.stringify([strengths, iterations]));
  const edits = $derived(Object.entries(strengths));
  const stale = $derived(custom !== null && customKey !== draftKey);
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
    try {
      const shared = scenarioFromUrl(location.search, event);
      if (shared) {
        strengths = shared.strengths;
        iterations = shared.iterations;
        team = Object.keys(strengths)[0] ?? team;
        linkMessage =
          "Shared scenario loaded. Review the adjustments, then run it on your device.";
      }
    } catch (error) {
      simulationError = error instanceof Error ? error.message : String(error);
    }
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
        $state.snapshot(strengths),
        iterations,
      );
      const label = edits.length
        ? edits
            .map(([number, value]) => `Team ${number}: ${value}%`)
            .join(" · ")
        : "Published team strengths";
      const key = draftKey;
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
            customKey = key;
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

  function setStrength(number: string, value: number) {
    const updated = { ...strengths };
    if (value === 100) delete updated[number];
    else updated[number] = value;
    strengths = updated;
    sharedLink = "";
    shareMessage = "";
  }

  function resetAll() {
    strengths = {};
    iterations = 1000;
    custom = null;
    customKey = "";
    viewingCustom = false;
    message = "";
    simulationError = "";
    linkMessage = "";
    sharedLink = "";
    shareMessage = "";
  }

  async function shareScenario() {
    try {
      sharedLink = scenarioUrl(location.href, event, { strengths, iterations });
      try {
        await navigator.clipboard.writeText(sharedLink);
        shareMessage = "Scenario link copied.";
      } catch {
        shareMessage = "Select and copy the link below.";
      }
    } catch (error) {
      simulationError = error instanceof Error ? error.message : String(error);
    }
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
        </p>
        {#if stale}<p class="draft-notice">
            These results are from your last run. Run the edited inputs to
            update them.
          </p>{/if}
      {/if}
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
              ></tr
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
                  ><span class="metric-value"
                    >{summary.mean_rank?.toFixed(1) ?? "—"}</span
                  >
                  {#if viewingCustom}<span
                      class="comparison-delta"
                      aria-label="Rank change"
                      >{forecastChange(
                        summary.mean_rank,
                        event.forecast.teams[number].mean_rank,
                      )}</span
                    >{/if}</td
                >
                <td
                  ><span class="metric-value">{percent(summary.p_captain)}</span
                  >
                  {#if viewingCustom}<span
                      class="comparison-delta"
                      aria-label="Captain probability change"
                      >{forecastChange(
                        summary.p_captain,
                        event.forecast.teams[number].p_captain,
                        true,
                      )}</span
                    >{/if}</td
                ><td>{percent(summary.p_selected)}</td>
                <td class="win-value"
                  ><span class="metric-value">{percent(summary.p_win)}</span>
                  {#if viewingCustom}<span
                      class="comparison-delta"
                      aria-label="Win probability change"
                      >{forecastChange(
                        summary.p_win,
                        event.forecast.teams[number].p_win,
                        true,
                      )}</span
                    >{/if}</td
                ><td>{percent(summary.p_advance)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <p class="table-note">
        Average rank is a simulation average, not a current standing. Select a
        team to explore a scenario.
        {#if viewingCustom}Changes are scenario minus shared forecast; lower
          ranks are better. Probability changes are in percentage points (pp).{/if}
      </p>
    </section>

    <aside class="scenario-panel" aria-labelledby="scenario-title">
      <div class="scenario-icon" aria-hidden="true">↗</div>
      <p class="eyebrow">CHANGE AN ASSUMPTION</p>
      <h2 id="scenario-title">What if?</h2>
      <p class="scenario-intro">
        Adjust several teams to explore how their performance could change the
        event.
      </p>
      {#if linkMessage}<p class="scenario-link-notice" role="status">
          {linkMessage}
        </p>{/if}
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
            >{strengths[team] ?? 100}%</output
          >
        </div>
        <input
          id="strength"
          type="range"
          min="50"
          max="150"
          step="5"
          value={strengths[team] ?? 100}
          oninput={(e) => setStrength(team, Number(e.currentTarget.value))}
          disabled={running}
        />
        <div class="range-labels">
          <span>50%</span><span>Published: 100%</span><span>150%</span>
        </div>
        <p class="field-note">
          Scales this team’s scoring components equally. Played matches stay
          fixed. Select another team to add an adjustment.
        </p>
        <div class="adjustment-heading">
          <span>Adjusted teams · {edits.length}</span>
          <button
            type="button"
            class="text-button"
            onclick={resetAll}
            disabled={running}>Reset scenario</button
          >
        </div>
        {#if edits.length}<ul class="adjustments" aria-label="Adjusted teams">
            {#each edits as [number, value] (number)}<li>
                <span title={event.teams[number]}
                  ><strong>{number}</strong> · {value}%</span
                >
                <button
                  type="button"
                  class="text-button"
                  aria-label={`Reset team ${number}`}
                  disabled={running}
                  onclick={() => setStrength(number, 100)}>Reset</button
                >
              </li>{/each}
          </ul>{:else}<p class="field-note">
            All teams use their published strength.
          </p>{/if}
        <label for="iterations">Simulations</label>
        <select
          id="iterations"
          bind:value={iterations}
          disabled={running}
          onchange={() => {
            sharedLink = "";
            shareMessage = "";
          }}
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
      <div class="share-scenario">
        <button
          class="share-button"
          type="button"
          disabled={running}
          onclick={shareScenario}>Share these inputs</button
        >
        <p>
          Links share adjustments and simulation count. Open a link to review
          the inputs before running.
        </p>
        {#if sharedLink}<label class="sr-only" for="scenario-link"
            >Scenario link</label
          ><input
            id="scenario-link"
            readonly
            value={sharedLink}
            onclick={(e) => e.currentTarget.select()}
          />{/if}
        <p role="status">{shareMessage}</p>
      </div>
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
