"""
ArcGIS World Geocoding Service kao izvor TAČKASTIH feature-a (peak/
settlement/viewpoint) -- ZAMENA za Overpass API (`app.services.osm`) za
ovu namjenu.

ZAŠTO: javni besplatni Overpass mirror-i (overpass-api.de, private.coffee)
su se pokazali nepouzdanim na produkciji (Render) -- overpass-api.de
blokira IP opsege deljenih cloud provajdera, private.coffee je
nepredvidivo spor. Korisnik već ima ArcGIS Online licencu (koja se već
koristi za mapu, vidi app.services.arcgis_auth) -- ArcGIS World Geocoding
Service podržava `category`-bazirano pretraživanje BEZ teksta adrese,
koje pokriva tačno naš scope. Ovo dodatno ojačava "Esri deo" portfolija
(brief tačka 3/37 -- eksplicitan zahtjev da Esri infrastruktura bude
STVARNI, vidljiv dio projekta, ne samo pomenuta u README-u).

EMPIRIJSKA PROVJERA (prije implementacije, vidi
docs/architecture-feasibility-review.md za pun kontekst): direktan poziv
`findAddressCandidates` sa `category=Mountain,Scenic Overlook,City` i
`location` na Kopaoniku je vratio TAČNE, imenovane rezultate (uklj.
"Pančićev Vrh" na 43.26943/20.82303 -- razlika svega par metara od OSM
koordinate 43.26925/20.82366 za isti vrh).

NIJE zamena za `app.services.osm_areas` (rijeke/parkovi/vodene površine/
nacionalni parkovi): ArcGIS geocoding vraća SAMO tačke (jednu (x,y) po
kandidatu), nikad poligon/liniju geometriju -- area feature-i OSTAJU na
OSM/Overpass izvoru (area feature-i imaju manje kritičnu zavisnost o
Overpass-u jer nisu na kritičnoj putanji za osnovni "šta gledam" odgovor
na isti način -- prihvaćen kompromis, ne rješavamo taj rizik sada).

MAPIRANJE KATEGORIJA (na `OSMPointFeature.category`):
- "Mountain"        -> "peak"
- "Scenic Overlook" -> "viewpoint"
- "City"            -> "settlement" (NAPOMENA: World Geocoding Service
  "Populated Place" grupa NEMA odvojenu "Town"/"Village" kategoriju kao
  OSM place=town/village -- manja naselja se neće naći ovim putem. Poznato
  suženje pokrivenosti u odnosu na prethodni OSM scope, prihvaćeno kao
  razuman kompromis za pouzdanost -- vidi arhitekturni dokument.)

ELEVATION: odgovor NE sadrži `ele` polje (potvrđeno empirijski) -- svi
kandidati iz ovog izvora imaju `ele_m=None`, pa target elevation UVIJEK
ide na DEM fallback (već postojeća logika u
`app.services.visibility.resolve_target_elevation` -- nema izmjene
potrebne tamo).

`osm_id` POLJE (ime ostavljeno nepromijenjeno radi minimalne izmjene
ostatka pipeline-a -- `OSMPointFeature`/`PointCandidate`/`AnalyzedFeature`
ga koriste samo kao neprozirni identifikator, nikad za stvaran OSM
lookup, vidi grep provjeru prije implementacije) je ovdje SINTETIČKI
stabilan hash (naziv, lat, lon) -- Esri odgovor NE sadrži persistent ID
za POI kandidate iz ovog endpointa.

AUTENTIFIKACIJA: koristi POSTOJEĆI OAuth access token
(`app.services.arcgis_auth.ArcGISAuthService`, isti mehanizam/keš kao za
mapu -- vidi `app.api.routes.arcgis_token.get_arcgis_auth_service`), NE
anonimni pristup. Anonimni pristup (bez tokena) je empirijski RADIO
tokom testiranja ovog pristupa, ali nije dokumentovano podržan način rada
za produkcione servise -- oslanjanje na njega bi bilo neopravdano.

CREDITS: svaki poziv troši ArcGIS Online geocoding kredite. Zvanično
dokumentovana standardna stopa je 40 kredita/1000 geocoding transakcija
(doc.arcgis.com/en/arcgis-online/administer/credits.htm) -- NIJE bilo
moguće iz dokumentacije potvrditi da se TAČNO ova operacija (category-only
pretraga bez adrese, bez `forStorage`) naplaćuje po istoj stopi (moguće
je jeftinije, npr. tretirano kao "geosearch" koji doc.arcgis.com
eksplicitno navodi kao besplatan za lokatore -- ali to se odnosi na
custom locator-e objavljene u AGOL-u, ne na World Geocoding Service
per se). PREPORUKA (dokumentovano i korisniku prenešeno prije
implementacije): ručno provjeriti ArcGIS Online credit dashboard
(Organization -> Status) nakon prvih poziva da se potvrdi stvarna
potrošnja prije oslanjanja na procjenu.

Caching: identičan obrazac kao `app.services.osm.OverpassService` (in-
memory TTL keš po zaokruženom (lat, lon, radius)) -- ovdje dodatno bitno
i radi kontrole troška kredita, ne samo brzine/fair-use.
"""

from __future__ import annotations

import time
import zlib
from typing import Literal

import httpx

from app.core.config import Settings
from app.models.feature import OSMPointFeature
from app.services.arcgis_auth import ArcGISAuthError, ArcGISAuthService

_GEOCODE_URL = "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"

# Redosled/spisak kategorija -- vidi modul docstring za mapiranje i poznato
# ograničenje (nema Town/Village).
_CATEGORIES = "Mountain,Scenic Overlook,City"

