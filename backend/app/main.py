"""FastAPI application entrypoint.

Phase 1 scope: app setup, CORS, /api/v1/health i /api/v1/arcgis-token
(potonji je dodatak otkriven tokom Phase 1 — korisnikova ArcGIS Online
organizacija ne dozvoljava plain API key credentials, pa backend posreduje
OAuth app-auth token; vidi app/services/arcgis_auth.py). Ostali endpointi
(/api/v1/analyze) se dodaju u kasnijim fazama (vidi
docs/architecture-feasibility-review.md, sekcija 13 — MVP backlog).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import arcgis_token, health
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Deterministic GIS engine (geometry, OSM, DEM, line-of-sight) za "
        "identifikaciju planinskih vrhova u vidnom polju korisnika. "
        "Vidi /docs za interaktivnu API dokumentaciju."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(arcgis_token.router, prefix="/api/v1")


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": f"{settings.app_name} backend. Vidi /docs za API dokumentaciju.",
        "version": settings.app_version,
    }
