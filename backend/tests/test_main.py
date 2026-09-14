from fastapi.testclient import TestClient

from app import main
from app.config import settings


def test_health_reports_read_only_flag(monkeypatch):
    monkeypatch.setattr(settings, "hosted_demo_read_only", True)
    client = TestClient(main.app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["read_only"] is True


def test_jobs_refused_when_hosted_demo_read_only(monkeypatch):
    monkeypatch.setattr(settings, "hosted_demo_read_only", True)
    client = TestClient(main.app)
    resp = client.post("/api/jobs", json={"model_a": "mistral-3-14B", "model_b": "deepseek-4-flash"})
    assert resp.status_code == 403
    assert "read-only" in resp.json()["detail"]


def test_jobs_allowed_when_not_read_only(monkeypatch):
    # TestClient runs BackgroundTasks synchronously within the request, so this
    # actually executes run_comparison() — force dry_run regardless of any real
    # .env/SI_API_KEY present, so this test never makes a real, billed API call.
    monkeypatch.setattr(settings, "hosted_demo_read_only", False)
    monkeypatch.setattr(settings, "dry_run", True)
    monkeypatch.setattr(main, "_job_in_flight", False)
    client = TestClient(main.app)
    resp = client.post("/api/jobs", json={"model_a": "mistral-3-14B", "model_b": "deepseek-4-flash", "limit": 1})
    assert resp.status_code == 200
    assert "job_id" in resp.json()