# Dokumentovani maksimum za `maxLocations` na ovom endpointu (vidi
# developers.arcgis.com/rest/geocode/find-address-candidates).
_MAX_LOCATIONS = 50

_TYPE_TO_CATEGORY: dict[str, Literal["peak", "settlement", "viewpoint"]] = {
    "Mountain": "peak",
    "Scenic Overlook": "viewpoint",
    "City": "settlement",
}

# Isto obrazloženje kao app.services.osm._CACHE_COORD_PRECISION/_CACHE_TTL_S
# -- ovdje dodatno bitno radi kontrole troška kredita.
_CACHE_COORD_PRECISION = 3
_CACHE_TTL_S = 24 * 60 * 60

_REQUEST_TIMEOUT_S = 10.0


class ArcGISPlacesError(RuntimeError):
    """Podignuto kad ArcGIS geocoding servis ne odgovori ili vrati
    neočekivan odgovor za point-feature upit."""


class _CacheEntry:
    __slots__ = ("features", "expires_at_epoch_s")

    def __init__(self, features: list[OSMPointFeature], expires_at_epoch_s: float) -> None:
        self.features = features
        self.expires_at_epoch_s = expires_at_epoch_s

    def is_valid(self) -> bool:
        return time.monotonic() < self.expires_at_epoch_s


def _cache_key(latitude: float, longitude: float, radius_km: float) -> tuple[float, float, float]:
    return (
        round(latitude, _CACHE_COORD_PRECISION),
        round(longitude, _CACHE_COORD_PRECISION),
        round(radius_km, 1),
    )


def _synthetic_id(name: str | None, latitude: float, longitude: float) -> int:
    """Esri odgovor ne sadrži persistent ID za POI kandidate iz ovog
    endpointa (vidi modul docstring) -- generišemo stabilan (isti ulaz ->
    isti izlaz) sintetički int preko CRC32 hash-a, dovoljno za `osm_id`
    polje koje se koristi samo kao neprozirni identifikator nizvodno."""
    key = f"{name or ''}|{latitude:.6f}|{longitude:.6f}"
    return zlib.crc32(key.encode("utf-8"))


class ArcGISPlacesService:
    """Drži jedan in-memory keš po procesu, isti obrazac kao
    `app.services.osm.OverpassService`. Zavisi od `ArcGISAuthService` za
    access token -- ne pravi sopstvenu OAuth razmjenu (dijeli keš tokena
    sa `/api/v1/arcgis-token`, vidi `get_arcgis_auth_service`)."""

    def __init__(self, settings: Settings, auth_service: ArcGISAuthService) -> None:
        self._settings = settings
        self._auth_service = auth_service
        self._cache: dict[tuple[float, float, float], _CacheEntry] = {}

    async def fetch_point_features_in_radius(
        self, latitude: float, longitude: float, radius_km: float
    ) -> list[OSMPointFeature]:
        """`radius_km` se ovdje NE šalje Esri servisu kao tvrd prostorni
        cutoff (findAddressCandidates nema jednostavan ekvivalent Overpass
        `around:radius` za category-only upit) -- umjesto toga, `location`
        bias vraća prostorno relevantne kandidate, a stvarno geodesic
        filtriranje po `radius_km` se već radi nizvodno u
        `app.services.geometry.select_candidates` (identično kao za
        Overpass rezultate ranije -- taj korak je uvijek radio punu
        provjeru distance/FOV, bez obzira na to da li je izvor već
        pred-filtrirao po radijusu)."""
        key = _cache_key(latitude, longitude, radius_km)
        cached = self._cache.get(key)
        if cached and cached.is_valid():
            return cached.features

        try:
            token = await self._auth_service.get_access_token()
        except ArcGISAuthError as exc:
            raise ArcGISPlacesError(str(exc)) from exc

        params = {
            "f": "json",
            "token": token,
            "location": f"{longitude},{latitude}",
            "category": _CATEGORIES,
            "maxLocations": _MAX_LOCATIONS,
            "outFields": "Type",
        }

        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_S) as client:
                response = await client.get(_GEOCODE_URL, params=params)
        except httpx.HTTPError as exc:
            raise ArcGISPlacesError(f"ArcGIS geocoding nedostupan: {exc}") from exc

        if response.status_code != 200:
            raise ArcGISPlacesError(f"ArcGIS geocoding vratio {response.status_code}: {response.text[:300]}")

        payload = response.json()
        if "error" in payload:
            raise ArcGISPlacesError(f"ArcGIS geocoding greška: {payload['error']}")

        features: list[OSMPointFeature] = []
        for candidate in payload.get("candidates", []):
            attributes = candidate.get("attributes", {})
            category = _TYPE_TO_CATEGORY.get(attributes.get("Type"))
            if category is None:
                # Kategorija van našeg mapiranja (ne bi trebalo da se
                # desi s obzirom na `_CATEGORIES` upit, ali odbacujemo
                # umjesto da pucamo ako Esri ikad doda/promijeni tip).
                continue

            location = candidate.get("location") or {}
            candidate_latitude = location.get("y")
            candidate_longitude = location.get("x")
            if candidate_latitude is None or candidate_longitude is None:
                continue

            name = candidate.get("address") or None
            features.append(
                OSMPointFeature(
                    osm_id=_synthetic_id(name, candidate_latitude, candidate_longitude),
                    name=name,
                    latitude=candidate_latitude,
                    longitude=candidate_longitude,
                    ele_m=None,
                    category=category,
                )
            )

        self._cache[key] = _CacheEntry(features=features, expires_at_epoch_s=time.monotonic() + _CACHE_TTL_S)
        return features
