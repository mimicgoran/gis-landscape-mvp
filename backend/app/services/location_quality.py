"""
Location quality servis -- Phase 7.

Implementira pragove i logiku već odobrene u Architecture & Feasibility
Review, sekcija 6 ("Predloženi pragovi" i "Location confidence"), plus dva
granična slučaja dogovorena tokom Phase 7 predloga (vidi
docs/architecture-feasibility-review.md, Phase 7 status, za puno
obrazloženje prije implementacije):

1. **DEM nedostupan** (van pokrivenosti ili mrežni problem) -> `confidence`
   je automatski "low", bez obzira na GPS horizontal accuracy. Nema
   pouzdane elevacije -> nema pouzdanog rezultata, bez izuzetka.
2. **`horizontal_accuracy_m is None`** (manual/desktop observer, Phase 2 --
   klik na mapu nema GPS accuracy koncept) -> tretira se kao "high", ne kao
   nepoznato/low. Manuelni klik NIJE GPS fix nepoznate preciznosti, već
   namjerno, tačno postavljena tačka bez GPS greške -- tretirati ga kao
   "low" bi neopravdano obezvrijedilo svaki desktop-development test (brief,
   tačka 38 -- "manual mode" mora ostati punopravan način rada, ne
   degradiran).

Vertical datum / phone-DEM fuzija (elevation_source "dem_phone_fusion" /
"dem_phone_disagreement") je namjerno van MVP scope-a -- sekcija 6 već
objašnjava zašto (nepouzdano poznat referentni sistem phone altitude-a bez
pristupa fizičkim uređajima za empirijsku provjeru). `selected_ground_elevation_m`
je zato u MVP-u uvijek jednak `dem_elevation_m`.
"""

from __future__ import annotations

from app.core.config import Settings
from app.models.location_quality import LocationConfidence, LocationQuality
from app.models.observer import ObserverInput


def classify_confidence(
    horizontal_accuracy_m: float | None,
    dem_available: bool,
    settings: Settings,
) -> LocationConfidence:
    """Vidi modul docstring za oba granična slučaja (DEM nedostupan,
    accuracy None) i architecture-feasibility-review.md sekciju 6 za
    obrazloženje samih brojčanih pragova."""
    if not dem_available:
        return "low"

    if horizontal_accuracy_m is None:
        return "high"

    if horizontal_accuracy_m <= settings.horizontal_accuracy_high_m:
        return "high"
    if horizontal_accuracy_m <= settings.horizontal_accuracy_medium_m:
        return "medium"
    return "low"


def compute_observer_elevation_m(
    selected_ground_elevation_m: float | None,
    eye_height_m: float,
) -> float | None:
    """`observer_elevation = terrain_elevation + observer_eye_height`
    (architecture-feasibility-review.md, sekcija 6). Vraća `None` ako
    terrain elevacija nije dostupna -- observer_elevation se ne može
    izmisliti bez ijednog izvora tla (Phase 8 line-of-sight mora ovo
    tretirati kao "analiza nije moguća za ovu lokaciju", ne pasti)."""
    if selected_ground_elevation_m is None:
        return None
    return selected_ground_elevation_m + eye_height_m


def build_location_quality(
    observer: ObserverInput,
    dem_elevation_m: float | None,
    settings: Settings,
) -> LocationQuality:
    """Sastavlja LocationQuality blok iz observer inputa i DEM elevacije
    (Phase 6 `ElevationService.get_elevation()`)."""
    dem_available = dem_elevation_m is not None

    return LocationQuality(
        horizontal_accuracy_m=observer.horizontal_accuracy_m,
        phone_altitude_m=observer.phone_altitude_m,
        phone_altitude_accuracy_m=observer.phone_altitude_accuracy_m,
        dem_elevation_m=dem_elevation_m,
        selected_ground_elevation_m=dem_elevation_m,
        elevation_source="dem" if dem_available else None,
        confidence=classify_confidence(observer.horizontal_accuracy_m, dem_available, settings),
    )
