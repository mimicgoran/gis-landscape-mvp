"""
Privremeni dev endpoint za Phase 8/9 -- povezuje CIJELI dosadašnji GIS
pipeline: observer + location quality [Phase 7] -> TAČKASTI OSM kandidati
[Phase 4/5/9: peak/settlement/viewpoint] -> DEM/line-of-sight [Phase 6/8],
i (Phase 9) AREA feature-i [rijeke/vodene površine/parkovi/nacionalni
parkovi] -> sector intersect + mini-viewshed [`app.services.area_visibility`].
Vraća skoro-finalni oblik iz docs/architecture-feasibility-review.md,
sekcija 11, BEZ `ai_description` polja (AI sloj je Phase 13).

Nije konačan API dizajn -- finalni `/api/v1/analyze` (Phase 9+) će biti
POST sa observer objektom u body-ju, ne GET sa query parametrima; ovaj
endpoint postoji isključivo radi ručne verifikacije da cijeli lanac
funkcioniše end-to-end prije nego što se doda AI opis i frontend UI.
"""

import asyncio

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.models.feature import AnalyzedAreaFeature, AnalyzedFeature, AreaSamplePoint
from app.models.observer import ObserverInput
from app.services.area_visibility import evaluate_area_feature_visibility
from app.services.elevation import ElevationService
from app.services.geometry import build_sector_polygon, select_candidates
from app.services.location_quality import build_location_quality, compute_observer_elevation_m
from app.services.osm import OverpassError, OverpassService
from app.services.osm_areas import OverpassAreaError, OverpassAreaService
from app.services.visibility import check_visibility, resolve_target_elevation

router = APIRouter(tags=["analyze-dev"])

_overpass_service = OverpassService(get_settings())
_overpass_area_service = OverpassAreaService(get_settings())
_elevation_service = ElevationService(get_settings())


