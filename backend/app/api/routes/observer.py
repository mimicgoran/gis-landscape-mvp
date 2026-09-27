"""
Privremeni dev endpoint za Phase 7 -- ručna potvrda da observer elevation +
location quality logika radi (vidi docs/architecture-feasibility-review.md,
sekcija 11 za finalni `/api/v1/analyze` oblik, i Phase 7 status za
obrazloženje graničnih slučajeva). Nije dio konačnog API dizajna -- biće
obuhvaćen kroz `/api/v1/analyze` kad Phase 8-9 povežu ovo sa
line-of-sight/UI.
"""

from fastapi import APIRouter, Query

from app.core.config import get_settings
from app.models.observer import ObserverInput
from app.services.elevation import ElevationService
from app.services.location_quality import build_location_quality, compute_observer_elevation_m

router = APIRouter(tags=["observer-dev"])

# Isti obrazac kao ostali dev endpointi (osm.py, elevation.py) -- jedan
# servis-instance po procesu; ElevationService već ima sopstveni disk keš
# (Phase 6), pa dodatni in-memory keš ovdje nije potreban.
_elevation_service = ElevationService(get_settings())


@router.get("/observer/elevation")
def get_observer_elevation(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Geografska širina observera."),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Geografska dužina observera."),
    horizontal_accuracy_m: float | None = Query(
        default=None, ge=0.0, description="GPS horizontalna preciznost. Izostavi za manual/desktop observer."
    ),
    phone_altitude_m: float | None = Query(default=None, description="Sirova visina sa telefona, dijagnostika."),
    phone_altitude_accuracy_m: float | None = Query(default=None, ge=0.0),
) -> dict[str, object]:
    """Phase 7 dev endpoint -- pregled `observer`/`location_quality` blokova
    iz sekcije 11 arhitekture, prije nego što se povežu u finalni
    `/api/v1/analyze` (Phase 9). Kombinuje Phase 6 `ElevationService` sa
    Phase 7 `location_quality` servisom."""
    settings = get_settings()
    observer = ObserverInput(
        latitude=lat,
        longitude=lon,
        horizontal_accuracy_m=horizontal_accuracy_m,
        phone_altitude_m=phone_altitude_m,
        phone_altitude_accuracy_m=phone_altitude_accuracy_m,
    )

    dem_elevation_m = _elevation_service.get_elevation(lat, lon)
    location_quality = build_location_quality(observer, dem_elevation_m, settings)
    observer_elevation_m = compute_observer_elevation_m(
        location_quality.selected_ground_elevation_m, settings.observer_eye_height_m
    )

    return {
        "observer": {
            "latitude": lat,
            "longitude": lon,
            "dem_elevation_m": dem_elevation_m,
            "observer_eye_height_m": settings.observer_eye_height_m,
            "observer_elevation_m": observer_elevation_m,
        },
        "location_quality": location_quality,
    }
