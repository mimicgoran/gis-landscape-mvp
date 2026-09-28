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
    OSMAreaFeature,
    OverpassAreaError,
    OverpassAreaService,
    _build_area_query,
    _infer_category,
    _relation_to_polygon,
    _way_geometry_to_shape,
    merge_overlapping_river_water_features,
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

# --- merge_overlapping_river_water_features (dodano nakon terenskog testa,
# Sava kod Orasca -- vidi docs/architecture-feasibility-review.md, sekcija
# 29/30: OSM rijeku mapira i kao imenovanu `river` liniju i kao bezimen
# `water` poligon, za isti fizicki objekat) --------------------------------


def test_merge_leaves_non_overlapping_features_untouched() -> None:
    river = OSMAreaFeature(
        osm_id=1, osm_type="way", name="Sava", category="river", geometry=LineString([(0.0, 0.0), (0.0, 1.0)])
    )
    water = OSMAreaFeature(
        osm_id=2,
        osm_type="way",
        name=None,
        category="water",
        # Poligon daleko od rijeke -- ne preklapaju se, treba ostati odvojen.
        geometry=Polygon([(5.0, 5.0), (5.1, 5.0), (5.1, 5.1), (5.0, 5.1), (5.0, 5.0)]),
    )

    result = merge_overlapping_river_water_features([river, water])

    assert len(result) == 2
    ids = {f.osm_id for f in result}
    assert ids == {1, 2}


def test_merge_combines_overlapping_river_and_water_into_one_feature() -> None:
    river = OSMAreaFeature(
        osm_id=1, osm_type="way", name="Sava", category="river", geometry=LineString([(0.0, -0.5), (0.0, 0.5)])
    )
    water = OSMAreaFeature(
        osm_id=2,
        osm_type="way",
        name=None,
        category="water",
        # Poligon koji sadrzi dio linije -- realan slucaj (natural=water
        # pokriva vodenu povrsinu koju waterway=river linija prolazi kroz).
        geometry=Polygon([(-0.1, -0.2), (0.1, -0.2), (0.1, 0.2), (-0.1, 0.2), (-0.1, -0.2)]),
    )

    result = merge_overlapping_river_water_features([river, water])

    assert len(result) == 1
    merged = result[0]
    # Zadrzano ime i osm_id/tip RIJEKE (informativnije od bezimenog poligona).
    assert merged.osm_id == 1
    assert merged.name == "Sava"
    assert merged.category == "river"
    assert merged.geometry.geom_type == "GeometryCollection"
    assert len(list(merged.geometry.geoms)) == 2


def test_merge_river_absorbs_multiple_overlapping_water_features() -> None:
    river = OSMAreaFeature(
        osm_id=1, osm_type="way", name="Sava", category="river", geometry=LineString([(0.0, -1.0), (0.0, 1.0)])
    )
    water_a = OSMAreaFeature(
        osm_id=2, osm_type="way", name=None, category="water",
        geometry=Polygon([(-0.1, -0.9), (0.1, -0.9), (0.1, -0.5), (-0.1, -0.5), (-0.1, -0.9)]),
    )
    water_b = OSMAreaFeature(
        osm_id=3, osm_type="way", name=None, category="water",
        geometry=Polygon([(-0.1, 0.5), (0.1, 0.5), (0.1, 0.9), (-0.1, 0.9), (-0.1, 0.5)]),
    )

    result = merge_overlapping_river_water_features([river, water_a, water_b])

    assert len(result) == 1
    assert result[0].osm_id == 1
    assert len(list(result[0].geometry.geoms)) == 3  # river + water_a + water_b


def test_merge_keeps_unmatched_water_features_separate() -> None:
    river = OSMAreaFeature(
        osm_id=1, osm_type="way", name="Sava", category="river", geometry=LineString([(0.0, -0.5), (0.0, 0.5)])
    )
    overlapping_water = OSMAreaFeature(
        osm_id=2, osm_type="way", name=None, category="water",
        geometry=Polygon([(-0.1, -0.2), (0.1, -0.2), (0.1, 0.2), (-0.1, 0.2), (-0.1, -0.2)]),
    )
    unrelated_lake = OSMAreaFeature(
        osm_id=3, osm_type="way", name="Neko jezero", category="water",
        geometry=Polygon([(9.0, 9.0), (9.1, 9.0), (9.1, 9.1), (9.0, 9.1), (9.0, 9.0)]),
    )

    result = merge_overlapping_river_water_features([river, overlapping_water, unrelated_lake])

    assert len(result) == 2
    names = {f.name for f in result}
    assert "Sava" in names
    assert "Neko jezero" in names
    # Nepovezano jezero mora ostati NEDIRNUTO (obican Polygon, ne GeometryCollection).
    lake_result = next(f for f in result if f.osm_id == 3)
    assert lake_result.geometry.geom_type == "Polygon"


def test_merge_does_not_touch_park_or_national_park_features() -> None:
    river = OSMAreaFeature(
        osm_id=1, osm_type="way", name="Sava", category="river", geometry=LineString([(0.0, -0.5), (0.0, 0.5)])
    )
    park = OSMAreaFeature(
        osm_id=2, osm_type="way", name="Gradski park", category="park",
        geometry=Polygon([(0.0, 0.0), (0.05, 0.0), (0.05, 0.05), (0.0, 0.05), (0.0, 0.0)]),
    )

    result = merge_overlapping_river_water_features([river, park])

    # Park preklapa liniju rijeke geometrijski, ali merge namjerno gleda SAMO
    # (river, water) parove -- park mora ostati nedirnut i odvojen.
    assert len(result) == 2
    park_result = next(f for f in result if f.osm_id == 2)
    assert park_result.geometry.geom_type == "Polygon"


def test_merge_returns_empty_list_for_empty_input() -> None:
    assert merge_overlapping_river_water_features([]) == []

