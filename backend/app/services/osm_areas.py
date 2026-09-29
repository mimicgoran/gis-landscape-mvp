"""
Overpass API servis -- dohvatanje OSM AREA feature-a (rijeke, vodene
površine, parkovi, nacionalni parkovi) sa PUNOM geometrijom (way ->
LineString/Polygon, relation -> Polygon/MultiPolygon), za geometrijski
intersect sa viewing-sector poligonom (Phase 9).

Za razliku od tačkastih feature-a (`app.services.osm` -- peak/settlement/
viewpoint, jedna (lat, lon) tačka po objektu), ovi feature-i imaju STVARNU
prostornu protežnost, pa se korisnikovo pitanje "da li je taj park/rijeka
unutar mog vidnog polja" ne može odgovoriti poređenjem samo JEDNE tačke
(npr. centroida) sa sektorom -- eksplicitna korisnička odluka (vidi
docs/architecture-feasibility-review.md, Phase 9 status): centroid-only
pristup je odbačen jer sektor može pokrivati DIO poligona a ne njegov
centroid (npr. nacionalni park čiji je geometrijski centar van vidnog
polja, ali čija ivica jeste unutra).

OSM kategorije (Phase 9 scope, dogovoreno sa korisnikom):
- waterway=river         -> way, LineString
- natural=water          -> way (Polygon) ili relation (Multi/Polygon) --
  "sve vodene površine" (jezera, akumulacije...), ne samo rijeke
- leisure=park           -> way (Polygon), rijetko relation
- boundary=national_park -> obično relation (Multi/Polygon), ponekad way

Geometrija se dobija preko Overpass `out geom;`. Za way elemente ovo vraća
punu listu koordinata (`element["geometry"]`). Za relation elemente,
Overpass ugrađuje geometriju SVAKOG člana direktno u
`element["members"][i]["geometry"]` -- ovo je dokumentovano, standardno
Overpass ponašanje (isti pristup koristi npr. overpass-turbo za renderovanje
relacija, bez potrebe za posebnim rekurzivnim `.a >;` upitom).

VAŽNA NAPOMENA (vidi Phase 9 status u architecture-feasibility-review.md):
ovo specifično ponašanje (member geometrija ugrađena u `out geom` odgovor
za relacije) NIJE moglo biti empirijski provjereno iz ovog razvojnog
okruženja -- i cloud sandbox i lokalna VM u kojoj radi device_bash imaju
egress politiku koja blokira overpass-api.de (potvrđeno: obje vraćaju 403
na CONNECT). Ovo je PRVA stvar koju treba ručno provjeriti (Swagger/curl na
tvojoj mašini, van te VM-a) prije nego što se rezultat za relacije uzme
zdravo za gotovo -- ako se pokaže da member geometrija NIJE uključena,
rješenje je dodati eksplicitan rekurzivni upit (`->.a; (.a; .a >;); out
geom;`), što je manja izmjena samo u `_build_area_query`.
"""

from __future__ import annotations

import time
from typing import Literal

from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Polygon
from shapely.ops import polygonize, unary_union

from app.core.config import Settings
from app.services.overpass_http import OverpassHTTPError, fetch_overpass_json

_CACHE_COORD_PRECISION = 3
_CACHE_TTL_S = 24 * 60 * 60

_USER_AGENT = (
    "GIS-Landscape-Identification-MVP/0.1 "
    "(https://github.com/mimicgoran/gis-landscape-mvp; portfolio/demo projekat)"
)

# Retry/mirror-fallback logika (uklj. tranzitorne statusne kodove) sada
# živi u `app.services.overpass_http` (Phase 15 -- multi-mirror fallback,
# vidi taj modul za puno obrazloženje).

AreaCategory = Literal["river", "water", "park", "national_park"]


class OverpassAreaError(RuntimeError):
    """Podignuto kad Overpass API ne odgovori ili vrati neočekivan odgovor
    za area-feature upit. Odvojeno od `app.services.osm.OverpassError` iz
    istog razloga zbog kog su servisi odvojeni -- vidi modul docstring."""


