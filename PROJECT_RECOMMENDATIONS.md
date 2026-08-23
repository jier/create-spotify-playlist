# Project Recommendations

Reviewed: 2026-08-21

## Decision

Invest as a focused portfolio product. Keep it private until security, documentation, and tests are complete.

## Value

The project shows distinctive playlist selection and ordering. It uses similarity, constraints, and optimization strategies. It also shows adapting to Spotify API changes and handling destructive operations safely. It works well as a polished personal tool, not as a large multi user service.

## Todo

Track progress here. Check each box when done.

1. [x] Rotate the Spotify client secret and refresh token as a precaution.
2. [x] Add an OAuth state parameter and verify it on callback.
2b. [x] Bind the server to localhost only, enforced by middleware, not just the run command.
3. [x] Write README.md, .env.example, and LICENSE.
4. [x] Add tests for selection strategies (Jaccard distance, greedy, simulated annealing) and mocked Spotify and token flows.
5. [x] Expose the simulated annealing energy trace so it can be visualized. Persisted as `runs/{run_id}.jsonl` (`src/algorithms/persistence.py`, `RunTraceWriter`), all 7 stages covered: seed, candidate, threshold_step, sa_iteration, tsp_walk + tsp_generation (content-addressed walk cache with parent lineage, full population every generation), final. `GET /runs/{run_id}` serves a run's trace over HTTP, path-traversal guarded. Every `tsp_walk` carries `parent_walk_ids` (0 = random init, 1 = mutation, 2 = crossover) recorded at creation time, verified against a real run to form a valid DAG (every parent id appears before it's referenced) including the hard case: a crossover child mutated within the same generation, before any generation boundary. `runs/` is gitignored and age-based (`runs_retention_days`, default 7 days): pruned automatically on app startup and via `make clean-runs`. Found and fixed a real bug along the way: the test suite itself was writing real files into the project's `runs/` directory on every run (no isolation) — fixed with an autouse `tmp_path` fixture.
6. [ ] Build a minimal web interface. Visualize playlist DNA: genre mix, year spread, distance from seed, TSP improvement, annealing convergence. Idea: use each candidate's artist picture (already available via /artists, just need artist_id from the candidate trace) inside its blob in the animation, so a viewer can see which real artists are in the mix as it replays.
   - Rendering approach decided (Canvas 2D + CSS/SVG gooey filter + a couple of standalone `d3-*` math modules, no framework, no WebGL): grounded in real sources (MDN Canvas/WebGL docs, official D3 "What is D3?" docs, CSS-Tricks' Gooey Effect article), not guesswork. Validated with a throwaway prototype (`prototype/`, gitignored) confirming `filter: url(#goo)` actually renders/animates on a `<canvas>` element.
   - `web/` package scaffolded: TypeScript event types (`web/src/generated/models.ts`) generated from `src/algorithms/models.py` via `pydantic2zod` (`web/scripts/generate_ts_models.py`, `make generate-ts-models`) so the frontend can't drift from the backend's actual wire protocol. Verified against a real backend-produced trace (1622 real events), including an independent TypeScript-side re-check of the `tsp_walk` DAG lineage.
   - Event-log -> view-model projector (`web/src/projector.ts`) built: resolves `tsp_walk`/`tsp_generation` references, and reconstructs the full SA-selected track set at every iteration by walking the trace backward from the final result (a `sa_iteration` event only records what swapped). Handles the real edge case of a second, independent anneal from the discography fallback path (iteration numbers restart from 0) correctly rather than silently corrupting the reconstruction.
   - First working version of the actual visualization exists (`web/index.html` + `main.ts`/`renderer.ts`/`playback.ts`/`colors.ts`): candidates drift in as genre-colored blobs, `strategy=sa` runs replay the real annealing trace live (growing/highlighting the currently-selected tracks iteration by iteration), then settle on the final playlist. Verified end to end against a real running backend + real Vite dev server + a real browser (CDP-driven, not just "it compiles"): confirmed the gooey CSS filter resolves, pixels draw, animation progresses, and phase transitions (candidates -> sa -> final) all happen correctly over a real ~1800-event trace, zero console errors.
   - Not yet built: TSP generation playback (the population of orderings evolving via parent lineage), artist pictures in the blobs, and the other DNA facets from this item's original description (year spread, distance-from-seed, TSP improvement, annealing convergence as an explicit readout rather than just the live iteration counter).
7. [ ] Confirm Spotify Developer Policy compliance before offering the app to other users.

## Interface Choice

CLI, MCP, and web interface were compared. Web interface won because the algorithm already produces rich internal data per track and per run: genre set, release year, distance from seed, fallback reason, TSP score before and after. A chart shows this data far better than text output. This became the playlist DNA visualization idea in item 6.
