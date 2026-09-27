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
