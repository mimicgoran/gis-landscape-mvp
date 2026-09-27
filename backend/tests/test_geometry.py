"""
Testovi za geometrijske funkcije — Phase 3.

Posebna pažnja na wrap-around slučajeve (heading/bearing preko 0°/360°
granice), jer je to eksplicitan zahtjev iz brifa (tačka 24: "heading 359° +
feature na 1°") i najčešći izvor tihih grešaka u ovakvoj matematici.
"""

import pytest

from app.services.geometry import (
    angular_difference_deg,
    geodesic_distance_km,
    initial_bearing_deg,
    is_within_sector,
)


def test_geodesic_distance_km_zero_for_same_point():
    assert geodesic_distance_km(43.29, 20.82, 43.29, 20.82) == pytest.approx(0.0, abs=1e-6)


def test_geodesic_distance_km_known_value_along_equator():
    # 1 stepen geografske dužine na ekvatoru je poznata referentna vrijednost
    # (~111.32 km za WGS84) — dobar sanity-check da pyproj.Geod radi ispravno.
    distance = geodesic_distance_km(0.0, 0.0, 0.0, 1.0)
    assert distance == pytest.approx(111.32, abs=0.05)


def test_initial_bearing_due_north_is_zero():
    # Tačka direktno sjeverno (veći latitude, isti longitude) -> bearing ~0.
    bearing = initial_bearing_deg(43.0, 20.0, 44.0, 20.0)
    assert bearing == pytest.approx(0.0, abs=0.5)


def test_initial_bearing_due_east_is_ninety():
    # Na ekvatoru, tačka direktno istočno -> bearing ~90.
    bearing = initial_bearing_deg(0.0, 20.0, 0.0, 21.0)
    assert bearing == pytest.approx(90.0, abs=0.5)


def test_initial_bearing_is_normalized_to_0_360():
    # Tačka jugozapadno (manji lat, manji lon) -> bearing između 180 i 270,
    # nikad negativan.
    bearing = initial_bearing_deg(44.0, 21.0, 43.0, 20.0)
    assert 0.0 <= bearing < 360.0
    assert 180.0 < bearing < 270.0


def test_angular_difference_simple_case():
    assert angular_difference_deg(100.0, 80.0) == pytest.approx(20.0)


def test_angular_difference_wraparound_359_and_1():
    # Ovo je eksplicitni test slučaj iz brifa (tačka 24): heading 359° i
    # feature na 1° moraju dati razliku 2°, ne 358°.
    assert angular_difference_deg(1.0, 359.0) == pytest.approx(2.0)
    assert angular_difference_deg(359.0, 1.0) == pytest.approx(2.0)


def test_angular_difference_opposite_directions_is_180():
    assert angular_difference_deg(0.0, 180.0) == pytest.approx(180.0)


def test_angular_difference_is_symmetric_and_non_negative():
    for b, h in [(10.0, 350.0), (200.0, 5.0), (0.0, 0.0), (359.9, 0.1)]:
        diff_a = angular_difference_deg(b, h)
        diff_b = angular_difference_deg(h, b)
        assert diff_a == pytest.approx(diff_b)
        assert 0.0 <= diff_a <= 180.0


def test_is_within_sector_wraparound_heading_359_feature_1():
    # Heading 359°, FOV 10° (pola-ugao 5°) -> sektor pokriva otprilike 354°-4°.
    # Feature na 1° mora biti unutra.
    assert is_within_sector(bearing_deg=1.0, heading_deg=359.0, fov_deg=10.0) is True


def test_is_within_sector_outside_fov():
    assert is_within_sector(bearing_deg=90.0, heading_deg=0.0, fov_deg=45.0) is False


def test_is_within_sector_exact_boundary_is_included():
    # diff == fov/2 tačno -> mora biti True (<=, ne <) — vidi sekciju 8,
    # napomena o edge case-u sa granicom sektora.
    assert is_within_sector(bearing_deg=25.0, heading_deg=0.0, fov_deg=50.0) is True


