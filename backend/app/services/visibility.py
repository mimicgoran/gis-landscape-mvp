"""
Line-of-sight (visibility) servis -- Phase 8.

Implementira algoritam definisan u Architecture & Feasibility Review,
sekcija 9, plus implementacione detalje dogovorene prije koda (vidi Phase 8
status u istom dokumentu):

- Batch DEM sampling duž linije preko `ElevationService.get_elevation_profile()`
  (Phase 6) -- jedan `rasterio` open po tile-u, ne po tački.
- Sample tačke preko `geometry.geodesic_intermediate_points()` (Phase 3
  modul), na `Settings.line_of_sight_sample_spacing_m` razmaku (~30 m,
  jednako DEM rezoluciji -- sekcija 9, korak 2).
- Granični slučaj (dogovoren prije implementacije): terenska tačka blokira
  target samo ako je njen elevation angle STROGO veći od target ugla
  (`>`, ne `>=`) -- tačka čiji je ugao jednak target uglu dodiruje liniju
  posmatranja tačno na nivou cilja, što nije stvarna prepreka ispred njega.
- Ugaona tolerancija (dodano Phase 10, nakon Sava/Orašac istrage -- vidi
  docs/architecture-feasibility-review.md, sekcija 31): terenska tačka se
  poredi ne sa golim target uglom, nego sa `target_angle_deg + tolerance`,
  gdje je `tolerance = atan(Settings.dem_vertical_accuracy_m / distance_m)`
  IZRAČUNATO ZA TU KONKRETNU terensku tačku (ne za target). Razlog: DEM
  vrijednost ima dokumentovanu vertikalnu nesigurnost od par metara
  (sekcija 26); na kratkim distancama (stotinjak metara) ta nesigurnost
  odgovara ugaonoj grešci reda veličine 1°+, uporedivoj sa samim target
  uglom -- bez tolerancije, jedan "bučan" 30 m DEM piksel (rezidualna
  vegetacija u Copernicus DSM-izvedenom DEM-u, ili sitna stvarna
  neravnina terena) lažno blokira cilj koji bi golim okom očigledno bio
  vidljiv. Tolerancija je namjerno primijenjena SAMO na terensku tačku, ne
  i na target ugao (pojednostavljenje -- dovoljno za MVP, ne pretenduje da
  modeluje kombinovanu nesigurnost oba ugla).
- "DEM gap" (terenska tačka bez dostupne elevacije, npr. rijedak nodata
  slučaj usred inače pokrivenog tile-a) se NE tretira kao blokada niti kao
  fatalna greška -- tačka se jednostavno preskače u max-angle računu, a
  `dem_gap=True` transparentno signalizira pozivaocu da je rezultat
  zasnovan na nepotpunom terenskom profilu (data-quality awareness, isti
  princip kao location_quality iz Phase 7).

Earth curvature/refrakcija OSTAJE isključena (`Settings.enable_earth_curvature_correction`
= False) -- eksplicitno Future/Phase 2 stavka (brief, tačke 30 i 53), NIJE
implementirana ovdje. Funkcije ispod su ipak strukturirane tako da bi
korekcija ušla kao izolovan dodatni term u `_elevation_angle_deg`, bez
diranja ostatka algoritma, kad/ako se ta odluka donese.
"""

from __future__ import annotations

import math
from typing import Literal

from app.core.config import Settings
from app.models.feature import ProfilePoint
from app.services.elevation import ElevationService
from app.services.geometry import geodesic_intermediate_points


class VisibilityResult:
    """Rezultat `check_visibility()` poziva. Obična klasa (ne Pydantic) --
    ovo je interni servisni rezultat, ne API response oblik (taj je
    `AnalyzedFeature`, sastavljen od pozivaoca u app/api/routes/analyze.py)."""

    __slots__ = ("visible", "target_angle_deg", "max_terrain_angle_deg", "profile", "dem_gap")

    def __init__(
        self,
        visible: bool,
        target_angle_deg: float,
        max_terrain_angle_deg: float | None,
        profile: list[ProfilePoint],
        dem_gap: bool,
    ) -> None:
        self.visible = visible
        self.target_angle_deg = target_angle_deg
        self.max_terrain_angle_deg = max_terrain_angle_deg
        self.profile = profile
        self.dem_gap = dem_gap


def _elevation_angle_deg(elevation_m: float, observer_elevation_m: float, distance_m: float) -> float:
    """`angle = atan2(elevation - observer_elevation, distance)` (sekcija 9,
    koraci 4-5), u stepenima radi čitljivijeg debug outputa."""
    return math.degrees(math.atan2(elevation_m - observer_elevation_m, distance_m))


