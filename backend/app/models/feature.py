"""
Pydantic modeli za geografske objekte (feature-e) identifikovane preko OSM-a.

Phase 4-8 scope je bio samo natural=peak. Phase 9 proširuje scope na
eksplicitan korisnički zahtjev (vidi docs/architecture-feasibility-review.md,
Phase 9 status): korisnik ne pita samo "koji je vrh ispred mene" nego i
"koja je rijeka/koje je mjesto/koji je park ispred mene". Dvije porodice
modela postoje zbog stvarne geometrijske razlike:

- TAČKASTI feature-i (peak/settlement/viewpoint) -- `OSMPointFeature`,
  `PointCandidate`, dio `AnalyzedFeature` -- imaju JEDNU (lat, lon) tačku,
  pa im je "vidljiv/blokiran" binarna, jednoznačna vrijednost (Phase 8
  line-of-sight, jedna provjera po feature-u).
- AREA feature-i (river/water/park/national_park) -- `AnalyzedAreaFeature`
  -- imaju STVARNU prostornu protežnost (linija/poligon), pa "vidljivost"
  nije binarna: dio rijeke/parka unutar sektora može biti djelimično
  vidljiv (npr. bliža obala vidljiva, dalja zaklonjena teren-om). Zato
  `AnalyzedAreaFeature` nosi `visible_fraction`/`sample_count` umjesto
  jedne `visibility` booleovske vrijednosti -- vidi
  app.services.area_visibility za algoritam.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class OSMPointFeature(BaseModel):
    """Sirov tačkasti OSM feature dobijen iz Overpass API-ja, prije bilo
    kakvog geometrijskog filtriranja (distance/bearing/FOV -- Phase 5) ili
    DEM/visibility obrade (Phase 6-8).

    Preimenovano iz `OSMPeak` u Phase 9 kad je scope proširen sa
    natural=peak na i place=city/town/village i tourism=viewpoint -- sve
    tri kategorije dijele identičan geometrijski/DEM/line-of-sight
    pipeline (jedna tačka = jedna provjera), razlikuju se samo po
    `category` (i, kasnije, po formulaciji u AI opisu -- Phase 13)."""

    osm_id: int = Field(..., description="OSM node ID.")
    name: str | None = Field(default=None, description="OSM 'name' tag, ako postoji.")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    ele_m: float | None = Field(
        default=None,
        description=(
            "OSM 'ele' tag u metrima, ako postoji i numerički je smislen "
            "(vidi app.services.osm._parse_ele_tag). Prioritet nad DEM "
            "elevation-om za target elevation -- sekcija 9, korak 8. U "
            "praksi gotovo isključivo prisutan kod category='peak'."
        ),
    )
    category: Literal["peak", "settlement", "viewpoint"] = Field(
        ..., description="Koji OSM tag je uparen -- natural=peak / place=city|town|village / tourism=viewpoint."
    )


class PointCandidate(BaseModel):
    """Tačkasti feature koji je prošao distance/FOV/sector filter (Phase 5)
    i dobio geometrijske metapodatke (distance/bearing/angular difference
    od observera). Namjeran međukorak -- NIJE finalni `AnalyzedFeature`
    (taj dobija elevation_m/elevation_source/visibility tek u Phase 6-8).

    Preimenovano iz `PeakCandidate` u Phase 9 (vidi `OSMPointFeature`)."""

    osm_id: int
    name: str | None = None
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    ele_m: float | None = None
    category: Literal["peak", "settlement", "viewpoint"]
    distance_km: float = Field(..., ge=0.0)
    bearing_deg: float = Field(..., ge=0.0, lt=360.0)
    angular_difference_deg: float = Field(
        ...,
        ge=0.0,
        le=180.0,
        description="Vidi app.services.geometry.angular_difference_deg -- koristi se za rangiranje (sekcija 44 originalnog brifa).",
    )


class ProfilePoint(BaseModel):
    """Jedna tačka terenskog elevation profila duž observer->target linije
    (Phase 8 line-of-sight). `elevation_m` je `None` ako DEM nije dostupan
    baš za tu tačku (rijedak "rupa u pokrivenosti" slučaj -- vidi
    app.services.visibility.check_visibility, `dem_gap` polje)."""

    distance_m: float = Field(..., ge=0.0, description="Distanca od observera duž linije, u metrima.")
    elevation_m: float | None = None


class AnalyzedFeature(BaseModel):
    """Finalni, potpuno obrađen TAČKASTI feature -- rezultat cijelog
    pipeline-a (OSM -> geometrija -> DEM -> line-of-sight, Phase 4-8).
    Oblik prati docs/architecture-feasibility-review.md, sekcija 11
    (`visible_features`/`blocked_features` unutar `/api/v1/analyze`)."""

    osm_id: int
    name: str | None = None
    category: Literal["peak", "settlement", "viewpoint"]
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    distance_km: float = Field(..., ge=0.0)
    bearing_deg: float = Field(..., ge=0.0, lt=360.0)
    elevation_m: float
    elevation_source: Literal["osm", "dem"]
    elevation_discrepancy_m: float | None = Field(
        default=None,
        description=(
            "Postavljeno samo ako se OSM ele i DEM na target koordinati razlikuju za više od "
            "Settings.target_elevation_discrepancy_threshold_m -- debug info, ne mijenja izabrani izvor "
            "(sekcija 9, korak 8)."
        ),
    )
    visibility: Literal["visible", "blocked"]
    profile: list[ProfilePoint] | None = Field(
        default=None, description="Samo kad je eksplicitno zatraženo (?include_profile=true) -- inače None."
    )


class AnalyzedAreaFeature(BaseModel):
    """Finalni, potpuno obrađen AREA feature (rijeka / vodena površina /
    park / nacionalni park) -- rezultat Phase 9 pipeline-a (OSM geometrija
    -> sector intersect -> "mini-viewshed" sampling -> agregacija, vidi
    app.services.area_visibility).

    Namjerno NEMA binarno `visibility: visible|blocked` polje kao
    `AnalyzedFeature` -- feature sa prostornom protežnošću nema
    jedinstvenu istinu o vidljivosti (dio može biti vidljiv, dio ne), pa
    `visibility` ovdje ima treću vrijednost (`partially_visible`) izvedenu
    iz `visible_fraction`."""

    osm_id: int
    osm_type: Literal["way", "relation"]
    name: str | None = None
    category: Literal["river", "water", "park", "national_park"]
    closest_distance_km: float = Field(
        ..., ge=0.0, description="Distanca od observera do najbliže tačke STVARNE geometrije feature-a (ne centroida)."
    )
    bearing_deg: float = Field(..., ge=0.0, lt=360.0, description="Bearing ka najbližoj tački feature-a.")
    sample_count: int = Field(
        ..., ge=0, description="Ukupan broj 'mini-viewshed' sample tačaka duž dijela geometrije unutar sektora."
    )
    visible_sample_count: int = Field(..., ge=0)
    dem_gap_sample_count: int = Field(
        default=0,
        description="Sample tačke bez dostupnog DEM-a -- isključene iz imenioca visible_fraction (nisu 'blokirane').",
    )
    visible_fraction: float = Field(
        ..., ge=0.0, le=1.0, description="visible_sample_count / (sample_count - dem_gap_sample_count)."
    )
    visibility: Literal["visible", "partially_visible", "blocked"]
