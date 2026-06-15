import json
import time
import urllib.parse
from itertools import islice

import requests
from fastapi import HTTPException

from ..settings import settings


class SpotifyService:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._token_data = self._load_token()

    def __repr__(self) -> str:
        authenticated = bool(self._token_data.get("access_token"))
        return f"SpotifyService(client_id={self._client_id!r}, authenticated={authenticated})"

    def _load_token(self) -> dict:
        if settings.token_path.exists():
            with open(settings.token_path) as f:
                return json.load(f)
        return {"access_token": "", "refresh_token": "", "expires_at": 0}

    def _save_token(self, data: dict) -> None:
        with open(settings.token_path, "w") as f:
            json.dump(data, f, indent=4)
        self._token_data = data

    def get_auth_url(self) -> str:
        params = {
            "client_id": self._client_id,
            "response_type": "code",
            "redirect_uri": self._redirect_uri,
            "scope": settings.spotify_scopes,
        }
        return f"{settings.spotify_auth_base}/authorize?{urllib.parse.urlencode(params)}"

    def exchange_code(self, code: str) -> None:
        auth_url = f"{settings.spotify_auth_base}/api/token"
        try:
            response = requests.post(
                auth_url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._redirect_uri,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=f"Spotify auth failed: {e}")

        data = response.json()
        self._save_token(
            {
                "access_token": data["access_token"],
                "refresh_token": data["refresh_token"],
                "expires_at": int(time.time()) + data["expires_in"],
            }
        )

    def _refresh(self) -> None:
        auth_url = f"{settings.spotify_auth_base}/api/token"
        refresh_token = self._token_data.get("refresh_token", "")
        if not refresh_token:
            raise HTTPException(status_code=401, detail="No refresh token — visit /login")
        try:
            response = requests.post(
                auth_url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise HTTPException(status_code=401, detail=f"Token refresh failed — visit /login: {e}")

        data = response.json()
        self._save_token(
            {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token", refresh_token),
                "expires_at": int(time.time()) + data["expires_in"],
            }
        )

    def _access_token(self) -> str:
        if int(time.time()) >= self._token_data.get("expires_at", 0) - 60:
            self._token_data = self._load_token()
            if int(time.time()) >= self._token_data.get("expires_at", 0) - 60:
                self._refresh()
        return self._token_data["access_token"]

    def _header(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token()}",
            "Accept": "application/json",
        }

    def _get(self, url: str) -> dict:
        try:
            response = requests.get(url=url, headers=self._header(), timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=f"Spotify request failed: {e}")
        return response.json()

    def _post(self, url: str, body: dict) -> dict:
        try:
            response = requests.post(url=url, headers=self._header(), json=body, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=f"Spotify request failed: {e}")
        return response.json()

    def _delete(self, url: str, body: dict) -> dict:
        try:
            response = requests.delete(url=url, headers=self._header(), json=body, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=f"Spotify request failed: {e}")
        return response.json() if response.content else {}

    def get_user_playlists(self, user_id: str, offset: int = 0, limit: int = 10) -> dict:
        """Single page of playlists for any user. Raw Spotify response."""
        url = f"{settings.spotify_api_base}/users/{user_id}/playlists?offset={offset}&limit={limit}"
        return self._get(url)

    def get_my_playlists(self, offset: int = 0, limit: int = 50) -> dict:
        """Single page of the authenticated user's playlists. Raw Spotify response."""
        url = f"{settings.spotify_api_base}/me/playlists?offset={offset}&limit={limit}"
        return self._get(url)

    def search_my_playlists(self, q: str) -> list[dict]:
        """Fetch all playlists and return those whose name contains q (case-insensitive)."""
        items = []
        offset = 0
        while True:
            page = self.get_my_playlists(offset=offset, limit=50)
            items.extend(page.get("items", []))
            if page.get("next") is None:
                break
            offset += 50
        return [p for p in items if q.lower() in p["name"].lower()]

    def get_liked_songs(self, offset: int = 0, limit: int = 50) -> dict:
        """Single page of liked songs. Spotify returns newest-added first. Raw Spotify response."""
        url = f"{settings.spotify_api_base}/me/tracks?offset={offset}&limit={limit}"
        return self._get(url)

    def iter_liked_songs(self, page_size: int = 50):
        """
        Generator — yields every liked song item newest-first (Spotify's native order).
        Each item: {"added_at": "YYYY-MM-DDTHH:MM:SSZ", "track": {...}}
        """
        offset = 0
        while True:
            page = self.get_liked_songs(offset=offset, limit=page_size)
            yield from page.get("items", [])
            if page.get("next") is None:
                break
            offset += page_size

    def get_liked_songs_before(self, before: str, offset: int = 0, limit: int = 50) -> dict:
        """
        Return liked songs added on or before `before` (YYYY-MM-DD), newest-first.
        Loads all matching items into memory before paginating — use offset/limit to page through results.
        Example: before="2025-09-16" → songs from 2025-09-16 back to oldest liked song.
        """
        all_items = [i for i in self.iter_liked_songs() if i["added_at"][:10] <= before]
        return {"total": len(all_items), "offset": offset, "limit": limit, "items": all_items[offset : offset + limit]}

    def get_liked_songs_after(self, after: str, offset: int = 0, limit: int = 50) -> dict:
        """
        Return liked songs added on or after `after` (YYYY-MM-DD), newest-first.
        Stops paginating as soon as a song older than `after` is found (early exit).
        Example: after="2025-09-16" → songs from now back to 2025-09-16 (the newer portion of your library).
        """
        all_items = []
        for item in self.iter_liked_songs():
            if item["added_at"][:10] < after:
                break
            all_items.append(item)
        return {"total": len(all_items), "offset": offset, "limit": limit, "items": all_items[offset : offset + limit]}

    def delete_liked_songs_on_or_before(self, before: str, dry_run: bool = True) -> int:
        """
        Delete liked songs added on or before `before` (YYYY-MM-DD).
        Streams newest-first, skips newer songs, deletes in 50-track batches (Spotify API max).
        dry_run=True (default): counts candidates without deleting — always run this first.
        Returns count of tracks deleted (or would-be deleted).
        """
        candidates = (item["track"]["id"] for item in self.iter_liked_songs() if item["added_at"][:10] <= before)
        deleted = 0
        while chunk := list(islice(candidates, 50)):
            if not dry_run:
                self.remove_liked_songs(chunk)
            deleted += len(chunk)
        return deleted

    def remove_liked_songs(self, track_ids: list[str]) -> dict:
        """Remove up to 50 tracks from liked songs by track ID. Spotify enforces the 50-per-request limit."""
        url = f"{settings.spotify_api_base}/me/tracks"
        return self._delete(url, {"ids": track_ids})

    def get_playlist_tracks(self, playlist_id: str, offset: int = 0, limit: int = 50) -> dict:
        """Single page of tracks in a playlist. Raw Spotify response."""
        url = f"{settings.spotify_api_base}/playlists/{playlist_id}/tracks?offset={offset}&limit={limit}"
        return self._get(url)

    def remove_playlist_tracks(self, playlist_id: str, track_ids: list[str]) -> dict:
        """Remove tracks from a playlist by track ID. Converts IDs to spotify:track URIs internally."""
        url = f"{settings.spotify_api_base}/playlists/{playlist_id}/tracks"
        body = {"tracks": [{"uri": f"spotify:track:{tid}"} for tid in track_ids]}
        return self._delete(url, body)

    def get_track(self, track_id: str) -> dict:
        """Fetch a single track object by ID."""
        return self._get(f"{settings.spotify_api_base}/tracks/{track_id}")

    def search_tracks(self, query: str, limit: int = 50) -> list[dict]:
        """Search for tracks by query string (supports genre:worship, artist:name, etc). Max 50 per call."""
        url = f"{settings.spotify_api_base}/search?q={urllib.parse.quote(query)}&type=track&limit={min(limit, 50)}"
        return self._get(url).get("tracks", {}).get("items", [])

    def get_artist_tracks(self, artist_id: str, max_albums: int = 5) -> list[dict]:
        """
        Fetch tracks from artist's recent albums and singles.
        Injects album object into each track so _build_track_features can extract release_year.
        Used as niche-artist fallback when genre search yields too few candidates.
        """
        albums = self._get(
            f"{settings.spotify_api_base}/artists/{artist_id}/albums?include_groups=album,single&limit={max_albums}"
        ).get("items", [])
        tracks = []
        for album in albums:
            album_tracks = self._get(f"{settings.spotify_api_base}/albums/{album['id']}/tracks?limit=50").get(
                "items", []
            )
            for track in album_tracks:
                track["album"] = album
                tracks.append(track)
        return tracks

    def get_related_artists(self, artist_id: str) -> list[dict]:
        """
        DEPRECATED by Spotify (November 2024) — returns 404 for new apps.
        Kept for reference. Do not use in new functionality.
        """
        return self._get(f"{settings.spotify_api_base}/artists/{artist_id}/related-artists").get("artists", [])

    def get_artist_top_tracks(self, artist_id: str) -> list[dict]:
        """Fetch up to 10 top tracks for an artist."""
        return self._get(f"{settings.spotify_api_base}/artists/{artist_id}/top-tracks").get("tracks", [])

    def get_me(self) -> dict:
        """Get current user's profile. Requires user-read-private scope."""
        return self._get(f"{settings.spotify_api_base}/me")

    def get_audio_features(self, track_ids: list[str]) -> list[dict]:
        """
        DEPRECATED by Spotify (November 2024) — returns 403 for apps registered after the cutoff.
        Kept for reference. Do not use in new functionality.
        Original fields: tempo, energy, danceability, valence, acousticness, speechiness, instrumentalness.
        """
        result = []
        it = iter(track_ids)
        while chunk := list(islice(it, 100)):
            batch = self._get(f"{settings.spotify_api_base}/audio-features?ids={','.join(chunk)}")
            result.extend(batch.get("audio_features", []))
        return result

    def get_artists(self, artist_ids: list[str]) -> list[dict]:
        """Batch fetch artist objects (50 per request, Spotify API max). Each artist includes genres list."""
        result = []
        it = iter(artist_ids)
        while chunk := list(islice(it, 50)):
            batch = self._get(f"{settings.spotify_api_base}/artists?ids={','.join(chunk)}")
            result.extend(batch.get("artists", []))
        return result

    def create_playlist(self, user_id: str, name: str, description: str = "", public: bool = False) -> dict:
        """Create a new empty playlist for the given user. Returns full playlist object including id."""
        url = f"{settings.spotify_api_base}/users/{user_id}/playlists"
        return self._post(url, {"name": name, "description": description, "public": public})

    def add_tracks_to_playlist(self, playlist_id: str, track_uris: list[str]) -> dict:
        """
        Add tracks to playlist in batches of 100 (Spotify API max).
        track_uris must be in 'spotify:track:{id}' format.
        """
        url = f"{settings.spotify_api_base}/playlists/{playlist_id}/tracks"
        result: dict = {}
        it = iter(track_uris)
        while chunk := list(islice(it, 100)):
            result = self._post(url, {"uris": chunk})
        return result
