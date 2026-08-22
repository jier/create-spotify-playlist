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
