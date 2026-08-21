from fastapi.testclient import TestClient

from src.app import app


def test_loopback_ipv4_request_is_allowed():
    client = TestClient(app, client=("127.0.0.1", 12345))
    response = client.get("/")
    assert response.status_code == 200


def test_loopback_ipv6_request_is_allowed():
    client = TestClient(app, client=("::1", 12345))
    response = client.get("/")
    assert response.status_code == 200


def test_non_loopback_request_is_rejected():
    client = TestClient(app, client=("203.0.113.5", 12345))
    response = client.get("/")
    assert response.status_code == 403
    assert response.json() == {"detail": "This service only accepts requests from localhost."}
