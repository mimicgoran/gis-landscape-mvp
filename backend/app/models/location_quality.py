"""
Location quality model -- Phase 7.

Puna šema i obrazloženje pragova su već odobreni u Architecture &
Feasibility Review, sekcija 6 ("Predloženi pragovi" i "Location
confidence") i sekcija 11 (JSON oblik unutar `/api/v1/analyze` response-a).
Ovaj model samo prevodi tu već odobrenu šemu u Pydantic -- logika koja ga
popunjava je u app/services/location_quality.py.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# "dem_phone_fusion" i "dem_phone_disagreement" su dio šeme (sekcija 6) za
# kompatibilnost sa budućom fuzijom, ali logika koja bi ih aktivno postavljala
# nije u MVP-u -- vidi docstring u app/services/location_quality.py.
ElevationSource = Literal["dem", "dem_phone_fusion", "dem_phone_disagreement"]
LocationConfidence = Literal["high", "medium", "low"]


class LocationQuality(BaseModel):
    """Diagnostic blok koji prati svaki `/api/v1/analyze` odgovor (Phase 9)
    -- transparentnost o tome koliko je pouzdana observer lokacija/elevacija
    korištena za analizu, ne skriven implementacioni detalj (brief, tačke
    14-15: "Ovo je posebno korisno za portfolio demo jer pokazuje
    data-quality awareness")."""

    horizontal_accuracy_m: float | None = Field(
        default=None, ge=0.0, description="Isto kao ObserverInput.horizontal_accuracy_m -- None za manual observer."
    )
    phone_altitude_m: float | None = None
    phone_altitude_accuracy_m: float | None = Field(default=None, ge=0.0)
    dem_elevation_m: float | None = Field(default=None, description="Sirova DEM vrijednost, prije bilo kakve fuzije.")
    selected_ground_elevation_m: float | None = Field(
        default=None,
        description="Vrijednost stvarno korišćena za observer_elevation. U MVP-u uvijek == dem_elevation_m (vidi sekciju 6).",
    )
    elevation_source: ElevationSource | None = Field(
        default=None,
        description="`None` znači da elevacija uopšte nije dostupna (DEM nedostupan za ovu lokaciju).",
    )
    confidence: LocationConfidence
