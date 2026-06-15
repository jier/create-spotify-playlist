from datetime import date

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from .services import playlist_builder, spotify

app = FastAPI()


class RemoveTracksRequest(BaseModel):
    track_ids: list[str]


@app.get("/")
def read_route():
    return "Hello World"


@app.get("/login")
def login():
    return RedirectResponse(spotify.get_auth_url())


@app.get("/callback")
def callback(code: str):
    spotify.exchange_code(code)
    return {"message": "Authenticated successfully"}


@app.get("/me/playlists")
def get_my_playlists(q: str | None = None, offset: int = 0, limit: int = 50):
    if q:
        items = spotify.search_my_playlists(q)
        return {"total": len(items), "items": items}
    return spotify.get_my_playlists(offset=offset, limit=limit)


@app.get("/me/tracks")
def get_liked_songs(offset: int = 0, limit: int = 50):
    return spotify.get_liked_songs(offset=offset, limit=limit)


@app.get("/me/tracks/before/{date}")
def get_liked_songs_before(date: date, offset: int = 0, limit: int = 50):
    return spotify.get_liked_songs_before(date.isoformat(), offset=offset, limit=limit)


@app.get("/me/tracks/after/{date}")
def get_liked_songs_after(date: date, offset: int = 0, limit: int = 50):
    return spotify.get_liked_songs_after(date.isoformat(), offset=offset, limit=limit)


@app.delete("/me/tracks")
def remove_liked_songs(body: RemoveTracksRequest):
    return spotify.remove_liked_songs(track_ids=body.track_ids)


@app.delete("/me/tracks/before/{date}")
def delete_liked_songs_on_or_before(date: date, dry_run: bool = True):
    count = spotify.delete_liked_songs_on_or_before(date.isoformat(), dry_run=dry_run)
    return {"deleted": count, "dry_run": dry_run}


@app.get("/playlists/{playlist_id}/tracks")
def get_playlist_tracks(playlist_id: str, offset: int = 0, limit: int = 50):
    return spotify.get_playlist_tracks(playlist_id=playlist_id, offset=offset, limit=limit)


@app.delete("/playlists/{playlist_id}/tracks")
def remove_playlist_tracks(playlist_id: str, body: RemoveTracksRequest):
    return spotify.remove_playlist_tracks(playlist_id=playlist_id, track_ids=body.track_ids)


@app.get("/users/{user_id}/playlists")
def get_user_playlists(user_id: str):
    return spotify.get_user_playlists(user_id)


@app.post("/me/playlists/seed/{track_id}")
def build_playlist_from_seed(track_id: str, n: int = 20, dry_run: bool = True):
    return playlist_builder.build_playlist_from_seed(track_id, n=n, dry_run=dry_run)


@app.post(
    "/me/playlists/{genre}/chronological",
    deprecated=True,
    description="Searches only liked songs. Prefer POST /me/playlists/seed/{track_id} for full catalog discovery.",
)
def build_chronological_playlist(genre: str, dry_run: bool = True):
    return playlist_builder.build_genre_playlist_chronological(genre, dry_run=dry_run)


@app.post(
    "/me/playlists/{genre}/tsp",
    deprecated=True,
    description="Searches only liked songs. Prefer POST /me/playlists/seed/{track_id} for full catalog discovery.",
)
def build_tsp_playlist(genre: str, dry_run: bool = True):
    return playlist_builder.build_genre_playlist_tsp(genre, dry_run=dry_run)