class OSMAreaFeature:
    """Sirov OSM area feature sa STVARNOM Shapely geometrijom (LineString
    ili Polygon/MultiPolygon), prije bilo kakvog sector-intersect ili
    visibility rada (Phase 9).

    NIJE Pydantic model (za razliku od `OSMPointFeature`) -- nosi Shapely
    geometry objekat koji se nikad direktno ne serijalizuje kroz API
    (finalni API oblik je `AnalyzedAreaFeature` u app/models/feature.py,
    sastavljen tek nakon intersect/sampling koraka). Isti princip kao
    `app.services.visibility.VisibilityResult`.

    Koordinatna konvencija: `geometry` koristi (longitude, latitude) red
    (standardni Shapely/GeoJSON red), NE (lat, lon) kako Overpass/OSM
    imenuje polja -- namjerno i eksplicitno testirano
    (`tests/test_osm_areas.py`), jer je zamjena redosleda čest izvor bugova.

    `geometry` je `GeometryCollection` samo za feature-e SASTAVLJENE preko
    `merge_overlapping_river_water_features()` (rijeka + preklapajuća vodena
    površina spojene u jedan feature, vidi tu funkciju) -- inače je uvijek
    LineString/Polygon/MultiPolygon direktno iz Overpass parsinga.
    """

    __slots__ = ("osm_id", "osm_type", "name", "category", "geometry")

    def __init__(
        self,
        osm_id: int,
        osm_type: Literal["way", "relation"],
        name: str | None,
        category: AreaCategory,
        geometry: LineString | Polygon | MultiPolygon | GeometryCollection,
    ) -> None:
        self.osm_id = osm_id
        self.osm_type = osm_type
        self.name = name
        self.category = category
        self.geometry = geometry


class _CacheEntry:
    __slots__ = ("features", "expires_at_epoch_s")

    def __init__(self, features: list[OSMAreaFeature], expires_at_epoch_s: float) -> None:
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


def _build_area_query(latitude: float, longitude: float, radius_km: float) -> str:
    radius_m = radius_km * 1000.0
    around = f"(around:{radius_m:.0f},{latitude},{longitude})"
    return (
        "[out:json][timeout:25];"
        "("
        f'way["waterway"="river"]{around};'
        f'way["natural"="water"]{around};'
        f'relation["natural"="water"]{around};'
        f'way["leisure"="park"]{around};'
        f'relation["leisure"="park"]{around};'
        f'way["boundary"="national_park"]{around};'
        f'relation["boundary"="national_park"]{around};'
        ");"
        "out geom;"
    )


def _infer_category(tags: dict[str, str]) -> AreaCategory | None:
    """Prioritet kad tagovi 'kolidiraju' (npr. relacija sa i leisure=park i
    boundary=national_park -- rijetko, ali moguće u realnim OSM podacima):
    national_park je specifičniji i informativniji odgovor na "šta gledam"
    nego generički "park", pa ima prioritet."""
    if tags.get("boundary") == "national_park":
        return "national_park"
    if tags.get("waterway") == "river":
        return "river"
    if tags.get("natural") == "water":
        return "water"
    if tags.get("leisure") == "park":
        return "park"
    return None


def _way_geometry_to_shape(geometry_coords: list[dict[str, float]]) -> LineString | Polygon | None:
    """Way `geometry` polje (lista {"lat":.., "lon":..}) u Shapely oblik.
    Zatvoren prsten (prva == zadnja tačka, i bar 4 tačke -- minimum za
    validan Polygon prsten) -> Polygon (vodena površina/park/nacionalni
    park kao way). Nezatvoren -> LineString (rijeka, ili way koji
    predstavlja granicu ali nije eksplicitno zatvoren u OSM podacima --
    čest slučaj kod nesavršeno unesenih realnih podataka). Vraća `None`
    ako je geometrija prekratka (< 2 tačke) da bi bila validna."""
    if len(geometry_coords) < 2:
        return None
    coords = [(point["lon"], point["lat"]) for point in geometry_coords]
    if coords[0] == coords[-1] and len(coords) >= 4:
        try:
            polygon = Polygon(coords)
        except Exception:  # noqa: BLE001 -- namjerno široko, vidi docstring
            polygon = None
        if polygon is not None and polygon.is_valid and not polygon.is_empty:
            return polygon
    return LineString(coords)