@router.get("/analyze/preview")
def get_analyze_preview(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Geografska širina observera."),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Geografska dužina observera."),
    heading_deg: float = Query(..., ge=0.0, lt=360.0, description="Pravac gledanja, 0 = sjever."),
    fov_deg: float = Query(..., gt=0.0, le=360.0, description="Field of view u stepenima."),
    radius_km: float = Query(..., gt=0.0, le=50.0, description="Radijus pretrage u km."),
    horizontal_accuracy_m: float | None = Query(default=None, ge=0.0),
    phone_altitude_m: float | None = Query(default=None),
    phone_altitude_accuracy_m: float | None = Query(default=None, ge=0.0),
    include_profile: bool = Query(
        default=False, description="Uključi pun elevation profil po kandidatu (veliki JSON -- default isključeno)."
    ),
) -> dict[str, object]:
    """Phase 8/9 dev endpoint -- vidi modul docstring. Sync `def` (ne
    `async def`) iz istog razloga kao ostali DEM/location-quality dev
    endpointi -- `rasterio`/`httpx.Client` pozivi unutra su blokirajući, a
    FastAPI sync rute izvršava u threadpool-u. Overpass pozivi su async
    (postojeći `OverpassService`/`OverpassAreaService`), pa se pokreću
    preko `asyncio.run()` unutar tog thread-a -- jednostavnije nego
    uvoditi `run_in_threadpool`, i sigurno je jer thread nema sopstvenu
    event loop."""
    settings = get_settings()

    observer_input = ObserverInput(
        latitude=lat,
        longitude=lon,
        horizontal_accuracy_m=horizontal_accuracy_m,
        phone_altitude_m=phone_altitude_m,
        phone_altitude_accuracy_m=phone_altitude_accuracy_m,
    )

    dem_elevation_m = _elevation_service.get_elevation(lat, lon)
    location_quality = build_location_quality(observer_input, dem_elevation_m, settings)
    observer_elevation_m = compute_observer_elevation_m(
        location_quality.selected_ground_elevation_m, settings.observer_eye_height_m
    )

    observer_block = {
        "latitude": lat,
        "longitude": lon,
        "dem_elevation_m": dem_elevation_m,
        "observer_eye_height_m": settings.observer_eye_height_m,
        "observer_elevation_m": observer_elevation_m,
        "heading_deg": heading_deg,
        "fov_deg": fov_deg,
        "radius_km": radius_km,
    }

    if observer_elevation_m is None:
        # DEM nedostupan za observer lokaciju -- analiza nije moguća bez
        # ijednog izvora tla (brief, tačka 42: graceful, ne pad aplikacije).
        return {
            "observer": observer_block,
            "location_quality": location_quality,
            "visible_features": [],
            "blocked_features": [],
            "area_features": [],
            "debug": {
                "error": "DEM elevacija nedostupna za observer lokaciju -- analiza nije moguća.",
            },
        }

    try:
        peaks = asyncio.run(_overpass_service.fetch_point_features_in_radius(lat, lon, radius_km))
    except OverpassError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    all_candidates = select_candidates(
        observer_latitude=lat,
        observer_longitude=lon,
        heading_deg=heading_deg,
        fov_deg=fov_deg,
        radius_km=radius_km,
        peaks=peaks,
    )
    candidates = all_candidates[: settings.candidate_ranking_max_n]

    visible_features: list[AnalyzedFeature] = []
    blocked_features: list[AnalyzedFeature] = []
    skipped_no_elevation = 0

    for candidate in candidates:
        target_elevation_m, elevation_source, discrepancy_m = resolve_target_elevation(
            candidate.ele_m, candidate.latitude, candidate.longitude, _elevation_service, settings
        )
        if target_elevation_m is None or elevation_source is None:
            # Ni OSM ele ni DEM nisu dostupni za ovaj target -- rijedak
            # edge case (van DEM pokrivenosti i bez OSM ele tag-a).
            # Preskačemo ga umjesto da izmišljamo elevaciju.
            skipped_no_elevation += 1
            continue

        result = check_visibility(
            observer_latitude=lat,
            observer_longitude=lon,
            observer_elevation_m=observer_elevation_m,
            target_latitude=candidate.latitude,
            target_longitude=candidate.longitude,
            target_elevation_m=target_elevation_m,
            target_distance_m=candidate.distance_km * 1000.0,
            elevation_service=_elevation_service,
            settings=settings,
        )

        feature = AnalyzedFeature(
            osm_id=candidate.osm_id,
            name=candidate.name,
            category=candidate.category,
            latitude=candidate.latitude,
            longitude=candidate.longitude,
            distance_km=candidate.distance_km,
            bearing_deg=candidate.bearing_deg,
            elevation_m=target_elevation_m,
            elevation_source=elevation_source,
            elevation_discrepancy_m=discrepancy_m,
            visibility="visible" if result.visible else "blocked",
            profile=result.profile if include_profile else None,
        )

        (visible_features if result.visible else blocked_features).append(feature)

    # --- Phase 9: area feature-i (rijeke/vodene površine/parkovi/nacionalni
    # parkovi) -- odvojen pipeline (sector intersect + mini-viewshed), vidi
    # app.services.area_visibility modul docstring.
    try:
        raw_area_features = asyncio.run(_overpass_area_service.fetch_area_features_in_radius(lat, lon, radius_km))
    except OverpassAreaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    sector_polygon = build_sector_polygon(lat, lon, heading_deg, fov_deg, radius_km)

    area_results: list[tuple[object, object]] = []
    area_skipped_no_elevation = 0
    for area_feature in raw_area_features:
        area_result = evaluate_area_feature_visibility(
            feature=area_feature,
            sector_polygon=sector_polygon,
            observer_latitude=lat,
            observer_longitude=lon,
            observer_elevation_m=observer_elevation_m,
            elevation_service=_elevation_service,
            settings=settings,
            # Isti include_profile flag kao za tačkaste feature-e (vidi
            # AnalyzedFeature.profile) -- veliki JSON, zato default isključeno.
            collect_sample_details=include_profile,
        )
        if area_result is None:
            # Ili van sektora (intersect prazan), ili nijedna sample tačka
            # nema dostupan DEM -- oba slučaja se tretiraju kao "izostavi iz
            # rezultata" (vidi evaluate_area_feature_visibility docstring).
            # Brojimo samo drugi slučaj odvojeno nije moguće bez dodatnog
            # signala iz funkcije, pa se oba prijavljuju zajedno kao
            # "nije uključeno" -- dovoljno za MVP debug transparentnost.
            area_skipped_no_elevation += 1
            continue
        area_results.append((area_feature, area_result))

    area_results.sort(key=lambda pair: pair[1].closest_distance_km)
    area_results = area_results[: settings.area_feature_max_results]

    area_features: list[AnalyzedAreaFeature] = [
        AnalyzedAreaFeature(
            osm_id=area_feature.osm_id,
            osm_type=area_feature.osm_type,
            name=area_feature.name,
            category=area_feature.category,
            closest_distance_km=area_result.closest_distance_km,
            bearing_deg=area_result.bearing_deg,
            sample_count=area_result.sample_count,
            visible_sample_count=area_result.visible_sample_count,
            dem_gap_sample_count=area_result.dem_gap_sample_count,
            visible_fraction=area_result.visible_fraction,
            visibility=area_result.visibility,
            samples=(
                [
                    AreaSamplePoint(
                        latitude=sample.latitude,
                        longitude=sample.longitude,
                        distance_km=sample.distance_km,
                        elevation_m=sample.elevation_m,
                        visible=sample.visible,
                        target_angle_deg=sample.target_angle_deg,
                        max_terrain_angle_deg=sample.max_terrain_angle_deg,
                    )
                    for sample in area_result.samples
                ]
                if area_result.samples is not None
                else None
            ),
        )
        for area_feature, area_result in area_results
    ]

    return {
        "observer": observer_block,
        "location_quality": location_quality,
        "visible_features": visible_features,
        "blocked_features": blocked_features,
        "area_features": area_features,
        "debug": {
            "osm_candidates_total": len(peaks),
            "candidates_after_fov_radius_filter": len(all_candidates),
            "candidates_analyzed": len(candidates),
            "candidates_skipped_no_elevation": skipped_no_elevation,
            "visible_count": len(visible_features),
            "blocked_count": len(blocked_features),
            "area_features_total": len(raw_area_features),
            "area_features_in_sector": len(area_features),
            "area_features_skipped_or_no_elevation": area_skipped_no_elevation,
        },
    }
