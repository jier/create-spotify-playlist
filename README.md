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

Run `make lint` for style checks, `make typecheck` for type checks, `make test` for the test suite, and `make check` for lint plus typecheck together.

## License

See `LICENSE`.
