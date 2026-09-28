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
    # namjerno NE izloženo u UI-ju u MVP-u (brief, tačka 10). Podignuto sa
    # 1.7 na 1.85 m (korisnička odluka, Phase 10 Sava/Orašac istraga) --
    # 1.7 m je bio konzervativan prosjek, 1.85 m je bliže prosječnoj visini
    # odraslog posmatrača koji nešto uspravnije stoji/drži telefon podignut;
    # razlika je mala (+15 cm) i ne mijenja suštinski zaključke, ali malo
    # smanjuje broj graničnih "blocked" slučajeva na kratkim distancama.
    observer_eye_height_m: float = 1.85

    # --- Location quality pragovi (Phase 7) ---
    # Vidi architecture-feasibility-review.md, sekcija 6, za puno obrazloženje.
    horizontal_accuracy_high_m: float = 15.0
    horizontal_accuracy_medium_m: float = 50.0
    phone_altitude_accuracy_usable_m: float = 20.0

    # --- Viewing sector granice (Phase 3) ---
    # Vidi architecture-feasibility-review.md, sekcija 8.
    fov_min_deg: float = 20.0
    fov_max_deg: float = 90.0
    # Default promijenjen sa 50 na 30 (korisnička odluka nakon prvog pravog
    # telefon testa, Phase 10 -- vidi docs/architecture-feasibility-review.md,
    # sekcija 33) -- i dalje unutar dokumentovanog 20-90 opsega iz sekcije 8,
    # samo uži početni sektor.
    fov_default_deg: float = 30.0
    radius_min_km: float = 5.0
    radius_max_km: float = 30.0
    # Default promijenjen sa 20 na 5 (ista odluka kao gore) -- donja granica
    # dokumentovanog opsega, jer manji radius znači brži Overpass/DEM/LOS
    # pipeline za tipičan demo slučaj; korisnik i dalje može podići slajder.
    radius_default_km: float = 5.0

    # --- Line-of-sight (Phase 8) ---
    # Sampling korak ~= DEM rezolucija (30 m). Vidi sekciju 9.
    line_of_sight_sample_spacing_m: float = 30.0
    # Earth curvature/refrakcija namjerno isključena u MVP-u (scope: Srbija,
    # mali radijusi -> zanemarljiv efekat). Feature-flag za Phase 2.
    enable_earth_curvature_correction: bool = False
    earth_curvature_refraction_coefficient: float = 0.13
    # DEM vertikalna tačnost -- koristi se kao ugaona TOLERANCIJA u
    # check_visibility() (Phase 10, dodano nakon Sava/Orašac istrage:
    # docs/architecture-feasibility-review.md, sekcija 31). Copernicus DEM
    # GLO-30 ima dokumentovanu tipičnu vertikalnu tačnost reda veličine
    # 1-4 m (arhitekturni dokument, sekcija 26); biramo 2.0 m kao razumnu
    # sredinu tog opsega, ne pesimistički gornji kraj. Na kratkim
    # distancama (stotinjak metara -- npr. riječna obala tik uz
    # posmatrača) i par metara DEM šuma/rezidualne vegetacije (Copernicus
    # DEM je DSM-izveden) daje ugaonu grešku od preko 1°, što je uporedivo
    # sa samim target uglom -- bez ove tolerancije, pojedinačni "bučan"
    # piksel lažno "blokira" cilj koji je u stvarnosti jasno vidljiv.
    # NIJE primijenjeno na target_angle_deg (samo na terensku tačku) --
    # namjerna MVP pojednostavljenje, vidi check_visibility docstring.
    dem_vertical_accuracy_m: float = 2.0

    # --- Candidate ranking (Phase 5) ---
    # Ako sektor sadrži više kandidata nego što ima smisla obraditi kroz
    # skup DEM/line-of-sight (Phase 6-8 -- svaki kandidat troši nekoliko
    # desetina DEM sample-ova), ograničavamo se na najrelevantnije. Brief
    # (tačka 44) predlaže "10-20"; biramo gornju granicu tog opsega jer
    # broj vrhova u jednom sektoru (i na gušće pokrivenim test lokacijama
    # poput Kopaonika -- vidi sekciju 22) rijetko prelazi ovaj broj, pa cap
    # praktično rijetko odbacuje stvarno vidljive vrhove. Vidi
    # app.services.geometry.select_candidates za samu logiku rangiranja.
    candidate_ranking_max_n: int = 20

    # --- Eksterni servisi ---
    overpass_api_url: str = "https://overpass-api.de/api/interpreter"
    # Javne Overpass instance povremeno vrate 429/502/503/504 pod
    # opterećenjem (potvrđeno empirijski u Phase 5 i Phase 8 -- vidi
    # docs/architecture-feasibility-review.md, sekcija 14, rizik "Overpass
    # reliability", i Phase 8 status). Ručni retry je u testiranju skoro
    # uvijek uspijevao iz drugog pokušaja, pa je automatski retry
    # opravdana, jeftina zaštita -- bitno za LinkedIn demo (brief, tačka
    # 50) da tranzitorni Overpass hiccup ne pokvari snimanje uživo.
    overpass_max_retries: int = 2
    overpass_retry_backoff_s: float = 2.0
    copernicus_dem_bucket: str = "copernicus-dem-30m"

    # DEM tile cache -- "download-once, cache-on-disk" pristup (Phase 6;
    # vidi app/services/elevation.py modul docstring za puno obrazloženje
    # zašto ne čist GDAL /vsicurl/ streaming). Relativna putanja se
    # rezolvira u odnosu na cwd procesa (backend/, isto kao .env).
    dem_cache_dir: str = "app/data/dem_cache"
    dem_download_timeout_s: float = 60.0

    # --- Target elevation discrepancy (Phase 8) ---
    # Sekcija 9 arhitekture pominje "npr. 50 m" kao ilustraciju praga na kom
    # OSM `ele` i DEM vrijednost za isti vrh vrijede zabilježiti kao
    # neslaganje (DEM ima tendenciju da blago potcijeni pravi vrh zbog 30 m
    # usrednjavanja piksela). Usvojeno kao stvaran prag u Phase 8 -- OSM
    # `ele` ostaje prioritet čak i kad je razlika veća (sekcija 9, korak 8),
    # razlika se samo bilježi kao debug info (`elevation_discrepancy_m`),
    # nikad ne mijenja koji izvor se koristi.
    target_elevation_discrepancy_threshold_m: float = 50.0

    # --- Area feature sampling (rijeke/vodene povrsine/parkovi/nacionalni
    # parkovi -- Phase 9) ---
    # Za razliku od tackastih feature-a (Phase 4-8, jedan target = jedna
    # line-of-sight provjera), feature sa geometrijom (way/relation)
    # zahtijeva VISE provjera duz presjecenog dijela geometrije unutar
    # sektora ("mini-viewshed po feature-u" -- eksplicitno odabrana opcija,
    # vidi docs/architecture-feasibility-review.md, Phase 9 status). Da bi
    # ukupan trosak (N feature-a x M sample-ova x line-of-sight profil po
    # sample-u) ostao razuman, sample spacing ovdje je namjerno KRUPNIJI od
    # `line_of_sight_sample_spacing_m` (30 m, DEM rezolucija za profil
    # IZMEDU observera i JEDNOG targeta) -- ovdje su sample tacke SAME
    # targeti, ne teren izmedju, pa gusce sample-ovanje samo umnozava broj
    # punih line-of-sight poziva bez proporcionalne koristi za MVP demo
    # svrhu.
    area_feature_sample_spacing_m: float = 200.0
    # Gornja granica broja sample tacaka po jednom feature-u (npr. vrlo
    # duga rijeka ili veliki nacionalni park unutar radijusa) -- sprecava
    # da jedan ogroman poligon/linija sam po sebi eksplodira broj
    # DEM/line-of-sight poziva. Ako presjecena geometrija ima vise
    # potencijalnih sample tacaka nego ovaj limit, ravnomjerno se
    # prorijede (ne samo prvih N -- vidi area_visibility._cap_samples).
    area_feature_max_samples_per_feature: int = 12
    # Gornja granica broja area feature-a (ukupno, svih kategorija) koji
    # se uopste obraduju kroz sampling/visibility pipeline po zahtjevu --
    # isti princip kao `candidate_ranking_max_n` za tackaste feature-e,
    # rangirano po `closest_distance_km` (najblizi prvo).
    area_feature_max_results: int = 15

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
