import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { buildViewModel } from "./projector";
import type { TSPGenerationFrame, TSPWalk } from "./projector";
import { parseTrace } from "./traceEvent";
import { diffGenerations } from "./walkLineage";

function walk(walkId: number): TSPWalk {
  return { walkId, trackIds: [`t${walkId}`], parentWalkIds: [] };
}

function generation(gen: number, walkIds: number[], scores: number[] = []): TSPGenerationFrame {
  return {
    generation: gen,
    members: walkIds.map((id, i) => ({ walk: walk(id), score: scores[i] ?? 0 })),
  };
}

test("diffGenerations: generation 0 has everything as appeared, nothing as disappeared", () => {
  const [diff] = diffGenerations([generation(0, [1, 2, 3])]);
  assert.deepEqual(diff!.appeared.sort(), [1, 2, 3]);
  assert.deepEqual(diff!.disappeared, []);
  assert.deepEqual(diff!.alive.sort(), [1, 2, 3]);
});

test("diffGenerations: a walk_id that stops appearing shows up as disappeared exactly once", () => {
  const diffs = diffGenerations([generation(0, [1, 2, 3]), generation(1, [1, 3, 4])]);
  assert.deepEqual(diffs[1]!.disappeared, [2]);
  assert.deepEqual(diffs[1]!.appeared, [4]);
  assert.deepEqual(diffs[1]!.alive.sort(), [1, 3, 4]);
});

test("diffGenerations: a walk_id present every generation never appears in appeared/disappeared after generation 0", () => {
  const diffs = diffGenerations([generation(0, [1]), generation(1, [1]), generation(2, [1])]);
  assert.deepEqual(diffs[1]!.appeared, []);
  assert.deepEqual(diffs[1]!.disappeared, []);
  assert.deepEqual(diffs[2]!.appeared, []);
  assert.deepEqual(diffs[2]!.disappeared, []);
});

test("diffGenerations: reappearance after disappearing counts as appeared again", () => {
  const diffs = diffGenerations([generation(0, [1]), generation(1, []), generation(2, [1])]);
  assert.deepEqual(diffs[1]!.disappeared, [1]);
  assert.deepEqual(diffs[2]!.appeared, [1]);
});

// ---------------------------------------------------------------------------
// Real trace verification
// ---------------------------------------------------------------------------

test("diffGenerations against the real fixture: every disappearance was previously alive, every generation's alive set fits within its own members", () => {
  const jsonl = readFileSync(join(import.meta.dirname, "fixtures", "sample-run.jsonl"), "utf-8");
  const vm = buildViewModel(parseTrace(jsonl));

  const diffs = diffGenerations(vm.tspGenerations);

  assert.equal(diffs.length, vm.tspGenerations.length);
  assert.deepEqual(diffs[0]!.disappeared, [], "generation 0 can't have disappearances, nothing came before it");

  let previousAlive = new Set<number>();
  for (const [i, diff] of diffs.entries()) {
    for (const id of diff.disappeared) {
      assert.ok(previousAlive.has(id), `generation ${diff.generation} claims walk_id ${id} disappeared, but it wasn't alive last generation`);
    }
    // alive.size can be <= members.length (duplicate walk content within one generation collapses in the Set).
    assert.ok(diff.alive.length <= vm.tspGenerations[i]!.members.length);
    previousAlive = new Set(diff.alive);
  }

  // Sanity: real population turnover actually happened somewhere in this trace
  // (otherwise this whole feature would have nothing to show).
  const anyDisappearances = diffs.some((d) => d.disappeared.length > 0);
  assert.ok(anyDisappearances, "expected at least one generation with real population turnover in this fixture");
});
