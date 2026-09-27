"""
DEM elevation servis -- Copernicus DEM GLO-30, "download-once, cache-on-disk"
pristup.

Phase 6 scope: samo čitanje elevacije terena na zadatoj (lat, lon) tački.
Observer/target elevation logika, phone altitude fuzija i location quality
model dolaze u Phase 7 (vidi docs/architecture-feasibility-review.md,
sekcija 6 i 10, i implementacione faze).

ARHITEKTURNA ODLUKA -- zašto ne čist GDAL /vsicurl/ streaming read:
Originalni DEM strategy plan je predviđao GDAL-ov /vsicurl/ virtuelni
filesystem, koji čita samo potrebne bajtove sa udaljenog COG-a preko HTTP
range requestova, bez punog preuzimanja tile-a. Empirijski je utvrđeno
(Phase 6 troubleshooting) da svaki pokušaj otvaranja
`/vsicurl/https://...tif` sa `rasterio.open()` baca:

    UnicodeDecodeError: 'utf-8' codec can't decode byte 0x97 ...

Uzrok je `# cython: c_string_encoding=utf8` direktiva ugrađena u rasterio-jev
kompajlirani `_err.pyx` (GDAL log/error callback) -- svaki GDAL log string se
striktno UTF-8 dekodira prije prosljeđivanja Python logging sloju, a jedan
od HTTP/CURL debug logova koje /vsicurl/ generiše sadrži bajt koji nije
validan UTF-8. Ovo se ne može zaobići ni env varijablama, ni logging
konfiguracijom, ni CPL_LOG redirekcijom (CPL_LOG utiče samo na GDAL-ov
DEFAULT error handler, a rasterio registruje svoj sopstveni preko
CPLPushErrorHandler) -- fix bi zahtijevao rekompajliranje rasteria iz izvora.

Umjesto toga: tile (1x1 stepen, ~40-45 MB) se preuzme JEDNOM preko običnog
httpx HTTP GET-a (bez GDAL-a, bez problema) na lokalni disk, keširan po
imenu tile-a, i SVAKO čitanje/sampling ide protiv te lokalne kopije.
Tradeoff: prvi request za novu geografsku oblast je sporiji (par sekundi
preuzimanja cijelog tile-a umjesto par range-readova od par KB), ali za MVP
sa nekoliko test lokacija (Kopaonik, Stara planina, Tara -- svaka najvjerovatnije
unutar jednog ili dva 1x1 stepen tile-a) ovo je i jednostavnije i u praksi
brže nakon prvog zahtjeva, jer dalje čitanje ide sa lokalnog diska.

PROJ_LIB/PROJ_DATA fix -- zašto se briše prije importa rasteria:
Na razvojnoj mašini je pronađen sukob: PostgreSQL/PostGIS instalacija je
postavila mašinski PROJ_LIB env var koji pokazuje na stariju, nekompatibilnu
proj.db bazu. rasterio/pyproj (instalirani preko pip-a) su je pokupili
umjesto svoje bundlovane verzije, što baca:

    rasterio.errors.CRSError: ... DATABASE.LAYOUT.VERSION.MINOR = 2
    whereas a number >= 6 is expected. It comes from another PROJ installation.

Potvrđen fix (rasterio FAQ + GitHub Discussion #2721, identičan slučaj sa
drugom PostgreSQL verzijom): obrisati PROJ_LIB i PROJ_DATA iz environment-a
PRIJE `import rasterio` -- rasterio se tad vraća na sopstvenu bundlovanu PROJ
verziju iz wheel-a. Ovo mora biti urađeno na nivou modula, prije import-a.
"""

from __future__ import annotations

import logging
import math
import os
from pathlib import Path

# MORA biti prije `import rasterio` -- vidi objašnjenje u docstringu iznad.
os.environ.pop("PROJ_LIB", None)
os.environ.pop("PROJ_DATA", None)