def _relation_to_polygon(members: list[dict]) -> Polygon | MultiPolygon | None:
    """Sastavlja OSM relation (npr. nacionalni park) u Polygon/MultiPolygon
    preko `shapely.ops.polygonize()` -- standardni pristup za spajanje
    nepovezanih LineString segmenata (way-ova koji čine granicu) u
    zatvorene prstenove (vidi Phase 9 status u
    architecture-feasibility-review.md za obrazloženje zašto je ovo
    ispravan pristup umjesto ručnog graph-traversal algoritma).

    NAMJERNA pojednostavljenja (dogovorena sa korisnikom -- Phase 9
    status, direktan odgovor na primjedbu "centroid cijele relacije nije
    dobar pristup"): relacija dobija ISTI pun tretman kao way (sector
    intersect + multi-point visibility), ne pojednostavljen centroid. Uzimaju
    se SAMO way-ovi sa role="outer" (role="inner", tj. "rupe" u poligonu
    poput enklava unutar parka, se ignorišu -- rezultat može biti blago
    prevelik poligon, dokumentovana granica MVP-a). Ako `polygonize()` ne
    uspije sastaviti nijedan zatvoren prsten (npr. nekompletni/loši OSM
    podaci za tu konkretnu relaciju), vraća `None` -- pozivalac tu relaciju
    preskače umjesto da pukne ili izmišlja geometriju."""
    outer_lines: list[LineString] = []
    for member in members:
        if member.get("type") != "way" or member.get("role") != "outer":
            continue
        geometry_coords = member.get("geometry")
        if not geometry_coords or len(geometry_coords) < 2:
            continue
        outer_lines.append(LineString([(point["lon"], point["lat"]) for point in geometry_coords]))

    if not outer_lines:
        return None

    polygons = list(polygonize(outer_lines))
    if not polygons:
        return None

    merged = unary_union(polygons)
    if merged.is_empty:
        return None
    if isinstance(merged, (Polygon, MultiPolygon)):
        return merged
    return None


class OverpassAreaService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache: dict[tuple[float, float, float], _CacheEntry] = {}

    async def fetch_area_features_in_radius(
        self, latitude: float, longitude: float, radius_km: float
    ) -> list[OSMAreaFeature]:
        """HTTP/retry/mirror-fallback logika sada živi u
        `app.services.overpass_http.fetch_overpass_json` -- dijeljeno sa
        `app.services.osm.OverpassService` (Phase 15 -- multi-mirror
        fallback, vidi taj modul za puno obrazloženje). Parsing odgovora
        ostaje ovdje odvojen jer se suštinski razlikuje od tačkastih
        feature-a (way/relation geometrija naspram prostih node-ova)."""
        key = _cache_key(latitude, longitude, radius_km)
        cached = self._cache.get(key)
        if cached and cached.is_valid():
            return cached.features

        query = _build_area_query(latitude, longitude, radius_km)
        try:
            payload = await fetch_overpass_json(self._settings, query, _USER_AGENT)
        except OverpassHTTPError as exc:
            raise OverpassAreaError(str(exc)) from exc

        features = self._parse_elements(payload.get("elements", []))
        self._cache[key] = _CacheEntry(features=features, expires_at_epoch_s=time.monotonic() + _CACHE_TTL_S)
        return features

    @staticmethod
    def _parse_elements(elements: list[dict]) -> list[OSMAreaFeature]:
        features: list[OSMAreaFeature] = []
        for element in elements:
            tags = element.get("tags", {})
            category = _infer_category(tags)
            if category is None:
                continue

            element_type = element.get("type")
            name = tags.get("name")

            if element_type == "way":
                geometry_coords = element.get("geometry")
                if not geometry_coords:
                    continue
                shape = _way_geometry_to_shape(geometry_coords)
                if shape is None:
                    continue
                features.append(
                    OSMAreaFeature(
                        osm_id=element["id"], osm_type="way", name=name, category=category, geometry=shape
                    )
                )
            elif element_type == "relation":
                members = element.get("members")
                if not members:
                    continue
                shape = _relation_to_polygon(members)
                if shape is None:
                    continue
                features.append(
                    OSMAreaFeature(
                        osm_id=element["id"], osm_type="relation", name=name, category=category, geometry=shape
                    )
                )
        return features


