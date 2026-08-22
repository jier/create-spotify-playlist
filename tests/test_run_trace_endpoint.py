import json

from fastapi.testclient import TestClient

from src.algorithms.persistence import RunTraceWriter
from src.app import app
from src.settings import settings

LOOPBACK = ("127.0.0.1", 12345)

# isolated_runs_dir (conftest.py, autouse) already points settings.runs_dir at
# a per-test tmp_path — write through that same path so the app's GET
# /runs/{run_id} (which reads settings.runs_dir) sees what this test wrote.


def test_get_run_trace_returns_jsonl_content_for_an_existing_run():
    writer = RunTraceWriter("run_1", runs_dir=settings.runs_dir)
    writer.write_seed("seed_track", ["rock"], 2000)
    writer.write_final(["seed_track"], tsp_score=0.0, initial_score=0.0)

    client = TestClient(app, client=LOOPBACK)
    response = client.get("/runs/run_1")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(line) for line in response.text.splitlines()]
    assert [line["stage"] for line in lines] == ["seed", "final"]


def test_get_run_trace_404s_for_a_run_that_was_never_written():
    client = TestClient(app, client=LOOPBACK)
    response = client.get("/runs/never_happened")

    assert response.status_code == 404


def test_get_run_trace_404s_rather_than_leaking_path_traversal():
    settings.runs_dir.parent.mkdir(parents=True, exist_ok=True)
    (settings.runs_dir.parent / "secret.txt").write_text("should not be readable via this endpoint")

    client = TestClient(app, client=LOOPBACK)
    response = client.get("/runs/..%2Fsecret.txt")

    assert response.status_code in (400, 404)
    assert "should not be readable" not in response.text
