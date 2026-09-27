"""
Overpass API servis -- dohvatanje TAČKASTIH OSM feature-a (peak/settlement/
viewpoint) u radijusu oko zadate tačke.

Phase 9 proširenje (vidi docs/architecture-feasibility-review.md, Phase 9
status): korisnik je eksplicitno tražio da se scope ne zadrži samo na
natural=peak (Phase 4) -- dodati su place=city|town|village i
tourism=viewpoint. Sve tri kategorije su i dalje TAČKE (node u OSM-u), pa
dijele identičan pipeline (jedan Overpass upit, jedan
select_candidates/DEM/line-of-sight prolaz -- razlika je samo `category`
polje). Feature-i sa stvarnom geometrijom (rijeke/parkovi/vodene površine/
nacionalni parkovi) su odvojen servis, `app.services.osm_areas`, jer im
treba suštinski drugačiji (sector-intersect + multi-point) pipeline.

Caching: jednostavan in-memory TTL keš keyed po zaokruženom (lat, lon,
radius) -- ni vrhovi ni naselja ni vidikovci se ne pomjeraju, pa je dug TTL
siguran, a usput poštuje Overpass fair-use politiku (javne instance
preporučuju izbjegavanje identičnih ponovljenih upita). Isti obrazac kao
ArcGISAuthService (app/services/arcgis_auth.py) -- jedan cache po procesu,
dovoljno za MVP saobraćaj, bez eksterne cache infrastrukture.
"""

from __future__ import annotations

import asyncio
import time
from typing import Literal

import httpx

from app.core.config import Settings
from app.models.feature import OSMPointFeature

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

# Statusni kodovi koji signaliziraju TRANZITORAN problem (server preopterećen,
# rate limit, gateway timeout) -- vrijedi ih retry-ovati. Sve ostalo (npr.
# 400 loš upit, 406 bez User-Agent -- taj slučaj je već riješen iznad) je
# trajna greška koju retry ne bi popravio, pa se odmah odustaje.
_TRANSIENT_STATUS_CODES = {429, 502, 503, 504}

_SETTLEMENT_PLACE_VALUES = {"city", "town", "village"}


class OverpassError(RuntimeError):
    """Podignuto kad Overpass API ne odgovori ili vrati neočekivan odgovor."""


class _CacheEntry:
    __slots__ = ("peaks", "expires_at_epoch_s")

    def __init__(self, peaks: list[OSMPointFeature], expires_at_epoch_s: float) -> None:
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
    """Union upit za sve tri tačkaste kategorije (Phase 9). Node je dovoljan
    za sve tri -- natural=peak, place=city/town/village i tourism=viewpoint
    su u OSM-u uvijek tačke (node), nikad way/relation. `out body;` vraća i
    tagove (name, ele, place, tourism...), ne samo koordinate -- potrebno da
    `_infer_category` odredi koja je kategorija u pitanju (Overpass ne
    prijavljuje koja OR grana je pogodila element)."""
    radius_m = radius_km * 1000.0
    around = f"(around:{radius_m:.0f},{latitude},{longitude})"
    return (
        "[out:json][timeout:25];"
        "("
        f'node["natural"="peak"]{around};'
        f'node["place"~"^(city|town|village)$"]{around};'
        f'node["tourism"="viewpoint"]{around};'
        ");"
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


def _infer_category(tags: dict[str, str]) -> Literal["peak", "settlement", "viewpoint"] | None:
    """Overpass union upit ne prijavljuje koja OR grana je pogodila dati
    element -- kategorija se mora izvesti direktno iz tagova. Vraća `None`
    (element se odbacuje) u teoretski nemogućem slučaju da nijedan od tri
    očekivana taga nije prisutan (npr. Overpass server bug ili neočekivana
    promjena podataka) -- defanzivno, radije preskočiti nego pogrešno
    kategorisati."""
    if tags.get("natural") == "peak":
        return "peak"
    if tags.get("place") in _SETTLEMENT_PLACE_VALUES:
        return "settlement"
    if tags.get("tourism") == "viewpoint":
        return "viewpoint"
    return None


class OverpassService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache: dict[tuple[float, float, float], _CacheEntry] = {}

    async def fetch_point_features_in_radius(
        self, latitude: float, longitude: float, radius_km: float
    ) -> list[OSMPointFeature]:
        """Vidi modul docstring (User-Agent fix) i `_TRANSIENT_STATUS_CODES`
        za obrazloženje retry logike -- do `Settings.overpass_max_retries`
        dodatnih pokušaja SAMO za tranzitorne greške (mrežni problem, 429/
        502/503/504), sa `Settings.overpass_retry_backoff_s` pauzom između
        pokušaja. Trajne greške (npr. 400) se odmah prijavljuju bez
        čekanja -- retry im ne bi pomogao.

        Preimenovano iz `fetch_peaks_in_radius` u Phase 9 (vidi
        `app.models.feature.OSMPointFeature`)."""
        key = _cache_key(latitude, longitude, radius_km)
        cached = self._cache.get(key)
        if cached and cached.is_valid():
            return cached.peaks

        query = _build_overpass_query(latitude, longitude, radius_km)
        max_attempts = self._settings.overpass_max_retries + 1
        last_error: OverpassError | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=25.0) as client:
                    response = await client.post(
                        self._settings.overpass_api_url,
                        data={"data": query},
                        headers={"User-Agent": _USER_AGENT},
                    )
            except httpx.HTTPError as exc:
                last_error = OverpassError(f"Overpass API nedostupan: {exc}")
            else:
                if response.status_code == 200:
                    payload = response.json()
                    peaks: list[OSMPointFeature] = []
                    for element in payload.get("elements", []):
                        if element.get("type") != "node":
                            continue
                        tags = element.get("tags", {})
                        category = _infer_category(tags)
                        if category is None:
                            continue
                        peaks.append(
                            OSMPointFeature(
                                osm_id=element["id"],
                                name=tags.get("name"),
                                latitude=element["lat"],
                                longitude=element["lon"],
                                ele_m=_parse_ele_tag(tags.get("ele")),
                                category=category,
                            )
                        )
                    self._cache[key] = _CacheEntry(peaks=peaks, expires_at_epoch_s=time.monotonic() + _CACHE_TTL_S)
                    return peaks

                if response.status_code not in _TRANSIENT_STATUS_CODES:
                    # Trajna greška -- retry ne bi pomogao, odustajemo odmah.
                    raise OverpassError(f"Overpass API vratio {response.status_code}: {response.text[:300]}")

                last_error = OverpassError(f"Overpass API vratio {response.status_code}: {response.text[:300]}")

            if attempt < max_attempts:
                await asyncio.sleep(self._settings.overpass_retry_backoff_s)

        assert last_error is not None  # max_attempts >= 1, pa je last_error uvijek postavljen prije ovog reda
        raise last_error
