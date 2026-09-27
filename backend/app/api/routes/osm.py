"""
Privremeni dev endpointi za Phase 4/5 -- ručna/vizuelna potvrda da OSM
integracija i geometrijsko filtriranje rade, PRIJE nego što se poveže u
finalni /api/v1/analyze (vidi docs/architecture-feasibility-review.md,
sekcija 11 -- API design, i sekcija 13 -- MVP backlog). Nijedan od ovih
endpointa nije dio konačnog API dizajna -- biće zamijenjeni/obuhvaćeni sa
/api/v1/analyze kad Phase 6-9 dovrše pipeline (DEM, visibility, UI).
"""

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.models.feature import OSMPeak, PeakCandidate
from app.services.geometry import select_candidates
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
    """Phase 4 dev endpoint -- sirovi OSM peakovi u radijusu, BEZ ikakvog
    geometrijskog filtriranja (distance/bearing/FOV -- Phase 5)."""
    try:
        return await _overpass_service.fetch_peaks_in_radius(lat, lon, radius_km)
    except OverpassError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/osm/candidates")
async def get_osm_candidates(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Geografska širina observera."),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Geografska dužina observera."),
    heading_deg: float = Query(..., ge=0.0, lt=360.0, description="Pravac gledanja, 0 = sjever."),
    fov_deg: float = Query(..., gt=0.0, le=360.0, description="Field of view u stepenima."),
    radius_km: float = Query(..., gt=0.0, le=50.0, description="Radijus pretrage u km."),
) -> dict[str, object]:
    """Phase 5 dev endpoint -- OSM peakovi filtrirani po radius/FOV sektoru
    i rangirani po ugaonoj blizini heading-u (vidi
    app.services.geometry.select_candidates). `debug` blok prati oblik iz
    docs/architecture-feasibility-review.md, sekcija 11 (finalni
    /api/v1/analyze response)."""
    try:
        peaks = await _overpass_service.fetch_peaks_in_radius(lat, lon, radius_km)
    except OverpassError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    all_candidates: list[PeakCandidate] = select_candidates(
        observer_latitude=lat,
        observer_longitude=lon,
        heading_deg=heading_deg,
        fov_deg=fov_deg,
        radius_km=radius_km,
        peaks=peaks,
    )

    max_n = get_settings().candidate_ranking_max_n
    returned_candidates = all_candidates[:max_n]

    return {
        "candidates": returned_candidates,
        "debug": {
            "osm_candidates_total": len(peaks),
            "candidates_after_fov_radius_filter": len(all_candidates),
            "candidates_returned": len(returned_candidates),
        },
    }
