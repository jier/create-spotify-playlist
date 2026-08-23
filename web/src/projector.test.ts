import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import {
  buildViewModel,
  reconstructLastEpisodeSelections,
  splitIntoSAEpisodes,
  type FinalResult,
  type SAIterationFrame,
  type SeedInfo,
} from "./projector";
import { parseTrace, type TraceEvent } from "./traceEvent";

function seedEvent(overrides: Partial<TraceEvent & { stage: "seed" }> = {}): TraceEvent {
  return { stage: "seed", track_id: "seed_1", genres: ["rock"], release_year: 2000, ...overrides };
}

function finalEvent(trackIds: string[]): TraceEvent {
  return { stage: "final", track_ids: trackIds, tsp_score: 1, initial_score: 2, improvement_pct: 50 };
}

test("buildViewModel resolves candidate fields verbatim", () => {
  const events: TraceEvent[] = [
    seedEvent(),
    {
      stage: "candidate",
      track_id: "t1",
      name: "Song",
      artist_name: "Artist",
      artist_id: "a1",
      genres: ["rock"],
      release_year: 1999,
    },
    finalEvent(["seed_1", "t1"]),
  ];

  const vm = buildViewModel(events);

  assert.deepEqual(vm.candidates.get("t1"), {
    trackId: "t1",
    name: "Song",
    artistName: "Artist",
    artistId: "a1",
    genres: ["rock"],
    releaseYear: 1999,
  });
});

test("buildViewModel throws if there is no seed event", () => {
  assert.throws(() => buildViewModel([finalEvent(["x"])]), /no seed event/);
});

test("buildViewModel throws if there is no final event", () => {
  assert.throws(() => buildViewModel([seedEvent()]), /no final event/);
});

test("buildViewModel resolves tsp_generation members against tsp_walk events", () => {
  const events: TraceEvent[] = [
    seedEvent(),
    { stage: "tsp_walk", walk_id: 0, track_ids: ["a", "b"], parent_walk_ids: [] },
    { stage: "tsp_walk", walk_id: 1, track_ids: ["b", "a"], parent_walk_ids: [0] },
    {
      stage: "tsp_generation",
      generation: 0,
      members: [
        { walk_id: 0, score: 1.5 },
        { walk_id: 1, score: 0.5 },
      ],
    },
    finalEvent(["seed_1", "a", "b"]),
  ];

  const vm = buildViewModel(events);

  assert.equal(vm.tspWalks.size, 2);
  assert.equal(vm.tspGenerations.length, 1);
  const [gen0] = vm.tspGenerations;
  assert.equal(gen0!.members.length, 2);
  assert.deepEqual(gen0!.members[0]!.walk.trackIds, ["a", "b"]);
  assert.equal(gen0!.members[1]!.walk.parentWalkIds[0], 0);
});

test("buildViewModel throws if a tsp_generation references an unwritten walk_id", () => {
  const events: TraceEvent[] = [
    seedEvent(),
    { stage: "tsp_generation", generation: 0, members: [{ walk_id: 99, score: 1 }] },
    finalEvent(["seed_1"]),
  ];

  assert.throws(() => buildViewModel(events), /references walk_id 99/);
});

// ---------------------------------------------------------------------------
// splitIntoSAEpisodes
// ---------------------------------------------------------------------------

function iter(iteration: number, overrides: Partial<SAIterationFrame> = {}): SAIterationFrame {
  return {
    iteration,
    temperature: 1,
    energy: 0,
    accepted: true,
    outTrackId: "out",
    inTrackId: "in",
    ...overrides,
  };
}

test("splitIntoSAEpisodes returns nothing for an empty trace (greedy strategy)", () => {
  assert.deepEqual(splitIntoSAEpisodes([]), []);
});

test("splitIntoSAEpisodes keeps one continuously-increasing run as a single episode", () => {
  const episodes = splitIntoSAEpisodes([iter(0), iter(1), iter(2), iter(3)]);
  assert.equal(episodes.length, 1);
  assert.equal(episodes[0]!.iterations.length, 4);
});

test("splitIntoSAEpisodes starts a new episode when iteration resets to 0 (discography fallback re-ran a second anneal)", () => {
  const episodes = splitIntoSAEpisodes([iter(0), iter(1), iter(2), iter(0), iter(1)]);
  assert.equal(episodes.length, 2);
  assert.deepEqual(
    episodes[0]!.iterations.map((i) => i.iteration),
    [0, 1, 2],
  );
  assert.deepEqual(
    episodes[1]!.iterations.map((i) => i.iteration),
    [0, 1],
  );
});

// ---------------------------------------------------------------------------
// reconstructLastEpisodeSelections
// ---------------------------------------------------------------------------

const seed: SeedInfo = { trackId: "seed_1", genres: [], releaseYear: 2000 };

test("reconstructLastEpisodeSelections is a no-op when there are no episodes", () => {
  assert.doesNotThrow(() => reconstructLastEpisodeSelections([], { trackIds: [], tspScore: 0, initialScore: 0, improvementPct: 0 }, seed));
});

