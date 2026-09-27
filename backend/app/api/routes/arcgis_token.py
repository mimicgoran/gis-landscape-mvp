"""
Endpoint koji frontend poziva na startup da dobije kratkotrajan ArcGIS
access token — vidi app/services/arcgis_auth.py za obrazloženje zašto
ovo postoji umjesto običnog statičnog API key-a u frontend kodu.
"""

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.services.arcgis_auth import ArcGISAuthError, ArcGISAuthService

router = APIRouter(tags=["arcgis-auth"])

# Jedan servis-instance po procesu — cache token-a živi ovdje.
_arcgis_auth_service = ArcGISAuthService(get_settings())


@router.get("/arcgis-token")
async def get_arcgis_token() -> dict[str, str]:
    try:
        access_token = await _arcgis_auth_service.get_access_token()
    except ArcGISAuthError as exc:
        # 503, ne 500: ovo je nedostupnost eksterne zavisnosti (ili
        # nedostajuća konfiguracija), ne bug u našem kodu.
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"access_token": access_token}
