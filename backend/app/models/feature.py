"""
Pydantic modeli za geografske objekte (feature-e) identifikovane preko OSM-a.

Phase 4 scope: samo natural=peak. Vidi
docs/architecture-feasibility-review.md, sekcije 7 i 18 -- dodatne OSM
kategorije (place=city/town/village, tourism=viewpoint...) su namjerno
odgođene do nakon Phase 9, kada je puni pipeline (OSM -> geometrija -> DEM
-> line-of-sight -> UI) dokazan na vrhovima. Kad se dodaju, ovaj modul je
mjesto gdje se dodaje odgovarajući model/tip.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class OSMPeak(BaseModel):
    """Sirov planinski vrh dobijen iz Overpass API-ja, prije bilo kakvog
    geometrijskog filtriranja (distance/bearing/FOV -- Phase 5) ili
    DEM/visibility obrade (Phase 6-8)."""

    osm_id: int = Field(..., description="OSM node ID.")
    name: str | None = Field(default=None, description="OSM 'name' tag, ako postoji.")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    ele_m: float | None = Field(
        default=None,
        description=(
            "OSM 'ele' tag u metrima, ako postoji i numerički je smislen "
            "(vidi app.services.osm._parse_ele_tag). Prioritet nad DEM "
            "elevation-om za target elevation -- sekcija 9, korak 8."
        ),
    )


class PeakCandidate(BaseModel):
    """Vrh koji je prošao distance/FOV/sector filter (Phase 5) i dobio
    geometrijske metapodatke (distance/bearing/angular difference od
    observera). Namjeran međukorak -- NIJE finalni FeatureResult iz
    docs/architecture-feasibility-review.md, sekcija 11 (taj dobija
    elevation_m/elevation_source/visibility tek u Phase 6-8)."""

    osm_id: int
    name: str | None = None
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    ele_m: float | None = None
    distance_km: float = Field(..., ge=0.0)
    bearing_deg: float = Field(..., ge=0.0, lt=360.0)
    angular_difference_deg: float = Field(
        ...,
        ge=0.0,
        le=180.0,
        description="Vidi app.services.geometry.angular_difference_deg -- koristi se za rangiranje (sekcija 44 originalnog brifa).",
    )