test("reconstructLastEpisodeSelections walks a single accepted swap backward correctly", () => {
  // Final selection is {a, c}. One iteration swapped b -> c and it was accepted,
  // so before that iteration the selection must have been {a, b}.
  const episodes = splitIntoSAEpisodes([iter(0, { accepted: true, outTrackId: "b", inTrackId: "c" })]);
  const final: FinalResult = { trackIds: ["seed_1", "a", "c"], tspScore: 0, initialScore: 0, improvementPct: 0 };

  reconstructLastEpisodeSelections(episodes, final, seed);

  const episode = episodes[0]!;
  assert.deepEqual(episode.selectionsAfter, [new Set(["a", "c"])]);
  assert.deepEqual(episode.initialSelection, new Set(["a", "b"]));
});

test("reconstructLastEpisodeSelections leaves the selection unchanged across a rejected iteration", () => {
  const episodes = splitIntoSAEpisodes([iter(0, { accepted: false, outTrackId: "b", inTrackId: "c" })]);
  const final: FinalResult = { trackIds: ["seed_1", "a", "b"], tspScore: 0, initialScore: 0, improvementPct: 0 };

  reconstructLastEpisodeSelections(episodes, final, seed);

  const episode = episodes[0]!;
  assert.deepEqual(episode.selectionsAfter, [new Set(["a", "b"])]);
  assert.deepEqual(episode.initialSelection, new Set(["a", "b"]));
});

test("reconstructLastEpisodeSelections handles a multi-step chain and only anchors the last episode", () => {
  // Two episodes: an abandoned first anneal, then the real one that produced the final result.
  const abandoned = [iter(0, { outTrackId: "x", inTrackId: "y" })];
  const real = [
    iter(0, { accepted: true, outTrackId: "a", inTrackId: "b" }), // {seed-only} -> after: {b}
    iter(1, { accepted: false, outTrackId: "b", inTrackId: "z" }), // no-op
    iter(2, { accepted: true, outTrackId: "b", inTrackId: "c" }), // after: {c}
  ];
  const episodes = splitIntoSAEpisodes([...abandoned, ...real]);
  assert.equal(episodes.length, 2);

  const final: FinalResult = { trackIds: ["seed_1", "c"], tspScore: 0, initialScore: 0, improvementPct: 0 };
  reconstructLastEpisodeSelections(episodes, final, seed);

  // Abandoned episode gets no reconstruction -- nothing sound to anchor it to.
  assert.equal(episodes[0]!.selectionsAfter, undefined);

  const lastEpisode = episodes[1]!;
  assert.deepEqual(lastEpisode.selectionsAfter, [new Set(["b"]), new Set(["b"]), new Set(["c"])]);
  assert.deepEqual(lastEpisode.initialSelection, new Set(["a"]));
});

// ---------------------------------------------------------------------------
// Real trace verification -- against a committed fixture, not the ambient
// runs/ directory.
//
// Two reasons this is a fixture (web/src/fixtures/sample-run.jsonl, copied
// verbatim from a real server run) rather than scanning runs/*.jsonl:
//
// 1. runs/ is gitignored. Scanning it made this suite non-deterministic
//    across environments -- on a fresh clone or CI, runs/ doesn't exist at
//    all, so these tests silently wouldn't run, and the "at least one real
//    trace file was found" assertion would fail outright.
// 2. runs/ grows unboundedly under normal use (every build_playlist_from_seed
//    call mints a fresh run_id, see src/services/playlistBuilderService.py).
//    Scanning it meant this suite's runtime scaled with how much you'd used
//    the app locally, not with the size of the test suite itself.
//
// A single frozen, committed fixture is a real backend output (not
// synthetic), bounded in size, and identical on every machine. To refresh
// it against current backend behavior, regenerate a run and copy it in:
//   cp runs/{run_id}.jsonl web/src/fixtures/sample-run.jsonl
// ---------------------------------------------------------------------------

const fixturePath = join(import.meta.dirname, "fixtures", "sample-run.jsonl");

test("buildViewModel handles a real backend-produced trace fixture", () => {
  const jsonl = readFileSync(fixturePath, "utf-8");
  const events = parseTrace(jsonl);

  const vm = buildViewModel(events);

  // Every tsp_generation's members must all resolve (buildViewModel already
  // throws on failure to resolve, so reaching here proves it for real data).
  for (const generation of vm.tspGenerations) {
    assert.ok(generation.members.length > 0);
  }

  // The last SA episode's reconstructed initial selection must have exactly
  // as many tracks as the final result (minus the seed) -- swaps preserve
  // selection size.
  assert.ok(vm.saEpisodes.length > 0, "this fixture is expected to be a strategy=sa run");
  const lastEpisode = vm.saEpisodes[vm.saEpisodes.length - 1]!;
  assert.ok(lastEpisode.selectionsAfter);
  const finalSelectionSize = vm.final.trackIds.filter((id) => id !== vm.seed.trackId).length;
  assert.equal(lastEpisode.initialSelection!.size, finalSelectionSize);
  for (const selection of lastEpisode.selectionsAfter!) {
    assert.equal(selection.size, finalSelectionSize);
  }
});
