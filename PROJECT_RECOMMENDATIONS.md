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
8. [ ] Make the frontend self-sufficient for a live demo: right now it can only *view* a run that already exists (`GET /runs/{run_id}`) — generating one still requires a manual `curl`/Postman call outside the browser first, which breaks flow for a live demo (fine for a pre-generated/rehearsed one). Two asks, really one underlying capability: let the frontend *trigger* a new backend run, not just replay an existing one.

   **8a. "Regenerate" — rerun the currently-loaded seed and visualize the new result.**
   SA and the TSP genetic algorithm are both stochastic (`random.sample`/`random.choice` throughout `src/algorithms/selection.py` and `tsp.py`, no seeded RNG) — the same seed track produces a *different* trace every call. A "Regenerate" button next to Load, reusing whatever seed track_id is already loaded, is the smallest version of "trigger a new run from the frontend": no new UI beyond one button + a strategy/`n` control, but real value — comparing runs of the same seed side by side is a genuinely interesting demo moment ("watch it converge differently every time").

   **8b. Seed-track input — build a playlist from any song, not just a pre-generated run_id.**
   The generalization of 8a: let the user type a song (not a raw track_id — nobody has those memorized, bad for a demo) and get a playlist built + visualized end to end. Needs a real search step first.

   **What both need, shared:**
   - A new frontend `api.ts` (or extending `traceEvent.ts`) with `buildPlaylistFromSeed(trackId, { n, strategy }): Promise<{ runId: string }>` — `POST /me/playlists/seed/{track_id}?n=...&strategy=...&dry_run=true`. **`dry_run` must always be hardcoded `true` from the frontend, never exposed as a toggle** — this UI is for visualizing the algorithm, not for creating real Spotify playlists; that stays a deliberate, explicit backend-only/CLI action, matching the existing "every destructive operation defaults to dry_run=true" safety posture in the README.
   - `_assemble_seed_playlist_result` (`src/services/playlistBuilderService.py`) currently returns a plain `dict`, not a Pydantic model — unlike every trace event, this response was never part of the codegen'd wire protocol. For consistency with "backend is the source of truth, nothing hand-duplicated on the frontend," this needs an actual Pydantic response model (at minimum `run_id`, `error: str | None`) added to `src/algorithms/models.py` or a new `src/api_models.py`, wired into `generate_ts_models.py`'s scope, so `buildPlaylistFromSeed`'s return type is generated too, not hand-typed.
   - Loading state + the existing actionable-error pattern from `fetchTrace` reused here (backend not running, non-2xx, etc.).
   - On success: auto-`fetchTrace(runId)` + construct a new `Renderer`, same as a manual Load does today — the two code paths (paste a run_id vs. build one live) should converge on the same "load and render" function rather than duplicating it.

   **8b additionally needs, before the input is usable for a demo**: a real search endpoint. There is currently no HTTP endpoint wrapping `SpotifyService.search_tracks` — `POST /me/playlists/seed/{track_id}` requires already knowing a Spotify track_id. Add e.g. `GET /search/tracks?q=...` (thin wrapper, same shape as the existing `/me/playlists?query=...` pattern) returning enough per-track info (id, name, artist) for a simple autocomplete/results list in the frontend, so the actual UX is: type a song name -> pick from real search results -> Build -> auto-load + play. Without this, 8b degrades to "paste a track_id you looked up yourself," which is 8a with extra steps, not a real "give it a song" experience.

## Interface Choice

CLI, MCP, and web interface were compared. Web interface won because the algorithm already produces rich internal data per track and per run: genre set, release year, distance from seed, fallback reason, TSP score before and after. A chart shows this data far better than text output. This became the playlist DNA visualization idea in item 6.
