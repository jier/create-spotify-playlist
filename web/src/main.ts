/**
 * DOM wiring for index.html. Fetches a run's trace from the backend
 * (fetchTrace, proxied to uvicorn by vite.config.ts's dev server proxy so
 * there's no CORS to deal with), projects it (buildViewModel), and hands
 * the result to a Renderer.
 */

import { buildViewModel } from "./projector";
import { Renderer, type PlaybackStatus } from "./renderer";
import { fetchTrace } from "./traceEvent";

const runIdInput = document.getElementById("run-id") as HTMLInputElement;
const loadButton = document.getElementById("load") as HTMLButtonElement;
const playPauseButton = document.getElementById("play-pause") as HTMLButtonElement;
const statusEl = document.getElementById("status") as HTMLDivElement;
const canvas = document.getElementById("scene") as HTMLCanvasElement;

let renderer: Renderer | null = null;

function formatStatus(status: PlaybackStatus): string {
  switch (status.phase) {
    case "candidates":
      return "phase: candidates (intro)";
    case "sa":
      return `phase: simulated annealing — iteration ${status.saIteration}/${status.saTotal}`;
    case "final":
      return "phase: final playlist";
  }
}

async function load(runId: string): Promise<void> {
  loadButton.disabled = true;
  playPauseButton.disabled = true;
  statusEl.textContent = `loading run ${runId}...`;

  try {
    const events = await fetchTrace(runId);
    const viewModel = buildViewModel(events);

    renderer?.pause();
    renderer = new Renderer(canvas, viewModel, {
      onStatusChange: (status) => {
        statusEl.textContent = formatStatus(status);
      },
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
