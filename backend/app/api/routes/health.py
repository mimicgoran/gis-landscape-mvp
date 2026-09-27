"""Health-check endpoint.

Koristi se za:
1. Osnovnu provjeru da je backend živ (deployment/monitoring).
2. "Buđenje" Render free-tier servisa prije demo snimanja (servis spava
   nakon ~15 min neaktivnosti — vidi architecture review, sekcija 17).
"""

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "app_name": settings.app_name,
        "version": settings.app_version,
    }
