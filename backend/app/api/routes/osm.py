"""
Privremen dev endpoint za Phase 4 -- vraća sirove OSM natural=peak objekte u
radijusu, BEZ ikakvog geometrijskog filtriranja (distance/bearing/FOV
dolaze u Phase 5) ili DEM/visibility obrade (Phase 6-8).

Svrha: ručna/vizuelna potvrda da Overpass integracija stvarno radi (npr. na
Kopaoniku) prije nego što se poveže u finalni /api/v1/analyze (vidi
docs/architecture-feasibility-review.md, sekcija 11 -- API design, i
sekcija 13 -- MVP backlog, red "Phase 4"). Ovaj endpoint NIJE dio konačnog
API dizajna iz sekcije 11 -- biće zamijenjen/obuhvaćen sa /api/v1/analyze
kad Phase 5-9 poveže cijeli pipeline, ne ostaje kao trajni javni endpoint.
"""

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.models.feature import OSMPeak
from app.services.osm import OverpassError, OverpassService

router = APIRouter(tags=["osm-dev"])

# Isti obrazac kao arcgis_token.py -- jedan servis-instance po procesu, keš
# živi u njemu.
_overpass_service = OverpassService(get_settings())


@router.get("/osm/peaks")
async def get_osm_peaks(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Geografska širina centra pretrage."),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Geografska dužina centra pretrage."),
    radius_km: float = Query(..., gt=0.0, le=50.0, description="Radijus pretrage u km."),
) -> list[OSMPeak]:
    try:
        return await _overpass_service.fetch_peaks_in_radius(lat, lon, radius_km)
    except OverpassError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
