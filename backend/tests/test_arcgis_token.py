from fastapi.testclient import TestClient

from app.api.routes import arcgis_token
from app.main import app

client = TestClient(app)


def test_arcgis_token_returns_503_when_not_configured(monkeypatch) -> None:
    """Bez ARCGIS_CLIENT_ID/SECRET u .env, endpoint mora vratiti jasnu 503
    grešku (nedostupna eksterna zavisnost), ne 500 (bug u našem kodu)."""
    monkeypatch.setattr(arcgis_token._arcgis_auth_service, "_cached_token", None)
    monkeypatch.setattr(arcgis_token._arcgis_auth_service._settings, "arcgis_client_id", None)
    monkeypatch.setattr(arcgis_token._arcgis_auth_service._settings, "arcgis_client_secret", None)

    response = client.get("/api/v1/arcgis-token")

    assert response.status_code == 503
    assert "ARCGIS_CLIENT_ID" in response.json()["detail"]


def test_arcgis_token_returns_cached_token_when_valid(monkeypatch) -> None:
    """Kad je token već u cache-u i još važi, ne smije se praviti novi HTTP poziv."""
    from app.services.arcgis_auth import _CachedToken
    import time

    fake_token = _CachedToken(access_token="fake-token-123", expires_at_epoch_s=time.monotonic() + 3600)
    monkeypatch.setattr(arcgis_token._arcgis_auth_service, "_cached_token", fake_token)

    response = client.get("/api/v1/arcgis-token")

    assert response.status_code == 200
    assert response.json() == {"access_token": "fake-token-123"}
