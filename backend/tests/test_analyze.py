"""
Testovi za `/api/v1/analyze/preview` -- Phase 8 dev endpoint, prošireno
Phase 9 (area feature-i).

Cilj ovih testova NIJE da ponovo provjere GIS matematiku (to rade
test_geometry.py, test_elevation.py, test_visibility.py, test_area_visibility.py)
-- provjeravaju SAMO orkestraciju: da li se rezultati ispravno razdvajaju u
visible/blocked (tačkasti feature-i) i area_features (Phase 9), da li debug
brojevi odgovaraju, i da li se error slučajevi (DEM nedostupan za observera,
Overpass down -- i za tačke i za area feature-e) korektno propagiraju. Zbog
toga se `resolve_target_elevation`/`check_visibility`/
`evaluate_area_feature_visibility` monkeypatch-uju na kanonske, unaprijed
poznate rezultate.
"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.routes import analyze as analyze_route
from app.main import app
from app.models.feature import OSMPointFeature
from app.services.area_visibility import AreaVisibilityResult
from app.services.arcgis_places import ArcGISPlacesError
from app.services.osm_areas import OverpassAreaError
from app.services.visibility import VisibilityResult

client = TestClient(app)

_PEAKS = [
    OSMPointFeature(osm_id=1, name="Visible Peak", latitude=43.28, longitude=20.81, ele_m=1832.0, category="peak"),
    OSMPointFeature(osm_id=2, name="Blocked Peak", latitude=43.30, longitude=20.83, ele_m=2050.0, category="peak"),
]

_AREA_FEATURES = [
    SimpleNamespace(osm_id=10, osm_type="way", name="Samokovska reka", category="river"),
    SimpleNamespace(osm_id=20, osm_type="relation", name="Nacionalni park Kopaonik", category="national_park"),
]


def _patch_full_pipeline(monkeypatch, observer_dem_elevation=1241.0, area_features=None):
    async def fake_fetch(latitude, longitude, radius_km):
        return _PEAKS

    async def fake_fetch_areas(latitude, longitude, radius_km):
        return area_features if area_features is not None else []

    monkeypatch.setattr(analyze_route._point_features_service, "fetch_point_features_in_radius", fake_fetch)
    monkeypatch.setattr(analyze_route._overpass_area_service, "fetch_area_features_in_radius", fake_fetch_areas)
    monkeypatch.setattr(analyze_route._elevation_service, "get_elevation", lambda lat, lon: observer_dem_elevation)

    def fake_resolve(candidate_ele_m, lat, lon, elevation_service, settings):
        return candidate_ele_m, "osm", None

    monkeypatch.setattr(analyze_route, "resolve_target_elevation", fake_resolve)

    # `rank_area_candidates_by_distance()` (Phase 9 performance optimizacija,
    # sekcija 37 u arhitekturnom dokumentu) radi PRAVU geometriju
    # (`intersect_with_sector` + `nearest_points` nad `feature.geometry`) da
    # bi jeftino sortirala/ograničila kandidate PRIJE skupog
    # `evaluate_area_feature_visibility()` poziva. Test fixture-i ovog fajla
    # namjerno koriste `SimpleNamespace` bez `.geometry` -- oni testiraju
    # SAMO orkestraciju endpointa (vidi docstring na vrhu fajla), ne pravu
    # geometriju (to pokriva test_area_visibility.py). Zato ovdje mockujemo
    # `rank_area_candidates_by_distance` kao passthrough koji vraća listu
    # nepromijenjenu -- isti princip kao mock za `evaluate_area_feature_visibility`
    # ispod, samo jedan korak ranije u pipeline-u.
    def fake_rank(features, sector_polygon, observer_latitude, observer_longitude):
        return list(features)

    monkeypatch.setattr(analyze_route, "rank_area_candidates_by_distance", fake_rank)

    def fake_check_visibility(**kwargs):
        target_lat = kwargs["target_latitude"]
        visible = target_lat == 43.28  # "Visible Peak" vidljiv, "Blocked Peak" blokiran
        return VisibilityResult(
            visible=visible, target_angle_deg=1.0, max_terrain_angle_deg=0.5, profile=[], dem_gap=False
        )

    monkeypatch.setattr(analyze_route, "check_visibility", fake_check_visibility)


def test_analyze_preview_splits_visible_and_blocked(monkeypatch):
    _patch_full_pipeline(monkeypatch)

    response = client.get(
        "/api/v1/analyze/preview",
        params={"lat": 43.27, "lon": 20.80, "heading_deg": 45.0, "fov_deg": 90.0, "radius_km": 20.0},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["visible_features"]) == 1
    assert body["visible_features"][0]["name"] == "Visible Peak"
    assert body["visible_features"][0]["category"] == "peak"
    assert len(body["blocked_features"]) == 1
    assert body["blocked_features"][0]["name"] == "Blocked Peak"
    assert body["debug"]["visible_count"] == 1
    assert body["debug"]["blocked_count"] == 1
    assert body["location_quality"]["elevation_source"] == "dem"
    # profile izostavljen po defaultu
    assert body["visible_features"][0]["profile"] is None
    # area_features prazno -- nijedan area feature nije zadat u ovom testu
    assert body["area_features"] == []


def test_analyze_preview_includes_profile_when_requested(monkeypatch):
    _patch_full_pipeline(monkeypatch)

    response = client.get(
        "/api/v1/analyze/preview",
        params={
            "lat": 43.27,
            "lon": 20.80,
            "heading_deg": 45.0,
            "fov_deg": 90.0,
            "radius_km": 20.0,
            "include_profile": True,
        },
    )

    body = response.json()
    # profile je [] u fake_check_visibility -- provjeravamo da POLJE postoji (nije None), ne da je popunjeno.
    assert body["visible_features"][0]["profile"] == []


def test_analyze_preview_handles_missing_observer_dem(monkeypatch):
    _patch_full_pipeline(monkeypatch, observer_dem_elevation=None)

    response = client.get(
        "/api/v1/analyze/preview",
        params={"lat": 0.0, "lon": 0.0, "heading_deg": 0.0, "fov_deg": 45.0, "radius_km": 20.0},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["visible_features"] == []
    assert body["blocked_features"] == []
    assert body["area_features"] == []
    assert "error" in body["debug"]


def test_analyze_preview_propagates_arcgis_places_error_as_503(monkeypatch):
    """Od Phase 15 tačkasti feature-i dolaze sa ArcGISPlacesService (vidi
    app.services.arcgis_places), NE više sa OverpassService -- area
    feature-i (Phase 9) ostaju na Overpass-u preko OverpassAreaService,
    nepromijenjeno."""

    async def fake_fetch_error(latitude, longitude, radius_km):
        raise ArcGISPlacesError("ArcGIS geocoding nedostupan: simulacija za test")

    monkeypatch.setattr(analyze_route._point_features_service, "fetch_point_features_in_radius", fake_fetch_error)
    monkeypatch.setattr(analyze_route._elevation_service, "get_elevation", lambda lat, lon: 1241.0)

    response = client.get(
        "/api/v1/analyze/preview",
        params={"lat": 43.27, "lon": 20.80, "heading_deg": 45.0, "fov_deg": 90.0, "radius_km": 20.0},
    )

    assert response.status_code == 503


# --- Phase 9: area feature wiring -----------------------------------------


def test_analyze_preview_includes_area_features(monkeypatch):
    _patch_full_pipeline(monkeypatch, area_features=_AREA_FEATURES)

    def fake_evaluate(feature, **kwargs):
        if feature.osm_id == 10:
            return AreaVisibilityResult(
                closest_distance_km=3.2, bearing_deg=250.0, sample_count=5, visible_sample_count=5, dem_gap_sample_count=0
            )
        return AreaVisibilityResult(
            closest_distance_km=8.7, bearing_deg=260.0, sample_count=6, visible_sample_count=2, dem_gap_sample_count=1
        )

    monkeypatch.setattr(analyze_route, "evaluate_area_feature_visibility", fake_evaluate)

    response = client.get(
        "/api/v1/analyze/preview",
        params={"lat": 43.27, "lon": 20.80, "heading_deg": 250.0, "fov_deg": 60.0, "radius_km": 20.0},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["area_features"]) == 2

    river = next(f for f in body["area_features"] if f["osm_id"] == 10)
    assert river["category"] == "river"
    assert river["visibility"] == "visible"
    assert river["visible_fraction"] == 1.0

    park = next(f for f in body["area_features"] if f["osm_id"] == 20)
    assert park["osm_type"] == "relation"
    assert park["category"] == "national_park"
    assert park["visibility"] == "partially_visible"
    assert park["dem_gap_sample_count"] == 1

    # Sortirano po closest_distance_km rastuće (rijeka bliža -> prva).
    assert body["area_features"][0]["osm_id"] == 10
    assert body["debug"]["area_features_total"] == 2
    assert body["debug"]["area_features_in_sector"] == 2


def test_analyze_preview_excludes_area_features_outside_sector(monkeypatch):
    _patch_full_pipeline(monkeypatch, area_features=_AREA_FEATURES)

    def fake_evaluate(feature, **kwargs):
        # Simulira da nijedan area feature ne upada u sektor (intersect prazan).
        return None

    monkeypatch.setattr(analyze_route, "evaluate_area_feature_visibility", fake_evaluate)

    response = client.get(
        "/api/v1/analyze/preview",
        params={"lat": 43.27, "lon": 20.80, "heading_deg": 45.0, "fov_deg": 30.0, "radius_km": 20.0},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["area_features"] == []
    assert body["debug"]["area_features_in_sector"] == 0
    assert body["debug"]["area_features_skipped_or_no_elevation"] == 2


def test_analyze_preview_propagates_overpass_area_error_as_503(monkeypatch):
    _patch_full_pipeline(monkeypatch)

    async def fake_fetch_areas_error(latitude, longitude, radius_km):
        raise OverpassAreaError("Overpass API vratio 504")

    monkeypatch.setattr(analyze_route._overpass_area_service, "fetch_area_features_in_radius", fake_fetch_areas_error)

    response = client.get(
        "/api/v1/analyze/preview",
        params={"lat": 43.27, "lon": 20.80, "heading_deg": 45.0, "fov_deg": 90.0, "radius_km": 20.0},
    )

    assert response.status_code == 503
