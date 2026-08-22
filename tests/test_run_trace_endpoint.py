import json

from fastapi.testclient import TestClient

from src.algorithms.persistence import RunTraceWriter
from src.app import app

LOOPBACK = ("127.0.0.1", 12345)


def test_get_run_trace_returns_jsonl_content_for_an_existing_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    writer = RunTraceWriter("run_1")
    writer.write_seed("seed_track", ["rock"], 2000)
    writer.write_final(["seed_track"], tsp_score=0.0, initial_score=0.0)

    client = TestClient(app, client=LOOPBACK)
    response = client.get("/runs/run_1")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(line) for line in response.text.splitlines()]
    assert [line["stage"] for line in lines] == ["seed", "final"]


def test_get_run_trace_404s_for_a_run_that_was_never_written(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    client = TestClient(app, client=LOOPBACK)
    response = client.get("/runs/never_happened")

    assert response.status_code == 404


def test_get_run_trace_404s_rather_than_leaking_path_traversal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "secret.txt").write_text("should not be readable via this endpoint")

    client = TestClient(app, client=LOOPBACK)
    response = client.get("/runs/..%2Fsecret.txt")

    assert response.status_code in (400, 404)
    assert "should not be readable" not in response.text
