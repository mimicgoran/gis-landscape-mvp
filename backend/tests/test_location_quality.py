"""
Testovi za location quality servis -- Phase 7.

Vidi app/services/location_quality.py modul docstring za obrazloženje oba
granična slučaja (DEM nedostupan -> "low"; horizontal_accuracy_m == None ->
"high") koje ovi testovi brane od regresije, i
docs/architecture-feasibility-review.md, sekcija 6, za obrazloženje samih
brojčanih pragova.
"""

from __future__ import annotations

import pytest

from app.api.routes import observer as observer_route
from app.core.config import get_settings
from app.main import app
from app.models.observer import ObserverInput
from app.services.location_quality import (
    build_location_quality,
    classify_confidence,
    compute_observer_elevation_m,
)
from fastapi.testclient import TestClient

client = TestClient(app)
_settings = get_settings()


# --- classify_confidence ----------------------------------------------


def test_classify_confidence_high_within_threshold() -> None:
    assert classify_confidence(10.0, dem_available=True, settings=_settings) == "high"


def test_classify_confidence_high_at_exact_threshold() -> None:
    # Granica je inkluzivna (<=) -- vidi sekciju 6, tabela pragova.
    assert classify_confidence(_settings.horizontal_accuracy_high_m, dem_available=True, settings=_settings) == "high"


def test_classify_confidence_medium_just_above_high_threshold() -> None:
    just_above = _settings.horizontal_accuracy_high_m + 0.1
    assert classify_confidence(just_above, dem_available=True, settings=_settings) == "medium"


def test_classify_confidence_medium_at_exact_threshold() -> None:
    assert (
        classify_confidence(_settings.horizontal_accuracy_medium_m, dem_available=True, settings=_settings)
        == "medium"
    )


def test_classify_confidence_low_above_medium_threshold() -> None:
    just_above = _settings.horizontal_accuracy_medium_m + 0.1
    assert classify_confidence(just_above, dem_available=True, settings=_settings) == "low"


def test_classify_confidence_none_accuracy_treated_as_high() -> None:
    """Manual/desktop observer (Phase 2) -- nema GPS-a, pa se ne kažnjava
    kao 'nepoznata preciznost'."""
    assert classify_confidence(None, dem_available=True, settings=_settings) == "high"


def test_classify_confidence_dem_unavailable_forces_low_even_with_good_accuracy() -> None:
    """DEM nedostupan uvijek pobjeđuje -- čak i savršen GPS fix ne pomaže
    ako nemamo elevaciju."""
    assert classify_confidence(1.0, dem_available=False, settings=_settings) == "low"
    assert classify_confidence(None, dem_available=False, settings=_settings) == "low"


# --- compute_observer_elevation_m --------------------------------------


def test_compute_observer_elevation_adds_eye_height() -> None:
    assert compute_observer_elevation_m(1241.0, 1.7) == pytest.approx(1242.7)


def test_compute_observer_elevation_none_when_ground_elevation_missing() -> None:
    assert compute_observer_elevation_m(None, 1.7) is None


# --- build_location_quality ---------------------------------------------


def test_build_location_quality_with_dem_available() -> None:
    observer = ObserverInput(
        latitude=43.27,
        longitude=20.82,
        horizontal_accuracy_m=6.4,
        phone_altitude_m=1248.0,
        phone_altitude_accuracy_m=9.0,
    )

    quality = build_location_quality(observer, dem_elevation_m=1241.0, settings=_settings)

    assert quality.dem_elevation_m == pytest.approx(1241.0)
    assert quality.selected_ground_elevation_m == pytest.approx(1241.0)
    assert quality.elevation_source == "dem"
    assert quality.confidence == "high"
    assert quality.phone_altitude_m == pytest.approx(1248.0)


def test_build_location_quality_with_dem_unavailable() -> None:
    observer = ObserverInput(latitude=0.0, longitude=0.0, horizontal_accuracy_m=5.0)

    quality = build_location_quality(observer, dem_elevation_m=None, settings=_settings)

    assert quality.dem_elevation_m is None
    assert quality.selected_ground_elevation_m is None
    assert quality.elevation_source is None
    assert quality.confidence == "low"


def test_build_location_quality_manual_observer_no_accuracy() -> None:
    observer = ObserverInput(latitude=43.27, longitude=20.82)

    quality = build_location_quality(observer, dem_elevation_m=1241.0, settings=_settings)

    assert quality.horizontal_accuracy_m is None
    assert quality.confidence == "high"


# --- GET /api/v1/observer/elevation (endpoint-level) ----------------------


def test_observer_elevation_endpoint_returns_full_shape(monkeypatch) -> None:
    monkeypatch.setattr(observer_route._elevation_service, "get_elevation", lambda lat, lon: 1241.0)

    response = client.get(
        "/api/v1/observer/elevation",
        params={"lat": 43.27, "lon": 20.82, "horizontal_accuracy_m": 6.4},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["observer"]["dem_elevation_m"] == pytest.approx(1241.0)
    assert body["observer"]["observer_elevation_m"] == pytest.approx(1241.0 + _settings.observer_eye_height_m)
    assert body["location_quality"]["confidence"] == "high"
    assert body["location_quality"]["elevation_source"] == "dem"


def test_observer_elevation_endpoint_handles_missing_dem(monkeypatch) -> None:
    monkeypatch.setattr(observer_route._elevation_service, "get_elevation", lambda lat, lon: None)

    response = client.get("/api/v1/observer/elevation", params={"lat": 0.0, "lon": 0.0})

    assert response.status_code == 200
    body = response.json()
    assert body["observer"]["observer_elevation_m"] is None
    assert body["location_quality"]["confidence"] == "low"


def test_observer_elevation_endpoint_rejects_out_of_range_coordinates() -> None:
    response = client.get("/api/v1/observer/elevation", params={"lat": 95.0, "lon": 20.0})
    assert response.status_code == 422
