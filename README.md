# Create Spotify Playlist

A personal FastAPI service that builds Spotify playlists from a single seed track. It searches your library and the catalog by genre, scores candidates by genre overlap and release year, orders the result with a genetic traveling salesman solver, and returns everything as a dry run by default so nothing is created until you say so.

## Requirements

Python 3.13 or newer, and a Spotify Developer application. Create one at the Spotify Developer Dashboard, then note the client id, client secret, and set a redirect URI of `http://127.0.0.1:8000/callback`.

## Setup

1. Copy `.env.example` to `.env` and fill in your Spotify client id and client secret.
2. Install dependencies with `uv sync`.
3. Run the service with `uv run uvicorn src.app:app --reload`.
4. Open `http://127.0.0.1:8000/login` in a browser and authorize the app.
5. Spotify redirects back to `/callback`, which stores a token locally in `token.json`.

The service binds to `127.0.0.1` only. It is a personal tool, not a public multi user service.

## Environment Variables

`SPOTIPY_CLIENT_ID`, your Spotify app client id.
`SPOTIPY_CLIENT_SECRET`, your Spotify app client secret.
`SPOTIFY_REDIRECT_URI`, defaults to `http://127.0.0.1:8000/callback`.

## Building a Playlist from a Seed Track

`POST /me/playlists/seed/{track_id}` is the main endpoint. It runs these steps.

1. Fetch the seed track and its primary artist genres.
2. Search the catalog for candidates matching those genres, capped per artist to avoid one artist dominating the pool.
3. Fetch genres for every candidate artist.
4. Score each candidate by Jaccard genre distance and release year distance from the seed.
5. Select the top tracks using one of two strategies, `greedy` or `sa`.
6. Order the selected tracks with a genetic traveling salesman algorithm so adjacent tracks are as similar as possible.
7. Return the result as JSON. If `dry_run` is true, no playlist is created; the response shows what would happen.

### Selection Strategies

`greedy` walks candidates in distance order, enforces the per artist cap, and relaxes the genre threshold in steps until enough tracks are found. It favors close matches to the seed.

`sa` uses simulated annealing. It balances relevance to the seed against diversity between selected tracks, and can undo an early choice that greedy would be stuck with. It favors variety alongside relevance.

Query parameters: `n` (track count, default 20), `dry_run` (default true), `strategy` (`greedy` or `sa`, default `greedy`).

### Playlist DNA Traces

Every call to the seed endpoint writes a JSONL trace of the run to `runs/{run_id}.jsonl`: the seed, every candidate considered, every genre-threshold relaxation step, every simulated annealing iteration (`strategy=sa` only), every distinct TSP track ordering with its parent lineage, and the final result. The response includes `run_id` and `trace_path`.

`GET /runs/{run_id}` serves a run's trace back as raw JSONL (`application/x-ndjson`). This is the data source for an in-progress playlist DNA visualization, see `web/` under Development below; there is no user-facing visualization yet.

Traces are not kept forever. `runs/` is pruned automatically on every app startup, deleting anything older than `runs_retention_days` (default 7 days), and on demand via `make clean-runs`.

## Other Endpoints

`GET /me/tracks`, list liked songs, paginated.
`GET /me/tracks/before/{date}` and `GET /me/tracks/after/{date}`, filter liked songs by date added.
`DELETE /me/tracks`, remove specific liked songs by id.
`DELETE /me/tracks/before/{date}`, bulk delete liked songs added on or before a date; defaults to `dry_run=true`.
`GET /me/playlists`, list your playlists, with optional name search.
`GET /playlists/{playlist_id}/tracks` and `DELETE /playlists/{playlist_id}/tracks`, read or remove tracks in a playlist you own.
`GET /users/{user_id}/playlists`, list another user's public playlists.

Two older endpoints, `/me/playlists/{genre}/chronological` and `/me/playlists/{genre}/tsp`, build playlists from liked songs only and are kept for reference. Prefer the seed based endpoint for full catalog discovery.

## Safety

Every destructive operation defaults to `dry_run=true`. Always run a dry run first and read the response before setting `dry_run=false`.

## Development

Run `make lint` for style checks, `make typecheck` for type checks, `make test` for the test suite, and `make check` for lint plus typecheck together. `make clean-runs` prunes old playlist DNA traces on demand (see Playlist DNA Traces above).

### Frontend (`web/`)

`web/` is a separate, in-progress TypeScript package for the playlist DNA visualization — no UI exists yet, this is currently the data layer only. Pure TypeScript/HTML/CSS, no frontend framework. The backend (`src/algorithms/models.py`) is the source of truth for the wire protocol: `make generate-ts-models` (or `uv run python web/scripts/generate_ts_models.py`) compiles those Pydantic models into Zod schemas at `web/src/generated/models.ts` via `pydantic2zod`, so the frontend's types can't silently drift from what the backend actually emits. `web/src/traceEvent.ts` builds the discriminated union over all trace stages and parses/validates a run's JSONL. `web/src/projector.ts` turns a parsed trace into a render-ready view model: resolves `tsp_walk`/`tsp_generation` references, and reconstructs the full SA-selected track set at every iteration by walking the trace backward from the final result (a `sa_iteration` event only records what swapped, not the full selection). `make web-typecheck` type-checks it, `make web-test` runs its tests (including against real `runs/*.jsonl` files, not just fixtures), `make web-check` runs both.

## License

See `LICENSE`.
