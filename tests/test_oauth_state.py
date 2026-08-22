import json
import urllib.parse
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from src.services.spotifyService import SpotifyService


def _make_service() -> SpotifyService:
    return SpotifyService(
        client_id="test_id", client_secret="test_secret", redirect_uri="http://127.0.0.1:8000/callback"
    )


def _state_from_url(url: str) -> str:
    query = urllib.parse.urlparse(url).query
    return urllib.parse.parse_qs(query)["state"][0]


def test_get_auth_url_includes_a_state_param():
    svc = _make_service()
    url = svc.get_auth_url()
    state = _state_from_url(url)
    assert state
    assert len(state) >= 32


def test_exchange_code_rejects_mismatched_state():
    svc = _make_service()
    svc.get_auth_url()

    with patch("src.services.spotifyService.requests.post") as mock_post:
        with pytest.raises(HTTPException) as exc_info:
            svc.exchange_code(code="irrelevant", state="wrong_value")

    assert exc_info.value.status_code == 400
    mock_post.assert_not_called()


def test_exchange_code_rejects_without_a_prior_login_call():
    svc = _make_service()

    with patch("src.services.spotifyService.requests.post") as mock_post:
        with pytest.raises(HTTPException) as exc_info:
            svc.exchange_code(code="irrelevant", state="anything")

    assert exc_info.value.status_code == 400
    mock_post.assert_not_called()


def test_state_is_single_use_second_attempt_with_same_state_fails(tmp_path):
    svc = _make_service()
    url = svc.get_auth_url()
    state = _state_from_url(url)

    fake_response = Mock()
    fake_response.json.return_value = {
        "access_token": "fake_access_token",
        "refresh_token": "fake_refresh_token",
        "expires_in": 3600,
    }
    fake_response.raise_for_status.return_value = None

    token_path = tmp_path / "token.json"
    with patch("src.services.spotifyService.settings.token_path", token_path):
        with patch("src.services.spotifyService.requests.post", return_value=fake_response):
            svc.exchange_code(code="real_code", state=state)

        with patch("src.services.spotifyService.requests.post") as mock_post_second:
            with pytest.raises(HTTPException) as exc_info:
                svc.exchange_code(code="another_code", state=state)

    assert exc_info.value.status_code == 400
    mock_post_second.assert_not_called()


def test_exchange_code_succeeds_with_matching_state_and_saves_token(tmp_path):
    svc = _make_service()
    url = svc.get_auth_url()
    state = _state_from_url(url)

    fake_response = Mock()
    fake_response.json.return_value = {
        "access_token": "fake_access_token",
        "refresh_token": "fake_refresh_token",
        "expires_in": 3600,
    }
    fake_response.raise_for_status.return_value = None

    token_path = tmp_path / "token.json"
    with patch("src.services.spotifyService.settings.token_path", token_path):
        with patch("src.services.spotifyService.requests.post", return_value=fake_response) as mock_post:
            svc.exchange_code(code="real_code", state=state)

        mock_post.assert_called_once()
        saved = json.loads(token_path.read_text())

    assert saved["access_token"] == "fake_access_token"
    assert saved["refresh_token"] == "fake_refresh_token"
