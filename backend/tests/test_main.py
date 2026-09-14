import base64

from fastapi.testclient import TestClient

from app import main
from app.config import settings


def _basic_auth_header(username: str, password: str) -> dict:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_health_open_when_no_demo_credentials_configured(monkeypatch):
    monkeypatch.setattr(settings, "demo_username", "")
    monkeypatch.setattr(settings, "demo_password", "")
    client = TestClient(main.app)
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_requests_refused_without_credentials_when_demo_auth_configured(monkeypatch):
    monkeypatch.setattr(settings, "demo_username", "reviewer")
    monkeypatch.setattr(settings, "demo_password", "secret")
    client = TestClient(main.app)
    resp = client.get("/api/health")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"].startswith("Basic")


def test_requests_refused_with_wrong_credentials(monkeypatch):
    monkeypatch.setattr(settings, "demo_username", "reviewer")
    monkeypatch.setattr(settings, "demo_password", "secret")
    client = TestClient(main.app)
    resp = client.get("/api/health", headers=_basic_auth_header("reviewer", "wrong"))
    assert resp.status_code == 401


def test_requests_allowed_with_correct_credentials(monkeypatch):
    monkeypatch.setattr(settings, "demo_username", "reviewer")
    monkeypatch.setattr(settings, "demo_password", "secret")
    client = TestClient(main.app)
    resp = client.get("/api/health", headers=_basic_auth_header("reviewer", "secret"))
    assert resp.status_code == 200


def test_jobs_allowed_when_no_demo_auth_configured(monkeypatch):
    # TestClient runs BackgroundTasks synchronously within the request, so this
    # actually executes run_comparison() — force dry_run regardless of any real
    # .env/SI_API_KEY present, so this test never makes a real, billed API call.
    monkeypatch.setattr(settings, "demo_username", "")
    monkeypatch.setattr(settings, "demo_password", "")
    monkeypatch.setattr(settings, "dry_run", True)
    monkeypatch.setattr(main, "_job_in_flight", False)
    client = TestClient(main.app)
    resp = client.post("/api/jobs", json={"model_a": "mistral-3-14B", "model_b": "deepseek-4-flash", "limit": 1})
    assert resp.status_code == 200
    assert "job_id" in resp.json()


def test_jobs_allowed_once_authenticated(monkeypatch):
    monkeypatch.setattr(settings, "demo_username", "reviewer")
    monkeypatch.setattr(settings, "demo_password", "secret")
    monkeypatch.setattr(settings, "dry_run", True)
    monkeypatch.setattr(main, "_job_in_flight", False)
    client = TestClient(main.app)
    resp = client.post(
        "/api/jobs",
        json={"model_a": "mistral-3-14B", "model_b": "deepseek-4-flash", "limit": 1},
        headers=_basic_auth_header("reviewer", "secret"),
    )
    assert resp.status_code == 200
    assert "job_id" in resp.json()