def _angular_tolerance_deg(distance_m: float, vertical_accuracy_m: float) -> float:
    """Pretvara DEM vertikalnu nesigurnost (`vertical_accuracy_m`, tipično
    par metara -- Settings.dem_vertical_accuracy_m) u ugaonu toleranciju NA
    DATOJ DISTANCI: `atan(vertical_accuracy_m / distance_m)`. Namjerno
    distance-scaled, ne fiksni broj stepeni -- ista vertikalna greška od
    npr. 2 m znači ~3.8° na 30 m ali samo ~0.004° na 30 km, što je tačno
    ponašanje koje želimo (blaga tolerancija tik uz posmatrača gdje je
    algoritam najosjetljiviji na DEM šum, zanemarljiva na velikim
    distancama gdje već postoji dovoljno terenskih tačaka da usrednje
    slučajni šum). Vidi modul docstring i
    docs/architecture-feasibility-review.md, sekcija 31, za empirijsko
    obrazloženje (Sava/Orašac test slučaj)."""
    if distance_m <= 0:
        return 90.0
    return math.degrees(math.atan2(vertical_accuracy_m, distance_m))


def check_visibility(
    observer_latitude: float,
    observer_longitude: float,
    observer_elevation_m: float,
    target_latitude: float,
    target_longitude: float,
    target_elevation_m: float,
    target_distance_m: float,
    elevation_service: ElevationService,
    settings: Settings,
) -> VisibilityResult:
    """Da li je target vidljiv sa observera, po algoritmu iz sekcije 9. Vidi
    modul docstring za granični slučaj kod poređenja uglova i za "DEM gap"
    hendlovanje."""
    target_angle_deg = _elevation_angle_deg(target_elevation_m, observer_elevation_m, target_distance_m)

    intermediate = geodesic_intermediate_points(
        observer_latitude,
        observer_longitude,
        target_latitude,
        target_longitude,
        settings.line_of_sight_sample_spacing_m,
    )

    profile: list[ProfilePoint] = [ProfilePoint(distance_m=0.0, elevation_m=observer_elevation_m)]

    if not intermediate:
        # Kraća distanca od jednog sample intervala -- nema terena između
        # observera i targeta koji bi mogao blokirati (sekcija: vidi
        # geodesic_intermediate_points docstring).
        profile.append(ProfilePoint(distance_m=target_distance_m, elevation_m=target_elevation_m))
        return VisibilityResult(
            visible=True, target_angle_deg=target_angle_deg, max_terrain_angle_deg=None, profile=profile, dem_gap=False
        )

    terrain_elevations = elevation_service.get_elevation_profile([(lat, lon) for lat, lon, _ in intermediate])

    max_terrain_angle_deg: float | None = None
    dem_gap = False
    visible = True

    for (_, _, distance_m), terrain_elevation_m in zip(intermediate, terrain_elevations):
        if terrain_elevation_m is None:
            dem_gap = True
            profile.append(ProfilePoint(distance_m=distance_m, elevation_m=None))
            continue

        angle_deg = _elevation_angle_deg(terrain_elevation_m, observer_elevation_m, distance_m)
        profile.append(ProfilePoint(distance_m=distance_m, elevation_m=terrain_elevation_m))

        if max_terrain_angle_deg is None or angle_deg > max_terrain_angle_deg:
            max_terrain_angle_deg = angle_deg

        tolerance_deg = _angular_tolerance_deg(distance_m, settings.dem_vertical_accuracy_m)
        if angle_deg > target_angle_deg + tolerance_deg:
            visible = False

    profile.append(ProfilePoint(distance_m=target_distance_m, elevation_m=target_elevation_m))

    return VisibilityResult(
        visible=visible,
        target_angle_deg=target_angle_deg,
        max_terrain_angle_deg=max_terrain_angle_deg,
        profile=profile,
        dem_gap=dem_gap,
    )


def resolve_target_elevation(
    candidate_ele_m: float | None,
    target_latitude: float,
    target_longitude: float,
    elevation_service: ElevationService,
    settings: Settings,
) -> tuple[float | None, Literal["osm", "dem"] | None, float | None]:
    """Određuje target elevation po prioritetu iz sekcije 9, korak 8: OSM
    `ele` kad postoji (obično ručno unesena, precizna izmjerena visina
    vrha), DEM kao fallback. Ako oba postoje i razlikuju se za više od
    `Settings.target_elevation_discrepancy_threshold_m`, i dalje se koristi
    OSM `ele` (isti prioritet) -- razlika se samo bilježi, ne mijenja izbor.

    Vraća `(elevation_m, elevation_source, elevation_discrepancy_m)`. Prva
    dva su `None` samo u rijetkom slučaju da NI OSM `ele` NI DEM nisu
    dostupni (target van DEM pokrivenosti i bez OSM ele tag-a)."""
    dem_elevation_m = elevation_service.get_elevation(target_latitude, target_longitude)

    if candidate_ele_m is not None:
        discrepancy_m: float | None = None
        if dem_elevation_m is not None:
            diff = abs(candidate_ele_m - dem_elevation_m)
            if diff > settings.target_elevation_discrepancy_threshold_m:
                discrepancy_m = diff
        return candidate_ele_m, "osm", discrepancy_m

    if dem_elevation_m is not None:
        return dem_elevation_m, "dem", None

    return None, None, None
