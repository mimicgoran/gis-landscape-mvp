"""
Observer input model.

Phase 2 scope: korisnik (ili, u kasnijim fazama, browser Geolocation API)
daje samo latitude/longitude — nema još GPS accuracy, phone altitude ni
heading/FOV/radius (ti dolaze u Phase 3, 7, 10, 11). Polja za njih su već
tu kao opciona, u skladu sa API dizajnom iz architecture review-a (sekcija
11), da se model ne mora mijenjati kad se dodaju.

Validacija granica (lat -90..90, lon -180..180) je namjerno jedina logika
ovdje — Pydantic to radi automatski preko `ge`/`le` na poljima, bez ručnog
koda.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ObserverInput(BaseModel):
    """Ulazni podaci o posmatraču (observer) za GIS analizu.

    U Phase 2 se popunjava klikom na mapu (manual observer, vidi
    docs/architecture-feasibility-review.md, sekcija 13, MVP backlog #2).
    Od Phase 10 nadalje, isti model popunjava browser Geolocation API —
    otuda opciona polja za GPS/phone dijagnostiku već sada, ne naknadno.
    """

    latitude: float = Field(..., ge=-90.0, le=90.0, description="Geografska širina (WGS84), stepeni.")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Geografska dužina (WGS84), stepeni.")

    # Opciono od Phase 10 (mobile geolocation) nadalje — manual click (Phase 2)
    # ova polja ne popunjava, pa ostaju None.
    horizontal_accuracy_m: float | None = Field(
        default=None,
        ge=0.0,
        description="Horizontalna GPS preciznost u metrima (coords.accuracy). None za manual observer.",
    )
    phone_altitude_m: float | None = Field(
        default=None,
        description="Sirova visina sa telefona (coords.altitude), dijagnostika — nikad autoritativni izvor elevacije (vidi sekciju 6).",
    )
    phone_altitude_accuracy_m: float | None = Field(
        default=None,
        ge=0.0,
        description="Vertikalna GPS preciznost u metrima (coords.altitudeAccuracy), ako je browser vrati.",
    )
