from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert "app_name" in body
    assert "version" in body


def test_root_endpoint_returns_message() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()