import httpx
import rasterio
import rasterio.errors

from app.core.config import Settings

logger = logging.getLogger(__name__)


class ElevationError(RuntimeError):
    """Podignuto interno kad DEM tile nije moguće preuzeti ili pročitati.

    Ne izlazi iz `ElevationService.get_elevation()` -- hvata se tamo i
    pretvara u `None` (vidi tačku 42 brief-a: DEM nedostupnost mora biti
    graceful, ne smije oboriti cijeli zahtjev)."""


def _tile_name(latitude: float, longitude: float) -> str:
    """Računa naziv Copernicus DEM GLO-30 tile-a za zadatu tačku.

    Tile-ovi su 1x1 stepen, imenovani po jugozapadnom (SW) uglu -- npr.
    tačka (43.27, 20.82) pada u tile čiji je SW ugao (43, 20), tj.
    "Copernicus_DSM_COG_10_N43_00_E020_00_DEM" (potvrđeno empirijski protiv
    stvarnog S3 bucket-a za Kopaonik, Phase 6 troubleshooting).

    N/E strana konvencije je empirijski potvrđena. S/W strana (negativne
    lat/lon) prati istu SW-corner logiku prema AWS Open Data Registry
    dokumentaciji, ali NIJE empirijski testirana -- van scope-a MVP-a
    (test lokacije su sve na Balkanu, N/E hemisfera).
    """
    lat_sw = math.floor(latitude)
    lon_sw = math.floor(longitude)
    ns = "N" if lat_sw >= 0 else "S"
    ew = "E" if lon_sw >= 0 else "W"
    return f"Copernicus_DSM_COG_10_{ns}{abs(lat_sw):02d}_00_{ew}{abs(lon_sw):03d}_00_DEM"


