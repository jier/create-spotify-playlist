import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

import { fetchTrace, parseTrace, parseTraceLine } from "./traceEvent";

const originalFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = originalFetch;
});

function mockFetch(impl: typeof fetch): void {
  globalThis.fetch = impl as typeof globalThis.fetch;
}

test("parseTraceLine parses a valid seed line", () => {
  const event = parseTraceLine(JSON.stringify({ stage: "seed", track_id: "t1", genres: ["rock"], release_year: 2000 }));
  assert.equal(event.stage, "seed");
});

test("parseTrace skips blank lines", () => {
  const jsonl = [
    JSON.stringify({ stage: "seed", track_id: "t1", genres: [], release_year: 2000 }),
    "",
    JSON.stringify({ stage: "final", track_ids: ["t1"], tsp_score: 0, initial_score: 0, improvement_pct: 0 }),
    "",
  ].join("\n");

  const events = parseTrace(jsonl);
  assert.equal(events.length, 2);
});

test("fetchTrace throws an actionable error when fetch itself fails (backend not running)", async () => {
  mockFetch(async () => {
    throw new TypeError("Failed to fetch");
  });

  await assert.rejects(() => fetchTrace("run_1"), /Could not reach the backend.*Is it running.*uvicorn/s);
});

test("fetchTrace throws on a non-ok HTTP status", async () => {
  mockFetch(async () => new Response("not found", { status: 404, statusText: "Not Found" }));

  await assert.rejects(() => fetchTrace("run_1"), /GET \/runs\/run_1 failed: 404/);
});

test("fetchTrace throws a clear error when the response isn't application/x-ndjson (e.g. a dev proxy error page)", async () => {
  mockFetch(
    async () =>
      new Response("<html>502 Bad Gateway</html>", {
        status: 200,
        headers: { "content-type": "text/html" },
      }),
  );

  await assert.rejects(() => fetchTrace("run_1"), /content-type "text\/html".*not application\/x-ndjson/s);
});

test("fetchTrace parses a real ok application/x-ndjson response", async () => {
  const jsonl = [
    JSON.stringify({ stage: "seed", track_id: "t1", genres: ["rock"], release_year: 2000 }),
    JSON.stringify({ stage: "final", track_ids: ["t1"], tsp_score: 0, initial_score: 0, improvement_pct: 0 }),
  ].join("\n");

  mockFetch(async () => new Response(jsonl, { status: 200, headers: { "content-type": "application/x-ndjson" } }));

  const events = await fetchTrace("run_1");
  assert.equal(events.length, 2);
  assert.equal(events[0]!.stage, "seed");
});
