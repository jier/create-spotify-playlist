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
5. [x] Expose the simulated annealing energy trace so it can be visualized. Persisted as `runs/{run_id}.jsonl` (`src/algorithms/persistence.py`, `RunTraceWriter`), all 7 stages now covered: seed, candidate, threshold_step (both greedy and SA's relaxation loops), sa_iteration, tsp_walk + tsp_generation (content-addressed walk cache — full population every generation, not truncated), final. `GET /runs/{run_id}` serves a run's trace over HTTP. Verified end to end against a real server: `POST /me/playlists/seed/{track_id}?strategy=sa` then `GET /runs/{run_id}` returned 1446 real lines (1 seed, 58 candidate, 1 threshold_step, 1000 sa_iteration, 334 tsp_walk, 51 tsp_generation, 1 final), inspected line by line. Not yet done: TSP walk lineage (which parent produced which child) isn't recorded, only content + score.
6. [ ] Build a minimal web interface. Visualize playlist DNA: genre mix, year spread, distance from seed, TSP improvement, annealing convergence. Idea: use each candidate's artist picture (already available via /artists, just need artist_id from the candidate trace) inside its blob in the animation, so a viewer can see which real artists are in the mix as it replays.
7. [ ] Confirm Spotify Developer Policy compliance before offering the app to other users.

## Interface Choice

CLI, MCP, and web interface were compared. Web interface won because the algorithm already produces rich internal data per track and per run: genre set, release year, distance from seed, fallback reason, TSP score before and after. A chart shows this data far better than text output. This became the playlist DNA visualization idea in item 6.
