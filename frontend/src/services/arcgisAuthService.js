/**
 * Dohvata kratkotrajan ArcGIS access token sa backenda.
 *
 * Zašto ovo postoji: korisnikova ArcGIS Online organizacija ne dozvoljava
 * izdavanje plain API key credentials, pa se koristi OAuth 2.0 "App
 * authentication" — backend čuva client_id/client_secret i radi razmjenu
 * za access token; frontend samo pita backend za već-razmijenjen token.
 * Vidi backend/app/services/arcgis_auth.py za detalje.
 */

import { BACKEND_BASE_URL } from "../config.js";

/**
 * @returns {Promise<string>} važeći ArcGIS access token
 * @throws {Error} ako backend nije dostupan ili ArcGIS credentials nisu podešeni
 */
export async function fetchArcGISAccessToken() {
  const response = await fetch(`${BACKEND_BASE_URL}/api/v1/arcgis-token`);

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      `Backend nije mogao vratiti ArcGIS token (${response.status}): ${body.detail ?? "nepoznata greška"}`
    );
  }

  const { access_token: accessToken } = await response.json();
  return accessToken;
}
