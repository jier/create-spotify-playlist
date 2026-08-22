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
5. [x] Expose the simulated annealing energy trace so it can be visualized. Persisted as `runs/{run_id}.jsonl` (`src/algorithms/persistence.py`, `RunTraceWriter`), one line per seed/candidate/sa_iteration/final event, wired into `build_playlist_from_seed`. Verified against a real run: 1060 lines (1 seed, 58 candidates, 1000 sa_iteration, 1 final). Not yet done: threshold-relaxation steps inside greedy selection, per-generation TSP trace, and an HTTP endpoint to serve a run's file to a browser (needed before item 6 can consume it remotely).
6. [ ] Build a minimal web interface. Visualize playlist DNA: genre mix, year spread, distance from seed, TSP improvement, annealing convergence. Idea: use each candidate's artist picture (already available via /artists, just need artist_id from the candidate trace) inside its blob in the animation, so a viewer can see which real artists are in the mix as it replays.
7. [ ] Confirm Spotify Developer Policy compliance before offering the app to other users.

## Interface Choice

CLI, MCP, and web interface were compared. Web interface won because the algorithm already produces rich internal data per track and per run: genre set, release year, distance from seed, fallback reason, TSP score before and after. A chart shows this data far better than text output. This became the playlist DNA visualization idea in item 6.
