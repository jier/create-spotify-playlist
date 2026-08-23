/**
 * Throwaway verification script, not part of the app: replays the exact
 * same phase logic Renderer uses (candidates intro -> sa -> final),
 * driving the real pure functions from playback.ts directly, headless (no
 * browser, no canvas) — and measures whether selected blobs actually get
 * closer to the seed over time. Proves the convergence fix is real, not
 * just "looks plausible."
 *
 * Usage: npx tsx web/scripts/verify_convergence.ts <path-to-jsonl>
 */
import { readFileSync } from "node:fs";
import { applyAttraction, applySelection, createBlobs, stepPhysics, type BlobSeed } from "../src/playback";
import { buildViewModel } from "../src/projector";
import { parseTrace } from "../src/traceEvent";

const path = process.argv[2];
if (!path) {
  console.error("usage: verify_convergence.ts <path-to-jsonl>");
  process.exit(1);
}

const vm = buildViewModel(parseTrace(readFileSync(path, "utf-8")));
const episode = vm.saEpisodes[vm.saEpisodes.length - 1];
if (!episode?.selectionsAfter || !episode.initialSelection) {
  console.error("this trace has no reconstructed SA episode to verify against");
  process.exit(1);
}

const WIDTH = 900;
const HEIGHT = 600;
const ATTRACTION_STRENGTH = 1.5;
const MIN_JITTER_SCALE = 0.08;
const DT_MS = 16; // ~60fps

const entries: BlobSeed[] = [
  { id: vm.seed.trackId, genres: vm.seed.genres },
  ...[...vm.candidates.values()].map((c) => ({ id: c.trackId, genres: c.genres })),
];
let blobs = createBlobs(entries, WIDTH, HEIGHT);
blobs = applySelection(blobs, episode.initialSelection);

function avgDistanceOfSelectedToSeed(): number {
  const seed = blobs.get(vm.seed.trackId)!;
  const selected = [...blobs.values()].filter((b) => b.selected);
  if (selected.length === 0) return NaN;
  const total = selected.reduce((sum, b) => sum + Math.hypot(b.x - seed.x, b.y - seed.y), 0);
  return total / selected.length;
}

/** Never-selected candidate: proves unselected blobs stay alive throughout, not frozen by SA cooling. */
const neverSelectedId = [...vm.candidates.keys()].find(
  (id) => ![...episode.selectionsAfter!, episode.initialSelection!].some((sel) => sel.has(id)),
);
if (!neverSelectedId) {
  console.error("could not find a candidate that's never selected in any frame of this trace — pick a different fixture");
  process.exit(1);
}

console.log(`Replaying ${episode.iterations.length} SA iterations for run at ${path}`);
console.log(`Tracking a never-selected candidate (${neverSelectedId}) to confirm it keeps moving, not frozen.`);
console.log(`avg distance of selected blobs to seed  |  cumulative movement of the never-selected blob, sampled every 100 iterations:`);
console.log(`  iteration 0 (initial random selection): ${avgDistanceOfSelectedToSeed().toFixed(1)}px`);

let unselectedTravel = 0;
let lastUnselectedPos = { x: blobs.get(neverSelectedId)!.x, y: blobs.get(neverSelectedId)!.y };

for (let i = 0; i < episode.iterations.length; i++) {
  const iter = episode.iterations[i]!;
  const jitterScale = Math.max(iter.temperature, MIN_JITTER_SCALE);

  blobs = stepPhysics(blobs, DT_MS, WIDTH, HEIGHT, Math.random, jitterScale);
  const seedBlob = blobs.get(vm.seed.trackId)!;
  blobs = applyAttraction(blobs, { x: seedBlob.x, y: seedBlob.y }, ATTRACTION_STRENGTH, DT_MS);
  blobs = applySelection(blobs, episode.selectionsAfter[i]!);

  const unselectedBlob = blobs.get(neverSelectedId)!;
  unselectedTravel += Math.hypot(unselectedBlob.x - lastUnselectedPos.x, unselectedBlob.y - lastUnselectedPos.y);
  lastUnselectedPos = { x: unselectedBlob.x, y: unselectedBlob.y };

  if ((i + 1) % 100 === 0 || i === episode.iterations.length - 1) {
    console.log(
      `  iteration ${i + 1}: ${avgDistanceOfSelectedToSeed().toFixed(1)}px  |  cumulative travel: ${unselectedTravel.toFixed(1)}px  (temperature ${iter.temperature.toFixed(3)})`,
    );
  }
}

blobs = applySelection(blobs, new Set(vm.final.trackIds));
console.log(`  final phase: ${avgDistanceOfSelectedToSeed().toFixed(1)}px`);
console.log(`\nTotal distance traveled by the never-selected blob over the whole anneal: ${unselectedTravel.toFixed(1)}px`);
console.log(unselectedTravel > 50 ? "PASS: unselected blob kept moving throughout." : "FAIL: unselected blob looks frozen.");
