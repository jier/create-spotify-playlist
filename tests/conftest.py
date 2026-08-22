import json
import time
from unittest.mock import Mock

import pytest

from src.services.spotifyService import SpotifyService

REDIRECT_URI = "http://127.0.0.1:8000/callback"


@pytest.fixture
def token_path(tmp_path, monkeypatch):
    """tmp_path location for token.json, wired into settings. No file written yet.

    Every SpotifyService test goes through this fixture (directly or via
    make_spotify_service/spotify_service below), so no test can ever read or
    write the real project token.json.
    """
    path = tmp_path / "token.json"
    monkeypatch.setattr("src.services.spotifyService.settings.token_path", path)
    return path


@pytest.fixture
def make_spotify_service(token_path):
    """Factory: build a fresh SpotifyService, reading whatever token_path holds."""

    def _make() -> SpotifyService:
        return SpotifyService(client_id="test_id", client_secret="test_secret", redirect_uri=REDIRECT_URI)

    return _make


@pytest.fixture
def spotify_service(make_spotify_service) -> SpotifyService:
    """A single fresh SpotifyService with no prior token, the /login starting point."""
    return make_spotify_service()


@pytest.fixture
def write_token(token_path):
    """Factory: write a token.json-shaped file at the wired token_path.

    Call this before make_spotify_service()/spotify_service to control the
    token state the service loads at construction time.
    """

    def _write(*, access_token="access_abc", refresh_token="refresh_abc", expires_at=None):
        if expires_at is None:
            expires_at = int(time.time()) + 3600
        data = {"access_token": access_token, "refresh_token": refresh_token, "expires_at": expires_at}
        token_path.write_text(json.dumps(data))

    return _write


@pytest.fixture
def fake_token_response():
    """Factory: build a Mock requests.Response for a successful token exchange/refresh."""

    def _make(*, access_token="new_access_token", refresh_token="new_refresh_token", expires_in=3600):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
        }
        return response

    return _make


@pytest.fixture
def rock_seed_feat() -> list:
    """A simple rock-genre seed track feature, reused across selection strategy tests."""
    return ["seed", {"genres": {"rock"}, "release_year": 2000}]


@pytest.fixture
def rock_candidate_pool():
    """Factory: build (candidate_features, candidate_tracks) for `count` distinct
    rock-genre tracks, each by a different artist, release years incrementing from 2000."""

    def _make(count: int) -> tuple[list[list], dict[str, dict]]:
        candidate_features = [[f"track_{i}", {"genres": {"rock"}, "release_year": 2000 + i}] for i in range(count)]
        candidate_tracks = {f"track_{i}": {"artists": [{"id": f"artist_{i}"}]} for i in range(count)}
        return candidate_features, candidate_tracks

    return _make


class FakePlaylistSpotify:
    """
    Minimal test double implementing only the methods PlaylistBuilderService
    calls on its SpotifyService. Not a real SpotifyService, no auth, no HTTP,
    no token.json, everything is preloaded data a test controls directly.
    """

    def __init__(self) -> None:
        self.tracks: dict[str, dict] = {}
        self.artists: dict[str, dict] = {}
        self.search_results: dict[str, list[dict]] = {}
        self.artist_tracks: dict[str, list[dict]] = {}
        self.liked_songs: list[dict] = []
        self.me: dict = {"id": "user_1"}
        self.created_playlists: list[dict] = []
        self.added_tracks: list[tuple[str, list[str]]] = []

    def get_track(self, track_id: str) -> dict:
        return self.tracks[track_id]

    def get_artists(self, artist_ids: list[str]) -> list[dict]:
        return [self.artists[aid] for aid in artist_ids if aid in self.artists]

    def search_tracks(self, query: str, limit: int = 50) -> list[dict]:
        return self.search_results.get(query, [])

    def get_artist_tracks(self, artist_id: str, max_albums: int = 5) -> list[dict]:
        return self.artist_tracks.get(artist_id, [])

    def get_me(self) -> dict:
        return self.me

    def create_playlist(self, user_id: str, name: str, description: str = "", public: bool = False) -> dict:
        playlist = {"id": f"playlist_{len(self.created_playlists)}", "name": name}
        self.created_playlists.append(playlist)
        return playlist

    def add_tracks_to_playlist(self, playlist_id: str, track_uris: list[str]) -> dict:
        self.added_tracks.append((playlist_id, track_uris))
        return {}

    def iter_liked_songs(self, page_size: int = 50):
        yield from self.liked_songs


@pytest.fixture
def fake_playlist_spotify() -> FakePlaylistSpotify:
    """A fresh FakePlaylistSpotify with nothing preloaded."""
    return FakePlaylistSpotify()


@pytest.fixture
def rock_track_features():
    """Factory: build track_features for `count` distinct rock-genre tracks.
    Release years increment from 2000 by default, or are all identical if distinct_years=False."""

    def _make(count: int, *, distinct_years: bool = True) -> list[list]:
        return [
            [f"track_{i}", {"genres": {"rock"}, "release_year": 2000 + i if distinct_years else 2000}]
            for i in range(count)
        ]

    return _make
