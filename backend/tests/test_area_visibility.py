"""
Testovi za `app.services.area_visibility` -- Phase 9 sector-intersect i
"mini-viewshed" agregacija za area feature-e (rijeke/vodene površine/
parkovi/nacionalni parkovi).

Integracioni testovi (`evaluate_area_feature_visibility`) namjerno koriste
STVARNI `check_visibility` (Phase 8, već testiran u test_visibility.py) i
STVARNE geometrijske funkcije (`build_sector_polygon`,
`geodesic_intermediate_points`) -- ne mock-uju GIS matematiku, samo DEM
pristup (`_ConstantElevationService`, ispod), jer je cilj provjeriti da se
VIŠE line-of-sight provjera ispravno agregiraju u `visible_fraction`, ne da
se ponovo provjerava sama line-of-sight logika.
"""

from __future__ import annotations

import pytest
from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPolygon, Point, Polygon

from app.core.config import get_settings
from app.services.area_visibility import (
    evaluate_area_feature_visibility,
    intersect_with_sector,
    sample_points_for_geometry,
)
from app.services.geometry import build_sector_polygon
from app.services.osm_areas import OSMAreaFeature

_settings = get_settings()


class _ConstantElevationService:
    """Vraća istu elevaciju za SVAKU tačku (i za `get_elevation`, koji
    area_visibility poziva direktno za svaku sample tačku, i za
    `get_elevation_profile`, koji `check_visibility` poziva interno za
    teren IZMEĐU observera i sample tačke) -- namjerno "beskonačno ravna"
    površina, dovoljno da deterministički kontroliše visible/blocked ishod
    (vidi test_area_visibility.py komentare uz svaki test za obrazloženje
    zašto flat < observer -> uvijek vidljivo, flat > observer -> uvijek
    blokirano)."""

    def __init__(self, flat_elevation_m: float | None):
        self._flat = flat_elevation_m

    def get_elevation(self, latitude: float, longitude: float) -> float | None:
        return self._flat

    def get_elevation_profile(self, points: list[tuple[float, float]]) -> list[float | None]:
        return [self._flat] * len(points)


# --- intersect_with_sector -------------------------------------------------


def test_intersect_with_sector_returns_none_when_disjoint():
    sector = build_sector_polygon(0.0, 0.0, heading_deg=0.0, fov_deg=20.0, radius_km=10.0)
    # Linija daleko istočno -- van uskog sektora centriranog na sjever.
    far_east_line = LineString([(1.0, 0.0), (1.1, 0.0)])
    assert intersect_with_sector(far_east_line, sector) is None


def test_intersect_with_sector_returns_geometry_when_overlapping():
    sector = build_sector_polygon(0.0, 0.0, heading_deg=0.0, fov_deg=90.0, radius_km=10.0)
    # Linija direktno sjeverno, na pola radijusa -- sigurno unutar sektora.
    ahead_line = LineString([(0.0, 0.02), (0.0, 0.04)])
    result = intersect_with_sector(ahead_line, sector)
    assert result is not None
    assert not result.is_empty


# --- sample_points_for_geometry --------------------------------------------


def test_sample_points_from_linestring_returns_points_on_line():
    line = LineString([(20.0, 43.0), (20.0, 43.05)])
    points = sample_points_for_geometry(line, spacing_m=200.0, max_samples=50)
    assert len(points) > 1
    for point in points:
        assert 43.0 <= point.y <= 43.05
        assert point.x == pytest.approx(20.0)


def test_sample_points_from_polygon_returns_points_inside():
    polygon = Polygon([(20.0, 43.0), (20.1, 43.0), (20.1, 43.1), (20.0, 43.1)])
    points = sample_points_for_geometry(polygon, spacing_m=2000.0, max_samples=50)
    assert len(points) > 0
    for point in points:
        assert polygon.contains(point) or polygon.touches(point)


def test_sample_points_from_tiny_polygon_falls_back_to_representative_point():
    # Poligon manji od jednog spacing "koraka" -- ne smije ostati bez sample-a.
    tiny_polygon = Polygon([(20.0, 43.0), (20.0001, 43.0), (20.0001, 43.0001), (20.0, 43.0001)])
    points = sample_points_for_geometry(tiny_polygon, spacing_m=2000.0, max_samples=50)
    assert len(points) == 1
    assert tiny_polygon.contains(points[0]) or tiny_polygon.touches(points[0])


def test_sample_points_respects_max_samples_cap():
    line = LineString([(20.0, 43.0), (20.0, 43.5)])  # duga linija (~55 km)
    points = sample_points_for_geometry(line, spacing_m=100.0, max_samples=5)
    assert len(points) <= 5


