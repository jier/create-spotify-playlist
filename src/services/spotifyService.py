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

    def _paginate_liked_songs(self, page_size: int = 50):
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
        all_items = [i for i in self._paginate_liked_songs() if i["added_at"][:10] <= before]
        return {"total": len(all_items), "offset": offset, "limit": limit, "items": all_items[offset : offset + limit]}

    def get_liked_songs_after(self, after: str, offset: int = 0, limit: int = 50) -> dict:
        """
        Return liked songs added on or after `after` (YYYY-MM-DD), newest-first.
        Stops paginating as soon as a song older than `after` is found (early exit).
        Example: after="2025-09-16" → songs from now back to 2025-09-16 (the newer portion of your library).
        """
        all_items = []
        for item in self._paginate_liked_songs():
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
        candidates = (
            item["track"]["id"]
            for item in self._paginate_liked_songs()
            if item["added_at"][:10] <= before
        )
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
