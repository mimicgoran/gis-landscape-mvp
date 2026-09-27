"""
Privremeni dev endpoint za Phase 6 -- ručna potvrda da DEM servis radi
(vidi docs/architecture-feasibility-review.md, sekcija 11 -- API design, i
app/services/elevation.py za arhitekturno obrazloženje). Nije dio konačnog
API dizajna -- biće obuhvaćen kroz /api/v1/analyze kad Phase 7-8 povežu
observer/target elevation i line-of-sight na ovaj servis.
"""

from fastapi import APIRouter, Query

from app.core.config import get_settings
from app.services.elevation import ElevationService

router = APIRouter(tags=["elevation-dev"])

# Isti obrazac kao OverpassService u app/api/routes/osm.py -- jedan
# servis-instance po procesu.
_elevation_service = ElevationService(get_settings())


@router.get("/elevation/lookup")
def get_elevation_lookup(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Geografska širina."),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Geografska dužina."),
) -> dict[str, object]:
    """Phase 6 dev endpoint -- DEM elevacija na (lat, lon).

    Namjerno sync `def`, ne `async def`: `rasterio`/`httpx.Client` pozivi
    unutra su blokirajući, a FastAPI sync rute automatski izvršava u
    threadpool-u -- dovoljno za MVP saobraćaj, bez dodatne async
    komplikacije oko blokirajućih GIS biblioteka.

    `elevation_m: null` znači da DEM nije dostupan za tu tačku (van
    pokrivenosti, nodata piksel, ili privremeni mrežni problem pri
    preuzimanju tile-a) -- servis namjerno ne pravi razliku između ovih
    slučajeva (vidi ElevationService.get_elevation docstring).
    """
    elevation_m = _elevation_service.get_elevation(lat, lon)
    return {
        "latitude": lat,
        "longitude": lon,
        "elevation_m": elevation_m,
        "elevation_source": "dem" if elevation_m is not None else None,
    }
