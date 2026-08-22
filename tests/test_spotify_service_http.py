import json
import time
from unittest.mock import Mock, patch

import pytest
import requests
from fastapi import HTTPException


def test_access_token_returns_cached_token_when_not_expired(write_token, make_spotify_service):
    write_token(access_token="access_abc", expires_at=int(time.time()) + 3600)
    svc = make_spotify_service()

    with patch("src.services.spotifyService.requests.post") as mock_post:
        token = svc._access_token()

    assert token == "access_abc"
    mock_post.assert_not_called()


def test_access_token_refreshes_when_expired(write_token, make_spotify_service, fake_token_response):
    write_token(expires_at=int(time.time()) - 3600)
    svc = make_spotify_service()
    response = fake_token_response(access_token="new_access_token")

    with patch("src.services.spotifyService.requests.post", return_value=response) as mock_post:
        token = svc._access_token()

    mock_post.assert_called_once()
    assert token == "new_access_token"


def test_refresh_raises_401_when_no_refresh_token_present(write_token, make_spotify_service):
    write_token(refresh_token="", expires_at=0)
    svc = make_spotify_service()

    with pytest.raises(HTTPException) as exc_info:
        svc._refresh()

    assert exc_info.value.status_code == 401


def test_refresh_persists_new_token_data(write_token, make_spotify_service, fake_token_response, token_path):
    write_token(access_token="old", expires_at=0)
    svc = make_spotify_service()
    response = fake_token_response(access_token="new_access_token", refresh_token="new_refresh_token")

    with patch("src.services.spotifyService.requests.post", return_value=response):
        svc._refresh()

    saved = json.loads(token_path.read_text())
    assert saved["access_token"] == "new_access_token"
    assert saved["refresh_token"] == "new_refresh_token"


@pytest.fixture
def authenticated_spotify_service(write_token, make_spotify_service):
    """SpotifyService with a valid, non-expired token, ready to call the API.

    _get/_post/_delete all call _access_token() internally before the actual
    request; without a live token they would 401 on refresh before ever
    reaching the mocked HTTP call this fixture's tests are exercising.
    """
    write_token(expires_at=int(time.time()) + 3600)
    return make_spotify_service()


@pytest.mark.parametrize(
    ("method_name", "call_args"),
    [
        ("_get", ("https://api.spotify.com/v1/me",)),
        ("_post", ("https://api.spotify.com/v1/playlists", {})),
    ],
    ids=["get", "post"],
)
def test_get_and_post_wrap_request_exception_as_502(authenticated_spotify_service, method_name, call_args):
    requests_method = {"_get": "get", "_post": "post"}[method_name]
    with patch(f"src.services.spotifyService.requests.{requests_method}", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(HTTPException) as exc_info:
            getattr(authenticated_spotify_service, method_name)(*call_args)

    assert exc_info.value.status_code == 502


def test_delete_wraps_request_exception_as_502(authenticated_spotify_service):
    with patch("src.services.spotifyService.requests.delete", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(HTTPException) as exc_info:
            authenticated_spotify_service._delete("https://api.spotify.com/v1/me/tracks", {"ids": ["1"]})

    assert exc_info.value.status_code == 502


@pytest.mark.parametrize(
    ("content", "json_body", "expected"),
    [
        (b"", None, {}),
        (b'{"snapshot_id": "abc"}', {"snapshot_id": "abc"}, {"snapshot_id": "abc"}),
    ],
    ids=["no_content", "with_content"],
)
def test_delete_returns_empty_dict_or_parsed_body_based_on_content(
    authenticated_spotify_service, content, json_body, expected
):
    fake_response = Mock()
    fake_response.raise_for_status.return_value = None
    fake_response.content = content
    fake_response.json.return_value = json_body

    with patch("src.services.spotifyService.requests.delete", return_value=fake_response):
        result = authenticated_spotify_service._delete("https://api.spotify.com/v1/me/tracks", {"ids": ["1"]})

    assert result == expected
