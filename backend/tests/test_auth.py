from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def credentials(username: str = "reader_one", password: str = "safe-pass-123") -> dict:
    return {"username": username, "password": password}


def test_register_login_session_and_logout(settings) -> None:
    app = create_app(settings=settings)
    with TestClient(app) as client:
        registered = client.post("/api/auth/register", json=credentials())
        assert registered.status_code == 201
        assert registered.json()["username"] == "reader_one"
        cookie = registered.headers["set-cookie"].lower()
        assert "httponly" in cookie
        assert "samesite=lax" in cookie

        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["username"] == "reader_one"

        logged_out = client.post("/api/auth/logout")
        assert logged_out.status_code == 200
        assert client.get("/api/auth/me").status_code == 401

        logged_in = client.post("/api/auth/login", json=credentials())
        assert logged_in.status_code == 200
        assert client.get("/api/auth/me").json()["id"] == me.json()["id"]


def test_auth_rejects_duplicates_and_invalid_credentials(settings) -> None:
    app = create_app(settings=settings)
    with TestClient(app) as client:
        assert client.post("/api/auth/register", json=credentials()).status_code == 201
        duplicate = client.post(
            "/api/auth/register",
            json=credentials(username="READER_ONE", password="another-pass-123"),
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"]["code"] == "USERNAME_TAKEN"

        wrong = client.post(
            "/api/auth/login",
            json=credentials(password="incorrect-pass"),
        )
        assert wrong.status_code == 401
        assert wrong.json()["detail"]["code"] == "INVALID_CREDENTIALS"


def test_download_and_summary_endpoints_require_login(settings) -> None:
    app = create_app(settings=settings)
    with TestClient(app) as client:
        download = client.post(
            "/api/inspect",
            json={"url": "https://8.8.8.8/video"},
        )
        summary = client.post(
            "/api/ai-summaries",
            json={"url": "https://8.8.8.8/video"},
        )
    assert download.status_code == 401
    assert download.json()["detail"]["code"] == "AUTH_REQUIRED"
    assert summary.status_code == 401


def test_password_is_not_stored_as_plaintext(settings) -> None:
    app = create_app(settings=settings)
    with TestClient(app) as client:
        assert client.post("/api/auth/register", json=credentials()).status_code == 201
    database_bytes = b"".join(
        path.read_bytes()
        for path in settings.auth_db_path.parent.glob(f"{settings.auth_db_path.name}*")
        if path.is_file()
    )
    assert b"safe-pass-123" not in database_bytes
    assert b"scrypt$" in database_bytes


def test_auth_attempts_are_rate_limited(settings) -> None:
    app = create_app(settings=settings)
    with TestClient(app) as client:
        responses = [
            client.post(
                "/api/auth/login",
                json=credentials(username="missing_user"),
            )
            for _ in range(11)
        ]
    assert all(response.status_code == 401 for response in responses[:10])
    assert responses[10].status_code == 429
    assert responses[10].json()["detail"]["code"] == "AUTH_RATE_LIMITED"