def _download_tile(url: str, dest_path: Path, timeout_s: float) -> None:
    """Preuzima tile na `dest_path`, preko privremenog `.part` fajla koji se
    tek na kraju atomski preimenuje -- ako preuzimanje pukne na pola (mreža,
    disk puni), keš direktorijum nikad ne sadrži polovičan/oštećen fajl koji
    bi kasniji pozivi tiho pokušali da čitaju."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")

    try:
        with httpx.Client(timeout=timeout_s) as client, client.stream("GET", url, follow_redirects=True) as response:
            if response.status_code == 404:
                raise ElevationError(
                    f"DEM tile nije dostupan (404): {url} -- oblast vjerovatno nije "
                    "pokrivena Copernicus GLO-30 Public bucket-om."
                )
            response.raise_for_status()
            with open(tmp_path, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
    except httpx.HTTPError as exc:
        tmp_path.unlink(missing_ok=True)
        raise ElevationError(f"Preuzimanje DEM tile-a nije uspjelo ({url}): {exc}") from exc

    tmp_path.rename(dest_path)


class ElevationService:
    """Čita terensku elevaciju iz Copernicus DEM GLO-30, uz lokalni disk keš
    po tile-u (vidi modul docstring za obrazloženje pristupa)."""

    def __init__(self, settings: Settings) -> None:
        self._cache_dir = Path(settings.dem_cache_dir)
        self._bucket = settings.copernicus_dem_bucket
        self._download_timeout_s = settings.dem_download_timeout_s

    def _tile_url(self, tile_name: str) -> str:
        return f"https://{self._bucket}.s3.amazonaws.com/{tile_name}/{tile_name}.tif"

    def _cache_path(self, tile_name: str) -> Path:
        return self._cache_dir / f"{tile_name}.tif"

    def _ensure_tile_downloaded(self, tile_name: str) -> Path:
        """Preuzima tile ako nije već keširan (vidi modul docstring za
        obrazloženje download-cache pristupa); ne radi ništa ako fajl već
        postoji na disku."""
        cache_path = self._cache_path(tile_name)
        if not cache_path.exists():
            _download_tile(self._tile_url(tile_name), cache_path, self._download_timeout_s)
        return cache_path

    def get_elevation(self, latitude: float, longitude: float) -> float | None:
        """Vraća terensku elevaciju u metrima na (latitude, longitude), ili
        `None` ako tile nije dostupan/pokriven, preuzimanje ne uspije, ili
        tačka pada na "nodata" piksel unutar tile-a.

        Namjerno ne pravi razliku (kroz povratnu vrijednost) između "van
        pokrivenosti" i "privremeni mrežni problem" -- pozivalac (Phase 7
        location quality logika) u oba slučaja treba isto: tretirati kao
        "DEM nedostupan" i nastaviti dalje (brief, tačka 42).

        Za VIŠE tačaka odjednom (npr. Phase 8 line-of-sight profil), koristi
        `get_elevation_profile()` -- ova metoda otvara `rasterio` fajl po
        pozivu, što je u redu za pojedinačne upite (dev endpoint), ali
        rasipnički za stotine/hiljade tačaka duž jedne linije."""
        tile_name = _tile_name(latitude, longitude)

        try:
            cache_path = self._ensure_tile_downloaded(tile_name)
            with rasterio.open(cache_path) as dataset:
                sample = next(dataset.sample([(longitude, latitude)]))
                elevation_m = float(sample[0])
                if dataset.nodata is not None and elevation_m == dataset.nodata:
                    logger.warning(
                        "DEM nodata piksel na (%s, %s) u tile-u %s", latitude, longitude, tile_name
                    )
                    return None
                return elevation_m
        except (ElevationError, rasterio.errors.RasterioIOError, OSError) as exc:
            logger.warning("DEM elevacija nedostupna za (%s, %s): %s", latitude, longitude, exc)
            return None

    def get_elevation_profile(self, points: list[tuple[float, float]]) -> list[float | None]:
        """Batch verzija `get_elevation()` -- grupiše tačke po DEM tile-u i
        svaki tile fajl otvara SAMO JEDNOM (umjesto po tačku), pa sve
        njegove tačke čita u jednom `rasterio.sample()` pozivu. Bitno za
        Phase 8 line-of-sight, gdje jedan zahtjev sampluje na stotine do
        hiljade tačaka duž geodesic linije -- otvaranje fajla po tački bi
        bilo besmisleno sporo (vidi Phase 8 status u
        architecture-feasibility-review.md).

        `points` je lista `(latitude, longitude)` -- isti redoslijed
        argumenata kao `get_elevation()`. Povratna vrijednost prati
        redoslijed ulaza tačku-po-tačku (uključujući `None` za svaku tačku
        čiji tile/nodata/preuzimanje ne uspije -- ista graceful-degradation
        logika kao `get_elevation()`, samo na nivou pojedinačne tačke, ne
        cijelog poziva)."""
        results: list[float | None] = [None] * len(points)

        points_by_tile: dict[str, list[int]] = {}
        for idx, (latitude, longitude) in enumerate(points):
            tile_name = _tile_name(latitude, longitude)
            points_by_tile.setdefault(tile_name, []).append(idx)

        for tile_name, indices in points_by_tile.items():
            try:
                cache_path = self._ensure_tile_downloaded(tile_name)
                with rasterio.open(cache_path) as dataset:
                    nodata = dataset.nodata
                    coords = [(points[i][1], points[i][0]) for i in indices]  # (lon, lat) za rasterio
                    for idx, sample in zip(indices, dataset.sample(coords)):
                        value = float(sample[0])
                        results[idx] = None if (nodata is not None and value == nodata) else value
            except (ElevationError, rasterio.errors.RasterioIOError, OSError) as exc:
                logger.warning("DEM profil nedostupan za tile %s (%d tačaka): %s", tile_name, len(indices), exc)
                # results[idx] ostaju None za sve tačke ovog tile-a (već inicijalizovano)

        return results