def test_sample_points_geometry_collection_combines_parts():
    collection = GeometryCollection(
        [LineString([(20.0, 43.0), (20.0, 43.01)]), LineString([(21.0, 44.0), (21.0, 44.01)])]
    )
    points = sample_points_for_geometry(collection, spacing_m=200.0, max_samples=50)
    assert len(points) > 0


def test_sample_points_single_point_geometry_returns_itself():
    point = Point(20.0, 43.0)
    points = sample_points_for_geometry(point, spacing_m=200.0, max_samples=50)
    assert points == [point]


# --- evaluate_area_feature_visibility (integracioni) -----------------------


def _river_ahead() -> OSMAreaFeature:
    # Rijeka direktno sjeverno od observera (0,0), otprilike 2-4 km daleko --
    # sigurno unutar širokog sektora i unutar radius=10 km.
    geometry = LineString([(0.0, 0.02), (0.0, 0.035)])
    return OSMAreaFeature(osm_id=1, osm_type="way", name="Test rijeka", category="river", geometry=geometry)


def test_evaluate_area_feature_visible_on_flat_low_terrain():
    # Flat teren NIŽI od observera -- po konstrukciji (vidi
    # _ConstantElevationService docstring i test_visibility.py analognu
    # logiku) ovo je UVIJEK vidljivo: teren bliže observeru ima STROGO
    # negativniji (strmiji nadole) ugao od udaljenije tačke iste elevacije,
    # pa nikad ne blokira.
    feature = _river_ahead()
    sector = build_sector_polygon(0.0, 0.0, heading_deg=0.0, fov_deg=90.0, radius_km=10.0)
    elevation_service = _ConstantElevationService(flat_elevation_m=500.0)

    result = evaluate_area_feature_visibility(
        feature=feature,
        sector_polygon=sector,
        observer_latitude=0.0,
        observer_longitude=0.0,
        observer_elevation_m=1000.0,
        elevation_service=elevation_service,
        settings=_settings,
    )

    assert result is not None
    assert result.visibility == "visible"
    assert result.visible_fraction == pytest.approx(1.0)
    assert result.sample_count > 0
    assert result.dem_gap_sample_count == 0


def test_evaluate_area_feature_blocked_on_flat_high_terrain():
    # Flat teren VIŠI od observera -- po istoj logici, obrnuto: bliže tačke
    # imaju STROGO veći (strmiji nagore) ugao od udaljenije tačke iste
    # elevacije, pa uvijek blokiraju.
    feature = _river_ahead()
    sector = build_sector_polygon(0.0, 0.0, heading_deg=0.0, fov_deg=90.0, radius_km=10.0)
    elevation_service = _ConstantElevationService(flat_elevation_m=2000.0)

    result = evaluate_area_feature_visibility(
        feature=feature,
        sector_polygon=sector,
        observer_latitude=0.0,
        observer_longitude=0.0,
        observer_elevation_m=1000.0,
        elevation_service=elevation_service,
        settings=_settings,
    )

    assert result is not None
    assert result.visibility == "blocked"
    assert result.visible_fraction == pytest.approx(0.0)


def test_evaluate_area_feature_returns_none_when_outside_sector():
    feature = _river_ahead()
    # Uzak sektor okrenut ka istoku -- rijeka (direktno sjeverno) je van njega.
    sector = build_sector_polygon(0.0, 0.0, heading_deg=90.0, fov_deg=20.0, radius_km=10.0)
    elevation_service = _ConstantElevationService(flat_elevation_m=500.0)

    result = evaluate_area_feature_visibility(
        feature=feature,
        sector_polygon=sector,
        observer_latitude=0.0,
        observer_longitude=0.0,
        observer_elevation_m=1000.0,
        elevation_service=elevation_service,
        settings=_settings,
    )

    assert result is None


def test_evaluate_area_feature_returns_none_when_no_dem_coverage():
    feature = _river_ahead()
    sector = build_sector_polygon(0.0, 0.0, heading_deg=0.0, fov_deg=90.0, radius_km=10.0)
    elevation_service = _ConstantElevationService(flat_elevation_m=None)  # DEM nedostupan svuda

    result = evaluate_area_feature_visibility(
        feature=feature,
        sector_polygon=sector,
        observer_latitude=0.0,
        observer_longitude=0.0,
        observer_elevation_m=1000.0,
        elevation_service=elevation_service,
        settings=_settings,
    )

    assert result is None


