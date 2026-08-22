import urllib.parse
from unittest.mock import patch

import pytest
from fastapi import HTTPException


def _state_from_url(url: str) -> str:
    query = urllib.parse.urlparse(url).query
    return urllib.parse.parse_qs(query)["state"][0]


def test_get_auth_url_includes_a_state_param(spotify_service):
    url = spotify_service.get_auth_url()
    state = _state_from_url(url)
    assert state
    assert len(state) >= 32


@pytest.mark.parametrize(
    ("call_login_first", "sent_state"),
    [(True, "wrong_value"), (False, "anything")],
    ids=["mismatched_state", "no_prior_login_call"],
)
def test_exchange_code_rejects_invalid_state(spotify_service, call_login_first, sent_state):
    if call_login_first:
        spotify_service.get_auth_url()

    with patch("src.services.spotifyService.requests.post") as mock_post:
        with pytest.raises(HTTPException) as exc_info:
            spotify_service.exchange_code(code="irrelevant", state=sent_state)

    assert exc_info.value.status_code == 400
    mock_post.assert_not_called()


def test_state_is_single_use_second_attempt_with_same_state_fails(spotify_service, fake_token_response):
    url = spotify_service.get_auth_url()
    state = _state_from_url(url)

    with patch("src.services.spotifyService.requests.post", return_value=fake_token_response()):
        spotify_service.exchange_code(code="real_code", state=state)

    with patch("src.services.spotifyService.requests.post") as mock_post_second:
        with pytest.raises(HTTPException) as exc_info:
            spotify_service.exchange_code(code="another_code", state=state)

    assert exc_info.value.status_code == 400
    mock_post_second.assert_not_called()


def test_exchange_code_succeeds_with_matching_state_and_saves_token(spotify_service, fake_token_response, token_path):
    url = spotify_service.get_auth_url()
    state = _state_from_url(url)
    response = fake_token_response(access_token="fake_access_token", refresh_token="fake_refresh_token")

    with patch("src.services.spotifyService.requests.post", return_value=response) as mock_post:
        spotify_service.exchange_code(code="real_code", state=state)

    mock_post.assert_called_once()
    assert token_path.exists()
