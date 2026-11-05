from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_ai_summary_capabilities_do_not_expose_key(settings, monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    app = create_app(settings=settings)
    with TestClient(app) as client:
        response = client.get("/api/ai-summaries/capabilities")
    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert "api_key" not in response.text.lower()


def test_ai_summary_returns_clear_error_when_unconfigured(settings, monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    app = create_app(settings=settings)
    with TestClient(app) as client:
        response = client.post(
            "/api/ai-summaries",
            json={"url": "https://8.8.8.8/video"},
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "AI_NOT_CONFIGURED"


def test_ai_summary_rejects_private_url(settings, monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    app = create_app(settings=settings)
    with TestClient(app) as client:
        response = client.post(
            "/api/ai-summaries",
            json={"url": "http://127.0.0.1/video"},
        )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNSAFE_URL"


def test_ai_summary_missing_job_returns_404(settings) -> None:
    app = create_app(settings=settings)
    with TestClient(app) as client:
        response = client.get("/api/ai-summaries/not-found")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "SUMMARY_NOT_FOUND"