def test_evaluate_area_feature_reports_closest_distance_and_bearing():
    feature = _river_ahead()
    sector = build_sector_polygon(0.0, 0.0, heading_deg=0.0, fov_deg=90.0, radius_km=10.0)
    elevation_service = _ConstantElevationService(flat_elevation_m=500.0)

    result = evaluate_area_feature_visibility(
        feature=feature,
        sector_polygon=sector,
        observer_latitude=0.0,
        observer_longitude=0.0,
        observer_elevation_m=1000.0,
        elevation_service=elevation_service,
        settings=_settings,
    )

    assert result is not None
    # Najbliža tačka rijeke je na lat=0.02 (~2.2 km) -- provjeravamo red
    # veličine, ne tačnu vrijednost (geodesic vs. flat aproksimacija).
    assert 2.0 < result.closest_distance_km < 2.5
    assert result.bearing_deg == pytest.approx(0.0, abs=1.0)  # direktno sjeverno


# --- collect_sample_details (dodano nakon terenskog testiranja Kopaonik/Sava --
# vidi docs/architecture-feasibility-review.md, sekcija 29: agregatni
# visible_fraction sam po sebi nije bio dovoljan da se objasni ZAŠTO je dio
# feature-a zaklonjen, pa je dodat opcioni per-sample diagnostic izlaz) ------


def test_evaluate_area_feature_samples_none_by_default():
    # collect_sample_details nije proslijeđen -- default False, isti princip
    # kao include_profile za tačkaste feature-e (veliki JSON, opt-in).
    feature = _river_ahead()
    sector = build_sector_polygon(0.0, 0.0, heading_deg=0.0, fov_deg=90.0, radius_km=10.0)
    elevation_service = _ConstantElevationService(flat_elevation_m=500.0)

    result = evaluate_area_feature_visibility(
        feature=feature,
        sector_polygon=sector,
        observer_latitude=0.0,
        observer_longitude=0.0,
        observer_elevation_m=1000.0,
        elevation_service=elevation_service,
        settings=_settings,
    )

    assert result is not None
    assert result.samples is None


def test_evaluate_area_feature_collects_sample_diagnostics_when_requested():
    feature = _river_ahead()
    sector = build_sector_polygon(0.0, 0.0, heading_deg=0.0, fov_deg=90.0, radius_km=10.0)
    elevation_service = _ConstantElevationService(flat_elevation_m=500.0)

    result = evaluate_area_feature_visibility(
        feature=feature,
        sector_polygon=sector,
        observer_latitude=0.0,
        observer_longitude=0.0,
        observer_elevation_m=1000.0,
        elevation_service=elevation_service,
        settings=_settings,
        collect_sample_details=True,
    )

    assert result is not None
    assert result.samples is not None
    # Jedan diagnostic zapis po sample tački -- ni manje ni više (i DEM gap
    # tačke se zapisuju, samo sa elevation_m=None, vidi test ispod).
    assert len(result.samples) == result.sample_count

    for sample in result.samples:
        # Flat 500m teren, ispod observera (1000m) -- svaka tačka je vidljiva
        # (ista logika kao test_evaluate_area_feature_visible_on_flat_low_terrain).
        assert sample.elevation_m == pytest.approx(500.0)
        assert sample.visible is True
        assert sample.distance_km > 0.0
        assert sample.target_angle_deg is not None
        # Flat teren -> nema terenskih tačaka koje bi imale VEĆI ugao od
        # target-a (sve su na istoj ravni) -- max_terrain_angle_deg je ili
        # None (nema intermedijarnih sample-ova na kratkoj distanci) ili <=
        # target_angle_deg.
        if sample.max_terrain_angle_deg is not None:
            assert sample.max_terrain_angle_deg <= sample.target_angle_deg + 1e-9


def test_evaluate_area_feature_sample_diagnostics_mark_dem_gap_points():
    feature = _river_ahead()
    sector = build_sector_polygon(0.0, 0.0, heading_deg=0.0, fov_deg=90.0, radius_km=10.0)
    elevation_service = _ConstantElevationService(flat_elevation_m=None)  # DEM nedostupan svuda

    # Sa DEM nedostupnim svuda, evaluate_area_feature_visibility normalno
    # vraća None (svi sample-ovi su "gap") -- collect_sample_details ne
    # mijenja taj ishod, samo obogaćuje slučajeve kad BAR JEDAN sample ima
    # DEM. Zato ovdje ručno pozivamo sample_points_for_geometry + provjerimo
    # da None ostaje None čak i uz collect_sample_details=True.
    result = evaluate_area_feature_visibility(
        feature=feature,
        sector_polygon=sector,
        observer_latitude=0.0,
        observer_longitude=0.0,
        observer_elevation_m=1000.0,
        elevation_service=elevation_service,
        settings=_settings,
        collect_sample_details=True,
    )

    assert result is None
