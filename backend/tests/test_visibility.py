"""
Testovi za line-of-sight (visibility) servis -- Phase 8.

`geodesic_intermediate_points` se monkeypatch-uje na fiksnu listu tačaka za
sve `check_visibility` testove ovdje -- prava geodetska matematika je već
testirana u tests/test_geometry.py; ovi testovi provjeravaju SAMO odluku
visible/blocked/dem_gap za dati (kontrolisan) teren profil, nezavisno od
stvarne geometrije ili DEM pristupa.
"""

from __future__ import annotations

import math

import pytest

from app.core.config import get_settings
from app.services import visibility as visibility_module
from app.services.visibility import check_visibility, resolve_target_elevation

_settings = get_settings()


class _FakeElevationService:
    """Minimalna zamjena za ElevationService -- vraća unaprijed zadate
    elevacije, bez ikakvog stvarnog DEM/mrežnog pristupa."""

    def __init__(self, profile_elevations=None, point_elevation=None):
        self._profile_elevations = profile_elevations
        self._point_elevation = point_elevation
        self.profile_calls = 0

    def get_elevation_profile(self, points):
        self.profile_calls += 1
        return list(self._profile_elevations)

    def get_elevation(self, latitude, longitude):
        return self._point_elevation


def _patch_intermediate_points(monkeypatch, points):
    """`points` je lista `(lat, lon, distance_m)`."""
    monkeypatch.setattr(visibility_module, "geodesic_intermediate_points", lambda *a, **kw: points)


# --- check_visibility --------------------------------------------------


def test_check_visibility_flat_terrain_is_visible(monkeypatch):
    _patch_intermediate_points(monkeypatch, [(43.0, 20.0, 2000.0), (43.0, 20.01, 4000.0)])
    fake_service = _FakeElevationService(profile_elevations=[900.0, 900.0])

    result = check_visibility(
        observer_latitude=43.0,
        observer_longitude=20.0,
        observer_elevation_m=1000.0,
        target_latitude=43.0,
        target_longitude=20.02,
        target_elevation_m=1200.0,
        target_distance_m=6000.0,
        elevation_service=fake_service,
        settings=_settings,
    )

    assert result.visible is True
    assert result.dem_gap is False
    assert len(result.profile) == 4  # observer + 2 unutrašnje + target


def test_check_visibility_blocked_by_higher_terrain(monkeypatch):
    _patch_intermediate_points(monkeypatch, [(43.0, 20.005, 1000.0)])
    # Teren na 1000 m sa elevacijom 1500 -- ugao iz (1000, 1500-1000=500) je
    # veći od target ugla iz (6000, 1200-1000=200).
    fake_service = _FakeElevationService(profile_elevations=[1500.0])

    result = check_visibility(
        observer_latitude=43.0,
        observer_longitude=20.0,
        observer_elevation_m=1000.0,
        target_latitude=43.0,
        target_longitude=20.02,
        target_elevation_m=1200.0,
        target_distance_m=6000.0,
        elevation_service=fake_service,
        settings=_settings,
    )

    assert result.visible is False
    assert result.max_terrain_angle_deg > result.target_angle_deg


def test_check_visibility_equal_angle_is_not_blocked(monkeypatch):
    """Granični slučaj (dogovoren prije implementacije): jednak ugao je
    VISIBLE, ne BLOCKED -- vidi app.services.visibility.check_visibility
    docstring."""
    observer_elevation_m = 1000.0
    target_distance_m = 6000.0
    target_delta = 600.0
    target_angle = math.atan2(target_delta, target_distance_m)

    terrain_distance_m = 3000.0
    terrain_delta = math.tan(target_angle) * terrain_distance_m  # isti ugao kao target
    terrain_elevation_m = observer_elevation_m + terrain_delta

    _patch_intermediate_points(monkeypatch, [(43.0, 20.01, terrain_distance_m)])
    fake_service = _FakeElevationService(profile_elevations=[terrain_elevation_m])

    result = check_visibility(
        observer_latitude=43.0,
        observer_longitude=20.0,
        observer_elevation_m=observer_elevation_m,
        target_latitude=43.0,
        target_longitude=20.02,
        target_elevation_m=observer_elevation_m + target_delta,
        target_distance_m=target_distance_m,
        elevation_service=fake_service,
        settings=_settings,
    )

    assert result.visible is True


def test_check_visibility_dem_gap_does_not_block(monkeypatch):
    _patch_intermediate_points(monkeypatch, [(43.0, 20.005, 1000.0), (43.0, 20.01, 3000.0)])
    fake_service = _FakeElevationService(profile_elevations=[None, 900.0])

    result = check_visibility(
        observer_latitude=43.0,
        observer_longitude=20.0,
        observer_elevation_m=1000.0,
        target_latitude=43.0,
        target_longitude=20.02,
        target_elevation_m=1200.0,
        target_distance_m=6000.0,
        elevation_service=fake_service,
        settings=_settings,
    )

    assert result.visible is True
    assert result.dem_gap is True


def test_check_visibility_short_distance_skips_dem_sampling(monkeypatch):
    monkeypatch.setattr(visibility_module, "geodesic_intermediate_points", lambda *a, **kw: [])
    fake_service = _FakeElevationService(profile_elevations=[])

    result = check_visibility(
        observer_latitude=43.0,
        observer_longitude=20.0,
        observer_elevation_m=1000.0,
        target_latitude=43.0,
        target_longitude=20.0001,
        target_elevation_m=1010.0,
        target_distance_m=10.0,
        elevation_service=fake_service,
        settings=_settings,
    )

    assert result.visible is True
    assert fake_service.profile_calls == 0  # nema poziva ako nema tačaka
    assert len(result.profile) == 2  # samo observer + target


# --- resolve_target_elevation --------------------------------------------


def test_resolve_target_elevation_prefers_osm_when_no_discrepancy():
    fake_service = _FakeElevationService(point_elevation=1830.0)
    elevation_m, source, discrepancy_m = resolve_target_elevation(1832.0, 43.0, 20.0, fake_service, _settings)
    assert elevation_m == pytest.approx(1832.0)
    assert source == "osm"
    assert discrepancy_m is None


def test_resolve_target_elevation_flags_large_discrepancy_but_keeps_osm():
    fake_service = _FakeElevationService(point_elevation=1700.0)  # 132 m ispod OSM ele
    elevation_m, source, discrepancy_m = resolve_target_elevation(1832.0, 43.0, 20.0, fake_service, _settings)
    assert elevation_m == pytest.approx(1832.0)
    assert source == "osm"
    assert discrepancy_m == pytest.approx(132.0)


def test_resolve_target_elevation_falls_back_to_dem_when_no_osm_ele():
    fake_service = _FakeElevationService(point_elevation=1241.0)
    elevation_m, source, discrepancy_m = resolve_target_elevation(None, 43.0, 20.0, fake_service, _settings)
    assert elevation_m == pytest.approx(1241.0)
    assert source == "dem"
    assert discrepancy_m is None


def test_resolve_target_elevation_none_when_neither_available():
    fake_service = _FakeElevationService(point_elevation=None)
    elevation_m, source, discrepancy_m = resolve_target_elevation(None, 43.0, 20.0, fake_service, _settings)
    assert elevation_m is None
    assert source is None
    assert discrepancy_m is None
