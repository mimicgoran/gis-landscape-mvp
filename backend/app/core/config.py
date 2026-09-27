"""
Centralna konfiguracija backend aplikacije.

Sve "magic number" vrijednosti (thresholds, default parametri) koje utiču na
GIS logiku žive ovdje kao imenovane konstante sa komentarom koji objašnjava
zašto imaju baš tu vrijednost — vidi Architecture & Feasibility Review,
sekcija 6 (location quality pragovi) i sekcija 9 (line-of-sight parametri)
za puno obrazloženje.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven podešavanja. Čita se iz .env fajla (vidi .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Opšte ---
    app_name: str = "GIS Landscape Identification MVP"
    app_version: str = "0.1.0-phase1"
    environment: str = "development"

    # CORS: u razvoju dozvoljavamo lokalni frontend dev server; u produkciji
    # se ovo ograničava na stvarni GitHub Pages domen (Phase 15).
    cors_allow_origins: list[str] = [
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8080",
    ]

    # --- Observer / elevation (Phase 7+) ---
    # Prosječna visina očiju odrasle osobe iznad tla. Konfigurabilno ovdje,
    # namjerno NE izloženo u UI-ju u MVP-u (brief, tačka 10).
    observer_eye_height_m: float = 1.7

    # --- Location quality pragovi (Phase 7) ---
    # Vidi architecture-feasibility-review.md, sekcija 6, za puno obrazloženje.
    horizontal_accuracy_high_m: float = 15.0
    horizontal_accuracy_medium_m: float = 50.0
    phone_altitude_accuracy_usable_m: float = 20.0

    # --- Viewing sector granice (Phase 3) ---
    # Vidi architecture-feasibility-review.md, sekcija 8.
    fov_min_deg: float = 20.0
    fov_max_deg: float = 90.0
    fov_default_deg: float = 50.0
    radius_min_km: float = 5.0
    radius_max_km: float = 30.0
    radius_default_km: float = 20.0

    # --- Line-of-sight (Phase 8) ---
    # Sampling korak ~= DEM rezolucija (30 m). Vidi sekciju 9.
    line_of_sight_sample_spacing_m: float = 30.0
    # Earth curvature/refrakcija namjerno isključena u MVP-u (scope: Srbija,
    # mali radijusi -> zanemarljiv efekat). Feature-flag za Phase 2.
    enable_earth_curvature_correction: bool = False
    earth_curvature_refraction_coefficient: float = 0.13

    # --- Eksterni servisi ---
    overpass_api_url: str = "https://overpass-api.de/api/interpreter"
    copernicus_dem_bucket: str = "copernicus-dem-30m"

    # --- ArcGIS auth (Phase 1) ---
    # Organizacija korisnika ima isključeno izdavanje plain "API key"
    # credentials (admin policy) — dostupne su samo OAuth 2.0 credentials.
    # Koristimo "App authentication" (client_credentials grant): backend
    # razmjenjuje client_id/client_secret za kratkotrajan access token i
    # servira ga frontend-u preko /api/v1/arcgis-token. client_secret je
    # tajna istog ranga kao OPENAI_API_KEY — nikad u frontend kodu.
    # Vidi docs/architecture-feasibility-review.md, sekcija 4 (Esri arhitektura).
    arcgis_client_id: str | None = None
    arcgis_client_secret: str | None = None
    arcgis_oauth_token_url: str = "https://www.arcgis.com/sharing/rest/oauth2/token"
    # Osvježi token malo prije stvarnog isteka da izbjegnemo race condition
    # gdje frontend dobije token koji istekne par sekundi kasnije.
    arcgis_token_refresh_margin_s: int = 60

    # Secrets — nikad default vrijednost, moraju doći iz .env / env varijable.
    openai_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Cache-ovan singleton — Settings se čita jednom po procesu."""
    return Settings()