def merge_overlapping_river_water_features(features: list[OSMAreaFeature]) -> list[OSMAreaFeature]:
    """Spaja `river` + preklapajuci `water` feature u JEDAN rezultat.

    Otkriveno rucčnim testiranjem (Sava kod Orašca, vidi
    docs/architecture-feasibility-review.md, sekcija 29): OSM veće rijeke
    tipično mapira NA OBA NAČINA istovremeno -- imenovana `waterway=river`
    linija (centralni tok) I bezimen `natural=water` poligon (stvarna vodena
    površina, obala-do-obale). Ovo su DVA različita OSM elementa (različit
    `osm_id`) koja predstavljaju ISTI fizički objekat -- bez spajanja,
    korisnik u rezultatima vidi "Sava" i "Vodena površina" kao dva odvojena
    rezultata za istu rijeku, što je zbunjujuće iako je svaki pojedinačno
    tačan.

    Spajanje je STVARNO GEOMETRIJSKO (`.intersects()`), ne po imenu ili
    blizini -- ime je često potpuno odsutno na `water` poligonu, pa se
    name-matching ne bi mogao osloniti ni na šta u baš ovom slučaju.
    Spojena geometrija je `GeometryCollection([river, *matched_waters])` --
    `area_visibility.sample_points_for_geometry()` već rekurzivno sample-uje
    svaku komponentu GeometryCollection-a (linija duz toka, poligon kao
    grid), pa se sam visibility algoritam NE MIJENJA, samo ulazni feature-i
    -- kombinovani `visible_fraction` prirodno pokriva OBA geometrijska
    izvora umjesto da se dva odvojeno računata rezultata naknadno spajaju
    (izbjegnuto jer bi zahtijevalo proizvoljno težinjenje dva različita
    sample seta).

    Namjerno OGRANIČENO na (river, water) parove -- park/national_park
    preklapanje nije prijavljeno kao problem (različita fizička pojava, ne
    isti objekat mapiran dvaput), pa se ne dira (YAGNI). Ako jedan `river`
    preklapa VIŠE `water` feature-a (rijedak slučaj, npr. rukavci), svi se
    spajaju u isti GeometryCollection. Ako jedan `water` feature preklapa
    VIšE `river`-a (npr. sutok), pripada PRVOM rijeci koja ga zahvati u
    ulaznoj listi -- rijedak edge case, prihvatljivo pojednostavljenje za
    MVP (nema kanonskog "ispravnog" vlasnika u takvom slučaju).

    O(n*m) parovanje (n rijeka * m voda) -- broj area feature-a po pozivu je
    mali (desetine, ograničeno Overpass radijusom), zanemarivo naspram
    Overpass/DEM poziva koji dominiraju vremenom izvršavanja.
    """
    rivers = [f for f in features if f.category == "river"]
    waters = [f for f in features if f.category == "water"]
    other_features = [f for f in features if f.category not in ("river", "water")]

    consumed_water_ids: set[int] = set()
    merged: list[OSMAreaFeature] = []

    for river in rivers:
        matched_waters = [
            water
            for water in waters
            if water.osm_id not in consumed_water_ids and river.geometry.intersects(water.geometry)
        ]

        if not matched_waters:
            merged.append(river)
            continue

        consumed_water_ids.update(water.osm_id for water in matched_waters)
        merged.append(
            OSMAreaFeature(
                osm_id=river.osm_id,
                osm_type=river.osm_type,
                name=river.name,
                category="river",
                geometry=GeometryCollection([river.geometry, *(water.geometry for water in matched_waters)]),
            )
        )

    leftover_waters = [water for water in waters if water.osm_id not in consumed_water_ids]

    return merged + leftover_waters + other_features
