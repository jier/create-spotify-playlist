/**
 * Throwaway verification script, not part of the app: proves the TSP
 * phase's data actually improves generation to generation (the real
 * "annealing convergence"/"TSP improvement" signal this phase is supposed
 * to represent), and that the walk-tree population-turnover diff produces
 * sane, real numbers against the actual fixture — not just "it doesn't
 * throw."
 *
 * Usage: npx tsx web/scripts/verify_tsp_playback.ts <path-to-jsonl>
 */
import { readFileSync } from "node:fs";
import { buildViewModel } from "../src/projector";
import { parseTrace } from "../src/traceEvent";
import { diffGenerations } from "../src/walkLineage";

const path = process.argv[2];
if (!path) {
  console.error("usage: verify_tsp_playback.ts <path-to-jsonl>");
  process.exit(1);
}

const vm = buildViewModel(parseTrace(readFileSync(path, "utf-8")));

if (vm.tspGenerations.length === 0) {
  console.error("this trace has no TSP generations to verify against");
  process.exit(1);
}

console.log(`${vm.tspGenerations.length} TSP generations, ${vm.tspWalks.size} distinct walks ever registered.\n`);

console.log("Best (members[0]) score per generation, sampled every 10 generations:");
let previousBest = Infinity;
let everImproved = false;
for (const generation of vm.tspGenerations) {
  const best = generation.members[0]?.score;
  if (best !== undefined && best < previousBest - 1e-9) everImproved = true;
  if (best !== undefined) previousBest = Math.min(previousBest, best);
  if (generation.generation % 10 === 0 || generation.generation === vm.tspGenerations.length - 1) {
    console.log(`  generation ${generation.generation}: best score ${best?.toFixed(4)}`);
  }
}

const firstBest = vm.tspGenerations[0]!.members[0]!.score;
const lastBest = vm.tspGenerations[vm.tspGenerations.length - 1]!.members[0]!.score;
console.log(`\nFirst generation's best score: ${firstBest.toFixed(4)}`);
console.log(`Last generation's best score:  ${lastBest.toFixed(4)}`);
console.log(`vm.final.tspScore:             ${vm.final.tspScore.toFixed(4)}`);
console.log(`vm.final.improvementPct:       ${vm.final.improvementPct}%`);
console.log(everImproved ? "PASS: best score improved (decreased) at some point across generations." : "FAIL: best score never improved.");

console.log("\n--- Walk population turnover (walkLineage.diffGenerations) ---");
const diffs = diffGenerations(vm.tspGenerations);
let totalAppeared = 0;
let totalDisappeared = 0;
for (const diff of diffs) {
  totalAppeared += diff.appeared.length;
  totalDisappeared += diff.disappeared.length;
}
console.log(`Total "appeared" events across the run: ${totalAppeared}`);
console.log(`Total "disappeared" events across the run: ${totalDisappeared}`);
console.log(`Distinct walk_ids ever alive: ${new Set(diffs.flatMap((d) => d.alive)).size}`);
console.log(
  totalDisappeared > 0
    ? "PASS: real population turnover happened -- the walk-tree list will actually have entries appear and disappear."
    : "FAIL: no turnover -- the walk-tree list would just grow forever, nothing to fade out.",
);
