import pytest
from fastapi.testclient import TestClient

from src.app import app


@pytest.mark.parametrize("loopback_address", ["127.0.0.1", "::1"])
def test_loopback_request_is_allowed(loopback_address):
    client = TestClient(app, client=(loopback_address, 12345))
    response = client.get("/")
    assert response.status_code == 200


@pytest.mark.parametrize("non_loopback_address", ["203.0.113.5", "10.0.0.5", "::2"])
def test_non_loopback_request_is_rejected(non_loopback_address):
    client = TestClient(app, client=(non_loopback_address, 12345))
    response = client.get("/")
    assert response.status_code == 403
    assert response.json() == {"detail": "This service only accepts requests from localhost."}


@pytest.mark.parametrize("method", ["post", "delete"])
def test_cross_origin_browser_mutation_is_rejected(method):
    client = TestClient(app, client=("127.0.0.1", 12345))

    response = getattr(client, method)("/does-not-exist", headers={"Origin": "https://attacker.example"})

    assert response.status_code == 403
    assert response.json() == {"detail": "Cross-origin mutation rejected."}


@pytest.mark.parametrize("origin", ["http://127.0.0.1:8000", "http://localhost:5173"])
def test_allowlisted_browser_origin_passes_origin_guard(origin):
    client = TestClient(app, client=("127.0.0.1", 12345))

    response = client.post("/does-not-exist", headers={"Origin": origin})

    assert response.status_code == 404


def test_cli_mutation_without_origin_passes_origin_guard():
    client = TestClient(app, client=("127.0.0.1", 12345))

    response = client.post("/does-not-exist")

    assert response.status_code == 404


@pytest.mark.parametrize("n", [0, -1, 101])
def test_seed_playlist_rejects_invalid_track_count_before_calling_service(n):
    client = TestClient(app, client=("127.0.0.1", 12345))

    response = client.post(f"/me/playlists/seed/seed?n={n}")

    assert response.status_code == 422
