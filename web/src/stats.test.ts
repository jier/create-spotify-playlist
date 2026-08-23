import assert from "node:assert/strict";
import { test } from "node:test";

import type { CandidateInfo, SeedInfo } from "./projector";
import { computeStats } from "./stats";

const seed: SeedInfo = { trackId: "seed_1", genres: ["gospel", "reggae"], releaseYear: 2000 };

function candidate(overrides: Partial<CandidateInfo> & { trackId: string }): CandidateInfo {
  return {
    name: "Song",
    artistName: "Artist",
    artistId: null,
    genres: [],
    releaseYear: 2000,
    ...overrides,
  };
}

const candidates = new Map<string, CandidateInfo>([
  ["t1", candidate({ trackId: "t1", genres: ["gospel"], releaseYear: 1990 })],
  ["t2", candidate({ trackId: "t2", genres: ["gospel", "reggae"], releaseYear: 2020 })],
  ["t3", candidate({ trackId: "t3", genres: ["pop"], releaseYear: 2010 })],
]);

test("computeStats counts genres across every resolved track, including the seed", () => {
  const stats = computeStats(["seed_1", "t1", "t2"], candidates, seed);

  const byGenre = Object.fromEntries(stats.genreCounts.map((g) => [g.genre, g.count]));
  assert.equal(byGenre["gospel"], 3); // seed + t1 + t2
  assert.equal(byGenre["reggae"], 2); // seed + t2
  assert.equal(stats.trackCount, 3);
});

test("computeStats sorts genreCounts descending by count, ties broken alphabetically", () => {
  const stats = computeStats(["t1", "t3"], candidates, seed); // t1: gospel, t3: pop -- 1 each, tie
  assert.deepEqual(
    stats.genreCounts.map((g) => g.genre),
    ["gospel", "pop"], // alphabetical tiebreak
  );
});

test("computeStats reports year min/max across the resolved set", () => {
  const stats = computeStats(["t1", "t2"], candidates, seed);
  assert.equal(stats.yearMin, 1990);
  assert.equal(stats.yearMax, 2020);
});

test("computeStats returns null year bounds for an empty set", () => {
  const stats = computeStats([], candidates, seed);
  assert.equal(stats.yearMin, null);
  assert.equal(stats.yearMax, null);
  assert.equal(stats.avgDistanceFromSeed, null);
});

test("computeStats excludes the seed itself from avgDistanceFromSeed (distance to itself is always 0, would deflate the average)", () => {
  const onlySeed = computeStats(["seed_1"], candidates, seed);
  assert.equal(onlySeed.avgDistanceFromSeed, null, "no non-seed tracks -- nothing to average");
});

test("computeStats averages distance from seed over non-seed tracks only", () => {
  // t2 shares both genres with the seed and is 20 years apart -> distance = 1*0 + 0.5*(20/50) = 0.2
  const stats = computeStats(["seed_1", "t2"], candidates, seed);
  assert.ok(stats.avgDistanceFromSeed !== null);
  assert.ok(Math.abs(stats.avgDistanceFromSeed! - 0.2) < 1e-9);
});

test("computeStats silently skips an unresolvable track id instead of throwing", () => {
  const stats = computeStats(["seed_1", "does_not_exist"], candidates, seed);
  assert.equal(stats.trackCount, 1); // only the seed resolved
});
