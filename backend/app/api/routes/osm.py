"""
Privremeni dev endpointi za Phase 4/5/9 -- ručna/vizuelna potvrda da OSM
integracija i geometrijsko filtriranje rade, PRIJE nego što se poveže u
finalni /api/v1/analyze (vidi docs/architecture-feasibility-review.md,
sekcija 11 -- API design). Nijedan od ovih endpointa nije dio konačnog API
dizajna -- biće zamijenjeni/obuhvaćeni sa /api/v1/analyze.

Phase 9 dodaje area-feature endpoint (`/osm/areas`) -- vraća sirovu
geometriju (GeoJSON-oblik preko `shapely.geometry.mapping`) BEZ sector
intersect-a/visibility obrade, isključivo radi provjere da Overpass upit i
parsing (way/relation -> Shapely) rade ispravno PRIJE nego što se doda
sledeći, skuplji sloj (sector intersect + mini-viewshed sampling,
`app.services.area_visibility`) -- ovo je NAMJERNO prva stvar za ručnu
verifikaciju (vidi napomenu u app.services.osm_areas modul docstring o
neprovjerenom Overpass relation-geometry ponašanju)."""

from shapely.geometry import mapping

from fastapi import APIRouter, HTTPException, Query

from app.api.routes.arcgis_token import get_arcgis_auth_service
from app.core.config import get_settings
from app.models.feature import OSMPointFeature, PointCandidate
from app.services.arcgis_places import ArcGISPlacesError, ArcGISPlacesService
from app.services.geometry import select_candidates
from app.services.osm_areas import OverpassAreaError, OverpassAreaService

router = APIRouter(tags=["osm-dev"])

# Isti obrazac kao arcgis_token.py -- jedan servis-instance po procesu, keš
# živi u njemu. Tačkasti feature-i (peak/settlement/viewpoint) dolaze sa
# ArcGIS World Geocoding Service (Phase 15 zamjena za Overpass -- vidi
# app.services.arcgis_places modul docstring za puno obrazloženje); area
# feature-i (rijeke/parkovi/vodene površine/nacionalni parkovi) OSTAJU na
# Overpass-u jer ArcGIS geocoding ne vraća geometriju.
_point_features_service = ArcGISPlacesService(get_settings(), get_arcgis_auth_service())
_overpass_area_service = OverpassAreaService(get_settings())


@router.get("/osm/points")
async def get_osm_points(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Geografska širina centra pretrage."),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Geografska dužina centra pretrage."),
    radius_km: float = Query(..., gt=0.0, le=50.0, description="Radijus pretrage u km."),
) -> list[OSMPointFeature]:
    """Phase 4/9 dev endpoint -- sirovi tačkasti OSM feature-i (peak/
    settlement/viewpoint) u radijusu, BEZ ikakvog geometrijskog filtriranja
    (distance/bearing/FOV -- Phase 5). Preimenovano iz `/osm/peaks`."""
    try:
        return await _point_features_service.fetch_point_features_in_radius(lat, lon, radius_km)
    except ArcGISPlacesError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/osm/point-candidates")
async def get_osm_point_candidates(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Geografska širina observera."),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Geografska dužina observera."),
    heading_deg: float = Query(..., ge=0.0, lt=360.0, description="Pravac gledanja, 0 = sjever."),
    fov_deg: float = Query(..., gt=0.0, le=360.0, description="Field of view u stepenima."),
    radius_km: float = Query(..., gt=0.0, le=50.0, description="Radijus pretrage u km."),
) -> dict[str, object]:
    """Phase 5/9 dev endpoint -- tačkasti feature-i filtrirani po radius/FOV
    sektoru i rangirani po ugaonoj blizini heading-u (vidi
    app.services.geometry.select_candidates). `debug` blok prati oblik iz
    docs/architecture-feasibility-review.md, sekcija 11. Preimenovano iz
    `/osm/candidates`."""
    try:
        peaks = await _point_features_service.fetch_point_features_in_radius(lat, lon, radius_km)
    except ArcGISPlacesError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    all_candidates: list[PointCandidate] = select_candidates(
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
            "point_candidates_total": len(peaks),
            "candidates_after_fov_radius_filter": len(all_candidates),
            "candidates_returned": len(returned_candidates),
        },
    }


@router.get("/osm/areas")
async def get_osm_areas(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Geografska širina centra pretrage."),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Geografska dužina centra pretrage."),
    radius_km: float = Query(..., gt=0.0, le=50.0, description="Radijus pretrage u km."),
) -> dict[str, object]:
    """Phase 9 dev endpoint -- sirovi area feature-i (rijeke/vodene
    površine/parkovi/nacionalni parkovi) u radijusu, BEZ sector intersect-a
    ili visibility obrade (vidi modul docstring). Geometrija je vraćena kao
    GeoJSON-oblik dict (preko `shapely.geometry.mapping`) radi čitljivosti u
    Swagger UI/pregledaču -- NIJE konačan API oblik."""
    try:
        features = await _overpass_area_service.fetch_area_features_in_radius(lat, lon, radius_km)
    except OverpassAreaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "features": [
            {
                "osm_id": feature.osm_id,
                "osm_type": feature.osm_type,
                "name": feature.name,
                "category": feature.category,
                "geometry": mapping(feature.geometry),
            }
            for feature in features
        ],
        "debug": {"area_features_total": len(features)},
    }
