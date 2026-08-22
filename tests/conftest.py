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
