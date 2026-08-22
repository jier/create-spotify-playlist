import json
import time
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from src.services.spotifyService import SpotifyService


def _write_token(path, *, access_token: str, refresh_token: str, expires_at: int) -> None:
    data = {"access_token": access_token, "refresh_token": refresh_token, "expires_at": expires_at}
    path.write_text(json.dumps(data))


def _make_service_with_token(monkeypatch, tmp_path, *, refresh_token: str = "refresh_abc", expires_at: int):
    token_path = tmp_path / "token.json"
    _write_token(token_path, access_token="access_abc", refresh_token=refresh_token, expires_at=expires_at)
    monkeypatch.setattr("src.services.spotifyService.settings.token_path", token_path)
    return SpotifyService(client_id="id", client_secret="secret", redirect_uri="http://127.0.0.1:8000/callback")


def test_access_token_returns_cached_token_when_not_expired(monkeypatch, tmp_path):
    svc = _make_service_with_token(monkeypatch, tmp_path, expires_at=int(time.time()) + 3600)

    with patch("src.services.spotifyService.requests.post") as mock_post:
        token = svc._access_token()

    assert token == "access_abc"
    mock_post.assert_not_called()


def test_access_token_refreshes_when_expired(monkeypatch, tmp_path):
    svc = _make_service_with_token(monkeypatch, tmp_path, expires_at=int(time.time()) - 3600)

    fake_response = Mock()
    fake_response.json.return_value = {
        "access_token": "new_access_token",
        "refresh_token": "new_refresh_token",
        "expires_in": 3600,
    }
    fake_response.raise_for_status.return_value = None

    with patch("src.services.spotifyService.requests.post", return_value=fake_response) as mock_post:
        token = svc._access_token()

    mock_post.assert_called_once()
    assert token == "new_access_token"


def test_refresh_raises_401_when_no_refresh_token_present(monkeypatch, tmp_path):
    svc = _make_service_with_token(monkeypatch, tmp_path, refresh_token="", expires_at=0)

    with pytest.raises(HTTPException) as exc_info:
        svc._refresh()

    assert exc_info.value.status_code == 401


def test_refresh_persists_new_token_data(monkeypatch, tmp_path):
    token_path = tmp_path / "token.json"
    _write_token(token_path, access_token="old", refresh_token="refresh_abc", expires_at=0)
    monkeypatch.setattr("src.services.spotifyService.settings.token_path", token_path)
    svc = SpotifyService(client_id="id", client_secret="secret", redirect_uri="http://127.0.0.1:8000/callback")

    fake_response = Mock()
    fake_response.json.return_value = {
        "access_token": "new_access_token",
        "refresh_token": "new_refresh_token",
        "expires_in": 1800,
    }
    fake_response.raise_for_status.return_value = None

    with patch("src.services.spotifyService.requests.post", return_value=fake_response):
        svc._refresh()

    saved = json.loads(token_path.read_text())
    assert saved["access_token"] == "new_access_token"
    assert saved["refresh_token"] == "new_refresh_token"


def test_get_wraps_request_exception_as_502(monkeypatch, tmp_path):
    svc = _make_service_with_token(monkeypatch, tmp_path, expires_at=int(time.time()) + 3600)

    import requests

    with patch("src.services.spotifyService.requests.get", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(HTTPException) as exc_info:
            svc._get("https://api.spotify.com/v1/me")

    assert exc_info.value.status_code == 502


def test_post_wraps_request_exception_as_502(monkeypatch, tmp_path):
    svc = _make_service_with_token(monkeypatch, tmp_path, expires_at=int(time.time()) + 3600)

    import requests

    with patch("src.services.spotifyService.requests.post", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(HTTPException) as exc_info:
            svc._post("https://api.spotify.com/v1/playlists", {})

    assert exc_info.value.status_code == 502


def test_delete_returns_empty_dict_when_response_has_no_content(monkeypatch, tmp_path):
    svc = _make_service_with_token(monkeypatch, tmp_path, expires_at=int(time.time()) + 3600)

    fake_response = Mock()
    fake_response.raise_for_status.return_value = None
    fake_response.content = b""

    with patch("src.services.spotifyService.requests.delete", return_value=fake_response):
        result = svc._delete("https://api.spotify.com/v1/me/tracks", {"ids": ["1"]})

    assert result == {}


def test_delete_returns_json_body_when_response_has_content(monkeypatch, tmp_path):
    svc = _make_service_with_token(monkeypatch, tmp_path, expires_at=int(time.time()) + 3600)

    fake_response = Mock()
    fake_response.raise_for_status.return_value = None
    fake_response.content = b'{"snapshot_id": "abc"}'
    fake_response.json.return_value = {"snapshot_id": "abc"}

    with patch("src.services.spotifyService.requests.delete", return_value=fake_response):
        result = svc._delete("https://api.spotify.com/v1/playlists/1/tracks", {"tracks": []})

    assert result == {"snapshot_id": "abc"}
