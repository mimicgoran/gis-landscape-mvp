"""
Sector-intersect i "mini-viewshed" visibility agregacija za AREA feature-e
(rijeke, vodene površine, parkovi, nacionalni parkovi -- Phase 9).

Razlika naspram `app.services.visibility` (Phase 8, tačkasti feature-i):
tamo je JEDAN target = JEDNA line-of-sight provjera. Ovdje feature ima
STVARNU geometriju (linija/poligon), pa se ISTA `check_visibility()`
funkcija (ne novi algoritam) poziva VIŠE PUTA -- jednom po sample tački duž
DIJELA geometrije koji stvarno upada u korisnikov viewing sector (nakon
Shapely intersect-a), a rezultati se agregiraju u "koliki dio ovog
feature-a je vidljiv" (`visible_fraction`).

Ovo je eksplicitna korisnička odluka (vidi Phase 9 status u
docs/architecture-feasibility-review.md) -- "mini-viewshed po feature-u",
namjerno demandingnija opcija od jedne reprezentativne tačke, ali
OGRANIČENA (fiksni mali broj sample-ova po feature-u, vidi
`Settings.area_feature_max_samples_per_feature`) -- NIJE puni raster
viewshed (brief, tačka 52 -- eksplicitno isključeno iz MVP-a).

Koordinatna konvencija: sve Shapely geometrije ovdje su u (longitude,
latitude) redu (vidi app.services.osm_areas modul docstring). Sve stvarne
distance/bearing/DEM lookup pozive i dalje rade postojeće funkcije koje
očekuju (lat, lon) -- konverzija se radi eksplicitno na granici ovog modula
(`point.y` = latitude, `point.x` = longitude).
"""

from __future__ import annotations

from typing import Literal

from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points

from app.core.config import Settings
from app.services.elevation import ElevationService
from app.services.geometry import geodesic_distance_km, initial_bearing_deg
from app.services.osm_areas import OSMAreaFeature
from app.services.visibility import check_visibility

# Gruba pretvorba stepen<->metar korišćena SAMO za odlučivanje KOLIKO sample
# tačaka generisati duž/unutar presječene geometrije (Shapely radi u
# stepenima -- isti princip kao geometry.build_sector_polygon). Zasnovano na
# geografskoj širini regiona projekta (Balkan, ~43-45°N) -- NIJE opštevažeća
# konstanta, ali za obim ovog MVP-a (jedan region, radius <= 30 km) dovoljno
# tačna aproksimacija. Stvarne distance do konkretnih sample tačaka i dalje
# se računaju preko `pyproj.Geod` (geodesic_distance_km) -- ovo utiče samo
# na RAZMAK sample-ova, ne na tačnost pojedinačnog rezultata.
_METERS_PER_DEGREE_LATITUDE = 111_320.0


class AreaVisibilityResult:
    """Rezultat agregirane visibility provjere za jedan area feature. Obična
    klasa (ne Pydantic) -- interni servisni rezultat, isti princip kao
    `app.services.visibility.VisibilityResult`. Finalni API oblik je
    `AnalyzedAreaFeature` (app/models/feature.py), sastavljen od pozivaoca."""

    __slots__ = (
        "closest_distance_km",
        "bearing_deg",
        "sample_count",
        "visible_sample_count",
        "dem_gap_sample_count",
        "visible_fraction",
        "visibility",
    )

    def __init__(
        self,
        closest_distance_km: float,
        bearing_deg: float,
        sample_count: int,
        visible_sample_count: int,
        dem_gap_sample_count: int,
    ) -> None:
        self.closest_distance_km = closest_distance_km
        self.bearing_deg = bearing_deg
        self.sample_count = sample_count
        self.visible_sample_count = visible_sample_count
        self.dem_gap_sample_count = dem_gap_sample_count
        evaluated_count = sample_count - dem_gap_sample_count
        self.visible_fraction = (visible_sample_count / evaluated_count) if evaluated_count > 0 else 0.0
        self.visibility: Literal["visible", "partially_visible", "blocked"] = _classify(self.visible_fraction)


