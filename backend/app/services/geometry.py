"""
Geometrijske GIS funkcije: geodesic distance, initial bearing, angular
difference, sector inclusion, i (Phase 9) viewing-sector kao Shapely
Polygon za intersect sa area feature-ima.

Sve računice distanci/bearing-a koriste WGS84 elipsoid preko `pyproj.Geod`
(ne haversine na sferi, ne ravnu Euclidean distancu) — tačnije na većim
udaljenostima, vidi docs/architecture-feasibility-review.md, sekcija 8/24.

Wrap-around (heading/bearing preko 0°/360° granice, npr. heading 359° i
feature na 1°) je najčešći izvor bugova u ovakvoj matematici — svaka
funkcija ovdje je eksplicitno testirana na te slučajeve (vidi
backend/tests/test_geometry.py).
"""

from __future__ import annotations

from pyproj import Geod
from shapely.geometry import Polygon

from app.models.feature import OSMPointFeature, PointCandidate

# Jedan Geod objekat po procesu — inicijalizacija nije besplatna, a instanca
# je immutable/thread-safe za `.inv()`/`.fwd()`/`.npts()` pozive.
_WGS84_GEOD = Geod(ellps="WGS84")


def geodesic_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Geodesic (WGS84 elipsoid) distanca u kilometrima između dvije tačke."""
    _, _, distance_m = _WGS84_GEOD.inv(lon1, lat1, lon2, lat2)
    return distance_m / 1000.0


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Početni (forward) bearing od tačke 1 ka tački 2, normalizovan na [0, 360)."""
    forward_azimuth_deg, _, _ = _WGS84_GEOD.inv(lon1, lat1, lon2, lat2)
    return forward_azimuth_deg % 360.0


def angular_difference_deg(bearing_deg: float, heading_deg: float) -> float:
    """Najmanja ugaona razlika između dva pravca, u opsegu [0, 180].

    Hvata wrap-around slučajeve (npr. heading=359, bearing=1 -> razlika 2,
    ne 358) tako što se apsolutna razlika normalizovanih uglova poredi sa
    njenim komplementom do punog kruga i uzima manja vrijednost.
    """
    diff = abs(bearing_deg % 360.0 - heading_deg % 360.0)
    return min(diff, 360.0 - diff)


def is_within_sector(bearing_deg: float, heading_deg: float, fov_deg: float) -> bool:
    """Da li je pravac `bearing_deg` unutar vidnog polja `fov_deg` centriranog na `heading_deg`.

    Ekvivalentno provjeri granica sektora (start/end bearing), ali
    implementaciono jednostavnije i manje podložno wrap-around bugovima —
    vidi docs/architecture-feasibility-review.md, sekcija 8, korak 4.
    """
    return angular_difference_deg(bearing_deg, heading_deg) <= fov_deg / 2.0


def geodesic_intermediate_points(
    lat1: float, lon1: float, lat2: float, lon2: float, sample_spacing_m: float
) -> list[tuple[float, float, float]]:
    """Ravnomjerno raspoređene tačke duž geodesic linije (tačka1 -> tačka2,
    WGS84 elipsoid), na približno `sample_spacing_m` razmaku -- koristi se
    za line-of-sight DEM sampling (Phase 8, vidi
    docs/architecture-feasibility-review.md, sekcija 9, korak 2).

    Vraća listu `(lat, lon, distance_from_start_m)`, BEZ krajnjih tačaka
    (tačka1, tačka2) -- pozivalac (`app.services.visibility`) njih tretira
    odvojeno (tačka1/observer je referenca za ugao, tačka2/target je ono
    što se provjerava, ne "teren između").

    Broj tačaka: `round(distance_m / sample_spacing_m) - 1`, minimum 0. Ako
    je distanca kraća od jednog sample intervala, vraća praznu listu --
    linija je toliko kratka da je "teren između" zanemarljiv slučaj (nema
    prostora za prepreku)."""
    _, _, distance_m = _WGS84_GEOD.inv(lon1, lat1, lon2, lat2)
    npts = max(0, round(distance_m / sample_spacing_m) - 1)
    if npts == 0:
        return []

    raw_points = _WGS84_GEOD.npts(lon1, lat1, lon2, lat2, npts)
    step_m = distance_m / (npts + 1)
    return [(lat, lon, step_m * (i + 1)) for i, (lon, lat) in enumerate(raw_points)]


