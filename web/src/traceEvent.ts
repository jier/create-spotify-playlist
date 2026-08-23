/**
 * The discriminated union over every trace event stage, and the parsing
 * layer that turns raw JSONL text (as returned by GET /runs/{run_id}) into
 * validated, typed events.
 *
 * Deliberately NOT generated: pydantic2zod compiles each Pydantic model in
 * src/algorithms/models.py to its own Zod schema (see ./generated/models.ts),
 * but "here is the union of all of them, discriminated on stage" isn't a
 * Python-side concept to derive from — it's purely a TypeScript-side
 * decision about how to consume the wire protocol. Kept in this separate,
 * hand-written file so re-running the codegen script never touches it.
 */

import { z } from "zod";
import {
  CandidateTraceEvent,
  FinalTraceEvent,
  SAIterationEvent,
  SeedTraceEvent,
  ThresholdStepEvent,
  TSPGenerationEvent,
  TSPWalkEvent,
} from "./generated/models";

export const TraceEvent = z.discriminatedUnion("stage", [
  SeedTraceEvent,
  CandidateTraceEvent,
  ThresholdStepEvent,
  SAIterationEvent,
  TSPWalkEvent,
  TSPGenerationEvent,
  FinalTraceEvent,
]);

export type TraceEvent = z.infer<typeof TraceEvent>;

/**
 * Parse and validate a single JSONL line. Throws (via Zod) on malformed or
 * unrecognised input rather than silently passing bad data through — the
 * backend is trusted as the source of truth, but the wire is not.
 */
export function parseTraceLine(line: string): TraceEvent {
  return TraceEvent.parse(JSON.parse(line));
}

/**
 * Parse the full JSONL text of a run's trace (the exact string GET
 * /runs/{run_id} returns) into an ordered array of validated events.
 */
export function parseTrace(jsonl: string): TraceEvent[] {
  return jsonl
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .map(parseTraceLine);
}

/**
 * Fetch and parse a run's trace directly from the running backend.
 * baseUrl defaults to same-origin — override for local dev if the frontend
 * is served from a different port than uvicorn.
 */
export async function fetchTrace(runId: string, baseUrl = ""): Promise<TraceEvent[]> {
  const response = await fetch(`${baseUrl}/runs/${encodeURIComponent(runId)}`);
  if (!response.ok) {
    throw new Error(`GET /runs/${runId} failed: ${response.status} ${response.statusText}`);
  }
  return parseTrace(await response.text());
}
