"""
Testovi za `app.services.osm_areas` -- Phase 9 (rijeke/vodene površine/
parkovi/nacionalni parkovi, sa PUNOM geometrijom).

Svi HTTP-nivoi testovi koriste mock-ovan httpx odgovor (monkeypatch), ne
pravu mrežu -- isti princip kao test_osm.py. Stvarna integracija (i,
posebno, PRETPOSTAVKA da Overpass `out geom;` ugrađuje member geometriju
direktno u relation odgovor -- vidi modul docstring u
app.services.osm_areas) se provjerava ručno preko GET /api/v1/osm/areas,
JER OVO NIJE MOGLO BITI EMPIRIJSKI PROVJERENO iz ovog razvojnog okruženja
(cloud sandbox i lokalna bridge VM obje blokiraju overpass-api.de)."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from shapely.geometry import LineString, MultiPolygon, Polygon

from app.core.config import get_settings
from app.services.osm_areas import (
    OverpassAreaError,
    OverpassAreaService,
    _build_area_query,
    _infer_category,
    _relation_to_polygon,
    _way_geometry_to_shape,
)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


def _fake_settings():
    return get_settings()


# --- _infer_category --------------------------------------------------


def test_infer_category_river() -> None:
    assert _infer_category({"waterway": "river"}) == "river"


def test_infer_category_water() -> None:
    assert _infer_category({"natural": "water"}) == "water"


def test_infer_category_park() -> None:
    assert _infer_category({"leisure": "park"}) == "park"


def test_infer_category_national_park() -> None:
    assert _infer_category({"boundary": "national_park"}) == "national_park"


def test_infer_category_national_park_takes_priority_over_park() -> None:
    # Rijedak, ali moguć slučaj -- relacija sa oba taga (vidi modul docstring
    # u osm_areas.py za obrazloženje prioriteta).
    assert _infer_category({"leisure": "park", "boundary": "national_park"}) == "national_park"


def test_infer_category_none_when_no_match() -> None:
    assert _infer_category({"highway": "primary"}) is None


# --- _way_geometry_to_shape ---------------------------------------------


def test_way_geometry_closed_ring_becomes_polygon() -> None:
    coords = [
        {"lat": 0.0, "lon": 0.0},
        {"lat": 0.0, "lon": 1.0},
        {"lat": 1.0, "lon": 1.0},
        {"lat": 1.0, "lon": 0.0},
        {"lat": 0.0, "lon": 0.0},
    ]
    shape = _way_geometry_to_shape(coords)
    assert isinstance(shape, Polygon)
    assert shape.area == pytest.approx(1.0)


def test_way_geometry_open_line_becomes_linestring() -> None:
    coords = [
        {"lat": 43.0, "lon": 20.0},
        {"lat": 43.1, "lon": 20.05},
        {"lat": 43.2, "lon": 20.1},
    ]
    shape = _way_geometry_to_shape(coords)
    assert isinstance(shape, LineString)


def test_way_geometry_too_short_returns_none() -> None:
    assert _way_geometry_to_shape([{"lat": 43.0, "lon": 20.0}]) is None


def test_way_geometry_uses_lon_lat_order() -> None:
    # Regresija protiv lat/lon zamjene -- vidi modul docstring, "čest izvor
    # bugova". Prva tačka geometrije ima lat=0, lon=5 -- Shapely koordinata
    # MORA biti (5, 0) = (x=lon, y=lat), ne (0, 5).
    coords = [{"lat": 0.0, "lon": 5.0}, {"lat": 1.0, "lon": 6.0}]
    shape = _way_geometry_to_shape(coords)
    assert shape.coords[0] == (5.0, 0.0)


# --- _relation_to_polygon -------------------------------------------------


def _square_outer_members() -> list[dict]:
    # Dvije way "polovine" kvadrata (0,0)-(1,1) u (lat,lon) obliku, sa
    # zajedničkim krajnjim tačkama -- polygonize() ih mora spojiti u jedan
    # zatvoren kvadrat.
    return [
        {
            "type": "way",
            "role": "outer",
            "geometry": [
                {"lat": 0.0, "lon": 0.0},
                {"lat": 1.0, "lon": 0.0},
                {"lat": 1.0, "lon": 1.0},
            ],
        },
        {
            "type": "way",
            "role": "outer",
            "geometry": [
                {"lat": 1.0, "lon": 1.0},
                {"lat": 0.0, "lon": 1.0},
                {"lat": 0.0, "lon": 0.0},
            ],
        },
    ]


def test_relation_to_polygon_assembles_disconnected_outer_ways() -> None:
    polygon = _relation_to_polygon(_square_outer_members())
    assert isinstance(polygon, (Polygon, MultiPolygon))
    assert polygon.area == pytest.approx(1.0, abs=1e-9)


def test_relation_to_polygon_ignores_inner_role_hole() -> None:
    # Dodajemo malu "rupu" (role=inner) unutar kvadrata -- namjerno
    # pojednostavljenje (dogovoreno sa korisnikom, vidi modul docstring):
    # rupe se IGNORIŠU, pa rezultujuća površina mora ostati puna (1.0), ne
    # umanjena za površinu rupe.
    members = _square_outer_members() + [
        {
            "type": "way",
            "role": "inner",
            "geometry": [
                {"lat": 0.4, "lon": 0.4},
                {"lat": 0.4, "lon": 0.6},
                {"lat": 0.6, "lon": 0.6},
                {"lat": 0.6, "lon": 0.4},
                {"lat": 0.4, "lon": 0.4},
            ],
        }
    ]
    polygon = _relation_to_polygon(members)
    assert polygon.area == pytest.approx(1.0, abs=1e-9)


def test_relation_to_polygon_returns_none_when_no_outer_members() -> None:
    members = [{"type": "way", "role": "inner", "geometry": [{"lat": 0.0, "lon": 0.0}, {"lat": 1.0, "lon": 1.0}]}]
    assert _relation_to_polygon(members) is None


def test_relation_to_polygon_returns_none_when_ways_dont_close() -> None:
    # Jedna otvorena linija koja se ne zatvara -- polygonize() ne može
    # napraviti nijedan prsten.
    members = [
        {
            "type": "way",
            "role": "outer",
            "geometry": [{"lat": 0.0, "lon": 0.0}, {"lat": 1.0, "lon": 1.0}, {"lat": 2.0, "lon": 0.0}],
        }
    ]
    assert _relation_to_polygon(members) is None


# --- _build_area_query ------------------------------------------------


def test_build_area_query_contains_all_category_filters() -> None:
    query = _build_area_query(43.28, 20.81, 15.0)
    assert 'way["waterway"="river"]' in query
    assert 'way["natural"="water"]' in query
    assert 'relation["natural"="water"]' in query
    assert 'way["leisure"="park"]' in query
    assert 'relation["leisure"="park"]' in query
    assert 'way["boundary"="national_park"]' in query
    assert 'relation["boundary"="national_park"]' in query
    assert "out geom;" in query
    assert "around:15000" in query


# --- OverpassAreaService.fetch_area_features_in_radius --------------------

_SAMPLE_AREA_RESPONSE = {
    "elements": [
        {
            "type": "way",
            "id": 1001,
            "tags": {"waterway": "river", "name": "Samokovska reka"},
            "geometry": [
                {"lat": 43.20, "lon": 20.80},
                {"lat": 43.21, "lon": 20.81},
                {"lat": 43.22, "lon": 20.82},
            ],
        },
        {
            "type": "relation",
            "id": 2002,
            "tags": {"boundary": "national_park", "name": "Nacionalni park Kopaonik"},
            "members": [
                {
                    "type": "way",
                    "role": "outer",
                    "geometry": [
                        {"lat": 43.0, "lon": 20.0},
                        {"lat": 43.5, "lon": 20.0},
                        {"lat": 43.5, "lon": 21.0},
                    ],
                },
                {
                    "type": "way",
                    "role": "outer",
                    "geometry": [
                        {"lat": 43.5, "lon": 21.0},
                        {"lat": 43.0, "lon": 21.0},
                        {"lat": 43.0, "lon": 20.0},
                    ],
                },
            ],
        },
        {
            # Nepoznat tag -- mora biti odbačen (_infer_category vraća None).
            "type": "way",
            "id": 3003,
            "tags": {"highway": "primary"},
            "geometry": [{"lat": 43.0, "lon": 20.0}, {"lat": 43.1, "lon": 20.1}],
        },
    ]
}


def test_fetch_area_features_parses_way_and_relation(monkeypatch) -> None:
    async def fake_post(self, url, data=None, **kwargs):
        return _FakeResponse(200, _SAMPLE_AREA_RESPONSE)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    service = OverpassAreaService(_fake_settings())
    features = asyncio.run(service.fetch_area_features_in_radius(43.28, 20.81, 20.0))

    assert len(features) == 2  # way highway=primary odbačen

    river = next(f for f in features if f.osm_id == 1001)
    assert river.osm_type == "way"
    assert river.category == "river"
    assert isinstance(river.geometry, LineString)

    park = next(f for f in features if f.osm_id == 2002)
    assert park.osm_type == "relation"
    assert park.category == "national_park"
    assert isinstance(park.geometry, (Polygon, MultiPolygon))


def test_fetch_area_features_uses_cache(monkeypatch) -> None:
    call_count = 0

    async def fake_post(self, url, data=None, **kwargs):
        nonlocal call_count
        call_count += 1
        return _FakeResponse(200, _SAMPLE_AREA_RESPONSE)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    service = OverpassAreaService(_fake_settings())

    async def _run_twice():
        await service.fetch_area_features_in_radius(43.28, 20.81, 20.0)
        await service.fetch_area_features_in_radius(43.28, 20.81, 20.0)

    asyncio.run(_run_twice())
    assert call_count == 1


def test_fetch_area_features_retries_transient_error_then_succeeds(monkeypatch) -> None:
    call_count = 0

    async def flaky_then_ok_post(self, url, data=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return _FakeResponse(503, text="Service Unavailable")
        return _FakeResponse(200, _SAMPLE_AREA_RESPONSE)

    async def instant_sleep(seconds):
        return None

    monkeypatch.setattr(httpx.AsyncClient, "post", flaky_then_ok_post)
    monkeypatch.setattr(asyncio, "sleep", instant_sleep)

    service = OverpassAreaService(_fake_settings())
    features = asyncio.run(service.fetch_area_features_in_radius(43.28, 20.81, 20.0))

    assert call_count == 2
    assert len(features) == 2


def test_fetch_area_features_does_not_retry_permanent_error(monkeypatch) -> None:
    call_count = 0

    async def fake_post(self, url, data=None, **kwargs):
        nonlocal call_count
        call_count += 1
        return _FakeResponse(400, text="Bad Request")

    async def sleep_that_must_not_be_called(seconds):
        raise AssertionError("asyncio.sleep ne smije biti pozvan za trajnu grešku")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(asyncio, "sleep", sleep_that_must_not_be_called)

    service = OverpassAreaService(_fake_settings())
    with pytest.raises(OverpassAreaError):
        asyncio.run(service.fetch_area_features_in_radius(43.28, 20.81, 20.0))

    assert call_count == 1


# --- GET /api/v1/osm/areas (endpoint-level) -------------------------------


def test_osm_areas_endpoint_returns_geojson_like_geometry(monkeypatch) -> None:
    from app.services.osm_areas import OSMAreaFeature
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    async def fake_fetch(self, latitude, longitude, radius_km):
        return [
            OSMAreaFeature(
                osm_id=1001,
                osm_type="way",
                name="Samokovska reka",
                category="river",
                geometry=LineString([(20.80, 43.20), (20.82, 43.22)]),
            )
        ]

    monkeypatch.setattr(OverpassAreaService, "fetch_area_features_in_radius", fake_fetch)

    response = client.get("/api/v1/osm/areas", params={"lat": 43.28, "lon": 20.81, "radius_km": 20.0})

    assert response.status_code == 200
    body = response.json()
    assert len(body["features"]) == 1
    assert body["features"][0]["category"] == "river"
    assert body["features"][0]["geometry"]["type"] == "LineString"


def test_osm_areas_endpoint_returns_503_on_overpass_error(monkeypatch) -> None:
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    async def fake_fetch(self, latitude, longitude, radius_km):
        raise OverpassAreaError("Overpass API nedostupan: simulacija za test")

    monkeypatch.setattr(OverpassAreaService, "fetch_area_features_in_radius", fake_fetch)

    response = client.get("/api/v1/osm/areas", params={"lat": 43.28, "lon": 20.81, "radius_km": 20.0})
    assert response.status_code == 503
