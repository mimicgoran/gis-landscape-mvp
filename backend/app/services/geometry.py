"""
Geometrijske GIS funkcije: geodesic distance, initial bearing, angular
difference, sector inclusion.

Sve računice koriste WGS84 elipsoid preko `pyproj.Geod` (ne haversine na
sferi, ne ravnu Euclidean distancu) — tačnije na većim udaljenostima, vidi
docs/architecture-feasibility-review.md, sekcija 8/24.

Wrap-around (heading/bearing preko 0°/360° granice, npr. heading 359° i
feature na 1°) je najčešći izvor bugova u ovakvoj matematici — svaka
funkcija ovdje je eksplicitno testirana na te slučajeve (vidi
backend/tests/test_geometry.py).
"""

from __future__ import annotations

from pyproj import Geod

from app.models.feature import OSMPeak, PeakCandidate

# Jedan Geod objekat po procesu — inicijalizacija nije besplatna, a instanca
# je immutable/thread-safe za `.inv()` pozive.
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


def select_candidates(
    observer_latitude: float,
    observer_longitude: float,
    heading_deg: float,
    fov_deg: float,
    radius_km: float,
    peaks: list[OSMPeak],
) -> list[PeakCandidate]:
    """Filtrira sirove OSM peakove na one unutar `radius_km` I unutar
    viewing sektora (`heading_deg`/`fov_deg`), računa distance/bearing/
    angular-difference za svaki preživjeli, i sortira po relevantnosti.

    Rangiranje (obrazloženje, vidi i docs/architecture-feasibility-review.md,
    napomena o candidate ranking pragu u core/config.py): prvo po ugaonoj
    blizini heading-u (`angular_difference_deg` rastuće) -- vrh koji je
    najbliže centru vidnog polja je najrelevantniji odgovor na "šta gledam",
    pa po `distance_km` rastuće kao tiebreaker za vrhove na približno istom
    pravcu. Elevation/prominence NAMJERNO ne ulazi u rangiranje ovdje --
    DEM (Phase 6) i pouzdana OSM `ele` pokrivenost nisu još dostupni za sve
    kandidate u ovoj fazi, pa bi uključivanje nepotpunog signala u
    rangiranje bilo neopravdana "smart" heuristika (isti princip kao odluka
    o elevation fusion-u, sekcija 6 arhitekture).

    NE ograničava broj rezultata -- capping na max-N kandidata je
    odgovornost pozivaoca (vidi `Settings.candidate_ranking_max_n`), jer
    zavisi od konteksta (trošak DEM/line-of-sight po kandidatu u Phase
    6-8), ne od same geometrije.
    """
    candidates: list[PeakCandidate] = []

    for peak in peaks:
        distance_km = geodesic_distance_km(observer_latitude, observer_longitude, peak.latitude, peak.longitude)
        if distance_km > radius_km:
            continue

        bearing_deg = initial_bearing_deg(observer_latitude, observer_longitude, peak.latitude, peak.longitude)
        if not is_within_sector(bearing_deg, heading_deg, fov_deg):
            continue

        candidates.append(
            PeakCandidate(
                osm_id=peak.osm_id,
                name=peak.name,
                latitude=peak.latitude,
                longitude=peak.longitude,
                ele_m=peak.ele_m,
                distance_km=distance_km,
                bearing_deg=bearing_deg,
                angular_difference_deg=angular_difference_deg(bearing_deg, heading_deg),
            )
        )

    candidates.sort(key=lambda c: (c.angular_difference_deg, c.distance_km))
    return candidates
