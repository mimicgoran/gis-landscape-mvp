/**
 * Frontend konfiguracija.
 *
 * NAPOMENA o ArcGIS autentifikaciji: korisnikova ArcGIS Online organizacija
 * ima isključeno izdavanje plain "API key" credentials (admin security
 * policy) — dostupne su samo OAuth 2.0 credentials. Zbog toga NEMA
 * statičnog ARCGIS_API_KEY ovdje. Frontend umjesto toga dohvata
 * kratkotrajan access token sa backenda (vidi src/services/arcgisAuthService.js
 * i backend/app/services/arcgis_auth.py) — client_id/client_secret ostaju
 * na backendu, isti nivo tajnosti kao OpenAI key.
 */

// Ako se u AGOL-u napravi poseban Web Map item (vidi review, sekcija 4),
// njegov item ID ide ovdje. Dok je prazan, koristimo Map sastavljen ručno
// sa standardnim basemap stilom (dovoljno za Phase 1 sanity-check).
export const ARCGIS_WEB_MAP_ITEM_ID = "";

// Centar Srbije (okvirno) — MVP scope je geografski ograničen na Srbiju
// (vidi review, sekcija 0/15). Koristi se kao početni extent mape.
export const DEFAULT_MAP_CENTER = [20.9, 44.0]; // [longitude, latitude]
export const DEFAULT_MAP_ZOOM = 7;

export const BACKEND_BASE_URL =
  window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : "https://REPLACE-ME.onrender.com"; // popuniti u Phase 15 (deployment)
