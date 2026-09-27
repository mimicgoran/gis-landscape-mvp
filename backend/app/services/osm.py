"""
Overpass API servis -- dohvatanje OSM natural=peak objekata u radijusu oko
zadate tačke.

Phase 4 scope: samo natural=peak (vidi docs/architecture-feasibility-review.md,
sekcije 7 i 18 -- ostale kategorije su follow-up nakon Phase 9).

Caching: jednostavan in-memory TTL keš keyed po zaokruženom (lat, lon,
radius) -- planinski vrhovi se ne pomjeraju, pa je dug TTL siguran, a usput
poštuje Overpass fair-use politiku (javne instance preporučuju izbjegavanje
identičnih ponovljenih upita). Isti obrazac kao ArcGISAuthService
(app/services/arcgis_auth.py) -- jedan cache po procesu, dovoljno za MVP
saobraćaj, bez eksterne cache infrastrukture.
"""

from __future__ import annotations

import time

import httpx

from app.core.config import Settings
from app.models.feature import OSMPeak

# Zaokruživanje na 3 decimale (~111 m na ekvatoru) je dovoljno grubo da keš
# pogodi ponovljene zahtjeve sa iste test lokacije (razvoj/demo), a dovoljno
# fino da ne miješa stvarno različite lokacije.
_CACHE_COORD_PRECISION = 3
_CACHE_TTL_S = 24 * 60 * 60

# Overpass API (overpass-api.de) je 2026. uveo stroža anti-abuse pravila
# zbog preopterećenja servera -- zahtjevi bez identifikacionog User-Agent
# header-a dobijaju "406 Not Acceptable" (potvrđeno: zvanični Overpass-API
# GitHub issue #791 i OSM community forum thread o istoj grešci). Ne šaljemo
# Referer (nema live domena prije Phase 15 deploymenta) -- User-Agent je,
# prema istim izvorima, dovoljan i najčešće naveden fix.
_USER_AGENT = (
    "GIS-Landscape-Identification-MVP/0.1 "
    "(https://github.com/mimicgoran/gis-landscape-mvp; portfolio/demo projekat)"
)


class OverpassError(RuntimeError):
    """Podignuto kad Overpass API ne odgovori ili vrati neočekivan odgovor."""


class _CacheEntry:
    __slots__ = ("peaks", "expires_at_epoch_s")

    def __init__(self, peaks: list[OSMPeak], expires_at_epoch_s: float) -> None:
        self.peaks = peaks
        self.expires_at_epoch_s = expires_at_epoch_s

    def is_valid(self) -> bool:
        return time.monotonic() < self.expires_at_epoch_s


def _cache_key(latitude: float, longitude: float, radius_km: float) -> tuple[float, float, float]:
    return (
        round(latitude, _CACHE_COORD_PRECISION),
        round(longitude, _CACHE_COORD_PRECISION),
        round(radius_km, 1),
    )


def _build_overpass_query(latitude: float, longitude: float, radius_km: float) -> str:
    radius_m = radius_km * 1000.0
    # Node je dovoljan -- natural=peak je u OSM-u uvijek tačka (node), nikad
    # way/relation. `out body;` vraća i tagove (name, ele), ne samo koordinate.
    return (
        "[out:json][timeout:25];"
        f'node["natural"="peak"](around:{radius_m:.0f},{latitude},{longitude});'
        "out body;"
    )


def _parse_ele_tag(raw_ele: str | None) -> float | None:
    """OSM 'ele' tag je slobodan tekst (npr. "2017", "2017.5", ponekad
    pogrešno unesen) -- parsiramo defanzivno i odbacujemo sve što nije čist,
    smislen broj za planinski vrh (vidi sekciju 9, korak 8: koristimo OSM
    ele samo "ako postoji i djeluje validno", inače DEM fallback u Phase 6+
    preuzima ulogu)."""
    if raw_ele is None:
        return None
    try:
        value = float(raw_ele)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value


class OverpassService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache: dict[tuple[float, float, float], _CacheEntry] = {}

    async def fetch_peaks_in_radius(self, latitude: float, longitude: float, radius_km: float) -> list[OSMPeak]:
        key = _cache_key(latitude, longitude, radius_km)
        cached = self._cache.get(key)
        if cached and cached.is_valid():
            return cached.peaks

        query = _build_overpass_query(latitude, longitude, radius_km)

        async with httpx.AsyncClient(timeout=25.0) as client:
            try:
                response = await client.post(
                    self._settings.overpass_api_url,
                    data={"data": query},
                    headers={"User-Agent": _USER_AGENT},
                )
            except httpx.HTTPError as exc:
                raise OverpassError(f"Overpass API nedostupan: {exc}") from exc

        if response.status_code != 200:
            raise OverpassError(f"Overpass API vratio {response.status_code}: {response.text[:300]}")

        payload = response.json()
        peaks = [
            OSMPeak(
                osm_id=element["id"],
                name=element.get("tags", {}).get("name"),
                latitude=element["lat"],
                longitude=element["lon"],
                ele_m=_parse_ele_tag(element.get("tags", {}).get("ele")),
            )
            for element in payload.get("elements", [])
            if element.get("type") == "node"
        ]

        self._cache[key] = _CacheEntry(peaks=peaks, expires_at_epoch_s=time.monotonic() + _CACHE_TTL_S)
        return peaks
