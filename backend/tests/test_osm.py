"""
Testovi za Overpass servis (tačkasti feature-i) -- Phase 4, prošireno Phase 9.

Svi testovi koriste mock-ovan httpx odgovor (monkeypatch), ne pravu mrežu --
CI runner ne smije zavisiti od dostupnosti javnog Overpass servisa da bi
build ostao zelen (vidi docs/architecture-feasibility-review.md, sekcija 14
-- "Overpass reliability" je eksplicitno naveden rizik). Stvarna integracija
protiv prave Overpass instance se provjerava ručno preko
GET /api/v1/osm/points (Swagger UI ili curl) za odabranu test lokaciju.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.routes import osm as osm_route
from app.main import app
from app.services.osm import OverpassError, OverpassService, _build_overpass_query, _cache_key, _parse_ele_tag

client = TestClient(app)


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


# Phase 9: namjerno miješa sve tri tačkaste kategorije (peak/settlement/
# viewpoint) u jednom odgovoru -- provjerava da widened union upit i
# _infer_category ispravno razlikuju kategorije IZ TAGOVA (Overpass ne
# prijavljuje koja OR grana je pogodila element).
_OVERPASS_SAMPLE_RESPONSE = {
    "elements": [
        {
            "type": "node",
            "id": 111,
            "lat": 43.2833,
            "lon": 20.8167,
            "tags": {"natural": "peak", "name": "Pančićev vrh", "ele": "2017"},
        },
        {
            "type": "node",
            "id": 222,
            "lat": 43.30,
            "lon": 20.83,
            # Nema 'name' tag -- mora ostati validan sa name=None.
            "tags": {"natural": "peak", "ele": "1950.5"},
        },
        {
            "type": "node",
            "id": 333,
            "lat": 43.31,
            "lon": 20.84,
            # 'ele' je besmislen (negativan) -- mora se odbaciti u None.
            "tags": {"natural": "peak", "name": "Loš unos", "ele": "-5"},
        },
        {
            "type": "node",
            "id": 444,
            "lat": 43.32,
            "lon": 20.85,
            # Nema 'ele' tag uopšte.
            "tags": {"natural": "peak", "name": "Bez elevacije"},
        },
        {
            "type": "node",
            "id": 555,
            "lat": 43.25,
            "lon": 20.80,
            "tags": {"place": "town", "name": "Brzeće"},
        },
        {
            "type": "node",
            "id": 666,
            "lat": 43.26,
            "lon": 20.79,
            "tags": {"tourism": "viewpoint", "name": "Vidikovac Suvo Rudište"},
        },
    ]
}


# --- _parse_ele_tag ---------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2017", 2017.0),
        ("2017.5", 2017.5),
        (None, None),
        ("", None),
        ("nepoznato", None),
        ("-5", None),
        ("0", None),
    ],
)
def test_parse_ele_tag(raw, expected) -> None:
    assert _parse_ele_tag(raw) == expected


# --- _infer_category (Phase 9) --------------------------------------------


def test_infer_category_peak() -> None:
    from app.services.osm import _infer_category

    assert _infer_category({"natural": "peak"}) == "peak"


@pytest.mark.parametrize("place_value", ["city", "town", "village"])
def test_infer_category_settlement(place_value) -> None:
    from app.services.osm import _infer_category

    assert _infer_category({"place": place_value}) == "settlement"


def test_infer_category_settlement_ignores_other_place_values() -> None:
    # place=hamlet/suburb/... namjerno NIJE u scope-u (Phase 9 dogovor:
    # city/town/village) -- mora vratiti None, ne pogrešnu kategoriju.
    from app.services.osm import _infer_category

    assert _infer_category({"place": "hamlet"}) is None


def test_infer_category_viewpoint() -> None:
    from app.services.osm import _infer_category

    assert _infer_category({"tourism": "viewpoint"}) == "viewpoint"


def test_infer_category_none_when_no_match() -> None:
    from app.services.osm import _infer_category

    assert _infer_category({"amenity": "shelter"}) is None


# --- _cache_key ---------------------------------------------------------


def test_cache_key_rounds_coordinates() -> None:
    key_a = _cache_key(43.28331234, 20.81669876, 20.0)
    key_b = _cache_key(43.2833, 20.8167, 20.0)
    assert key_a == key_b


def test_cache_key_differs_for_different_locations() -> None:
    assert _cache_key(43.0, 20.0, 20.0) != _cache_key(44.0, 20.0, 20.0)


# --- _build_overpass_query (Phase 9: widened union upit) ------------------


def test_build_overpass_query_contains_all_three_point_filters() -> None:
    query = _build_overpass_query(43.28, 20.81, 20.0)
    assert 'node["natural"="peak"]' in query
    assert 'node["place"~"^(city|town|village)$"]' in query
    assert 'node["tourism"="viewpoint"]' in query
    assert "around:20000" in query  # 20 km -> 20000 m


# --- OverpassService.fetch_point_features_in_radius -----------------------


def test_fetch_point_features_in_radius_parses_response(monkeypatch) -> None:
    async def fake_post(self, url, data=None, **kwargs):
        return _FakeResponse(200, _OVERPASS_SAMPLE_RESPONSE)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    service = OverpassService(_fake_settings())
    features = asyncio.run(service.fetch_point_features_in_radius(43.28, 20.81, 20.0))

    assert len(features) == 6
    assert features[0].osm_id == 111
    assert features[0].name == "Pančićev vrh"
    assert features[0].ele_m == 2017.0
    assert features[0].category == "peak"
    assert features[1].name is None
    assert features[2].ele_m is None  # negativan ele odbačen
    assert features[3].ele_m is None  # nema ele tag

    settlement = next(f for f in features if f.osm_id == 555)
    assert settlement.category == "settlement"
    assert settlement.name == "Brzeće"

    viewpoint = next(f for f in features if f.osm_id == 666)
    assert viewpoint.category == "viewpoint"


def test_fetch_point_features_in_radius_uses_cache(monkeypatch) -> None:
    call_count = 0

    async def fake_post(self, url, data=None, **kwargs):
        nonlocal call_count
        call_count += 1
        return _FakeResponse(200, _OVERPASS_SAMPLE_RESPONSE)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    service = OverpassService(_fake_settings())

    async def _run_twice():
        await service.fetch_point_features_in_radius(43.28, 20.81, 20.0)
        await service.fetch_point_features_in_radius(43.28, 20.81, 20.0)

    asyncio.run(_run_twice())

    assert call_count == 1  # drugi poziv mora pogoditi keš, ne mrežu


def test_fetch_point_features_in_radius_sends_identifying_user_agent(monkeypatch) -> None:
    """Overpass API vraća 406 bez identifikacionog User-Agent header-a
    (potvrđeno protiv zvaničnog Overpass-API GitHub issue-a i OSM community
    foruma, 2026) -- ovaj test brani protiv regresije te ispravke."""
    captured_headers: dict = {}

    async def fake_post(self, url, data=None, headers=None, **kwargs):
        captured_headers.update(headers or {})
        return _FakeResponse(200, _OVERPASS_SAMPLE_RESPONSE)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    service = OverpassService(_fake_settings())
    asyncio.run(service.fetch_point_features_in_radius(43.28, 20.81, 20.0))

    assert "User-Agent" in captured_headers
    assert "gis-landscape-mvp" in captured_headers["User-Agent"].lower()


def test_fetch_point_features_in_radius_raises_overpass_error_on_bad_status(monkeypatch) -> None:
    async def fake_post(self, url, data=None, **kwargs):
        return _FakeResponse(504, text="Gateway Timeout")

    async def instant_sleep(seconds):
        return None

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(asyncio, "sleep", instant_sleep)

    service = OverpassService(_fake_settings())
    with pytest.raises(OverpassError):
        asyncio.run(service.fetch_point_features_in_radius(43.28, 20.81, 20.0))


def test_fetch_point_features_in_radius_falls_back_to_next_mirror_on_transient_error(monkeypatch) -> None:
    """504 je tranzitoran (vidi app.services.overpass_http) -- servis mora
    preci na SLJEDECI mirror umjesto da odmah odustane. Od Phase 15 (Render
    "502 Bad Gateway" nalaz) je `overpass_max_retries` default 0 -- dakle
    NEMA retry-ja na istom mirror-u, prelazak na drugi mirror je jedini
    oporavak, i to nakon TACNO jednog neuspjelog poziva."""
    call_count = 0

    async def flaky_then_ok_post(self, url, data=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return _FakeResponse(504, text="Gateway Timeout")
        return _FakeResponse(200, _OVERPASS_SAMPLE_RESPONSE)

    async def instant_sleep(seconds):
        return None

    monkeypatch.setattr(httpx.AsyncClient, "post", flaky_then_ok_post)
    monkeypatch.setattr(asyncio, "sleep", instant_sleep)

    service = OverpassService(_fake_settings())
    features = asyncio.run(service.fetch_point_features_in_radius(43.28, 20.81, 20.0))

    assert call_count == 2  # prvi mirror otkazao (504), drugi mirror uspio
    assert len(features) == 6


def test_fetch_point_features_in_radius_does_not_retry_permanent_error(monkeypatch) -> None:
    """400 nije u _TRANSIENT_STATUS_CODES -- retry ne bi pomogao, pa se
    odmah odustaje bez čekanja/ponovnih pokušaja."""
    call_count = 0

    async def fake_post(self, url, data=None, **kwargs):
        nonlocal call_count
        call_count += 1
        return _FakeResponse(400, text="Bad Request")

    async def sleep_that_must_not_be_called(seconds):
        raise AssertionError("asyncio.sleep ne smije biti pozvan za trajnu grešku")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(asyncio, "sleep", sleep_that_must_not_be_called)

    service = OverpassService(_fake_settings())
    with pytest.raises(OverpassError):
        asyncio.run(service.fetch_point_features_in_radius(43.28, 20.81, 20.0))

    assert call_count == 1


def _fake_settings():
    from app.core.config import get_settings

    return get_settings()


# --- GET /api/v1/osm/points (endpoint-level) -------------------------------


def test_osm_points_endpoint_returns_parsed_features(monkeypatch) -> None:
    async def fake_fetch(self, latitude, longitude, radius_km):
        return [
            osm_route.OSMPointFeature(
                osm_id=111, name="Pančićev vrh", latitude=43.28, longitude=20.81, ele_m=2017.0, category="peak"
            )
        ]

    monkeypatch.setattr(OverpassService, "fetch_point_features_in_radius", fake_fetch)

    response = client.get("/api/v1/osm/points", params={"lat": 43.28, "lon": 20.81, "radius_km": 20.0})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["osm_id"] == 111
    assert body[0]["name"] == "Pančićev vrh"
    assert body[0]["category"] == "peak"


def test_osm_points_endpoint_rejects_invalid_radius() -> None:
    response = client.get("/api/v1/osm/points", params={"lat": 43.28, "lon": 20.81, "radius_km": 999.0})
    assert response.status_code == 422


def test_osm_points_endpoint_returns_503_on_overpass_error(monkeypatch) -> None:
    async def fake_fetch(self, latitude, longitude, radius_km):
        raise OverpassError("Overpass API nedostupan: simulacija za test")

    monkeypatch.setattr(OverpassService, "fetch_point_features_in_radius", fake_fetch)

    response = client.get("/api/v1/osm/points", params={"lat": 43.28, "lon": 20.81, "radius_km": 20.0})
    assert response.status_code == 503


# --- GET /api/v1/osm/point-candidates (Phase 5/9, endpoint-level) ---------


def test_osm_point_candidates_endpoint_filters_and_reports_debug_counts(monkeypatch) -> None:
    async def fake_fetch(self, latitude, longitude, radius_km):
        # Jedan feature sjeverno (~22 km, unutar radius=50 I unutar uskog
        # FOV oko heading=0), jedan istočno (~22 km, unutar radius=50 ali
        # VAN tog FOV) -- provjerava i filter i debug brojeve.
        return [
            osm_route.OSMPointFeature(
                osm_id=1, name="North", latitude=latitude + 0.2, longitude=longitude, ele_m=2000.0, category="peak"
            ),
            osm_route.OSMPointFeature(
                osm_id=2,
                name="East",
                latitude=latitude,
                longitude=longitude + 0.2,
                ele_m=1800.0,
                category="settlement",
            ),
        ]

    monkeypatch.setattr(OverpassService, "fetch_point_features_in_radius", fake_fetch)

    response = client.get(
        "/api/v1/osm/point-candidates",
        params={"lat": 0.0, "lon": 0.0, "heading_deg": 0.0, "fov_deg": 40.0, "radius_km": 50.0},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["candidates"]) == 1
    assert body["candidates"][0]["osm_id"] == 1
    assert body["debug"] == {
        "osm_candidates_total": 2,
        "candidates_after_fov_radius_filter": 1,
        "candidates_returned": 1,
    }


def test_osm_point_candidates_endpoint_returns_503_on_overpass_error(monkeypatch) -> None:
    async def fake_fetch(self, latitude, longitude, radius_km):
        raise OverpassError("Overpass API nedostupan: simulacija za test")

    monkeypatch.setattr(OverpassService, "fetch_point_features_in_radius", fake_fetch)

    response = client.get(
        "/api/v1/osm/point-candidates",
        params={"lat": 0.0, "lon": 0.0, "heading_deg": 0.0, "fov_deg": 40.0, "radius_km": 50.0},
    )
    assert response.status_code == 503