def _classify(visible_fraction: float) -> Literal["visible", "partially_visible", "blocked"]:
    if visible_fraction <= 0.0:
        return "blocked"
    if visible_fraction >= 1.0:
        return "visible"
    return "partially_visible"


def intersect_with_sector(feature_geometry: BaseGeometry, sector_polygon: Polygon) -> BaseGeometry | None:
    """Geometrijski intersect feature-a sa viewing-sector poligonom. Vraća
    `None` ako se uopšte ne preklapaju (feature van vidnog polja -- treba ga
    u potpunosti izostaviti iz rezultata) -- ovo je namjerna ZAMJENA za
    prvobitno predloženi (i eksplicitno odbačeni) "centroid unutar sektora"
    filter, vidi Phase 9 status."""
    intersection = feature_geometry.intersection(sector_polygon)
    if intersection.is_empty:
        return None
    return intersection


def _degrees_spacing_for_meters(spacing_m: float) -> float:
    return spacing_m / _METERS_PER_DEGREE_LATITUDE


def _cap_samples(points: list[Point], max_samples: int) -> list[Point]:
    """Ravnomjerno prorijeđuje listu sample tačaka na najviše `max_samples`
    (uzima svaku k-tu, ne samo prvih N -- bitno da prorijeđeni uzorak i
    dalje predstavlja CIJELU presječenu geometriju, ne samo njen početak)."""
    if max_samples <= 0 or len(points) <= max_samples:
        return points
    step = len(points) / max_samples
    return [points[int(i * step)] for i in range(max_samples)]


def _sample_points_from_line(geometry: LineString | MultiLineString, spacing_m: float, max_samples: int) -> list[Point]:
    lines = list(geometry.geoms) if isinstance(geometry, MultiLineString) else [geometry]
    spacing_deg = _degrees_spacing_for_meters(spacing_m)

    points: list[Point] = []
    for line in lines:
        if line.length == 0:
            points.append(Point(line.coords[0]))
            continue
        num_segments = max(1, round(line.length / spacing_deg))
        for i in range(num_segments + 1):
            points.append(line.interpolate(i / num_segments, normalized=True))

    return _cap_samples(points, max_samples)


def _sample_points_from_polygon(geometry: Polygon | MultiPolygon, spacing_m: float, max_samples: int) -> list[Point]:
    """Grid sampling UNUTAR presječenog poligona (ne duž njegove konture) --
    za razliku od linije, kontura presječenog poligona dijelom prati IVICE
    SAMOG SEKTORA (radijalne linije/luk), ne stvarnu granicu feature-a, pa
    sampling konture ne bi bio reprezentativan. Grid TAČKE su ipak sve
    unutar stvarne presječene površine (real geometrija ∩ sektor), pa je
    ovo ispravno bez obzira što dio konture nije "stvaran"."""
    polygons = list(geometry.geoms) if isinstance(geometry, MultiPolygon) else [geometry]
    spacing_deg = _degrees_spacing_for_meters(spacing_m)

    points: list[Point] = []
    if spacing_deg > 0:
        for polygon in polygons:
            min_x, min_y, max_x, max_y = polygon.bounds
            x = min_x
            while x <= max_x:
                y = min_y
                while y <= max_y:
                    candidate = Point(x, y)
                    if polygon.contains(candidate):
                        points.append(candidate)
                    y += spacing_deg
                x += spacing_deg

    if not points:
        # Presječeni poligon je manji od jednog spacing "koraka" (npr. uzak
        # trak parka/jezera koji sektor tek zahvata ivicom) -- koristi
        # representative_point() umjesto da feature ostane bez ijednog
        # sample-a i time lažno ispadne iz rezultata.
        points = [geometry.representative_point()]

    return _cap_samples(points, max_samples)