def build_sector_polygon(
    observer_latitude: float,
    observer_longitude: float,
    heading_deg: float,
    fov_deg: float,
    radius_km: float,
    arc_step_deg: float = 5.0,
) -> Polygon:
    """Konstruiše viewing sector kao Shapely `Polygon` (wedge/isječak) --
    Phase 9, koristi se za geometrijski intersect sa area feature-ima
    (rijeke, vodene površine, parkovi, nacionalni parkovi). Vidi
    docs/architecture-feasibility-review.md, Phase 9 status, za puno
    obrazloženje odluke (korisnik je eksplicitno odbacio centroid-only
    filtriranje u korist stvarnog geometrijskog intersect-a).

    NAMJERNO radi u sirovim WGS84 stepenima (lon, lat) — BEZ reprojekcije u
    metrički CRS. Na skali `radius_km <= Settings.radius_max_km` (30 km,
    sekcija 19/20 originalnog brifa) planarna distorzija stepena je
    zanemarljiva za jedinu upotrebu ovog poligona: topološki intersect
    ("da li se geometrije preklapaju"), NE mjerenje. Sve stvarne
    distance/bearing vrijednosti u projektu i dalje isključivo idu preko
    `pyproj.Geod` (`geodesic_distance_km`/`initial_bearing_deg` iznad) --
    ovaj poligon se nikad ne koristi za mjerenje.

    Koordinatni red: Shapely očekuje (x, y) = (longitude, latitude) — vidi
    app.services.osm_areas modul docstring za istu konvenciju na OSM strani.

    Konstrukcija: observer tačka + niz tačaka duž luka na `radius_km` (svaka
    dobijena preko `Geod.fwd()` -- geodesic destination point) od
    `heading - fov/2` do `heading + fov/2`, na koraku `arc_step_deg`
    (default 5° -- dovoljno gusto da luk topološki liči na kružni isječak
    na skali do 30 km, bez desetina nepotrebnih tačaka).

    Wrap-around (npr. heading=350°, fov=40° -> luk treba ići od 330° do
    390°) je BEZ posebne logike ovdje -- uglovi se namjerno NE normalizuju
    na [0, 360) prije generisanja niza, jer je `Geod.fwd()` potpuno ispravan
    i za azimute van tog opsega (interno ih tretira modulo 360). Ovo je
    drugačije od `angular_difference_deg`, koja poredi dva VEĆ GOTOVA ugla i
    zato mora eksplicitno hendlovati wrap-around."""
    radius_m = radius_km * 1000.0
    half_fov_deg = fov_deg / 2.0
    start_bearing_deg = heading_deg - half_fov_deg
    end_bearing_deg = heading_deg + half_fov_deg

    arc_points: list[tuple[float, float]] = []
    bearing_deg = start_bearing_deg
    while bearing_deg < end_bearing_deg:
        lon, lat, _ = _WGS84_GEOD.fwd(observer_longitude, observer_latitude, bearing_deg, radius_m)
        arc_points.append((lon, lat))
        bearing_deg += arc_step_deg

    # Uvijek uključi TAČAN krajnji bearing -- petlja gore može preskočiti
    # tačno end_bearing_deg zbog akumulacije float koraka, a sektor mora
    # imati oštru, tačnu ivicu na FOV granici.
    lon, lat, _ = _WGS84_GEOD.fwd(observer_longitude, observer_latitude, end_bearing_deg, radius_m)
    arc_points.append((lon, lat))

    ring_coords = [(observer_longitude, observer_latitude), *arc_points, (observer_longitude, observer_latitude)]
    return Polygon(ring_coords)


def select_candidates(
    observer_latitude: float,
    observer_longitude: float,
    heading_deg: float,
    fov_deg: float,
    radius_km: float,
    peaks: list[OSMPointFeature],
) -> list[PointCandidate]:
    """Filtrira sirove tačkaste OSM feature-e (peak/settlement/viewpoint,
    Phase 9) na one unutar `radius_km` I unutar viewing sektora
    (`heading_deg`/`fov_deg`), računa distance/bearing/angular-difference
    za svaki preživjeli, i sortira po relevantnosti.

    Rangiranje (obrazloženje, vidi i docs/architecture-feasibility-review.md,
    napomena o candidate ranking pragu u core/config.py): prvo po ugaonoj
    blizini heading-u (`angular_difference_deg` rastuće) -- feature koji je
    najbliže centru vidnog polja je najrelevantniji odgovor na "šta gledam",
    pa po `distance_km` rastuće kao tiebreaker za feature-e na približno
    istom pravcu. Elevation/prominence NAMJERNO ne ulazi u rangiranje ovdje
    -- isti princip kao odluka o elevation fusion-u, sekcija 6 arhitekture.

    NE ograničava broj rezultata -- capping na max-N kandidata je
    odgovornost pozivaoca (vidi `Settings.candidate_ranking_max_n`), jer
    zavisi od konteksta (trošak DEM/line-of-sight po kandidatu u Phase
    6-8), ne od same geometrije.
    """
    candidates: list[PointCandidate] = []

    for peak in peaks:
        distance_km = geodesic_distance_km(observer_latitude, observer_longitude, peak.latitude, peak.longitude)
        if distance_km > radius_km:
            continue

        bearing_deg = initial_bearing_deg(observer_latitude, observer_longitude, peak.latitude, peak.longitude)
        if not is_within_sector(bearing_deg, heading_deg, fov_deg):
            continue

        candidates.append(
            PointCandidate(
                osm_id=peak.osm_id,
                name=peak.name,
                latitude=peak.latitude,
                longitude=peak.longitude,
                ele_m=peak.ele_m,
                category=peak.category,
                distance_km=distance_km,
                bearing_deg=bearing_deg,
                angular_difference_deg=angular_difference_deg(bearing_deg, heading_deg),
            )
        )

    candidates.sort(key=lambda c: (c.angular_difference_deg, c.distance_km))
    return candidates
