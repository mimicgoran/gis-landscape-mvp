"""
ArcGIS OAuth 2.0 "App authentication" (client_credentials grant) servis.

Zašto ovo postoji: korisnikova ArcGIS Online organizacija ima isključeno
izdavanje plain "API key" credentials (admin security policy) — jedina
dostupna opcija su OAuth 2.0 credentials. Za app-only pristup (bez
prijave korisnika) to je "App authentication" tip: backend razmjenjuje
`client_id` + `client_secret` za kratkotrajan access token preko ArcGIS
sharing REST API-ja, isto kao standardni OAuth2 client_credentials flow.

`client_secret` je tajna istog ranga kao OpenAI API key — mora ostati na
backendu. Frontend nikad ne vidi client_id/client_secret, samo dobija
gotov, već-razmijenjen access token preko `/api/v1/arcgis-token`.

Token se cache-uje u memoriji procesa (jednostavno, dovoljno za MVP
saobraćaj) i osvježava malo prije isteka da se izbjegne race condition
gdje frontend dobije token koji ističe koji sekund kasnije.
"""

from __future__ import annotations

import time

import httpx

from app.core.config import Settings


class ArcGISAuthError(RuntimeError):
    """Podignuto kad ArcGIS token endpoint ne vrati validan access token."""


class _CachedToken:
    __slots__ = ("access_token", "expires_at_epoch_s")

    def __init__(self, access_token: str, expires_at_epoch_s: float) -> None:
        self.access_token = access_token
        self.expires_at_epoch_s = expires_at_epoch_s

    def is_valid(self, refresh_margin_s: int) -> bool:
        return time.monotonic() < (self.expires_at_epoch_s - refresh_margin_s)


class ArcGISAuthService:
    """Drži jedan cache-ovan token po procesu. Nije thread-safe po dizajnu —
    FastAPI/uvicorn worker sa async event loop-om ovo ne treba (nema pravog
    paralelizma unutar jednog worker-a); za MVP saobraćaj je ovo dovoljno.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cached_token: _CachedToken | None = None

    async def get_access_token(self) -> str:
        if self._cached_token and self._cached_token.is_valid(self._settings.arcgis_token_refresh_margin_s):
            return self._cached_token.access_token

        if not self._settings.arcgis_client_id or not self._settings.arcgis_client_secret:
            raise ArcGISAuthError(
                "ARCGIS_CLIENT_ID / ARCGIS_CLIENT_SECRET nisu podešeni u .env. "
                "Vidi backend/.env.example i docs/architecture-feasibility-review.md, sekcija 4."
            )

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                self._settings.arcgis_oauth_token_url,
                data={
                    "client_id": self._settings.arcgis_client_id,
                    "client_secret": self._settings.arcgis_client_secret,
                    "grant_type": "client_credentials",
                },
            )

        if response.status_code != 200:
            raise ArcGISAuthError(
                f"ArcGIS OAuth token endpoint vratio {response.status_code}: {response.text[:300]}"
            )

        payload = response.json()
        access_token = payload.get("access_token")
        expires_in_s = payload.get("expires_in")

        if not access_token or not isinstance(expires_in_s, int):
            raise ArcGISAuthError(f"Neočekivan odgovor ArcGIS token endpointa: {payload}")

        self._cached_token = _CachedToken(
            access_token=access_token,
            expires_at_epoch_s=time.monotonic() + expires_in_s,
        )
        return access_token
