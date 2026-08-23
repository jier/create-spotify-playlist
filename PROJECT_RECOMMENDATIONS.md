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
6. [x] Build a minimal web interface. Visualize playlist DNA: genre mix, year spread, distance from seed, TSP improvement, annealing convergence.
   - Rendering approach decided (Canvas 2D + CSS/SVG gooey filter + a couple of standalone `d3-*` math modules, no framework, no WebGL): grounded in real sources (MDN Canvas/WebGL docs, official D3 "What is D3?" docs, CSS-Tricks' Gooey Effect article), not guesswork. Validated with a throwaway prototype confirming `filter: url(#goo)` actually renders/animates on a `<canvas>` element.
   - `web/` package: TypeScript event types (`web/src/generated/models.ts`) generated from `src/algorithms/models.py` via `pydantic2zod` (`make generate-ts-models`), event-log -> view-model projector (`web/src/projector.ts`, resolves `tsp_walk`/`tsp_generation` references and reconstructs the full SA-selected track set at every iteration by walking the trace backward from the final result), and the actual visualization (`web/index.html` + `main.ts`/`renderer.ts`/`playback.ts`/`colors.ts`/`stats.ts`/`distance.ts`/`walkLineage.ts`).
   - Full playback: candidates drift in as genre-colored blobs -> `strategy=sa` runs replay the real annealing trace, selected tracks pulled toward the seed (real positional convergence, not just a radius change) with jitter cooling scoped only to the selected cluster -> TSP phase prunes to the fixed final set and "chases" a highlight through each generation's best walk order (`members[0]`, already sorted by the backend) -> settles on the final playlist.
   - Live stats panel: track count, year spread, avg. distance from seed (`distance.ts`, mirrors `src/algorithms/distance.py`'s formula and defaults), genre mix, SA energy, TSP score/improvement — all computed from real trace data for whatever's currently emphasized, not placeholders.
   - "TSP walk population" tree-list panel: a live DOM list of currently-active track orderings that grows as new ones appear and fades out entries that stop surviving tournament selection (`walkLineage.ts`'s `diffGenerations`) — a direct, real read of population turnover.
   - Two real mistakes made and caught by actually watching the animation, not just from code review: (1) selection state only changed blob radius with no positional effect, so nothing ever looked like it was converging — fixed with `applyAttraction`. (2) the temperature-driven "cooling" jitter reduction was applied to *every* blob instead of just the selected ones, so the whole candidate pool nearly froze once SA temperature dropped (which happens for most of a run) — fixed by scoping `stepPhysics`'s jitter scale to selected blobs only, unselected blobs always get full ambient motion. Both fixes verified quantitatively (a headless script replaying the real pure functions against the real fixture, not eyeballing) as well as live in a real browser.
   - Verified end to end repeatedly against a real running backend + real Vite dev server + a real browser (CDP-driven): phase transitions, live stat/score readouts matching the headless-verified numbers exactly, walk-tree list growing and shrinking, and the TSP chase highlight actually appearing on canvas during the TSP phase.
   - Artist pictures in the blobs (the earlier idea) deliberately deferred, not forgotten — a conscious scope decision, not a gap.
7. [ ] Confirm Spotify Developer Policy compliance before offering the app to other users.

## Interface Choice

CLI, MCP, and web interface were compared. Web interface won because the algorithm already produces rich internal data per track and per run: genre set, release year, distance from seed, fallback reason, TSP score before and after. A chart shows this data far better than text output. This became the playlist DNA visualization idea in item 6.
