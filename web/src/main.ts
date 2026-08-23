/**
 * DOM wiring for index.html. Fetches a run's trace from the backend
 * (fetchTrace, proxied to uvicorn by vite.config.ts's dev server proxy so
 * there's no CORS to deal with), projects it (buildViewModel), and hands
 * the result to a Renderer — then wires the renderer's three callbacks
 * (status, stats, generation diff) to the DOM panels. No logic lives here
 * beyond DOM plumbing; everything it displays is computed elsewhere
 * (renderer.ts/stats.ts/walkLineage.ts) and handed to it already-formed.
 */

import { buildViewModel } from "./projector";
import { Renderer, type PlaybackStatus } from "./renderer";
import type { DNAStats } from "./stats";
import { fetchTrace } from "./traceEvent";
import type { GenerationDiff } from "./walkLineage";

const runIdInput = document.getElementById("run-id") as HTMLInputElement;
const loadButton = document.getElementById("load") as HTMLButtonElement;
const playPauseButton = document.getElementById("play-pause") as HTMLButtonElement;
const statusEl = document.getElementById("status") as HTMLDivElement;
const canvas = document.getElementById("scene") as HTMLCanvasElement;

const statTrackCount = document.getElementById("stat-track-count") as HTMLElement;
const statYearSpread = document.getElementById("stat-year-spread") as HTMLElement;
const statDistance = document.getElementById("stat-distance") as HTMLElement;
const statEnergy = document.getElementById("stat-energy") as HTMLElement;
const statTspScore = document.getElementById("stat-tsp-score") as HTMLElement;
const genreMixEl = document.getElementById("genre-mix") as HTMLElement;
const walkTreeEl = document.getElementById("walk-tree") as HTMLUListElement;

let renderer: Renderer | null = null;

function formatStatus(status: PlaybackStatus): string {
  switch (status.phase) {
    case "candidates":
      return "phase: candidates (intro)";
    case "sa":
      return `phase: simulated annealing — iteration ${status.saIteration}/${status.saTotal}, energy ${status.saEnergy?.toFixed(3) ?? "—"}`;
    case "tsp":
      return `phase: TSP ordering — generation ${status.tspGeneration}/${status.tspGenerationsTotal}, best score ${status.tspBestScore?.toFixed(3) ?? "—"}`;
    case "final":
      return "phase: final playlist";
  }
}

function renderStats(stats: DNAStats): void {
  statTrackCount.textContent = String(stats.trackCount);
  statYearSpread.textContent = stats.yearMin !== null && stats.yearMax !== null ? `${stats.yearMin}–${stats.yearMax}` : "—";
  statDistance.textContent = stats.avgDistanceFromSeed !== null ? stats.avgDistanceFromSeed.toFixed(3) : "—";

  genreMixEl.replaceChildren(
    ...stats.genreCounts.slice(0, 12).map(({ genre, count }) => {
      const span = document.createElement("span");
      span.textContent = count > 1 ? `${genre} ×${count}` : genre;
      return span;
    }),
  );
}

/** phase-specific readouts that aren't part of DNAStats (energy, tsp score) get their own panel fields. */
function renderPhaseSpecificStats(status: PlaybackStatus): void {
  statEnergy.textContent = status.phase === "sa" && status.saEnergy !== null ? status.saEnergy.toFixed(3) : "—";
  if (status.phase === "tsp" && status.tspBestScore !== null) {
    const improvement =
      status.tspInitialScore && status.tspInitialScore > 0
        ? `(${(100 * (1 - status.tspBestScore / status.tspInitialScore)).toFixed(1)}% improved)`
        : "";
    statTspScore.textContent = `${status.tspBestScore.toFixed(3)} ${improvement}`;
  } else if (status.phase === "final") {
    statTspScore.textContent = status.tspBestScore !== null ? status.tspBestScore.toFixed(3) : "—";
  } else {
    statTspScore.textContent = "—";
  }
}

/** Adds new <li>s for appeared walk_ids, fades out and removes <li>s for disappeared ones. */
function applyGenerationDiff(diff: GenerationDiff): void {
  for (const walkId of diff.appeared) {
    const li = document.createElement("li");
    li.textContent = `walk #${walkId}`;
    li.dataset["walkId"] = String(walkId);
    walkTreeEl.append(li);
  }
  for (const walkId of diff.disappeared) {
    const li = walkTreeEl.querySelector(`li[data-walk-id="${walkId}"]`);
    if (!li) continue;
    li.classList.add("fading");
    li.addEventListener("transitionend", () => li.remove(), { once: true });
  }
}

async function load(runId: string): Promise<void> {
  loadButton.disabled = true;
  playPauseButton.disabled = true;
  statusEl.textContent = `loading run ${runId}...`;
  walkTreeEl.replaceChildren();

  try {
    const events = await fetchTrace(runId);
    const viewModel = buildViewModel(events);

    renderer?.pause();
    renderer = new Renderer(canvas, viewModel, {
      onStatusChange: (status) => {
        statusEl.textContent = formatStatus(status);
        renderPhaseSpecificStats(status);
      },
      onStatsChange: renderStats,
      onGenerationDiff: applyGenerationDiff,
    });

    playPauseButton.disabled = false;
    playPauseButton.textContent = "Play";
    statusEl.textContent = `loaded ${events.length} events for run ${runId}`;
  } catch (err) {
    statusEl.textContent = `failed to load run ${runId}: ${err instanceof Error ? err.message : String(err)}`;
  } finally {
    loadButton.disabled = false;
  }
}

loadButton.addEventListener("click", () => {
  const runId = runIdInput.value.trim();
  if (runId) void load(runId);
});

runIdInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") loadButton.click();
});

playPauseButton.addEventListener("click", () => {
  if (!renderer) return;
  if (renderer.isPlaying) {
    renderer.pause();
    playPauseButton.textContent = "Play";
  } else {
    renderer.start();
    playPauseButton.textContent = "Pause";
  }
});
