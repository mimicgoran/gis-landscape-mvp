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

/**
 * `?backend=<url>` query parametar override -- namjerno dodano za
 * privremeno HTTPS tunnel testiranje na pravom telefonu (cloudflared quick
 * tunnel, vidi docs/architecture-feasibility-review.md sekcija 32) PRIJE
 * Phase 15 stvarnog deploymenta. Kad se frontend otvori preko tunnel URL-a
 * (npr. https://xxxx.trycloudflare.com), `window.location.hostname` NIJE
 * "localhost", pa bi inače pao na placeholder Render URL ispod -- override
 * rješava to bez potrebe da se ovaj fajl ručno mijenja za svaki test.
 * Nema perzistencije (namjerno) -- vrijedi samo za tu jednu posjetu/URL.
 */
function resolveBackendBaseUrl() {
  const override = new URLSearchParams(window.location.search).get("backend");
  if (override) {
    return override;
  }
  if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
    return "http://localhost:8000";
  }
  return "https://REPLACE-ME.onrender.com"; // popuniti u Phase 15 (deployment)
}

export const BACKEND_BASE_URL = resolveBackendBaseUrl();

// --- Viewing sector granice (Phase 3) ---
// MORA biti usklađeno sa backend/app/core/config.py
// (fov_min_deg/fov_max_deg/fov_default_deg, radius_min_km/radius_max_km/
// radius_default_km) — obrazloženje pragova je tamo (i u
// docs/architecture-feasibility-review.md, sekcija 8). Nema build koraka
// koji bi ovo automatski sinhronizovao u ovom MVP-u (namjeran kompromis za
// mali vanilla JS projekat bez shared paketa) — ako se pragovi mijenjaju,
// mijenjaju se na oba mjesta.
export const FOV_MIN_DEG = 20;
export const FOV_MAX_DEG = 90;
// Default 30 (ne 50) -- korisnička odluka nakon prvog pravog telefon testa
// (mora biti usklađeno sa backend/app/core/config.py fov_default_deg).
export const FOV_DEFAULT_DEG = 30;

// Donja granica 1 (ne 5) -- korisnička odluka nakon drugog pravog telefon
// testa, usklađeno sa backend radius_min_km. Omogućava analizu i vrlo
// bliskog sektora (npr. objekti u naselju), ne samo planinarskog opsega.
export const RADIUS_MIN_KM = 1;
export const RADIUS_MAX_KM = 30;
// Default 5 (ne 20) -- ista odluka, usklađeno sa radius_default_km.
export const RADIUS_DEFAULT_KM = 5;

// Heading nema "prirodan" default (zavisi isključivo od toga gdje korisnik
// gleda) — 0 (sjever) je proizvoljna ali razumna početna vrijednost dok se
// slajder ne pomjeri.
export const DEFAULT_HEADING_DEG = 0;
