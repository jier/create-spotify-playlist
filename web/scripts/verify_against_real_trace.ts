/**
 * Throwaway verification script, not part of the app: parse a real
 * runs/{run_id}.jsonl file (produced by the actual backend, not a fixture)
 * through parseTrace() and report what came out, to prove the Zod schemas
 * generated from Pydantic actually accept real backend output end to end.
 *
 * Usage: npx tsx web/scripts/verify_against_real_trace.ts <path-to-jsonl>
 */
import { readFileSync } from "node:fs";
import { parseTrace } from "../src/traceEvent";

const path = process.argv[2];
if (!path) {
  console.error("usage: verify_against_real_trace.ts <path-to-jsonl>");
  process.exit(1);
}

const jsonl = readFileSync(path, "utf-8");
const events = parseTrace(jsonl);

const counts = new Map<string, number>();
for (const event of events) {
  counts.set(event.stage, (counts.get(event.stage) ?? 0) + 1);
}

console.log(`Parsed ${events.length} events from ${path}`);
console.log("By stage:", Object.fromEntries(counts));

const walkEvents = events.filter((e) => e.stage === "tsp_walk");
const generationEvents = events.filter((e) => e.stage === "tsp_generation");
if (walkEvents.length > 0) {
  const knownIds = new Set<number>();
  let violations = 0;
  for (const w of walkEvents) {
    for (const parentId of w.parent_walk_ids) {
      if (!knownIds.has(parentId)) violations++;
    }
    knownIds.add(w.walk_id);
  }
  console.log(`tsp_walk lineage check: ${violations} DAG violations (should be 0)`);
}
if (generationEvents.length > 0) {
  const sizes = new Set(generationEvents.map((g) => g.members.length));
  console.log(`tsp_generation population sizes seen: ${[...sizes].join(", ")}`);
}

const seed = events.find((e) => e.stage === "seed");
const final = events.find((e) => e.stage === "final");
console.log("seed:", seed);
console.log("final:", final);