def test_is_within_sector_just_outside_boundary():
    assert is_within_sector(bearing_deg=25.1, heading_deg=0.0, fov_deg=50.0) is False


def test_is_within_sector_center_direction_always_inside():
    assert is_within_sector(bearing_deg=180.0, heading_deg=180.0, fov_deg=20.0) is True


# --- select_candidates (Phase 5) -----------------------------------------


def _peak(osm_id, lat, lon, name=None, ele_m=None):
    from app.models.feature import OSMPeak

    return OSMPeak(osm_id=osm_id, name=name, latitude=lat, longitude=lon, ele_m=ele_m)


def test_select_candidates_filters_out_of_radius():
    from app.services.geometry import select_candidates

    # Opservera je na (0, 0). Peak A je ~55 km sjeverno (unutar radius=100),
    # peak B je ~220 km sjeverno (van radius=100).
    peaks = [_peak(1, 0.5, 0.0, name="A"), _peak(2, 2.0, 0.0, name="B")]
    candidates = select_candidates(0.0, 0.0, heading_deg=0.0, fov_deg=90.0, radius_km=100.0, peaks=peaks)

    assert [c.osm_id for c in candidates] == [1]


def test_select_candidates_filters_outside_fov():
    from app.services.geometry import select_candidates

    # Peak A je sjeverno (bearing ~0, unutar FOV 40 centriranog na heading 0).
    # Peak B je istočno (bearing ~90, van tog FOV).
    peaks = [_peak(1, 0.5, 0.0, name="North"), _peak(2, 0.0, 0.5, name="East")]
    candidates = select_candidates(0.0, 0.0, heading_deg=0.0, fov_deg=40.0, radius_km=100.0, peaks=peaks)

    assert [c.osm_id for c in candidates] == [1]


def test_select_candidates_wraparound_heading_359():
    from app.services.geometry import select_candidates

    # Observer gleda ka heading=359, FOV=10 (sektor ~354-4 stepeni). Peak je
    # neznatno istočno-sjeverno od observera -- bearing blizu 1 stepen.
    # Ovo je eksplicitan wrap-around test slučaj iz brifa (tačka 24/51).
    peaks = [_peak(1, 1.0, 0.02, name="Wraparound peak")]
    candidates = select_candidates(0.0, 0.0, heading_deg=359.0, fov_deg=10.0, radius_km=200.0, peaks=peaks)

    assert len(candidates) == 1
    assert candidates[0].angular_difference_deg < 5.0


def test_select_candidates_sorted_by_angular_difference_then_distance():
    from app.services.geometry import select_candidates

    # Sva tri su unutar širokog FOV=90 centriranog na sjever (heading=0):
    #   - "Far but centered": tačno na sjeveru (bearing ~0), daleko.
    #   - "Near but off-center": blago istočno (veći bearing), blizu.
    #   - "Off-center medium": između njih po uglu.
    # Očekujemo redoslijed po angular_difference_deg rastuće, PA po
    # distance_km kao tiebreaker.
    peaks = [
        _peak(1, 2.0, 0.0, name="Far but centered"),
        _peak(2, 0.3, 0.3, name="Near but off-center"),
        _peak(3, 1.0, 0.5, name="Off-center medium"),
    ]
    candidates = select_candidates(0.0, 0.0, heading_deg=0.0, fov_deg=90.0, radius_km=500.0, peaks=peaks)

    assert candidates[0].osm_id == 1  # najmanji angular_difference (skoro 0)
    # Preostala dva redoslijeda zavise od stvarnih uglova -- provjeravamo samo
    # da je lista sortirana neopadajuće po (angular_difference_deg, distance_km).
    keys = [(c.angular_difference_deg, c.distance_km) for c in candidates]
    assert keys == sorted(keys)


def test_select_candidates_empty_input_returns_empty_list():
    from app.services.geometry import select_candidates

    assert select_candidates(0.0, 0.0, heading_deg=0.0, fov_deg=45.0, radius_km=20.0, peaks=[]) == []
