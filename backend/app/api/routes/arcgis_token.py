"""
Endpoint koji frontend poziva na startup da dobije kratkotrajan ArcGIS
access token — vidi app/services/arcgis_auth.py za obrazloženje zašto
ovo postoji umjesto običnog statičnog API key-a u frontend kodu.
"""

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.services.arcgis_auth import ArcGISAuthError, ArcGISAuthService

router = APIRouter(tags=["arcgis-auth"])

# Jedan servis-instance po procesu — cache token-a živi ovdje. Dijeli se
# sa `app.services.arcgis_places.ArcGISPlacesService` (vidi
# `get_arcgis_auth_service` ispod) -- isti token, jedan cache, umjesto da
# svaki potrošač radi sopstvenu OAuth razmjenu.
_arcgis_auth_service = ArcGISAuthService(get_settings())


def get_arcgis_auth_service() -> ArcGISAuthService:
    """Javni accessor za dijeljenu `ArcGISAuthService` instancu -- vidi
    komentar iznad `_arcgis_auth_service`."""
    return _arcgis_auth_service


@router.get("/arcgis-token")
async def get_arcgis_token() -> dict[str, str]:
    try:
        access_token = await _arcgis_auth_service.get_access_token()
    except ArcGISAuthError as exc:
        # 503, ne 500: ovo je nedostupnost eksterne zavisnosti (ili
        # nedostajuća konfiguracija), ne bug u našem kodu.
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"access_token": access_token}