def sample_points_for_geometry(geometry: BaseGeometry, spacing_m: float, max_samples: int) -> list[Point]:
    """Generiše sample tačke za PRESJEČENU geometriju (rezultat
    `intersect_with_sector`), tip-specifično: duž linije za LineString/
    MultiLineString, kao grid unutar poligona za Polygon/MultiPolygon.
    Mješoviti `GeometryCollection` (moguć rezultat intersect-a kad sektor
    siječe feature na više nepovezanih dijelova/tipova -- rijedak edge case)
    se rastavlja po komponentama i rezultati spajaju."""
    if geometry.geom_type == "GeometryCollection":
        points: list[Point] = []
        for part in geometry.geoms:
            if not part.is_empty:
                points.extend(sample_points_for_geometry(part, spacing_m, max_samples))
        return _cap_samples(points, max_samples)

    if isinstance(geometry, (LineString, MultiLineString)):
        return _sample_points_from_line(geometry, spacing_m, max_samples)
    if isinstance(geometry, (Polygon, MultiPolygon)):
        return _sample_points_from_polygon(geometry, spacing_m, max_samples)
    if isinstance(geometry, Point):
        return [geometry]
    return []


def evaluate_area_feature_visibility(
    feature: OSMAreaFeature,
    sector_polygon: Polygon,
    observer_latitude: float,
    observer_longitude: float,
    observer_elevation_m: float,
    elevation_service: ElevationService,
    settings: Settings,
) -> AreaVisibilityResult | None:
    """Puna Phase 9 obrada jednog area feature-a: sector intersect -> sample
    tačke -> DEM elevation + `check_visibility()` po sample tački (ISTA
    funkcija kao za tačkaste feature-e, Phase 8 -- ne novi algoritam) ->
    agregat.

    Vraća `None` u dva slučaja, oba tretirana kao "feature se izostavlja iz
    rezultata" od strane pozivaoca:
    1. feature uopšte ne upada u sektor (intersect prazan);
    2. NIJEDNA sample tačka nema dostupan DEM (sav teren van pokrivenosti) --
       isti princip kao `candidates_skipped_no_elevation` za tačkaste
       feature-e (Phase 8) -- ne izmišljamo elevaciju, radije preskačemo."""
    intersection = intersect_with_sector(feature.geometry, sector_polygon)
    if intersection is None:
        return None

    observer_point = Point(observer_longitude, observer_latitude)
    # nearest_points(g1, g2) vraća (tačka_na_g1, tačka_na_g2) -- g1 je
    # observer_point (trivijalno on sam), pa je DRUGI element (tačka na
    # feature geometriji) ono što nas zanima. Zamjena redosleda ovdje bi
    # tiho vratila closest_distance_km=0 za SVAKI feature -- namjerno
    # eksplicitan komentar jer je ovo lako pobrkati.
    _, nearest_on_feature = nearest_points(observer_point, feature.geometry)
    closest_distance_km = geodesic_distance_km(
        observer_latitude, observer_longitude, nearest_on_feature.y, nearest_on_feature.x
    )
    bearing_deg = initial_bearing_deg(
        observer_latitude, observer_longitude, nearest_on_feature.y, nearest_on_feature.x
    )

    sample_points = sample_points_for_geometry(
        intersection, settings.area_feature_sample_spacing_m, settings.area_feature_max_samples_per_feature
    )

    visible_count = 0
    dem_gap_count = 0

    for point in sample_points:
        target_latitude, target_longitude = point.y, point.x
        target_elevation_m = elevation_service.get_elevation(target_latitude, target_longitude)
        if target_elevation_m is None:
            dem_gap_count += 1
            continue

        target_distance_m = (
            geodesic_distance_km(observer_latitude, observer_longitude, target_latitude, target_longitude) * 1000.0
        )

        result = check_visibility(
            observer_latitude=observer_latitude,
            observer_longitude=observer_longitude,
            observer_elevation_m=observer_elevation_m,
            target_latitude=target_latitude,
            target_longitude=target_longitude,
            target_elevation_m=target_elevation_m,
            target_distance_m=target_distance_m,
            elevation_service=elevation_service,
            settings=settings,
        )
        if result.visible:
            visible_count += 1

    sample_count = len(sample_points)
    if sample_count == 0 or sample_count == dem_gap_count:
        return None

    return AreaVisibilityResult(
        closest_distance_km=closest_distance_km,
        bearing_deg=bearing_deg,
        sample_count=sample_count,
        visible_sample_count=visible_count,
        dem_gap_sample_count=dem_gap_count,
    )
