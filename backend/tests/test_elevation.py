"""
Testovi za DEM elevation servis -- Phase 6.

Mrežni download se svuda monkeypatch-uje (`_download_tile`) -- CI runner ne
smije zavisiti od dostupnosti Copernicus S3 bucket-a, isti princip kao kod
Overpass testova (vidi tests/test_osm.py). Stvarno čitanje/sampling
(rasterio open + sample) se NE mock-uje -- testovi pišu pravi mali GeoTIFF
fixture na disk i provjeravaju da servis stvarno ume da ga pročita, čime se
i dalje testira prava logika (nodata handling, cache-hit put), samo bez
prave mreže.

Stvarna integracija protiv pravog Copernicus S3 bucket-a je ručno potvrđena
za Kopaonik/Pančićev vrh tokom Phase 6 troubleshooting-a (elevacija 2011.6 m
naspram OSM ele=2017 m -- razlika u granicama očekivane GLO-30 vertikalne
tačnosti, vidi docs/architecture-feasibility-review.md, Phase 6 status).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from app.api.routes import elevation as elevation_route
from app.core.config import Settings
from app.main import app
from app.services.elevation import ElevationError, ElevationService, _tile_name

client = TestClient(app)

# --- Fixture raster geometrija -------------------------------------------
# 10x10 piksela, 0.01 stepeni/piksel, sjeverozapadni ugao na (lon=20.0,
# lat=44.0). Piksel [0, 0] (sjeverozapadni ugao) je namjerno "nodata";
# svi ostali pikseli imaju istu poznatu vrijednost.
_FIXTURE_ORIGIN_LON = 20.0
_FIXTURE_ORIGIN_LAT = 44.0
_FIXTURE_RES_DEG = 0.01
_FIXTURE_SIZE_PX = 10
_FIXTURE_VALUE_M = 1500.0
_FIXTURE_NODATA = -32767.0

# Tačka unutar piksela [0, 0] -> nodata.
_NODATA_POINT = (_FIXTURE_ORIGIN_LON + 0.005, _FIXTURE_ORIGIN_LAT - 0.005)
# Tačka unutar piksela [5, 5] -> poznata vrijednost.
_INSIDE_POINT = (_FIXTURE_ORIGIN_LON + 0.055, _FIXTURE_ORIGIN_LAT - 0.055)


def _write_fixture_tile(dest_path: Path) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    data = np.full((_FIXTURE_SIZE_PX, _FIXTURE_SIZE_PX), _FIXTURE_VALUE_M, dtype="float32")
    data[0, 0] = _FIXTURE_NODATA

    transform = from_origin(_FIXTURE_ORIGIN_LON, _FIXTURE_ORIGIN_LAT, _FIXTURE_RES_DEG, _FIXTURE_RES_DEG)
    with rasterio.open(
        dest_path,
        "w",
        driver="GTiff",
        height=_FIXTURE_SIZE_PX,
        width=_FIXTURE_SIZE_PX,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=_FIXTURE_NODATA,
    ) as dataset:
        dataset.write(data, 1)


def _fake_settings(cache_dir: Path) -> Settings:
    # Jedini servis kojem test treba prilagođen (izolovan, po-testu) keš
    # direktorijum -- ostali servisi (npr. OverpassService) nemaju perzistentno
    # stanje na disku pa im get_settings() (pravi .env) dovoljan.
    return Settings(dem_cache_dir=str(cache_dir))


# --- _tile_name ------------------------------------------------------------


@pytest.mark.parametrize(
    ("lat", "lon", "expected"),
    [
        (43.2692547, 20.8236633, "Copernicus_DSM_COG_10_N43_00_E020_00_DEM"),  # Kopaonik -- empirijski potvrđeno
        (43.999, 20.999, "Copernicus_DSM_COG_10_N43_00_E020_00_DEM"),  # blizu gornje granice istog tile-a
        (44.0, 21.0, "Copernicus_DSM_COG_10_N44_00_E021_00_DEM"),  # tačno na SW uglu SLJEDEĆEG tile-a
        (-5.3, 20.4, "Copernicus_DSM_COG_10_S06_00_E020_00_DEM"),  # južna hemisfera
        (43.2, -74.5, "Copernicus_DSM_COG_10_N43_00_W075_00_DEM"),  # zapadna hemisfera
        (-33.9, -70.6, "Copernicus_DSM_COG_10_S34_00_W071_00_DEM"),  # oba negativna (Santiago)
    ],
)
def test_tile_name(lat, lon, expected) -> None:
    assert _tile_name(lat, lon) == expected


# --- ElevationService.get_elevation ----------------------------------------


def test_get_elevation_downloads_when_not_cached(tmp_path, monkeypatch) -> None:
    import app.services.elevation as elevation_module

    fixture_path = tmp_path / "fixture_source.tif"
    _write_fixture_tile(fixture_path)

    download_calls: list[str] = []

    def fake_download_tile(url, dest_path, timeout_s):
        download_calls.append(url)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(fixture_path.read_bytes())

    monkeypatch.setattr(elevation_module, "_download_tile", fake_download_tile)

    service = ElevationService(_fake_settings(tmp_path / "cache"))
    lon, lat = _INSIDE_POINT
    result = service.get_elevation(lat, lon)

    assert result == pytest.approx(_FIXTURE_VALUE_M)
    assert len(download_calls) == 1


def test_get_elevation_uses_cache_without_downloading(tmp_path, monkeypatch) -> None:
    import app.services.elevation as elevation_module

    cache_dir = tmp_path / "cache"
    tile_name = _tile_name(*_INSIDE_POINT[::-1])
    _write_fixture_tile(cache_dir / f"{tile_name}.tif")

    monkeypatch.setattr(elevation_module, "_download_tile", _fail_if_called)

    service = ElevationService(_fake_settings(cache_dir))
    lon, lat = _INSIDE_POINT
    result = service.get_elevation(lat, lon)

    assert result == pytest.approx(_FIXTURE_VALUE_M)


def _fail_if_called(*args, **kwargs):
    raise AssertionError("_download_tile ne smije biti pozvan kad je tile već keširan")


def test_get_elevation_returns_none_on_nodata_pixel(tmp_path, monkeypatch) -> None:
    import app.services.elevation as elevation_module

    cache_dir = tmp_path / "cache"
    tile_name = _tile_name(*_NODATA_POINT[::-1])
    _write_fixture_tile(cache_dir / f"{tile_name}.tif")
    monkeypatch.setattr(elevation_module, "_download_tile", _fail_if_called)

    service = ElevationService(_fake_settings(cache_dir))
    lon, lat = _NODATA_POINT
    result = service.get_elevation(lat, lon)

    assert result is None


def test_get_elevation_returns_none_when_download_fails(tmp_path, monkeypatch) -> None:
    import app.services.elevation as elevation_module

    def fake_download_tile(url, dest_path, timeout_s):
        raise ElevationError("simulirani mrežni problem")

    monkeypatch.setattr(elevation_module, "_download_tile", fake_download_tile)

    service = ElevationService(_fake_settings(tmp_path / "cache"))
    lon, lat = _INSIDE_POINT
    result = service.get_elevation(lat, lon)

    assert result is None


# --- GET /api/v1/elevation/lookup (endpoint-level) -------------------------


def test_elevation_lookup_endpoint_returns_value(monkeypatch) -> None:
    monkeypatch.setattr(elevation_route._elevation_service, "get_elevation", lambda lat, lon: 2011.6)

    response = client.get("/api/v1/elevation/lookup", params={"lat": 43.27, "lon": 20.82})

    assert response.status_code == 200
    body = response.json()
    assert body["elevation_m"] == pytest.approx(2011.6)
    assert body["elevation_source"] == "dem"


def test_elevation_lookup_endpoint_returns_null_when_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(elevation_route._elevation_service, "get_elevation", lambda lat, lon: None)

    response = client.get("/api/v1/elevation/lookup", params={"lat": 0.0, "lon": 0.0})

    assert response.status_code == 200
    body = response.json()
    assert body["elevation_m"] is None
    assert body["elevation_source"] is None


def test_elevation_lookup_endpoint_rejects_out_of_range_coordinates() -> None:
    response = client.get("/api/v1/elevation/lookup", params={"lat": 95.0, "lon": 20.0})
    assert response.status_code == 422
